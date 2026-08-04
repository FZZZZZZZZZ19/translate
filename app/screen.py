"""截屏、坐标换算、图片裁剪/缩放/编码 —— 全项目唯一坐标换算点。

所有坐标换算（逻辑像素 ↔ 物理像素）必须经过本模块的 ScreenMapper，
其他模块不得自行乘除 DPI 缩放系数。

v1.1 新增：图片缩放（downscale_image）和 base64 编码（qimage_to_base64_png），
全部基于 Qt 内置能力完成，不引入 Pillow/numpy。
"""

from __future__ import annotations

import base64
import logging
from typing import Tuple

from PyQt5.QtCore import QBuffer, QByteArray, QIODevice, QRect, Qt
from PyQt5.QtGui import QImage, QPixmap
from PyQt5.QtWidgets import QApplication

logger = logging.getLogger(__name__)


def grab_fullscreen() -> QPixmap:
    """截取主屏全屏，返回物理像素尺寸的 QPixmap。

    Returns:
        主屏截图的 QPixmap（保留 devicePixelRatio）。
    """
    screen = QApplication.primaryScreen()
    if screen is None:
        raise RuntimeError("无法获取主屏幕")
    return screen.grabWindow(0)


class ScreenMapper:
    """主屏坐标换算器。

    属性：
        screen_geometry: 主屏逻辑尺寸（QRect）
        dpr: devicePixelRatio（物理/逻辑比，如 1.0 / 1.25 / 1.5 / 2.0）
    """

    def __init__(self) -> None:
        """初始化：读取主屏 geometry 与 devicePixelRatio。"""
        screen = QApplication.primaryScreen()
        if screen is None:
            raise RuntimeError("无法获取主屏幕")

        self.screen_geometry: QRect = screen.geometry()
        self.dpr: float = screen.devicePixelRatio()
        logger.info(
            "屏幕信息: 逻辑=%dx%d, DPR=%.2f, 物理≈%dx%d",
            self.screen_geometry.width(),
            self.screen_geometry.height(),
            self.dpr,
            int(self.screen_geometry.width() * self.dpr),
            int(self.screen_geometry.height() * self.dpr),
        )

    def logical_to_physical(self, x: int, y: int, w: int, h: int) -> QRect:
        """逻辑坐标 → 物理像素坐标。

        Args:
            x, y: 逻辑坐标左上角
            w, h: 逻辑宽高

        Returns:
            物理像素 QRect。
        """
        return QRect(
            int(x * self.dpr),
            int(y * self.dpr),
            int(w * self.dpr),
            int(h * self.dpr),
        )

    def physical_to_logical(self, rect: QRect) -> QRect:
        """物理像素坐标 → 逻辑坐标。"""
        return QRect(
            int(rect.x() / self.dpr),
            int(rect.y() / self.dpr),
            int(rect.width() / self.dpr),
            int(rect.height() / self.dpr),
        )

    def crop_qimage(self, pm: QPixmap, logical_rect: QRect) -> QImage:
        """从 QPixmap 按逻辑选区裁剪，返回物理像素 RGB QImage。

        Args:
            pm: 全屏截图的 QPixmap（物理像素）
            logical_rect: 用户选区（逻辑坐标，normalized）

        Returns:
            裁剪区域对应的 RGB888 QImage。
        """
        phys = self.logical_to_physical(
            logical_rect.x(),
            logical_rect.y(),
            logical_rect.width(),
            logical_rect.height(),
        )

        # 边界裁剪，防止越界
        img_w = pm.width()
        img_h = pm.height()
        x = max(0, phys.x())
        y = max(0, phys.y())
        w = min(phys.width(), img_w - x)
        h = min(phys.height(), img_h - y)

        if w <= 0 or h <= 0:
            raise ValueError(f"裁剪区域无效: phys={phys}, 截图={img_w}x{img_h}")

        image = pm.toImage()
        cropped = image.copy(x, y, w, h)

        # 确保 RGB888 格式
        if cropped.format() != QImage.Format_RGB888:
            cropped = cropped.convertToFormat(QImage.Format_RGB888)

        logger.info("裁剪选区: 逻辑=%s → 物理=%s (实际裁剪=%d,%d %dx%d)", logical_rect, phys, x, y, w, h)
        return cropped

    @staticmethod
    def downscale_image(img: QImage, max_side: int) -> Tuple[QImage, float]:
        """若图片最长边超过 max_side，等比缩放。

        Args:
            img: 原始 QImage
            max_side: 最长边上限 px

        Returns:
            (缩放后 QImage, 缩放比)。缩放比 = 原边长 / 新边长（>1 表示缩小）。
            若无需缩放，返回 (原图, 1.0)。
        """
        w = img.width()
        h = img.height()
        longest = max(w, h)

        if longest <= max_side:
            return img, 1.0

        scale = longest / max_side
        new_w = int(w / scale)
        new_h = int(h / scale)
        scaled = img.scaled(
            new_w, new_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        logger.info("图片缩放: %dx%d → %dx%d (scale=%.3f)", w, h, new_w, new_h, scale)
        return scaled, scale

    @staticmethod
    def qimage_to_base64_png(img: QImage) -> str:
        """将 QImage 编码为 PNG 并返回 base64 data URI。

        Args:
            img: 要编码的 QImage

        Returns:
            形如 "data:image/png;base64,..." 的字符串。
        """
        ba = QByteArray()
        buf = QBuffer(ba)
        buf.open(QIODevice.WriteOnly)
        img.save(buf, "PNG")
        buf.close()

        b64 = base64.b64encode(ba.data()).decode("ascii")
        return f"data:image/png;base64,{b64}"
