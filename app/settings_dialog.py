"""设置对话框 —— API Key、模型、快捷键、样式配置。

快捷键捕获：聚焦输入框后，用 keyboard.hook 捕获下一次组合键，
捕获后立刻移除钩子。避免 IME/输入法干扰。
"""

from __future__ import annotations

import logging
from typing import Optional

import keyboard
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtGui import QColor, QFont
from PyQt5.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from .config import AppConfig, ConfigManager
from .hotkey import GlobalHotkey

logger = logging.getLogger(__name__)

# 已知千问视觉模型列表（阿里云百炼控制台实际可用模型）
KNOWN_MODELS = [
    "qwen-vl-plus",
    "qwen-vl-max",
    "qwen2.5-vl-72b-instruct",
    "qwen2.5-vl-7b-instruct",
    "qwen3-vl-plus",
]


class HotkeyCaptureLineEdit(QLineEdit):
    """快捷键捕获输入框：聚焦后首次组合键被捕获并显示。

    信号：
        hotkey_captured(str): 捕获到的组合键文本（keyboard 格式）
    """

    hotkey_captured = pyqtSignal(str)

    def __init__(self, current_hotkey: str = "", parent=None) -> None:
        super().__init__(current_hotkey, parent)
        self._current = current_hotkey
        self._hook_id: Optional[int] = None
        self.setReadOnly(True)
        self.setPlaceholderText("点击此处后按下组合键…")

    def focusInEvent(self, event) -> None:
        """聚焦时开始监听。"""
        super().focusInEvent(event)
        self.setText("请按下快捷键…")
        self._start_hook()

    def focusOutEvent(self, event) -> None:
        """失焦时停止监听。"""
        self._stop_hook()
        self.setText(self._current)
        super().focusOutEvent(event)

    def _start_hook(self) -> None:
        """用 keyboard.hook 捕获下一次按键。"""
        self._stop_hook()

        captured_keys = []

        def on_key(e) -> None:
            if e.event_type == keyboard.KEY_DOWN:
                name = e.name
                if name not in captured_keys:
                    captured_keys.append(name)
                # 至少一个修饰键 + 一个普通键时完成捕获
                mods = {"ctrl", "alt", "shift", "windows", "cmd"}
                normals = [k for k in captured_keys if k not in mods]
                mods_pressed = [k for k in captured_keys if k in mods]
                if normals and mods_pressed:
                    combo = "+".join(
                        sorted(mods_pressed) + sorted(normals)
                    )
                    combo = combo.replace("windows", "windows")
                    self._current = combo
                    self.setText(combo)
                    self.hotkey_captured.emit(combo)
                    self._stop_hook()
                    self.clearFocus()

        self._hook_id = keyboard.hook(on_key, suppress=True)

    def _stop_hook(self) -> None:
        """停止键盘钩子。"""
        if self._hook_id is not None:
            try:
                keyboard.unhook(self._hook_id)
            except Exception:
                pass
            self._hook_id = None

    @property
    def current_hotkey(self) -> str:
        """当前捕获的组合键。"""
        return self._current


