"""热键解析单元测试 —— Win32 combo 字符串转 modifiers+vk。"""

from __future__ import annotations

import pytest

from app.hotkey import _parse_combo


class TestParseCombo:
    """组合键解析测试。"""

    def test_ctrl_alt_t(self) -> None:
        """标准组合键 ctrl+alt+t。"""
        mods, vk = _parse_combo("ctrl+alt+t")
        # MOD_NOREPEAT | MOD_CONTROL | MOD_ALT = 0x4003
        assert mods & 0x0002  # MOD_CONTROL
        assert mods & 0x0001  # MOD_ALT
        assert mods & 0x4000  # MOD_NOREPEAT
        assert vk == 0x54  # 'T'

    def test_ctrl_shift_x(self) -> None:
        """ctrl+shift+x。"""
        mods, vk = _parse_combo("ctrl+shift+x")
        assert mods & 0x0002  # MOD_CONTROL
        assert mods & 0x0004  # MOD_SHIFT
        assert vk == 0x58  # 'X'

    def test_win_key(self) -> None:
        """带 Windows 键的组合。"""
        mods, vk = _parse_combo("win+f1")
        assert mods & 0x0008  # MOD_WIN
        assert vk == 0x70  # F1

    def test_function_keys(self) -> None:
        """F 功能键。"""
        mods, vk = _parse_combo("ctrl+f12")
        assert vk == 0x7B

    def test_case_insensitive(self) -> None:
        """大小写不敏感。"""
        mods1, vk1 = _parse_combo("CTRL+ALT+T")
        mods2, vk2 = _parse_combo("ctrl+alt+t")
        assert vk1 == vk2
        assert mods1 == mods2

    def test_spaces_in_combo(self) -> None:
        """组合键中的空格被正确处理。"""
        mods, vk = _parse_combo("ctrl + alt + t")
        assert mods & 0x0002
        assert mods & 0x0001
        assert vk == 0x54

    def test_no_modifier_raises(self) -> None:
        """缺少修饰键抛出异常。"""
        with pytest.raises(ValueError, match="缺少修饰键"):
            _parse_combo("t")

    def test_no_normal_key_raises(self) -> None:
        """缺少普通键抛出异常。"""
        with pytest.raises(ValueError, match="缺少普通键"):
            _parse_combo("ctrl+alt")

    def test_unknown_key_raises(self) -> None:
        """无法识别的按键抛出异常。"""
        with pytest.raises(ValueError, match="无法识别"):
            _parse_combo("ctrl+alt+unknown")
