"""译文覆盖层窗口 —— 全屏透明窗口，在原文位置绘制中文译文。

每行独立绘制：背景块遮盖原文 → 中文译文绘制其上。
窗口鼠标穿透（WindowTransparentForInput），ESC 由全局钩子处理。
"""

from __future__ import annotations

import logging
from typing import List, Optional

from PyQt5.QtCore import (
    QRect,
    Qt,
)
from PyQt5.QtGui import (
    QColor,
    QFont,
    QFontMetrics,
    QPainter,
    QPen,
    QTextOption,
)
from PyQt5.QtWidgets import QWidget

from .qwen_client import VisionLine
from .screen import ScreenMapper

logger = logging.getLogger(__name__)


class ResultOverlay(QWidget):
    """译文覆盖层窗口 —— 全屏透明，鼠标穿透。

    Args:
        mapper: 屏幕坐标换算器
    """

    def __init__(self, mapper: ScreenMapper) -> None:
        super().__init__()
        self._mapper = mapper
        self._items: List[VisionLine] = []
        self._bg_color = QColor("#FFFFFF")
        self._text_color = QColor("#000000")
        self._padding = 4
        self._min_font_size = 9
        self._init_ui()

    def _init_ui(self) -> None:
        """配置窗口属性。"""
        self.setWindowFlags(
            Qt.FramelessWindowHint
            | Qt.WindowStaysOnTopHint
            | Qt.WindowTransparentForInput
            | Qt.WindowDoesNotAcceptFocus
            | Qt.Tool
        )
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        # 覆盖主屏逻辑区域
        geo = self._mapper.screen_geometry
        self.setGeometry(geo)

    def configure_style(
        self,
        bg_color: str = "#FFFFFF",
        text_color: str = "#000000",
        padding: int = 4,
        min_font_size: int = 9,
    ) -> None:
        """更新覆盖层样式。

        Args:
            bg_color: 背景块底色（CSS 颜色名或 #RRGGBB）
            text_color: 译文文字颜色
            padding: 背景块内边距 px
            min_font_size: 最小字号 pt
        """
        self._bg_color = QColor(bg_color)
        self._text_color = QColor(text_color)
        self._padding = padding
        self._min_font_size = min_font_size

    def show_translations(self, items: List[VisionLine]) -> None:
        """显示译文：先清除旧内容，设置新数据，一次性 show。

        Args:
            items: VisionLine 列表（bbox 为屏幕绝对物理坐标）
        """
        self._items = items
        self.hide()
        self.update()
        self.show()
        self.raise_()
        logger.info("覆盖层已显示: %d 行", len(items))

    def clear(self) -> None:
        """清除并隐藏覆盖层。"""
        self._items.clear()
        self.hide()
        logger.info("覆盖层已隐藏")

    # ── 绘制 ──────────────────────────────────────────────

    def paintEvent(self, event) -> None:
        """绘制所有行的背景块与译文。"""
        if not self._items:
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.TextAntialiasing)

        for item in self._items:
            self._draw_item(painter, item)

        painter.end()

    def _draw_item(self, painter: QPainter, item: VisionLine) -> None:
        """绘制单行：背景块 + 译文。

        Args:
            painter: QPainter 实例
            item: 单行翻译结果
        """
        bbox = item.bbox
        if len(bbox) != 4:
            return

        # 将物理坐标转为逻辑坐标
        # bbox 格式: [[x1,y1], [x2,y2], [x3,y3], [x4,y4]]
        # 左上、右上、右下、左下
        x_coords = [pt[0] for pt in bbox]
        y_coords = [pt[1] for pt in bbox]
        phys_rect = QRect(
            min(x_coords),
            min(y_coords),
            max(x_coords) - min(x_coords),
            max(y_coords) - min(y_coords),
        )
        log_rect = self._mapper.physical_to_logical(phys_rect)

        if log_rect.width() <= 0 or log_rect.height() <= 0:
            return

        # 背景块（padding 扩展）
        bg_rect = log_rect.adjusted(
            -self._padding, -self._padding,
            self._padding, self._padding,
        )
        painter.fillRect(bg_rect, self._bg_color)

        # 边框（可选，调试用）
        # painter.setPen(QPen(self._bg_color.darker(120), 1))
        # painter.drawRect(bg_rect)

        # 文字区域
        text_rect = bg_rect.adjusted(1, 1, -1, -1)
        if text_rect.width() <= 0 or text_rect.height() <= 0:
            return

        # 自适应字号
        font = self._fit_font(
            painter, item.translation,
            text_rect.width(), text_rect.height(),
        )
        painter.setFont(font)
        painter.setPen(self._text_color)

        # 垂直居中绘制
        painter.drawText(
            text_rect,
            Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap,
            item.translation,
        )

    def _fit_font(
        self, painter: QPainter, text: str, max_w: int, max_h: int
    ) -> QFont:
        """自适应字号：从较大字号递减，直到文本能放入 max_w × max_h。

        Args:
            painter: 当前 QPainter（用于 QFontMetrics 测量）
            text: 译文文本
            max_w: 最大宽度 px
            max_h: 最大高度 px

        Returns:
            适配后的 QFont。
        """
        font = painter.font()
        font_size = 16  # 起始字号

        while font_size >= self._min_font_size:
            font.setPixelSize(font_size)
            fm = QFontMetrics(font)

            # 测量文本包围矩形
            bounding = fm.boundingRect(
                0, 0, max_w, 0,
                Qt.TextWordWrap | Qt.AlignHCenter,
                text,
            )

            if bounding.height() <= max_h and bounding.width() <= max_w:
                return font

            font_size -= 1

        # 仍放不下：用最小字号 + 截断省略号
        font.setPixelSize(self._min_font_size)
        return font