class SettingsDialog(QDialog):
    """应用设置对话框。

    Args:
        cfg: 配置管理器
        hotkey: 全局热键管理器（用于保存后重新注册）
    """

    def __init__(
        self, cfg: ConfigManager, hotkey_mgr: GlobalHotkey, parent=None
    ) -> None:
        super().__init__(parent)
        self._cfg = cfg
        self._hotkey_mgr = hotkey_mgr
        self._config = cfg.load()
        self._init_ui()
        self.setWindowTitle("设置")
        self.setMinimumWidth(420)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowContextHelpButtonHint
        )

    def _init_ui(self) -> None:
        """构建 UI。"""
        layout = QVBoxLayout(self)

        # ── API 设置 ──
        api_group = QGroupBox("千问 API 设置")
        api_form = QFormLayout(api_group)

        # API Key
        key_layout = QHBoxLayout()
        self._key_edit = QLineEdit(self._config.api_key)
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setPlaceholderText("输入 DashScope API Key…")
        key_layout.addWidget(self._key_edit)

        self._show_key_cb = QCheckBox("显示")
        self._show_key_cb.toggled.connect(self._toggle_key_visibility)
        key_layout.addWidget(self._show_key_cb)
        api_form.addRow("API Key:", key_layout)

        # 模型
        model_layout = QHBoxLayout()
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems(KNOWN_MODELS)
        # 确保当前模型在列表中
        if self._config.model not in KNOWN_MODELS:
            self._model_combo.addItem(self._config.model)
        self._model_combo.setCurrentText(self._config.model)
        model_layout.addWidget(self._model_combo)
        api_form.addRow("模型:", model_layout)

        # API 端点
        self._api_base_edit = QLineEdit(self._config.api_base)
        api_form.addRow("API 端点:", self._api_base_edit)

        layout.addWidget(api_group)

        # ── 快捷键 ──
        hotkey_group = QGroupBox("全局快捷键")
        hotkey_form = QFormLayout(hotkey_group)
        self._hotkey_edit = HotkeyCaptureLineEdit(self._config.hotkey)
        hotkey_form.addRow("快捷键:", self._hotkey_edit)
        hotkey_form.addRow(
            QLabel("点击输入框后按下组合键（如 Ctrl+Alt+T）")
        )
        layout.addWidget(hotkey_group)

        # ── 图片设置 ──
        img_group = QGroupBox("图片设置")
        img_form = QFormLayout(img_group)
        self._max_side_spin = QSpinBox()
        self._max_side_spin.setRange(512, 4096)
        self._max_side_spin.setSingleStep(256)
        self._max_side_spin.setValue(self._config.max_image_side)
        self._max_side_spin.setSuffix(" px")
        img_form.addRow("上传图片最长边:", self._max_side_spin)
        layout.addWidget(img_group)

        # ── 覆盖层样式 ──
        style_group = QGroupBox("译文覆盖层样式")
        style_form = QFormLayout(style_group)

        # 背景色
        bg_layout = QHBoxLayout()
        self._bg_color_btn = QPushButton()
        self._bg_color_btn.setFixedSize(32, 24)
        self._bg_color_btn.setStyleSheet(
            f"background-color: {self._config.overlay.bg_color}; "
            "border: 1px solid #999; border-radius: 2px;"
        )
        self._bg_color_btn.clicked.connect(self._pick_bg_color)
        bg_layout.addWidget(self._bg_color_btn)
        bg_layout.addWidget(QLabel(self._config.overlay.bg_color))
        bg_layout.addStretch()
        style_form.addRow("背景色:", bg_layout)

        # 文字色
        text_layout = QHBoxLayout()
        self._text_color_btn = QPushButton()
        self._text_color_btn.setFixedSize(32, 24)
        self._text_color_btn.setStyleSheet(
            f"background-color: {self._config.overlay.text_color}; "
            "border: 1px solid #999; border-radius: 2px;"
        )
        self._text_color_btn.clicked.connect(self._pick_text_color)
        text_layout.addWidget(self._text_color_btn)
        text_layout.addWidget(QLabel(self._config.overlay.text_color))
        text_layout.addStretch()
        style_form.addRow("文字色:", text_layout)

        # 边距
        self._padding_spin = QSpinBox()
        self._padding_spin.setRange(0, 20)
        self._padding_spin.setValue(self._config.overlay.padding)
        self._padding_spin.setSuffix(" px")
        style_form.addRow("内边距:", self._padding_spin)

        # 最小字号
        self._min_font_spin = QSpinBox()
        self._min_font_spin.setRange(6, 24)
        self._min_font_spin.setValue(self._config.overlay.min_font_size)
        self._min_font_spin.setSuffix(" pt")
        style_form.addRow("最小字号:", self._min_font_spin)

        layout.addWidget(style_group)

        # ── 按钮 ──
        buttons = QDialogButtonBox(
            QDialogButtonBox.Ok | QDialogButtonBox.Cancel
        )
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    # ── 交互 ──────────────────────────────────────────────

    def _toggle_key_visibility(self, checked: bool) -> None:
        """切换 API Key 可见性。"""
        self._key_edit.setEchoMode(
            QLineEdit.Normal if checked else QLineEdit.Password
        )

    def _pick_bg_color(self) -> None:
        """选择背景色。"""
        color = QColorDialog.getColor(
            QColor(self._config.overlay.bg_color), self, "选择背景色"
        )
        if color.isValid():
            self._config.overlay.bg_color = color.name()
            self._bg_color_btn.setStyleSheet(
                f"background-color: {color.name()}; "
                "border: 1px solid #999; border-radius: 2px;"
            )
            # 更新 label
            btn_layout = self._bg_color_btn.parent().layout()
            if btn_layout and btn_layout.count() > 1:
                lbl = btn_layout.itemAt(1).widget()
                if isinstance(lbl, QLabel):
                    lbl.setText(color.name())

    def _pick_text_color(self) -> None:
        """选择文字色。"""
        color = QColorDialog.getColor(
            QColor(self._config.overlay.text_color), self, "选择文字色"
        )
        if color.isValid():
            self._config.overlay.text_color = color.name()
            self._text_color_btn.setStyleSheet(
                f"background-color: {color.name()}; "
                "border: 1px solid #999; border-radius: 2px;"
            )
            btn_layout = self._text_color_btn.parent().layout()
            if btn_layout and btn_layout.count() > 1:
                lbl = btn_layout.itemAt(1).widget()
                if isinstance(lbl, QLabel):
                    lbl.setText(color.name())

    def _on_save(self) -> None:
        """保存配置并重新注册热键。"""
        # 收集配置
        self._config.api_key = self._key_edit.text().strip()
        self._config.model = self._model_combo.currentText().strip()
        self._config.api_base = self._api_base_edit.text().strip()
        self._config.max_image_side = self._max_side_spin.value()
        self._config.overlay.padding = self._padding_spin.value()
        self._config.overlay.min_font_size = self._min_font_spin.value()

        new_hotkey = self._hotkey_edit.current_hotkey

        # 保存配置
        try:
            self._cfg.save(self._config)
        except OSError as e:
            logger.error("配置保存失败: %s", e)
            return

        # 重新注册热键（若变更）
        if new_hotkey != self._config.hotkey:
            ok, err = self._hotkey_mgr.register(new_hotkey)
            if not ok:
                logger.error("热键注册失败: %s", err)
                # 回滚：恢复旧热键
                self._hotkey_mgr.register(self._config.hotkey)
                # TODO: 显示错误对话框
                return
            self._config.hotkey = new_hotkey

        logger.info("设置已保存")
        self.accept()
