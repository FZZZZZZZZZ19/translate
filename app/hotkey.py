"""全局热键与 ESC 监听 —— 基于 keyboard 库。

keyboard 回调运行在独立钩子线程，必须通过 QTimer.singleShot 切回主线程
才能操作 Qt 对象。
"""

from __future__ import annotations

import logging
from typing import Callable, Optional

import keyboard
from PyQt5.QtCore import QTimer

logger = logging.getLogger(__name__)


class GlobalHotkey:
    """管理全局热键注册/注销，以及 ESC 监听。

    Args:
        on_trigger: 热键触发回调（已在主线程安全调用）
        on_esc: ESC 按下回调（已在主线程安全调用）
    """

    def __init__(self, on_trigger: Callable[[], None], on_esc: Callable[[], None]) -> None:
        self._on_trigger = on_trigger
        self._on_esc = on_esc
        self._current_combo: Optional[str] = None
        self._trigger_hook_id: Optional[int] = None
        self._esc_hook_id: Optional[int] = None

    @staticmethod
    def _qt_safe(fn: Callable[[], None]) -> Callable[[], None]:
        """包装回调：通过 QTimer.singleShot(0, fn) 切回 Qt 主线程。"""

        def wrapper(*args, **kwargs) -> None:
            QTimer.singleShot(0, fn)

        return wrapper

    def register(self, combo: str) -> tuple[bool, str]:
        """注册全局热键和 ESC 监听。

        Args:
            combo: keyboard 库格式热键，如 "ctrl+alt+t"。

        Returns:
            (是否成功, 错误信息)。成功时错误信息为空字符串。
        """
        # 先清理旧的
        self.unregister()

        self._current_combo = combo

        try:
            # 注册触发热键
            safe_trigger = self._qt_safe(self._on_trigger)
            self._trigger_hook_id = keyboard.add_hotkey(combo, safe_trigger, suppress=False)

            # 注册 ESC 监听
            safe_esc = self._qt_safe(self._on_esc)
            self._esc_hook_id = keyboard.add_hotkey("esc", safe_esc, suppress=False)

            logger.info("热键已注册: 触发=%s, ESC 监听已启用", combo)
            return True, ""
        except ValueError as e:
            self.unregister()
            return False, f"热键注册失败，可能与其他程序冲突: {e}"
        except Exception as e:
            self.unregister()
            logger.error("热键注册异常: %s", e)
            return False, f"热键注册失败: {e}"

    def unregister(self) -> None:
        """移除所有已注册的 keyboard 钩子。"""
        try:
            keyboard.unhook_all()
        except Exception:
            pass

        self._trigger_hook_id = None
        self._esc_hook_id = None
        self._current_combo = None
        logger.info("热键已全部注销")
