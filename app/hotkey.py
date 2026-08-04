"""全局热键与 ESC 监听。

热键：Win32 RegisterHotKey → 隐藏 QWidget 接收 WM_HOTKEY → Qt 信号
ESC：  keyboard 库低层钩子
"""

from __future__ import annotations

import ctypes
import logging
from ctypes import wintypes
from typing import Callable, Optional

import keyboard
from PyQt5.QtCore import QByteArray, QTimer, pyqtSignal
from PyQt5.QtWidgets import QWidget

logger = logging.getLogger(__name__)

# ── Win32 常量 ───────────────────────────────────────────

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312

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
}


def _parse_combo(combo: str) -> tuple[int, int]:
    """keyboard 格式组合键 → (Win32 modifiers, virtual key)。"""
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
                raise ValueError(f"多个普通键: {combo}")
            vk = _VK_MAP[part]
        elif len(part) == 1:
            vk = ord(part.upper())
        else:
            raise ValueError(f"无法识别按键: {part}")
    if vk == 0:
        raise ValueError(f"缺少普通键: {combo}")
    if modifiers == MOD_NOREPEAT:
        raise ValueError(f"缺少修饰键(Ctrl/Alt/Shift): {combo}")
    return modifiers, vk


# ── 隐藏的热键接收窗口 ─────────────────────────────────


class _HotkeyWindow(QWidget):
    """不可见的 1x1 窗口，用 Win32 RegisterHotKey 注册到它的 HWND，
    在 nativeEvent 中接收 WM_HOTKEY 并转发为 Qt 信号。"""

    triggered = pyqtSignal()

    def __init__(self, hotkey_id: int = 1) -> None:
        super().__init__()
        self._hotkey_id = hotkey_id
        self._registered = False
        self.setFixedSize(1, 1)  # 不可见但必须存在

    def register_hotkey(self, mods: int, vk: int) -> bool:
        """注册全局热键到本窗口句柄。"""
        self.unregister_hotkey()
        hwnd = int(self.winId())
        user32 = ctypes.windll.user32
        result = user32.RegisterHotKey(hwnd, self._hotkey_id, mods, vk)
        if result:
            self._registered = True
            logger.info("RegisterHotKey 成功: HWND=%d, id=%d, mods=0x%x, vk=0x%x", hwnd, self._hotkey_id, mods, vk)
            return True
        else:
            err = ctypes.get_last_error()
            logger.error("RegisterHotKey 失败: HWND=%d, 错误码=%d", hwnd, err)
            return False

    def unregister_hotkey(self) -> None:
        """注销热键。"""
        if self._registered:
            ctypes.windll.user32.UnregisterHotKey(None, self._hotkey_id)
            self._registered = False

    def nativeEvent(self, event_type: QByteArray, message: int) -> tuple:
        """接收 Windows 原生消息。"""
        msg = ctypes.cast(
            ctypes.c_void_p(int(message)),
            ctypes.POINTER(wintypes.MSG),
        )
        if msg.contents.message == WM_HOTKEY:
            if msg.contents.wParam == self._hotkey_id:
                logger.debug("WM_HOTKEY 收到，触发回调")
                self.triggered.emit()
                return True, 0
        return False, 0


# ── 公开类 ───────────────────────────────────────────────


class GlobalHotkey:
    """全局热键管理器。

    主热键 → Win32 RegisterHotKey（隐藏窗口接收 WM_HOTKEY）
    ESC    → keyboard 库全局钩子
    """

    def __init__(self, on_trigger: Callable[[], None], on_esc: Callable[[], None]) -> None:
        self._on_trigger = on_trigger
        self._on_esc_fn = on_esc
        self._current_combo: Optional[str] = None
        self._hotkey_win: Optional[_HotkeyWindow] = None

    def register(self, combo: str) -> tuple[bool, str]:
        """注册全局热键和 ESC 监听。"""
        self.unregister()

        self._current_combo = combo

        # 解析组合键
        try:
            mods, vk = _parse_combo(combo)
        except ValueError as e:
            return False, str(e)

        # 创建隐藏窗口并注册热键
        self._hotkey_win = _HotkeyWindow()
        self._hotkey_win.triggered.connect(self._on_trigger)
        self._hotkey_win.show()  # 必须 show 才能获得有效的 winId

        if not self._hotkey_win.register_hotkey(mods, vk):
            err = ctypes.get_last_error()
            self.unregister()
            if err == 1409:
                return False, f"热键 {combo} 已被其他程序占用"
            return False, f"热键 {combo} 注册失败 (错误码: {err})"

        # ESC 用 keyboard
        try:
            safe_esc = self._qt_safe(self._on_esc_fn)
            keyboard.add_hotkey("esc", safe_esc, suppress=False)
            logger.info("ESC 监听已启用")
        except Exception as e:
            logger.warning("ESC 注册失败（非致命）: %s", e)

        logger.info("热键就绪: %s", combo)
        return True, ""

    def unregister(self) -> None:
        """移除所有已注册的热键。"""
        if self._hotkey_win:
            self._hotkey_win.unregister_hotkey()
            self._hotkey_win.hide()
            self._hotkey_win.deleteLater()
            self._hotkey_win = None

        try:
            keyboard.unhook_all()
        except Exception:
            pass

        self._current_combo = None

    @staticmethod
    def _qt_safe(fn: Callable[[], None]) -> Callable[[], None]:
        def wrapper(*args, **kwargs) -> None:
            QTimer.singleShot(0, fn)
        return wrapper
