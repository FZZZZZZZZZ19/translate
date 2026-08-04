"""全局热键与 ESC 监听。

双引擎策略：
- 触发热键：Win32 RegisterHotKey API（可靠，无需管理员权限，不会与其他程序冲突）
- ESC 监听：keyboard 库低层钩子（覆盖层显示期间监听）

所有回调通过 QTimer.singleShot 切回 Qt 主线程。
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from typing import Callable, Optional

import keyboard
from PyQt5.QtCore import QAbstractNativeEventFilter, QByteArray, QObject, QTimer, pyqtSignal

logger = logging.getLogger(__name__)

# ── Win32 常量 ───────────────────────────────────────────

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

# 虚拟键码映射（keyboard 库格式 → Win32 VK）
_VK_MAP = {
    "a": 0x41, "b": 0x42, "c": 0x43, "d": 0x44, "e": 0x45,
    "f": 0x46, "g": 0x47, "h": 0x48, "i": 0x49, "j": 0x4A,
    "k": 0x4B, "l": 0x4C, "m": 0x4D, "n": 0x4E, "o": 0x4F,
    "p": 0x50, "q": 0x51, "r": 0x52, "s": 0x53, "t": 0x54,
    "u": 0x55, "v": 0x56, "w": 0x57, "x": 0x58, "y": 0x59,
    "z": 0x5A,
    "0": 0x30, "1": 0x31, "2": 0x32, "3": 0x33, "4": 0x34,
    "5": 0x35, "6": 0x36, "7": 0x37, "8": 0x38, "9": 0x39,
    "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73,
    "f5": 0x74, "f6": 0x75, "f7": 0x76, "f8": 0x77,
    "f9": 0x78, "f10": 0x79, "f11": 0x7A, "f12": 0x7B,
    "space": 0x20, "tab": 0x09, "enter": 0x0D,
    "backspace": 0x08, "delete": 0x2E, "insert": 0x2D,
    "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
    "up": 0x26, "down": 0x28, "left": 0x25, "right": 0x27,
    "escape": 0x1B, "esc": 0x1B,
    "printscreen": 0x2C, "scrolllock": 0x91, "pause": 0x13,
    "num0": 0x60, "num1": 0x61, "num2": 0x62, "num3": 0x63,
    "num4": 0x64, "num5": 0x65, "num6": 0x66, "num7": 0x67,
    "num8": 0x68, "num9": 0x69,
}


def _parse_combo(combo: str) -> tuple[int, int]:
    """将 keyboard 格式组合键解析为 Win32 modifiers + vk。

    Args:
        combo: 如 "ctrl+alt+t"、"ctrl+shift+x"

    Returns:
        (modifiers, virtual_key)

    Raises:
        ValueError: 无法解析的组合键
    """
    parts = [p.strip().lower() for p in combo.split("+")]

    modifiers = MOD_NOREPEAT
    vk = 0

    for part in parts:
        if part in ("ctrl", "control"):
            modifiers |= MOD_CONTROL
        elif part in ("alt",):
            modifiers |= MOD_ALT
        elif part in ("shift",):
            modifiers |= MOD_SHIFT
        elif part in ("win", "windows", "cmd"):
            modifiers |= MOD_WIN
        elif part in _VK_MAP:
            if vk != 0:
                raise ValueError(f"组合键含多个普通键: {combo}")
            vk = _VK_MAP[part]
        elif len(part) == 1:
            # 单字符直接用 ascii 大写的 VK
            vk = ord(part.upper())
        else:
            raise ValueError(f"无法识别的按键: {part}")

    if vk == 0:
        raise ValueError(f"组合键缺少普通键: {combo}")
    if modifiers == MOD_NOREPEAT:
        raise ValueError(f"组合键缺少修饰键(Ctrl/Alt/Shift): {combo}")

    return modifiers, vk


# ── Win32 原生热键过滤器 ─────────────────────────────────


class _HotkeyFilter(QAbstractNativeEventFilter):
    """拦截 WM_HOTKEY 消息并触发 Qt 信号。"""

    triggered = pyqtSignal()

    def nativeEventFilter(
        self, event_type: QByteArray, message: int
    ) -> tuple[bool, int]:
        # message 是一个指向 MSG 结构体的指针
        msg = ctypes.cast(
            ctypes.c_void_p(int(message)),
            ctypes.POINTER(wintypes.MSG),
        )
        if msg.contents.message == WM_HOTKEY:
            self.triggered.emit()
            return True, 0
        return False, 0


# ── 公开类 ───────────────────────────────────────────────


class GlobalHotkey(QObject):
    """全局热键管理器。

    主热键使用 Win32 RegisterHotKey（可靠、无需管理员权限），
    ESC 使用 keyboard 低层钩子。

    Args:
        on_trigger: 热键触发回调（已在主线程安全调用）
        on_esc: ESC 按下回调（已在主线程安全调用）
    """

    def __init__(self, on_trigger: Callable[[], None], on_esc: Callable[[], None]) -> None:
        super().__init__()
        self._on_trigger = on_trigger
        self._on_esc_fn = on_esc
        self._current_combo: Optional[str] = None
        self._hotkey_id = 1  # Win32 RegisterHotKey 的 ID
        self._registered = False
        self._filter: Optional[_HotkeyFilter] = None

    @staticmethod
    def _qt_safe(fn: Callable[[], None]) -> Callable[[], None]:
        """通过 QTimer.singleShot 切回 Qt 主线程。"""

        def wrapper(*args, **kwargs) -> None:
            QTimer.singleShot(0, fn)

        return wrapper

    def register(self, combo: str) -> tuple[bool, str]:
        """注册全局热键（Win32 RegisterHotKey）和 ESC 监听。

        Args:
            combo: keyboard 库格式热键，如 "ctrl+alt+t"。

        Returns:
            (是否成功, 错误信息)。
        """
        self.unregister()

        self._current_combo = combo

        # ── Win32 RegisterHotKey（主热键）──
        try:
            mods, vk = _parse_combo(combo)
        except ValueError as e:
            return False, str(e)

        # 安装原生事件过滤器
        from PyQt5.QtWidgets import QApplication

        app = QApplication.instance()
        if app is None:
            return False, "QApplication 未初始化"

        self._filter = _HotkeyFilter()
        self._filter.triggered.connect(self._on_trigger)
        app.installNativeEventFilter(self._filter)

        user32 = ctypes.windll.user32
        result = user32.RegisterHotKey(None, self._hotkey_id, mods, vk)
        if result == 0:
            self.unregister()
            err = ctypes.get_last_error()
            return False, f"热键 {combo} 注册失败 (错误码 {err})，可能被其他程序占用"

        self._registered = True
        logger.info("Win32 热键已注册: %s (mods=0x%x, vk=0x%x)", combo, mods, vk)

        # ── keyboard ESC 监听 ──
        try:
            safe_esc = self._qt_safe(self._on_esc_fn)
            keyboard.add_hotkey("esc", safe_esc, suppress=False)
            logger.info("ESC 监听已启用")
        except Exception as e:
            logger.warning("ESC 监听注册失败（非致命）: %s", e)

        return True, ""

    def unregister(self) -> None:
        """移除所有热键钩子。"""
        # 注销 Win32 热键
        if self._registered:
            user32 = ctypes.windll.user32
            user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False

        # 移除原生事件过滤器
        if self._filter is not None:
            from PyQt5.QtWidgets import QApplication

            app = QApplication.instance()
            if app is not None:
                app.removeNativeEventFilter(self._filter)
            self._filter = None

        # 注销 keyboard 钩子
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        self._current_combo = None
        logger.info("热键已全部注销")
