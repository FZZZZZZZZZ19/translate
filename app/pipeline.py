"""流程编排 —— 状态机 + 工作线程。

状态机：IDLE → SELECTING → RECOGNIZING → OVERLAYING → IDLE
任一阶段失败回 IDLE 并托盘提示。

v1.1：RECOGNIZING 阶段由 qwen_client 一次调用完成识别+翻译+坐标。
批次 A 阶段仅实现到选区完成+验证 PNG 输出。
"""

from __future__ import annotations

import logging
from enum import Enum, auto
from typing import Optional

from PyQt5.QtCore import QObject, QRect, QThread, pyqtSignal, pyqtSlot

from .config import ConfigManager
from .screen import ScreenMapper

logger = logging.getLogger(__name__)


class PipelineState(Enum):
    """流程状态枚举。"""
    IDLE = auto()
    SELECTING = auto()
    RECOGNIZING = auto()
    OVERLAYING = auto()


class AppController(QObject):
    """应用主控制器：持有状态机，编排热键→选区→识别→覆盖全流程。

    信号：
        status_message(str): 状态消息（供托盘/UI 显示）
        flow_started(): 新流程开始（供外部清理旧覆盖层等）
        flow_finished(): 流程结束回到 IDLE
    """

    status_message = pyqtSignal(str)
    flow_started = pyqtSignal()
    flow_finished = pyqtSignal()

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

    # ── 事件回调（由 main.py 连接） ────────────────────────

    @pyqtSlot(QRect)
    def on_selection_done(self, rect: QRect) -> None:
        """选区完成回调：进入识别翻译阶段。

        Args:
            rect: 用户选区（逻辑坐标，normalized）
        """
        if self._state != PipelineState.SELECTING:
            logger.warning("非 SELECTING 状态收到选区完成信号，忽略")
            return

        logger.info("选区完成: SELECTING → RECOGNIZING")
        self._state = PipelineState.RECOGNIZING
        self.status_message.emit("AI 识别翻译中…")
        # 批次 B 实现：启 worker 调用 qwen_client
        # 批次 A 验证：暂不启 worker，直接回到 IDLE（选区由 main.py 保存 PNG）

    @pyqtSlot()
    def on_selection_cancelled(self) -> None:
        """选区取消回调：回到 IDLE。"""
        logger.info("选区取消，回 IDLE")
        self._state = PipelineState.IDLE
        self.status_message.emit("就绪")
        self.flow_finished.emit()

    def on_esc_in_overlay(self) -> None:
        """ESC 按下：若在 OVERLAYING 状态则隐藏覆盖层回 IDLE。"""
        if self._state == PipelineState.OVERLAYING:
            logger.info("ESC 退出覆盖层 → IDLE")
            self._state = PipelineState.IDLE
            self.status_message.emit("就绪")
            self.flow_finished.emit()

    # ── 内部：识别翻译完成/失败 ────────────────────────────

    def _on_recognize_done(self, items: list) -> None:
        """识别翻译完成回调（批次 B 实现）。

        Args:
            items: VisionLine 列表
        """
        logger.info("识别翻译完成: %d 行", len(items))
        self._state = PipelineState.OVERLAYING
        self.status_message.emit(f"翻译完成 ({len(items)} 行)，按 ESC 退出")

    def _on_recognize_failed(self, error_msg: str) -> None:
        """识别翻译失败回调。

        Args:
            error_msg: 中文错误信息
        """
        logger.error("识别翻译失败: %s", error_msg)
        self._state = PipelineState.IDLE
        self.status_message.emit(error_msg)
        self.flow_finished.emit()
