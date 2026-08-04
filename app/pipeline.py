"""流程编排 —— 状态机 + QThread 工作线程。

状态机：IDLE → SELECTING → RECOGNIZING → OVERLAYING → IDLE
任一阶段失败回 IDLE 并托盘提示。

v1.1：RECOGNIZING 阶段由 qwen_client 一次调用完成识别+翻译+坐标。
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import List, Optional

from PyQt5.QtCore import QObject, QRect, QThread, pyqtSignal, pyqtSlot
from PyQt5.QtGui import QImage

from .config import AppConfig, ConfigManager
from .qwen_client import QwenClient, QwenError, VisionLine
from .screen import ScreenMapper

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """流程状态枚举。"""
    IDLE = auto()
    SELECTING = auto()
    RECOGNIZING = auto()
    OVERLAYING = auto()


# ── 工作线程 ──────────────────────────────────────────────


class RecognizeWorker(QThread):
    """后台线程：执行千问视觉识别+翻译。

    信号：
        progress(str): 进度消息
        done(list[VisionLine]): 识别翻译完成
        failed(str): 失败，携带中文错误信息
    """

    progress = pyqtSignal(str)
    done = pyqtSignal(list)
    failed = pyqtSignal(str)

    def __init__(
        self,
        client: QwenClient,
        image: QImage,
        offset_x: int,
        offset_y: int,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._client = client
        self._image = image
        self._offset_x = offset_x
        self._offset_y = offset_y

    def run(self) -> None:
        """在工作线程中执行 API 调用。"""
        try:
            self.progress.emit("AI 识别翻译中…")
            lines = self._client.recognize_and_translate(
                self._image, self._offset_x, self._offset_y
            )
            self.done.emit(lines)
        except QwenError as e:
            self.failed.emit(e.message)
        except ValueError as e:
            self.failed.emit(f"图片处理错误: {e}")
        except Exception as e:
            logger.exception("识别翻译未预期异常")
            self.failed.emit(f"未知错误: {e}")


# ── 应用控制器 ────────────────────────────────────────────


class AppController(QObject):
    """应用主控制器：持有状态机，编排热键→选区→识别→覆盖全流程。

    信号：
        status_message(str): 状态消息（供托盘/UI 显示）
        flow_started(): 新流程开始（供外部清理旧覆盖层等）
        flow_finished(): 流程结束回到 IDLE
        translations_ready(list[VisionLine]): 译文数据就绪
    """

    status_message = pyqtSignal(str)
    flow_started = pyqtSignal()
    flow_finished = pyqtSignal()
    translations_ready = pyqtSignal(list)

    def __init__(self, cfg: ConfigManager, mapper: ScreenMapper) -> None:
        """初始化控制器。

        Args:
            cfg: 配置管理器
            mapper: 屏幕坐标换算器
        """
        super().__init__()
        self._cfg = cfg
        self._mapper = mapper
        self._state = PipelineState.IDLE
        self._worker: Optional[RecognizeWorker] = None

    # ── 状态查询 ──────────────────────────────────────────

    @property
    def state(self) -> PipelineState:
        """当前流程状态。"""
        return self._state

    def is_idle(self) -> bool:
        """是否处于空闲状态（可接受新的热键触发）。"""
        return self._state == PipelineState.IDLE

    # ── 热键触发入口 ──────────────────────────────────────

    @pyqtSlot()
    def start_screen_flow(self) -> None:
        """热键/托盘「截图翻译」触发入口。

        防重入：仅 IDLE 态响应；否则托盘提示「正在处理中」。
        """
        if not self.is_idle():
            logger.info("当前状态 %s，忽略热键触发（防重入）", self._state)
            self.status_message.emit("正在处理中，请完成当前操作后再试")
            return

        logger.info("流程启动: IDLE → SELECTING")
        self._state = PipelineState.SELECTING
        self.status_message.emit("请拖拽选择翻译区域")
        self.flow_started.emit()

    # ── 选区完成 ──────────────────────────────────────────

    @pyqtSlot(QRect)
    def on_selection_done(self, rect: QRect) -> None:
        """选区完成回调：裁剪图片 → 启动识别翻译工作线程。

        Args:
            rect: 用户选区（逻辑坐标，normalized）
        """
        if self._state != PipelineState.SELECTING:
            logger.warning("非 SELECTING 状态收到选区完成信号，忽略")
            return

        # 获取当前配置
        config = self._cfg.load()

        # 裁剪选区图
        from .screen import grab_fullscreen

        screenshot = grab_fullscreen()
        try:
            cropped = self._mapper.crop_qimage(screenshot, rect)
        except ValueError as e:
            logger.error("裁剪失败: %s", e)
            self._on_failed(f"选区无效: {e}")
            return

        # 选区左上角物理坐标
        phys_rect = self._mapper.logical_to_physical(
            rect.x(), rect.y(), rect.width(), rect.height()
        )
        offset_x = phys_rect.x()
        offset_y = phys_rect.y()

        logger.info("选区完成: SELECTING → RECOGNIZING")
        self._state = PipelineState.RECOGNIZING
        self.status_message.emit("AI 识别翻译中…")

        # 创建千问客户端 + 工作线程
        client = QwenClient(config)
        self._worker = RecognizeWorker(
            client, cropped, offset_x, offset_y
        )
        self._worker.progress.connect(self.status_message.emit)
        self._worker.done.connect(self._on_recognize_done)
        self._worker.failed.connect(self._on_failed)
        self._worker.finished.connect(self._worker_cleanup)
        self._worker.start()

    # ── 选区取消 ──────────────────────────────────────────

    @pyqtSlot()
    def on_selection_cancelled(self) -> None:
        """选区取消回调：回到 IDLE。"""
        logger.info("选区取消，回 IDLE")
        self._state = PipelineState.IDLE
        self.status_message.emit("就绪")
        self.flow_finished.emit()

    # ── ESC 处理 ──────────────────────────────────────────

    def on_esc_in_overlay(self) -> None:
        """ESC 按下：若在 OVERLAYING 状态则隐藏覆盖层回 IDLE。"""
        if self._state == PipelineState.OVERLAYING:
            logger.info("ESC 退出覆盖层 → IDLE")
            self._state = PipelineState.IDLE
            self.status_message.emit("就绪")
            self.flow_finished.emit()

    # ── 内部：识别翻译完成/失败 ────────────────────────────

    @pyqtSlot(list)
    def _on_recognize_done(self, items: List[VisionLine]) -> None:
        """识别翻译完成回调。

        Args:
            items: VisionLine 列表
        """
        logger.info("识别翻译完成: %d 行", len(items))
        self._state = PipelineState.OVERLAYING
        self.status_message.emit(f"翻译完成 ({len(items)} 行)，按 ESC 退出")
        self.translations_ready.emit(items)

    @pyqtSlot(str)
    def _on_failed(self, error_msg: str) -> None:
        """识别翻译失败回调。

        Args:
            error_msg: 中文错误信息
        """
        logger.error("流程失败: %s", error_msg)
        self._state = PipelineState.IDLE
        self.status_message.emit(error_msg)
        self.flow_finished.emit()

    @pyqtSlot()
    def _worker_cleanup(self) -> None:
        """worker 线程结束后清理引用。"""
        if self._worker:
            self._worker.deleteLater()
            self._worker = None

    # ── 程序退出 ──────────────────────────────────────────

    def shutdown(self) -> None:
        """程序退出时等待 worker 结束。"""
        if self._worker and self._worker.isRunning():
            logger.info("等待 worker 线程结束…")
            self._worker.requestInterruption()
            self._worker.wait(3000)
