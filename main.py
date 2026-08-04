"""ScreenCaptureOCR Translator —— 程序入口。

启动显示主控制面板窗口；关闭窗口最小化到系统托盘。
"""

from __future__ import annotations

import logging
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from PyQt5.QtCore import Qt, QRect, QTimer
from PyQt5.QtGui import QColor, QIcon, QPainter, QPixmap
from PyQt5.QtWidgets import (
    QAction,
    QApplication,
    QMenu,
    QMessageBox,
    QSystemTrayIcon,
)

from app.config import AppConfig, ConfigManager
from app.hotkey import GlobalHotkey
from app.main_window import MainWindow
from app.pipeline import AppController
from app.qwen_client import VisionLine
from app.result_overlay import ResultOverlay
from app.screen import ScreenMapper, grab_fullscreen
from app.selection_overlay import SelectionOverlay

# ── 日志配置 ──────────────────────────────────────────────


def _setup_logging() -> str:
    """配置日志：输出到 %APPDATA%/ScreenCaptureOCR/app.log。"""
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
    """创建托盘图标：优先 icon.ico，否则程序绘制。"""
    if getattr(sys, "frozen", False):
        icon_dirs = [Path(sys.executable).parent / "assets", Path(sys.executable).parent]
    else:
        icon_dirs = [Path(__file__).parent / "assets"]

    for d in icon_dirs:
        p = d / "icon.ico"
        if p.exists():
            return QIcon(str(p))

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
    log_path = _setup_logging()
    logger = logging.getLogger("main")
    logger.info("=" * 60)
    logger.info("ScreenCaptureOCR Translator 启动 (v1.1)")
    logger.info("日志文件: %s", log_path)

    # ── HighDPI ──
    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)
    app.setApplicationName("ScreenCaptureOCR Translator")

    # ── 核心组件 ──
    cfg = ConfigManager()
    config = cfg.load()
    mapper = ScreenMapper()
    controller = AppController(cfg, mapper)

    # 覆盖层
    result_overlay = ResultOverlay(mapper)

    # 选区遮罩引用
    selection_overlay: Optional[SelectionOverlay] = None

    # ── 主窗口 ──
    main_win = MainWindow(
        api_key=config.api_key,
        model=config.model,
        hotkey=config.hotkey,
        bg_color=config.overlay.bg_color,
        text_color=config.overlay.text_color,
        padding=config.overlay.padding,
        min_font_size=config.overlay.min_font_size,
        max_image_side=config.max_image_side,
    )

    # ── 托盘 ──
    tray = QSystemTrayIcon()
    tray.setIcon(_create_tray_icon())
    tray.setToolTip("截图翻译 · ScreenCaptureOCR Translator")

    # 双击托盘 → 显示主窗口
    tray.activated.connect(
        lambda reason: (
            main_win.show() if reason == QSystemTrayIcon.DoubleClick else None
        )
    )

    # 托盘菜单
    tray_menu = QMenu()
    action_show = QAction("显示主窗口", tray_menu)
    action_show.triggered.connect(main_win.show)
    tray_menu.addAction(action_show)

    action_capture = QAction("截图翻译", tray_menu)
    tray_menu.addAction(action_capture)

    tray_menu.addSeparator()

    action_quit = QAction("退出", tray_menu)
    tray_menu.addAction(action_quit)

    tray.setContextMenu(tray_menu)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        logger.warning("系统托盘不可用")

    # ── 内部辅助函数 ──

    def _apply_style() -> None:
        """应用当前 UI 中的覆盖层样式。"""
        d = main_win.get_config_dict()
        result_overlay.configure_style(
            bg_color=d["bg_color"],
            text_color=d["text_color"],
            padding=d["padding"],
            min_font_size=d["min_font_size"],
        )

    def _hide_selection() -> None:
        nonlocal selection_overlay
        if selection_overlay:
            selection_overlay.hide()
            selection_overlay = None

    def _hide_result() -> None:
        result_overlay.clear()

    def create_selection_overlay() -> SelectionOverlay:
        nonlocal selection_overlay
        screenshot = grab_fullscreen()
        overlay = SelectionOverlay(mapper, screenshot)
        overlay.selection_done.connect(controller.on_selection_done)
        overlay.cancelled.connect(controller.on_selection_cancelled)
        overlay.selection_done.connect(
            lambda rect: _save_debug_png(screenshot, mapper, rect)
        )
        selection_overlay = overlay
        return overlay

    def _save_debug_png(screenshot, mapper_obj, rect) -> None:
        try:
            cropped = mapper_obj.crop_qimage(screenshot, rect)
            tmp_dir = Path(tempfile.gettempdir()) / "ScreenCaptureOCR"
            tmp_dir.mkdir(parents=True, exist_ok=True)
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            out = tmp_dir / f"selection_{ts}.png"
            cropped.save(str(out), "PNG")
        except Exception:
            pass

    # ── 热键回调 ──

    def on_hotkey_trigger() -> None:
        """热键触发：检查开关 → 启动流程。"""
        if not main_win.is_enabled:
            main_win.set_status("翻译已关闭，请先开启")
            return
        logger.info("热键触发")
        controller.start_screen_flow()

    def on_esc() -> None:
        controller.on_esc_in_overlay()

    hotkey = GlobalHotkey(on_hotkey_trigger, on_esc)

    def _reload_hotkey() -> None:
        """重新加载配置并注册热键。"""
        new_cfg = cfg.load()
        _apply_style()
        hotkey.register(new_cfg.hotkey)

    # ── 信号连接 ──

    # 主窗口设置保存 → 写配置 + 重新注册热键
    def _on_settings_changed() -> None:
        d = main_win.get_config_dict()
        new_cfg = AppConfig(
            api_key=d["api_key"],
            model=d["model"],
            hotkey=d["hotkey"],
            max_image_side=d["max_image_side"],
        )
        new_cfg.overlay.bg_color = d["bg_color"]
        new_cfg.overlay.text_color = d["text_color"]
        new_cfg.overlay.padding = d["padding"]
        new_cfg.overlay.min_font_size = d["min_font_size"]

        try:
            cfg.save(new_cfg)
        except OSError as e:
            logger.error("配置保存失败: %s", e)
            QMessageBox.warning(main_win, "错误", f"保存失败: {e}")
            return

        _apply_style()

        # 重新注册热键
        if d["hotkey"] != config.hotkey:
            ok, err = hotkey.register(d["hotkey"])
            if not ok:
                hotkey.register(config.hotkey)  # 回滚
                QMessageBox.warning(main_win, "热键注册失败", err)
            else:
                config.hotkey = d["hotkey"]
                main_win.set_status(f"热键已更新为 {d['hotkey']}")

        main_win.set_status("设置已保存")
        tray.showMessage("截图翻译", "设置已保存", QSystemTrayIcon.Information, 1500)

    main_win.settings_changed.connect(_on_settings_changed)

    # 翻译开关
    def _on_toggle(enabled: bool) -> None:
        if enabled:
            hotkey.register(config.hotkey)
            main_win.set_status("翻译已开启 · 按快捷键或托盘菜单开始")
        else:
            main_win.set_status("翻译已关闭")

    main_win.toggle_changed.connect(_on_toggle)

    # 托盘菜单"截图翻译"
    action_capture.triggered.connect(on_hotkey_trigger)

    # 流程信号
    controller.flow_started.connect(_hide_result)
    controller.flow_started.connect(lambda: create_selection_overlay().start())
    controller.flow_finished.connect(_hide_selection)
    controller.flow_finished.connect(_hide_result)
    controller.status_message.connect(main_win.set_status)
    controller.status_message.connect(
        lambda msg: tray.showMessage("截图翻译", msg, QSystemTrayIcon.Information, 2000)
    )

    # 翻译完成 → 显示覆盖层 + 记录日志
    def _on_translations(items: List[VisionLine]) -> None:
        result_overlay.show_translations(items)
        # 记录日志
        for item in items:
            main_win.add_log(item.text, item.translation)
        main_win.set_status(f"翻译完成 ({len(items)} 行)，按 ESC 退出")

    controller.translations_ready.connect(_on_translations)

    # 流程失败 → 日志
    def _on_failed_log(msg: str) -> None:
        main_win.add_status_log(f"错误: {msg}")

    controller.status_message.connect(
        lambda msg: main_win.add_status_log(msg) if "失败" in msg or "错误" in msg else None
    )

    # ── 退出 ──
    def _quit() -> None:
        logger.info("用户请求退出")
        hotkey.unregister()
        controller.shutdown()
        _hide_selection()
        _hide_result()
        main_win.hide()
        app.quit()

    action_quit.triggered.connect(_quit)

    # ── 启动 ──

    # 注册热键
    ok, err = hotkey.register(config.hotkey)
    if not ok:
        logger.error("热键注册失败: %s", err)
        main_win.add_status_log(f"热键 {config.hotkey} 注册失败: {err}")

    # 显示主窗口 + 托盘
    main_win.show()
    tray.show()

    # 首次运行：无 API Key → 提示
    if not config.api_key:
        main_win.set_status("请先填入 API Key 并保存设置")
        QTimer.singleShot(800, lambda: tray.showMessage(
            "截图翻译",
            "请先在主窗口中填入千问 API Key\n点击「保存设置」后即可使用",
            QSystemTrayIcon.Information,
            6000,
        ))

    logger.info("应用就绪")
    main_win.set_status(f"就绪 · 快捷键: {config.hotkey}")

    # ── 事件循环 ──
    try:
        exit_code = app.exec_()
    finally:
        hotkey.unregister()
        controller.shutdown()
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
