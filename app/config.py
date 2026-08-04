"""配置读写 —— 持久化用户设置到本地 JSON 文件。

配置路径：%APPDATA%/ScreenCaptureOCR/config.json
打包后优先使用 exe 同目录下的 config.json（若存在）。
"""

from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


def get_config_path() -> str:
    """返回配置文件路径。

    优先级：
    1. 可执行文件同目录下的 config.json（便携模式）
    2. %APPDATA%/ScreenCaptureOCR/config.json（标准路径）
    """
    # 便携模式：exe/脚本同目录
    import sys

    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).parent
    else:
        exe_dir = Path(__file__).resolve().parent.parent
    portable = exe_dir / "config.json"
    if portable.exists():
        return str(portable)

    # 标准路径
    appdata = os.environ.get("APPDATA", os.path.expanduser("~"))
    cfg_dir = Path(appdata) / "ScreenCaptureOCR"
    cfg_dir.mkdir(parents=True, exist_ok=True)
    return str(cfg_dir / "config.json")


@dataclass
class OverlayStyle:
    """覆盖层样式配置。"""

    bg_color: str = "#FFFFFF"  # 背景块底色
    text_color: str = "#000000"  # 译文文字颜色
    padding: int = 4  # 背景块内边距 px
    min_font_size: int = 9  # 最小字号 pt


@dataclass
class AppConfig:
    """应用全局配置。"""

    api_key: str = ""
    model: str = "qwen-vl-plus"  # qwen-vl-plus / qwen-vl-max / qwen2.5-vl-72b-instruct 等
    hotkey: str = "ctrl+alt+t"  # keyboard 库格式
    overlay: OverlayStyle = field(default_factory=OverlayStyle)
    max_image_side: int = 2048  # 上传图片最长边上限 px
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"


class ConfigManager:
    """配置管理器：读写 JSON、损坏容错、原子写。"""

    def __init__(self, path: Optional[str] = None) -> None:
        """初始化配置管理器。

        Args:
            path: 配置文件路径；为 None 时自动推导。
        """
        self._path = path or get_config_path()

    @property
    def path(self) -> str:
        """返回当前配置文件路径。"""
        return self._path

    def load(self) -> AppConfig:
        """从文件加载配置；文件不存在/损坏/缺字段时返回默认值，不抛异常。"""
        if not os.path.exists(self._path):
            return AppConfig()

        try:
            with open(self._path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            return AppConfig()

        cfg = AppConfig()
        if not isinstance(data, dict):
            return cfg

        # 顶层字段
        for key in ("api_key", "model", "hotkey", "api_base"):
            if key in data and isinstance(data[key], str):
                setattr(cfg, key, data[key])
        if "max_image_side" in data and isinstance(data["max_image_side"], int):
            cfg.max_image_side = data["max_image_side"]

        # 嵌套 OverlayStyle
        overlay_data = data.get("overlay", {})
        if isinstance(overlay_data, dict):
            ov = cfg.overlay
            if "bg_color" in overlay_data and isinstance(overlay_data["bg_color"], str):
                ov.bg_color = overlay_data["bg_color"]
            if "text_color" in overlay_data and isinstance(overlay_data["text_color"], str):
                ov.text_color = overlay_data["text_color"]
            if "padding" in overlay_data and isinstance(overlay_data["padding"], int):
                ov.padding = overlay_data["padding"]
            if "min_font_size" in overlay_data and isinstance(overlay_data["min_font_size"], int):
                ov.min_font_size = overlay_data["min_font_size"]

        return cfg

    def save(self, cfg: AppConfig) -> None:
        """原子写入：先写临时文件，再 rename 到目标路径。"""
        cfg_dir = os.path.dirname(self._path)
        os.makedirs(cfg_dir, exist_ok=True)

        data = {
            "api_key": cfg.api_key,
            "model": cfg.model,
            "hotkey": cfg.hotkey,
            "api_base": cfg.api_base,
            "max_image_side": cfg.max_image_side,
            "overlay": {
                "bg_color": cfg.overlay.bg_color,
                "text_color": cfg.overlay.text_color,
                "padding": cfg.overlay.padding,
                "min_font_size": cfg.overlay.min_font_size,
            },
        }

        # 原子写：写 .tmp 再 rename
        fd, tmp_path = tempfile.mkstemp(
            suffix=".tmp", prefix="config_", dir=cfg_dir
        )
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, self._path)
        except Exception:
            # 清理临时文件
            if os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            raise
