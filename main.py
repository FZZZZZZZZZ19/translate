"""ScreenCaptureOCR Translator —— 程序入口。

创建 QApplication、系统托盘、全局热键注册、状态机调度。
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QMenu,
    QSystemTrayIcon,
)

from app.config import ConfigManager
from app.hotkey import GlobalHotkey
from app.pipeline import AppController
from app.result_overlay import ResultOverlay
from app.screen import ScreenMapper, grab_fullscreen
from app.selection_overlay import SelectionOverlay

# ── 日志配置 ──────────────────────────────────────────────


def _setup_logging() -> str:
    """配置日志：输出到 %APPDATA%/ScreenCaptureOCR/app.log，级别 INFO。

    Returns:
        日志文件路径。
    """
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    log_dir = Path(appdata) / "ScreenCaptureOCR"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / "app.log"

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.FileHandler(str(log_path), encoding="utf-8"),
        ],
    )
    return str(log_path)


def _create_tray_icon() -> QIcon:
    """创建托盘图标：优先加载 icon.ico，否则程序绘制。

    Returns:
        QIcon 对象。
    """
    # 尝试加载 icon.ico
    if getattr(sys, "frozen", False):
        icon_dirs = [
            Path(sys.executable).parent / "assets",
            Path(sys.executable).parent,
        ]
    else:
        icon_dirs = [Path(__file__).parent / "assets"]

    for d in icon_dirs:
        p = d / "icon.ico"
        if p.exists():
            return QIcon(str(p))

    # 兜底：程序绘制简单图标（32x32 蓝色圆角矩形 + "译"字）
    pixmap = QPixmap(32, 32)
    pixmap.fill(Qt.transparent)

    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(66, 133, 244))
    painter.setPen(Qt.NoPen)
    painter.drawRoundedRect(2, 2, 28, 28, 6, 6)
    painter.setPen(QColor(255, 255, 255))
    font = painter.font()
    font.setPixelSize(16)
    font.setBold(True)
    painter.setFont(font)
    painter.drawText(pixmap.rect(), Qt.AlignCenter, "译")
    painter.end()

    return QIcon(pixmap)


# ── 程序入口 ──────────────────────────────────────────────


def main() -> int:
    """程序主入口。

    Returns:
        退出码（0 = 正常）。
    """
    log_path = _setup_logging()
    logger = logging.getLogger("main")
    logger.info("=" * 60)
    logger.info("ScreenCaptureOCR Translator 启动 (v1.1)")
    logger.info("日志文件: %s", log_path)

    # ── HighDPI 属性（必须在创建 QApplication 之前设置）──
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("ScreenCaptureOCR Translator")

    # ── 核心组件 ──────────────────────────────────────────
    cfg = ConfigManager()
    config = cfg.load()
    mapper = ScreenMapper()
    controller = AppController(cfg, mapper)

    # 覆盖层（单例复用）
    result_overlay = ResultOverlay(mapper)
    # 应用当前样式
    result_overlay.configure_style(
        bg_color=config.overlay.bg_color,
        text_color=config.overlay.text_color,
        padding=config.overlay.padding,
        min_font_size=config.overlay.min_font_size,
    )

    # 选区遮罩实例引用
    selection_overlay: Optional[SelectionOverlay] = None

    # ── 设置窗口工厂 ──────────────────────────────────────

    settings_dialog: Optional[object] = None

    def open_settings() -> None:
        """打开设置对话框。"""
        nonlocal settings_dialog
        from app.settings_dialog import SettingsDialog

        dlg = SettingsDialog(cfg, hotkey)
        if dlg.exec_() == dlg.Accepted:
            # 重新加载配置并应用样式
            new_cfg = cfg.load()
            result_overlay.configure_style(
                bg_color=new_cfg.overlay.bg_color,
                text_color=new_cfg.overlay.text_color,
                padding=new_cfg.overlay.padding,
                min_font_size=new_cfg.overlay.min_font_size,
            )
            tray.showMessage(
                "截图翻译", "设置已保存",
                QSystemTrayIcon.Information, 2000,
            )

    # ── 内部辅助函数 ──────────────────────────────────────

    def _save_selection_png(
        screenshot: QPixmap, mapper_obj: ScreenMapper, rect
    ) -> None:
        """保存选区图到临时目录 PNG（调试用）。"""
        try:
            cropped = mapper_obj.crop_qimage(screenshot, rect)
            tmp_dir = Path(tempfile.gettempdir()) / "ScreenCaptureOCR"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            out_path = tmp_dir / f"selection_{timestamp}.png"
            cropped.save(str(out_path), "PNG")
            logger.info(
                "选区图已保存: %s (%dx%d)",
                out_path, cropped.width(), cropped.height(),
            )
        except Exception as e:
            logger.error("保存选区图失败: %s", e)

    def _hide_selection() -> None:
        """隐藏选区遮罩（若有）。"""
        nonlocal selection_overlay
        if selection_overlay:
            selection_overlay.hide()
            selection_overlay = None

    def _hide_result_overlay() -> None:
        """隐藏覆盖层。"""
        result_overlay.clear()

    def create_selection_overlay() -> SelectionOverlay:
        """创建新的选区遮罩实例（每次流程新建，因为底图会变）。"""
        nonlocal selection_overlay
        screenshot = grab_fullscreen()
        overlay = SelectionOverlay(mapper, screenshot)
        overlay.selection_done.connect(controller.on_selection_done)
        overlay.cancelled.connect(controller.on_selection_cancelled)
        # 保存选区 PNG 供调试
        overlay.selection_done.connect(
            lambda rect: _save_selection_png(screenshot, mapper, rect)
        )
        selection_overlay = overlay
        return overlay

    # ── 热键回调 ──────────────────────────────────────────

    def on_hotkey_trigger() -> None:
        """全局热键触发：启动截图翻译流程。"""
        logger.info("热键触发")
        controller.start_screen_flow()

    def on_esc() -> None:
        """ESC 全局回调：退出覆盖层。"""
        logger.info("ESC 全局回调")
        controller.on_esc_in_overlay()

    hotkey = GlobalHotkey(on_hotkey_trigger, on_esc)

    # ── 流程信号连接 ──────────────────────────────────────

    # 流程开始：隐藏旧覆盖层 → 创建选区遮罩
    controller.flow_started.connect(_hide_result_overlay)
    controller.flow_started.connect(lambda: create_selection_overlay().start())

    # 流程结束：隐藏选区遮罩 + 覆盖层
    controller.flow_finished.connect(_hide_selection)
    controller.flow_finished.connect(_hide_result_overlay)

    # 翻译完成：显示覆盖层
    controller.translations_ready.connect(result_overlay.show_translations)

    # ── 系统托盘 ──────────────────────────────────────────

    tray_icon = _create_tray_icon()

    tray = QSystemTrayIcon()
    tray.setIcon(tray_icon)
    tray.setToolTip("屏幕截图 AI 翻译")

    # 双击托盘 = 触发截图翻译
    tray.activated.connect(
        lambda reason: (
            on_hotkey_trigger()
            if reason == QSystemTrayIcon.DoubleClick
            else None
        )
    )

    # 托盘菜单
    menu = QMenu()

    action_capture = QAction("截图翻译", menu)
    action_capture.triggered.connect(on_hotkey_trigger)
    menu.addAction(action_capture)

    menu.addSeparator()

    action_settings = QAction("设置", menu)
    action_settings.triggered.connect(open_settings)
    menu.addAction(action_settings)

    menu.addSeparator()

    action_quit = QAction("退出", menu)
    action_quit.triggered.connect(app.quit)
    menu.addAction(action_quit)

    tray.setContextMenu(menu)

    # 连接状态消息到托盘气泡
    controller.status_message.connect(
        lambda msg: tray.showMessage(
            "截图翻译", msg,
            QSystemTrayIcon.Information, 2000,
        )
    )

    # 检查托盘可用性
    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.warning("系统托盘不可用，请检查桌面环境")
    tray.show()

    # ── 注册热键 ──────────────────────────────────────────

    ok, err = hotkey.register(config.hotkey)
    if not ok:
        logger.error("热键注册失败: %s", err)
        tray.showMessage(
            "截图翻译",
            f"热键 {config.hotkey} 注册失败: {err}\n请在设置中更换快捷键",
            QSystemTrayIcon.Warning,
            5000,
        )

    logger.info("应用就绪，等待热键 %s", config.hotkey)
    tray.showMessage(
        "截图翻译",
        f"已启动\n快捷键: {config.hotkey}",
        QSystemTrayIcon.Information,
        2000,
    )

    # ── 事件循环 ──────────────────────────────────────────

    try:
        exit_code = app.exec_()
    finally:
        logger.info("应用退出中…")
        hotkey.unregister()
        controller.shutdown()
        if selection_overlay:
            selection_overlay.hide()
        result_overlay.clear()
        logger.info("应用已退出")
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
