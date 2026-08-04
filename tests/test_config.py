"""配置模块单元测试。"""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

from app.config import ConfigManager, AppConfig, OverlayStyle


class TestConfigManager:
    """ConfigManager 测试套件。"""

    def test_default_on_missing_file(self) -> None:
        """文件不存在时返回默认配置。"""
        mgr = ConfigManager("/nonexistent/path/config.json")
        cfg = mgr.load()
        assert isinstance(cfg, AppConfig)
        assert cfg.api_key == ""
        assert cfg.model == "qwen-vl-plus"
        assert cfg.hotkey == "ctrl+alt+t"
        assert cfg.max_image_side == 2048

    def test_default_on_empty_file(self) -> None:
        """空文件返回默认配置。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as f:
            f.write("")
            tmp_path = f.name
        try:
            mgr = ConfigManager(tmp_path)
            cfg = mgr.load()
            assert isinstance(cfg, AppConfig)
        finally:
            os.unlink(tmp_path)

    def test_default_on_corrupt_json(self) -> None:
        """损坏 JSON 返回默认配置。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            f.write("{invalid json")
            tmp_path = f.name
        try:
            mgr = ConfigManager(tmp_path)
            cfg = mgr.load()
            assert isinstance(cfg, AppConfig)
        finally:
            os.unlink(tmp_path)

    def test_load_partial_fields(self) -> None:
        """部分字段缺失时使用默认值。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            json.dump({"api_key": "sk-test", "model": "qwen-vl-max"}, f)
            tmp_path = f.name
        try:
            mgr = ConfigManager(tmp_path)
            cfg = mgr.load()
            assert cfg.api_key == "sk-test"
            assert cfg.model == "qwen-vl-max"
            # 未设置的字段使用默认值
            assert cfg.hotkey == "ctrl+alt+t"
            assert cfg.overlay.bg_color == "#FFFFFF"
        finally:
            os.unlink(tmp_path)

    def test_save_and_load_roundtrip(self) -> None:
        """保存后再加载，数据一致。"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False, encoding="utf-8"
        ) as f:
            tmp_path = f.name
        try:
            mgr = ConfigManager(tmp_path)
            cfg = AppConfig()
            cfg.api_key = "sk-roundtrip"
            cfg.model = "qwen-vl-plus"
            cfg.hotkey = "ctrl+shift+x"
            cfg.max_image_side = 1024
            cfg.overlay.bg_color = "#FF0000"
            cfg.overlay.text_color = "#00FF00"
            cfg.overlay.padding = 8
            cfg.overlay.min_font_size = 12

            mgr.save(cfg)

            # 重新加载
            loaded = mgr.load()
            assert loaded.api_key == "sk-roundtrip"
            assert loaded.model == "qwen-vl-plus"
            assert loaded.hotkey == "ctrl+shift+x"
            assert loaded.max_image_side == 1024
            assert loaded.overlay.bg_color == "#FF0000"
            assert loaded.overlay.text_color == "#00FF00"
            assert loaded.overlay.padding == 8
            assert loaded.overlay.min_font_size == 12
        finally:
            os.unlink(tmp_path)

    def test_overlay_style_defaults(self) -> None:
        """OverlayStyle 默认值正确。"""
        ov = OverlayStyle()
        assert ov.bg_color == "#FFFFFF"
        assert ov.text_color == "#000000"
        assert ov.padding == 4
        assert ov.min_font_size == 9
