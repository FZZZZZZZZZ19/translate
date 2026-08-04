"""千问客户端单元测试 —— 响应解析、错误分类（纯函数，无需网络）。"""

from __future__ import annotations

import json

import pytest

from app.qwen_client import (
    QwenError,
    _extract_error_message,
    _parse_response,
)


class TestParseResponse:
    """响应解析测试。"""

    # ── 正常解析 ──────────────────────────────────────

    def test_parse_standard_chat_response(self) -> None:
        """标准 chat/completions 格式，含 choices[0].message.content。"""
        lines = [
            {
                "text": "Hello World",
                "bbox": [[10, 20], [100, 20], [100, 40], [10, 40]],
                "translation": "你好世界",
            },
            {
                "text": "Goodbye",
                "bbox": [[10, 50], [80, 50], [80, 70], [10, 70]],
                "translation": "再见",
            },
        ]
        resp = {
            "choices": [
                {"message": {"content": json.dumps(lines, ensure_ascii=False)}}
            ]
        }
        result = _parse_response(json.dumps(resp))
        assert len(result) == 2
        assert result[0]["text"] == "Hello World"
        assert result[0]["translation"] == "你好世界"

    def test_parse_raw_json_array(self) -> None:
        """直接返回 JSON 数组（无外层 chat 包装）。"""
        lines = [
            {
                "text": "Settings",
                "bbox": [[5, 5], [60, 5], [60, 25], [5, 25]],
                "translation": "设置",
            }
        ]
        result = _parse_response(json.dumps(lines))
        assert len(result) == 1
        assert result[0]["text"] == "Settings"

    def test_parse_markdown_wrapped_json(self) -> None:
        """模型返回 markdown 代码块包裹的 JSON。"""
        lines = [
            {
                "text": "File",
                "bbox": [[0, 0], [30, 0], [30, 20], [0, 20]],
                "translation": "文件",
            }
        ]
        raw = "```json\n" + json.dumps(lines) + "\n```"
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0]["text"] == "File"

    def test_parse_json_object_with_array_value(self) -> None:
        """模型返回 {"items": [...]} 格式。"""
        lines = [
            {
                "text": "Open",
                "bbox": [[0, 0], [40, 0], [40, 20], [0, 20]],
                "translation": "打开",
            }
        ]
        raw = json.dumps({"items": lines})
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0]["text"] == "Open"

    # ── 缺失字段兜底 ──────────────────────────────────

    def test_missing_translation_uses_text(self) -> None:
        """translation 缺失时用 text 兜底。"""
        lines = [{"text": "OK", "bbox": [[0, 0], [20, 0], [20, 20], [0, 20]]}]
        raw = json.dumps(lines)
        result = _parse_response(raw)
        assert result[0]["translation"] == "OK"

    def test_empty_translation_uses_text(self) -> None:
        """translation 为空字符串时用 text 兜底。"""
        lines = [
            {
                "text": "Cancel",
                "bbox": [[0, 0], [50, 0], [50, 20], [0, 20]],
                "translation": "",
            }
        ]
        raw = json.dumps(lines)
        result = _parse_response(raw)
        assert result[0]["translation"] == "Cancel"

    def test_missing_text_skipped(self) -> None:
        """text 缺失的行被跳过。"""
        lines = [
            {"bbox": [[0, 0], [20, 0], [20, 20], [0, 20]], "translation": "?"},
            {
                "text": "Valid",
                "bbox": [[0, 30], [40, 30], [40, 50], [0, 50]],
                "translation": "有效",
            },
        ]
        raw = json.dumps(lines)
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0]["text"] == "Valid"

    def test_invalid_bbox_skipped(self) -> None:
        """bbox 格式异常的行被跳过。"""
        lines = [
            {
                "text": "Bad bbox",
                "bbox": [[0, 0], [20, 0]],  # 只有 2 点
                "translation": "坏",
            },
            {
                "text": "Good",
                "bbox": [[0, 30], [40, 30], [40, 50], [0, 50]],
                "translation": "好",
            },
        ]
        raw = json.dumps(lines)
        result = _parse_response(raw)
        assert len(result) == 1
        assert result[0]["text"] == "Good"

    # ── 异常路径 ──────────────────────────────────────

    def test_parse_empty_string_raises(self) -> None:
        """空字符串抛出 parse 错误。"""
        with pytest.raises(QwenError, match="未找到 JSON 数组"):
            _parse_response("")

    def test_parse_no_array_raises(self) -> None:
        """无 JSON 数组抛出 parse 错误。"""
        with pytest.raises(QwenError, match="未找到 JSON 数组"):
            _parse_response('{"result": "no array here"}')

    def test_parse_invalid_json_raises(self) -> None:
        """无效 JSON 抛出 parse 错误。"""
        with pytest.raises(QwenError, match="JSON 解析失败"):
            _parse_response("[invalid json content that is not valid JSON]")

    def test_parse_empty_array_raises(self) -> None:
        """空数组抛出 parse 错误（没有有效行）。"""
        with pytest.raises(QwenError, match="无有效行"):
            _parse_response("[]")


class TestExtractErrorMessage:
    """错误消息提取测试。"""

    def test_extract_from_openai_format(self) -> None:
        """OpenAI 兼容格式的 error.message。"""
        err = {"error": {"message": "Invalid API Key"}}
        msg = _extract_error_message(json.dumps(err))
        assert "Invalid API Key" in msg

    def test_extract_fallback(self) -> None:
        """无法解析时返回原始文本（截断到 200 字符）。"""
        msg = _extract_error_message("plain text error")
        assert "plain text error" in msg
