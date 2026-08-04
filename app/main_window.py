"""主控制面板窗口 —— 设置、翻译开关、日志查看。

应用启动时显示此窗口；关闭窗口 = 最小化到托盘。
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import List, Optional

from PyQt5.QtCore import Qt, QTimer, pyqtSignal
from PyQt5.QtGui import (
    QBrush,
    QColor,
    QFont,
    QIcon,
    QKeySequence,
    QPalette,
    QPixmap,
)
from PyQt5.QtWidgets import (
    QCheckBox,
    QColorDialog,
    QComboBox,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    QStyle,
)

logger = logging.getLogger(__name__)

# 已知模型列表
KNOWN_MODELS = [
    "qwen-vl-plus",
    "qwen-vl-max",
    "qwen2.5-vl-72b-instruct",
    "qwen2.5-vl-7b-instruct",
    "qwen3-vl-plus",
]

# 最大日志条目数
MAX_LOG_ENTRIES = 200


class LogEntry:
    """翻译日志条目。"""

    def __init__(self, timestamp: datetime, source: str, translation: str) -> None:
        self.timestamp = timestamp
        self.source = source
        self.translation = translation


class HotkeyCaptureButton(QPushButton):
    """快捷键捕获按钮：点击后捕获下一次组合键。

    信号：
        hotkey_captured(str): 捕获的组合键文本
    """

    hotkey_captured = pyqtSignal(str)

    def __init__(self, current: str = "", parent=None) -> None:
        super().__init__(current or "点击捕获快捷键…", parent)
        self._current = current
        self._capturing = False
        self._modifiers = set()
        self._normal_key: Optional[str] = None
        self.setCheckable(True)
        self.toggled.connect(self._on_toggle)
        self.setMinimumWidth(180)
        self.setMaximumHeight(32)

    def _on_toggle(self, checked: bool) -> None:
        if checked:
            self._start_capture()
        else:
            self._stop_capture(commit=False)

    def _start_capture(self) -> None:
        self._capturing = True
        self._modifiers.clear()
        self._normal_key = None
        self.setText("请按下组合键…")
        self.setStyleSheet(self._capture_style())

    def _stop_capture(self, commit: bool = True) -> None:
        self._capturing = False
        self.setChecked(False)
        if commit and self._normal_key:
            combo = self._build_combo()
            self._current = combo
            self.setText(combo)
            self.hotkey_captured.emit(combo)
        else:
            self.setText(self._current or "点击捕获快捷键…")
        self.setStyleSheet("")

    def _build_combo(self) -> str:
        parts = sorted(self._modifiers)
        parts.append(self._normal_key or "")
        return "+".join(p.replace("windows", "win") for p in parts)

    def keyPressEvent(self, event) -> None:
        if not self._capturing:
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()

        # 记录修饰键
        if mods & Qt.ControlModifier:
            self._modifiers.add("ctrl")
        if mods & Qt.AltModifier:
            self._modifiers.add("alt")
        if mods & Qt.ShiftModifier:
            self._modifiers.add("shift")
        if mods & Qt.MetaModifier:
            self._modifiers.add("win")

        # 普通键
        key_text = QKeySequence(key).toString()
        if key_text and key not in (
            Qt.Key_Control, Qt.Key_Alt, Qt.Key_Shift,
            Qt.Key_Meta, Qt.Key_AltGr, Qt.Key_unknown,
        ):
            self._normal_key = key_text.lower()
            self._stop_capture(commit=True)
            return

    def keyReleaseEvent(self, event) -> None:
        if self._capturing:
            # 如果只松开了修饰键（还没捕获到普通键），继续等
            pass
        else:
            super().keyReleaseEvent(event)

    def _capture_style(self) -> str:
        return """
            QPushButton {
                background-color: #FFF3CD;
                border: 2px dashed #FFC107;
                border-radius: 4px;
                color: #856404;
                font-weight: bold;
                padding: 4px 12px;
            }
        """

    @property
    def current_hotkey(self) -> str:
        return self._current


class MainWindow(QMainWindow):
    """主控制面板窗口。

    信号：
        settings_changed(): 设置已保存（通知外部重载配置）
        toggle_changed(bool): 翻译开关状态变化
    """

    settings_changed = pyqtSignal()
    toggle_changed = pyqtSignal(bool)

    def __init__(
        self,
        api_key: str = "",
        model: str = "qwen-vl-plus",
        hotkey: str = "ctrl+alt+t",
        bg_color: str = "#FFFFFF",
        text_color: str = "#000000",
        padding: int = 4,
        min_font_size: int = 9,
        max_image_side: int = 2048,
    ) -> None:
        super().__init__()
        self._api_key = api_key
        self._model = model
        self._hotkey = hotkey
        self._bg_color = bg_color
        self._text_color = text_color
        self._padding = padding
        self._min_font_size = min_font_size
        self._max_image_side = max_image_side
        self._enabled = True
        self._logs: List[LogEntry] = []

        self._init_ui()
        self.setWindowTitle("截图翻译 · ScreenCaptureOCR Translator")

    # ── UI 构建 ──────────────────────────────────────────

    def _init_ui(self) -> None:
        """构建完整 UI。"""
        self.setMinimumSize(520, 600)
        self.resize(560, 680)

        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setSpacing(10)
        root.setContentsMargins(16, 12, 16, 12)

        # ── 标题栏 ──
        root.addWidget(self._create_header())

        # 分割线
        line = QFrame()
        line.setFrameShape(QFrame.HLine)
        line.setFrameShadow(QFrame.Sunken)
        root.addWidget(line)

        # ── 开关 ──
        root.addWidget(self._create_toggle())

        # ── 设置区 ──
        root.addWidget(self._create_settings_group())

        # ── 日志区 ──
        root.addWidget(self._create_log_group(), 1)  # stretch

        # ── 底部按钮 ──
        root.addWidget(self._create_bottom_bar())

    def _create_header(self) -> QWidget:
        """标题栏：图标 + 应用名。"""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        # 图标
        icon_lbl = QLabel("译")
        icon_lbl.setFont(QFont("Microsoft YaHei", 16, QFont.Bold))
        icon_lbl.setStyleSheet(
            "background-color: #4285F4; color: white; "
            "border-radius: 8px; padding: 6px 12px;"
        )
        icon_lbl.setFixedSize(40, 36)
        icon_lbl.setAlignment(Qt.AlignCenter)
        layout.addWidget(icon_lbl)

        title = QLabel("截图翻译 · ScreenCaptureOCR Translator")
        title.setFont(QFont("Microsoft YaHei", 12, QFont.Bold))
        layout.addWidget(title)
        layout.addStretch()

        return w

    def _create_toggle(self) -> QWidget:
        """翻译开关。"""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        label = QLabel("翻译服务")
        label.setFont(QFont("Microsoft YaHei", 10))
        layout.addWidget(label)

        layout.addStretch()

        self._toggle_btn = QPushButton("●  已开启")
        self._toggle_btn.setCheckable(True)
        self._toggle_btn.setChecked(True)
        self._toggle_btn.setFont(QFont("Microsoft YaHei", 10, QFont.Bold))
        self._toggle_btn.setMinimumWidth(110)
        self._toggle_btn.setMaximumHeight(34)
        self._toggle_btn.toggled.connect(self._on_toggle)
        self._update_toggle_style(True)
        layout.addWidget(self._toggle_btn)

        return w

    def _update_toggle_style(self, enabled: bool) -> None:
        """更新开关按钮样式。"""
        if enabled:
            self._toggle_btn.setText("●  已开启")
            self._toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #E8F5E9; color: #2E7D32;
                    border: 1px solid #A5D6A7; border-radius: 4px;
                    padding: 4px 16px;
                }
                QPushButton:hover { background-color: #C8E6C9; }
            """)
        else:
            self._toggle_btn.setText("○  已关闭")
            self._toggle_btn.setStyleSheet("""
                QPushButton {
                    background-color: #FAFAFA; color: #9E9E9E;
                    border: 1px solid #E0E0E0; border-radius: 4px;
                    padding: 4px 16px;
                }
                QPushButton:hover { background-color: #F5F5F5; }
            """)

    def _create_settings_group(self) -> QWidget:
        """设置区：API Key、模型、快捷键、样式。"""
        group = QGroupBox("设置")
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # ── API Key ──
        key_layout = QHBoxLayout()
        key_layout.addWidget(QLabel("API Key:"))
        self._key_edit = QLineEdit(self._api_key)
        self._key_edit.setEchoMode(QLineEdit.Password)
        self._key_edit.setPlaceholderText("输入 DashScope API Key…")
        key_layout.addWidget(self._key_edit, 1)

        self._show_key_cb = QCheckBox("显示")
        self._show_key_cb.toggled.connect(
            lambda c: self._key_edit.setEchoMode(
                QLineEdit.Normal if c else QLineEdit.Password
            )
        )
        key_layout.addWidget(self._show_key_cb)
        layout.addLayout(key_layout)

        # ── 模型 ──
        model_layout = QHBoxLayout()
        model_layout.addWidget(QLabel("模型:"))
        self._model_combo = QComboBox()
        self._model_combo.setEditable(True)
        self._model_combo.addItems(KNOWN_MODELS)
        if self._model not in KNOWN_MODELS:
            self._model_combo.addItem(self._model)
        self._model_combo.setCurrentText(self._model)
        model_layout.addWidget(self._model_combo, 1)
        layout.addLayout(model_layout)

        # ── 快捷键 ──
        hotkey_layout = QHBoxLayout()
        hotkey_layout.addWidget(QLabel("快捷键:"))
        self._hotkey_btn = HotkeyCaptureButton(self._hotkey)
        self._hotkey_btn.hotkey_captured.connect(self._on_hotkey_captured)
        hotkey_layout.addWidget(self._hotkey_btn, 1)
        hotkey_layout.addWidget(QLabel("点击按钮后按下组合键"))
        layout.addLayout(hotkey_layout)

        # ── 样式 ──
        style_layout = QHBoxLayout()
        style_layout.addWidget(QLabel("背景色:"))
        self._bg_btn = QPushButton()
        self._bg_btn.setFixedSize(28, 24)
        self._bg_btn.setStyleSheet(
            f"background-color: {self._bg_color}; "
            "border: 1px solid #999; border-radius: 2px;"
        )
        self._bg_btn.clicked.connect(lambda: self._pick_color("bg"))
        style_layout.addWidget(self._bg_btn)

        style_layout.addWidget(QLabel("文字色:"))
        self._text_btn = QPushButton()
        self._text_btn.setFixedSize(28, 24)
        self._text_btn.setStyleSheet(
            f"background-color: {self._text_color}; "
            "border: 1px solid #999; border-radius: 2px;"
        )
        self._text_btn.clicked.connect(lambda: self._pick_color("text"))
        style_layout.addWidget(self._text_btn)

        style_layout.addWidget(QLabel("边距:"))
        self._pad_spin = QSpinBox()
        self._pad_spin.setRange(0, 20)
        self._pad_spin.setValue(self._padding)
        self._pad_spin.setMaximumWidth(50)
        style_layout.addWidget(self._pad_spin)

        style_layout.addWidget(QLabel("字号:"))
        self._font_spin = QSpinBox()
        self._font_spin.setRange(6, 24)
        self._font_spin.setValue(self._min_font_size)
        self._font_spin.setMaximumWidth(50)
        style_layout.addWidget(self._font_spin)
        style_layout.addStretch()
        layout.addLayout(style_layout)

        # ── 图片边长 ──
        img_layout = QHBoxLayout()
        img_layout.addWidget(QLabel("图片最长边:"))
        self._side_spin = QSpinBox()
        self._side_spin.setRange(512, 4096)
        self._side_spin.setSingleStep(256)
        self._side_spin.setValue(self._max_image_side)
        self._side_spin.setSuffix(" px")
        img_layout.addWidget(self._side_spin)
        img_layout.addStretch()
        layout.addLayout(img_layout)

        # ── 保存按钮 ──
        save_btn = QPushButton("💾  保存设置")
        save_btn.setMinimumHeight(34)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #4285F4; color: white;
                border: none; border-radius: 4px;
                font-weight: bold; padding: 6px 20px;
            }
            QPushButton:hover { background-color: #3367D6; }
        """)
        save_btn.clicked.connect(self._save_settings)
        layout.addWidget(save_btn)

        return group

    def _create_log_group(self) -> QWidget:
        """翻译日志区。"""
        group = QGroupBox("翻译日志")
        layout = QVBoxLayout(group)
        layout.setSpacing(4)

        # 标题 + 清空按钮
        header = QHBoxLayout()
        header.addWidget(QLabel(""))
        header.addStretch()
        clear_btn = QPushButton("清空")
        clear_btn.setMaximumHeight(26)
        clear_btn.clicked.connect(self._clear_logs)
        header.addWidget(clear_btn)
        layout.addLayout(header)

        # 日志表格
        self._log_table = QTableWidget(0, 3)
        self._log_table.setHorizontalHeaderLabels(["时间", "原文", "译文"])
        self._log_table.horizontalHeader().setStretchLastSection(True)
        self._log_table.horizontalHeader().setSectionResizeMode(
            0, QHeaderView.ResizeToContents
        )
        self._log_table.horizontalHeader().setSectionResizeMode(
            1, QHeaderView.Stretch
        )
        self._log_table.horizontalHeader().setSectionResizeMode(
            2, QHeaderView.Stretch
        )
        self._log_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self._log_table.setSelectionBehavior(QTableWidget.SelectRows)
        self._log_table.setAlternatingRowColors(True)
        self._log_table.verticalHeader().setVisible(False)
        layout.addWidget(self._log_table)

        return group

    def _create_bottom_bar(self) -> QWidget:
        """底部状态栏。"""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setContentsMargins(0, 0, 0, 0)

        self._status_label = QLabel("就绪")
        self._status_label.setStyleSheet("color: #666;")
        layout.addWidget(self._status_label)

        layout.addStretch()

        hide_btn = QPushButton("最小化到托盘")
        hide_btn.setMaximumHeight(28)
        hide_btn.clicked.connect(self.hide)
        layout.addWidget(hide_btn)

        return w

    # ── 交互 ──────────────────────────────────────────────

    def _on_toggle(self, checked: bool) -> None:
        """翻译开关切换。"""
        self._enabled = checked
        self._update_toggle_style(checked)
        self.toggle_changed.emit(checked)
        self._status_label.setText("翻译已开启" if checked else "翻译已关闭")

    def _on_hotkey_captured(self, combo: str) -> None:
        """快捷键捕获完成。"""
        self._hotkey = combo

    def _pick_color(self, target: str) -> None:
        """选择颜色。"""
        current = self._bg_color if target == "bg" else self._text_color
        color = QColorDialog.getColor(QColor(current), self, "选择颜色")
        if color.isValid():
            hex_color = color.name()
            if target == "bg":
                self._bg_color = hex_color
                self._bg_btn.setStyleSheet(
                    f"background-color: {hex_color}; "
                    "border: 1px solid #999; border-radius: 2px;"
                )
            else:
                self._text_color = hex_color
                self._text_btn.setStyleSheet(
                    f"background-color: {hex_color}; "
                    "border: 1px solid #999; border-radius: 2px;"
                )

    def _save_settings(self) -> None:
        """收集并发出设置保存信号。"""
        self._api_key = self._key_edit.text().strip()
        self._model = self._model_combo.currentText().strip()
        self._padding = self._pad_spin.value()
        self._min_font_size = self._font_spin.value()
        self._max_image_side = self._side_spin.value()

        if not self._api_key:
            QMessageBox.warning(self, "警告", "API Key 不能为空")
            return

        self.settings_changed.emit()
        self._status_label.setText("设置已保存")

    # ── 日志 ──────────────────────────────────────────────

    def add_log(self, source: str, translation: str) -> None:
        """添加一条翻译日志。

        Args:
            source: 英文原文（多行用 " / " 连接）
            translation: 中文译文（多行用 " / " 连接）
        """
        entry = LogEntry(datetime.now(), source, translation)
        self._logs.append(entry)

        # 限制日志数量
        while len(self._logs) > MAX_LOG_ENTRIES:
            self._logs.pop(0)

        # 更新表格
        self._refresh_log_table()

    def add_status_log(self, message: str) -> None:
        """添加一条状态日志（如错误信息）。"""
        entry = LogEntry(datetime.now(), "[系统]", message)
        self._logs.append(entry)
        while len(self._logs) > MAX_LOG_ENTRIES:
            self._logs.pop(0)
        self._refresh_log_table()

    def _refresh_log_table(self) -> None:
        """刷新日志表格。"""
        self._log_table.setRowCount(0)
        self._log_table.setRowCount(len(self._logs))

        for i, entry in enumerate(self._logs):
            # 时间
            time_item = QTableWidgetItem(
                entry.timestamp.strftime("%H:%M:%S")
            )
            time_item.setTextAlignment(Qt.AlignCenter)
            self._log_table.setItem(i, 0, time_item)

            # 原文
            src_item = QTableWidgetItem(entry.source)
            self._log_table.setItem(i, 1, src_item)

            # 译文
            tgt_item = QTableWidgetItem(entry.translation)
            self._log_table.setItem(i, 2, tgt_item)

        # 滚动到最新
        if self._logs:
            self._log_table.scrollToBottom()

    def _clear_logs(self) -> None:
        """清空日志。"""
        self._logs.clear()
        self._log_table.setRowCount(0)

    # ── 状态更新 ──────────────────────────────────────────

    def set_status(self, text: str) -> None:
        """更新底部状态栏文案。"""
        self._status_label.setText(text)

    @property
    def is_enabled(self) -> bool:
        """翻译开关是否开启。"""
        return self._enabled

    # ── 导出当前配置 ──────────────────────────────────────

    def get_config_dict(self) -> dict:
        """导出当前 UI 中的配置为字典。"""
        return {
            "api_key": self._api_key,
            "model": self._model,
            "hotkey": self._hotkey,
            "bg_color": self._bg_color,
            "text_color": self._text_color,
            "padding": self._padding,
            "min_font_size": self._min_font_size,
            "max_image_side": self._max_image_side,
        }

    # ── 窗口关闭行为 ──────────────────────────────────────

    def closeEvent(self, event) -> None:
        """关闭窗口 = 最小化到托盘（而非退出）。"""
        event.ignore()
        self.hide()
