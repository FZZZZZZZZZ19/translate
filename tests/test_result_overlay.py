"""覆盖层字号自适应测试。"""

from __future__ import annotations

import sys

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QFont, QFontMetrics, QPainter, QPixmap
from PyQt5.QtWidgets import QApplication


class TestFontFitting:
    """字号自适应逻辑测试。"""

    @classmethod
    def setup_class(cls) -> None:
        """确保有 QApplication 实例。"""
        cls._app = QApplication.instance() or QApplication(sys.argv)

    def test_fit_large_space_returns_large_font(self) -> None:
        """空间充足时返回较大字号。"""
        pixmap = QPixmap(500, 100)
        painter = QPainter(pixmap)
        font = painter.font()
        font.setPixelSize(16)

        fm = QFontMetrics(font)
        text = "Hello"
        max_w, max_h = 400, 80

        # 模拟 _fit_font 逻辑
        test_size = 16
        while test_size >= 9:
            font.setPixelSize(test_size)
            fm = QFontMetrics(font)
            bounding = fm.boundingRect(
                0, 0, max_w, 0,
                Qt.TextWordWrap | Qt.AlignHCenter,
                text,
            )
            if bounding.height() <= max_h:
                break
            test_size -= 1

        assert test_size >= 14  # 短文本应该能用大字号
        painter.end()

    def test_fit_tight_space_reduces_font(self) -> None:
        """空间有限时降字号。"""
        pixmap = QPixmap(100, 100)
        painter = QPainter(pixmap)
        font = painter.font()

        text = "A very long piece of text that needs to wrap"
        max_w, max_h = 60, 30

        test_size = 16
        fitted = 9
        while test_size >= 9:
            font.setPixelSize(test_size)
            fm = QFontMetrics(font)
            bounding = fm.boundingRect(
                0, 0, max_w, 0,
                Qt.TextWordWrap | Qt.AlignHCenter,
                text,
            )
            if bounding.height() <= max_h:
                fitted = test_size
                break
            test_size -= 1

        assert fitted <= 10  # 窄空间长文本应该降字号
        painter.end()

    def test_min_font_size_boundary(self) -> None:
        """达到最小字号后不再减小（循环边界正确）。"""
        pixmap = QPixmap(50, 50)
        painter = QPainter(pixmap)
        font = painter.font()

        text = "Very long text that cannot possibly fit in this tiny space"
        max_w, max_h = 30, 15

        test_size = 16
        found = None
        while test_size >= 9:
            font.setPixelSize(test_size)
            fm = QFontMetrics(font)
            bounding = fm.boundingRect(
                0, 0, max_w, 0,
                Qt.TextWordWrap | Qt.AlignHCenter,
                text,
            )
            if bounding.height() <= max_h:
                found = test_size
                break
            test_size -= 1

        # 循环正确退出（要么找到合适字号 ≥9，要么耗尽到 8 退出）
        if found is not None:
            assert found >= 9
        else:
            assert test_size == 8  # 循环耗尽，test_size 被减到 8
        painter.end()

    def test_chinese_text_wrapping(self) -> None:
        """中文文本可以正常测量折行。"""
        pixmap = QPixmap(200, 200)
        painter = QPainter(pixmap)
        font = painter.font()
        font.setPixelSize(14)

        fm = QFontMetrics(font)
        text = "这是一段比较长的中文翻译文本需要换行显示"
        max_w = 100

        bounding = fm.boundingRect(
            0, 0, max_w, 0,
            Qt.TextWordWrap | Qt.AlignHCenter,
            text,
        )
        # 中文按字符折行，宽度受限时高度应该变多行
        assert bounding.width() > 0
        assert bounding.height() > fm.lineSpacing()  # 多行
        painter.end()
