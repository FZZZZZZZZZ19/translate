"""选区遮罩窗口 —— 全屏半透明遮罩 + 鼠标拖拽矩形选区。

用户拖拽时，以按下点为左上角、松开点为右下角（内部 normalized），
选区内不暗、白色边框 + 实时尺寸显示；ESC 或右键取消。
"""

from __future__ import annotations

import logging
from typing import Optional

from PyQt5.QtCore import (
    QPoint,
    QRect,
    Qt,
    pyqtSignal,
)
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFont,
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt5.QtWidgets import QWidget

from .screen import ScreenMapper

logger = logging.getLogger(__name__)

# 单击判定阈值：press 和 release 距离 < 此值视为单击（无效选区）
CLICK_THRESHOLD = 3


class SelectionOverlay(QWidget):
    """全屏选区遮罩窗口。

    信号：
        selection_done(QRect): 选区完成，携带 normalized 逻辑坐标选区。
        cancelled(): 用户取消（ESC 或右键）。
    """

    selection_done = pyqtSignal(QRect)
    cancelled = pyqtSignal()

    def __init__(self, mapper: ScreenMapper, screenshot: QPixmap) -> None:
        """初始化遮罩窗口。

        Args:
            mapper: 屏幕坐标换算器
            screenshot: 全屏截图底图（物理像素 QPixmap）
        """
        super().__init__()
        self._mapper = mapper
        self._screenshot = screenshot

        # 拖拽状态
        self._start_point: Optional[QPoint] = None
        self._current_point: Optional[QPoint] = None
        self._selecting = False

        # 已完成选区（最后一次 valid 选区，用于绘制）
        self._last_rect: Optional[QRect] = None

        self._init_ui()

    def _init_ui(self) -> None:
        """配置窗口属性。"""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.Tool  # 不在任务栏显示
        )
        # 覆盖主屏逻辑区域
        geo = self._mapper.screen_geometry
        self.setGeometry(geo)
        self.setCursor(Qt.CrossCursor)
        # 启用鼠标追踪以实时更新
        self.setMouseTracking(True)

    def start(self) -> None:
        """显示全屏遮罩，重置拖拽状态。"""
        self._start_point = None
        self._current_point = None
        self._selecting = False
        self._last_rect = None
        self.showFullScreen()
        self.raise_()
        self.activateWindow()
        logger.info("选区遮罩已显示")

    # ── 鼠标事件 ──────────────────────────────────────────

    def mousePressEvent(self, event: QMouseEvent) -> None:
        """左键按下：记录起点（选区左上角）。"""
        if event.button() == Qt.LeftButton:
            self._start_point = event.pos()
            self._current_point = event.pos()
            self._selecting = True
            self._last_rect = None
            self.update()
        elif event.button() == Qt.RightButton:
            logger.info("右键取消选区")
            self.cancelled.emit()

    def mouseMoveEvent(self, event: QMouseEvent) -> None:
        """拖拽中：更新当前点并重绘。"""
        if self._selecting:
            self._current_point = event.pos()
            self.update()

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:
        """左键松开：判定选区有效性。"""
        if not self._selecting or self._start_point is None:
            return

        self._selecting = False
        end_point = event.pos()

        # 单击判定
        dx = abs(end_point.x() - self._start_point.x())
        dy = abs(end_point.y() - self._start_point.y())
        if dx < CLICK_THRESHOLD and dy < CLICK_THRESHOLD:
            logger.info("单击无效选区（< %dpx），保持遮罩", CLICK_THRESHOLD)
            self._start_point = None
            self._current_point = None
            self.update()
            return

        rect = QRect(self._start_point, end_point).normalized()
        self._last_rect = rect

        # 选区过小（宽或高 < 10px）警告但不阻止
        if rect.width() < 10 or rect.height() < 10:
            logger.warning("选区过小: %s", rect)

        logger.info("选区完成: %s", rect)
        self.selection_done.emit(rect)

    # ── 键盘事件 ──────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """ESC 键取消选区。"""
        if event.key() == Qt.Key_Escape:
            logger.info("ESC 取消选区")
            self.cancelled.emit()
        else:
            super().keyPressEvent(event)

    # ── 绘制 ──────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        """绘制遮罩层：
        1. 先画截图底图
        2. 盖上半透明黑（rgba(0,0,0,120)）
        3. 选区内挖空（不暗）+ 白色 2px 边框 + 尺寸提示
        4. 顶部提示文字
        """
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 1. 底图（缩放到窗口逻辑尺寸）
        if not self._screenshot.isNull():
            scaled = self._screenshot.scaled(
                self.width(), self.height(),
                Qt.KeepAspectRatio, Qt.SmoothTransformation,
            )
            painter.drawPixmap(0, 0, scaled)

        # 2. 半透明黑遮罩
        overlay_color = QColor(0, 0, 0, 120)
        painter.fillRect(self.rect(), overlay_color)

        # 确定当前选区矩形
        current_rect: Optional[QRect] = None
        if self._selecting and self._start_point and self._current_point:
            current_rect = QRect(self._start_point, self._current_point).normalized()
        elif self._last_rect:
            current_rect = self._last_rect

        # 3. 选区内挖空 + 白色边框 + 尺寸
        if current_rect and current_rect.isValid():
            # 挖空（恢复底图）
            if not self._screenshot.isNull():
                src_rect = QRect(
                    current_rect.x(), current_rect.y(),
                    current_rect.width(), current_rect.height(),
                )
                painter.drawPixmap(current_rect, self._screenshot, src_rect)
            else:
                # 无底图时仅用较浅的遮罩填充
                painter.fillRect(current_rect, QColor(0, 0, 0, 30))

            # 白色 2px 边框
            pen = QPen(QColor(255, 255, 255), 2)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawRect(current_rect)

            # 尺寸提示（右上角或跟随）
            size_text = f"{current_rect.width()} × {current_rect.height()}"
            font = QFont("Microsoft YaHei", 10)
            painter.setFont(font)
            painter.setPen(QColor(255, 255, 255))

            text_x = current_rect.right() + 6
            text_y = current_rect.top() + 16
            # 若太靠右则放到选区内部右上角
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(size_text)
            if text_x + text_w > self.width() - 10:
                text_x = current_rect.right() - text_w - 4
                text_y = current_rect.top() + fm.height() + 2
                # 确保不超出选区
                if text_y > current_rect.bottom() - 2:
                    text_y = current_rect.bottom() - 2

            painter.drawText(text_x, text_y, size_text)

        # 4. 顶部提示
        hint_font = QFont("Microsoft YaHei", 11)
        painter.setFont(hint_font)
        painter.setPen(QColor(255, 255, 255, 200))
        painter.drawText(
            12, 28,
            "拖拽选择区域 · ESC 取消",
        )

        painter.end()
