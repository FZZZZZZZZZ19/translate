"""屏幕/图片处理模块单元测试（纯函数部分）。

注意：ScreenMapper 需 QApplication 实例，因此涉及坐标换算的测试
需要 QApplication 上下文。本文件测试不依赖 GUI 的纯函数。
"""

from __future__ import annotations

from PyQt5.QtGui import QImage

from app.screen import ScreenMapper


class TestDownscaleImage:
    """图片缩放测试（纯函数，不需要 QApplication）。"""

    def test_no_scale_when_small(self) -> None:
        """图片小于 max_side 时不做缩放。"""
        img = QImage(100, 80, QImage.Format_RGB888)
        result, scale = ScreenMapper.downscale_image(img, 2048)
        assert scale == 1.0
        assert result.width() == 100
        assert result.height() == 80

    def test_scale_when_too_large_width(self) -> None:
        """宽度超过 max_side 时等比缩放。"""
        img = QImage(4096, 100, QImage.Format_RGB888)
        result, scale = ScreenMapper.downscale_image(img, 2048)
        assert scale > 1.0
        assert result.width() <= 2048
        # 等比缩放
        assert abs(scale - 4096.0 / result.width()) < 0.01

    def test_scale_when_too_large_height(self) -> None:
        """高度超过 max_side 时等比缩放。"""
        img = QImage(100, 4096, QImage.Format_RGB888)
        result, scale = ScreenMapper.downscale_image(img, 2048)
        assert scale > 1.0
        assert result.height() <= 2048
        assert abs(scale - 4096.0 / result.height()) < 0.01

    def test_scale_preserves_aspect_ratio(self) -> None:
        """缩放保持宽高比。"""
        img = QImage(4000, 3000, QImage.Format_RGB888)
        result, scale = ScreenMapper.downscale_image(img, 2048)
        orig_ratio = 4000.0 / 3000.0
        new_ratio = result.width() / result.height()
        assert abs(orig_ratio - new_ratio) < 0.02


class TestQimageToBase64:
    """PNG 编码测试。"""

    def test_returns_data_uri(self) -> None:
        """返回有效的 data URI 格式。"""
        img = QImage(10, 10, QImage.Format_RGB888)
        img.fill(0xFF0000)  # 红色
        result = ScreenMapper.qimage_to_base64_png(img)
        assert result.startswith("data:image/png;base64,")
        assert len(result) > len("data:image/png;base64,")

    def test_encoding_is_valid_base64(self) -> None:
        """base64 部分可解码。"""
        import base64

        img = QImage(5, 5, QImage.Format_RGB888)
        result = ScreenMapper.qimage_to_base64_png(img)
        b64_part = result[len("data:image/png;base64,"):]
        decoded = base64.b64decode(b64_part)
        # PNG 文件头
        assert decoded[:8] == b"\x89PNG\r\n\x1a\n"
