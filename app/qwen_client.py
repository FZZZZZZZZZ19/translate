"""千问视觉客户端 —— 识别+翻译+坐标一条龙（v1.1 核心模块）。

一次 API 调用完成：英文识别 → 中文翻译 → 文本包围盒坐标。
基于千问 DashScope OpenAI 兼容端点，使用 requests 直连。

坐标换算链（顺序不可错）：
    屏幕绝对物理坐标 = 模型 bbox × scale + (offset_x, offset_y)
"""

from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass
from typing import Any, List, Optional

import requests
from PyQt5.QtGui import QImage

from .config import AppConfig
from .screen import ScreenMapper

logger = logging.getLogger(__name__)

# ── 结构化 Prompt 模板 ───────────────────────────────────

SYSTEM_PROMPT = "你是屏幕文本识别与翻译引擎。严格按照用户要求输出 JSON 格式结果，不输出任何其他内容。"

USER_PROMPT_TEMPLATE = """请识别图片中所有文字行（包括英文和中文），英文行翻译为简体中文，中文行原文保留。
图片尺寸为 {w}x{h} 像素。

严格按以下 json 对象格式输出，不要输出任何其他内容：
{{"lines": [{{"text": "识别原文", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "translation": "中文译文"}}]}}

要求：
1. 逐行输出图片中出现的每一行文字，无论英文还是中文，不要遗漏任何一行。
2. bbox 为每行文字四个角点的像素坐标，顺序为左上、右上、右下、左下；坐标值须在 0~{w} 与 0~{h} 范围内，完整包裹整行文字。
3. 英文行：translation 为完整简体中文翻译，把每一个英文单词都翻译成中文，包括专有名词、产品名、技术术语，不得保留任何英文单词。
4. 中文行：translation 与 text 相同，原样保留，无需修改。
5. 所有 translation 须为纯简体中文。"""


# ── 数据类 ───────────────────────────────────────────────


@dataclass
class VisionLine:
    """千问视觉模型返回的单行识别+翻译结果。

    Attributes:
        text: 识别出的英文原文
        bbox: 四角点坐标（屏幕绝对物理坐标，已换算）
        translation: 中文译文（缺失时用 text 兜底）
    """

    text: str
    bbox: list  # list[list[int]] —— 四角点 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]
    translation: str


class QwenError(Exception):
    """千问 API 错误，带分类 code 和中文 message。

    code 取值：
        auth —— 401/403，Key 无效或无权限
        rate_limit —— 429，请求过于频繁
        timeout —— 请求/读取超时
        network —— 连接失败（DNS/TCP/SSL）
        parse —— 模型返回格式异常（非 JSON / 缺字段）
        bad_response —— 其他 4xx/5xx
    """

    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


# ── 客户端 ───────────────────────────────────────────────


class QwenClient:
    """千问 DashScope 视觉模型客户端。

    Args:
        cfg: 应用配置（api_key, model, api_base, max_image_side）
    """

    def __init__(self, cfg: AppConfig) -> None:
        self._cfg = cfg
        self._session: Optional[requests.Session] = None

    def _get_session(self) -> requests.Session:
        """获取或创建复用 Session。"""
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update({
                "Authorization": f"Bearer {self._cfg.api_key}",
                "Content-Type": "application/json",
            })
        return self._session

    def recognize_and_translate(
        self, image: QImage, offset_x: int, offset_y: int
    ) -> List[VisionLine]:
        """识别+翻译一条龙。

        Args:
            image: 选区裁剪后的 RGB QImage（物理像素）
            offset_x: 选区左上角屏幕物理 X 坐标
            offset_y: 选区左上角屏幕物理 Y 坐标

        Returns:
            VisionLine 列表（bbox 已换算为屏幕绝对物理坐标）。

        Raises:
            QwenError: API 调用或解析失败。
            ValueError: image 为空。
        """
        if image.isNull() or image.width() == 0 or image.height() == 0:
            raise ValueError("输入图片为空")

        # 1. 缩放
        upload_img, scale = ScreenMapper.downscale_image(
            image, self._cfg.max_image_side
        )

        # 2. 编码
        data_uri = ScreenMapper.qimage_to_base64_png(upload_img)

        # 3. 构造请求
        upload_w = upload_img.width()
        upload_h = upload_img.height()
        prompt = USER_PROMPT_TEMPLATE.format(w=upload_w, h=upload_h)

        body = {
            "model": self._cfg.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": data_uri},
                        },
                    ],
                },
            ],
            "temperature": 0.1,
        }

        # 4. 发送请求（带重试）
        session = self._get_session()
        url = f"{self._cfg.api_base.rstrip('/')}/chat/completions"

        raw_lines = self._request_with_retry(session, url, body)

        # 5. 坐标换算
        result: List[VisionLine] = []
        for item in raw_lines:
            bbox_raw = item.get("bbox", [])
            if not isinstance(bbox_raw, list) or len(bbox_raw) != 4:
                continue
            # 换算：模型 bbox × scale + offset
            bbox_screen = []
            for pt in bbox_raw:
                if not isinstance(pt, (list, tuple)) or len(pt) != 2:
                    bbox_screen = None
                    break
                sx = int(round(pt[0] * scale + offset_x))
                sy = int(round(pt[1] * scale + offset_y))
                bbox_screen.append([sx, sy])

            if bbox_screen is None:
                continue

            text = item.get("text", "")
            translation = item.get("translation", "") or text
            if not text:
                continue

            result.append(VisionLine(
                text=str(text),
                bbox=bbox_screen,
                translation=str(translation),
            ))

        logger.info("识别翻译完成: %d 行", len(result))
        return result

    # ── 内部：请求 + 重试 + 解析 ──────────────────────────

    def _request_with_retry(
        self, session: requests.Session, url: str, body: dict
    ) -> list:
        """发送请求，5xx/超时重试 1 次；4xx 不重试。"""
        last_error: Optional[QwenError] = None

        for attempt in range(2):
            try:
                resp = session.post(url, json=body, timeout=(10, 60))
            except requests.exceptions.Timeout:
                last_error = QwenError(
                    "timeout", "AI 服务响应超时，请检查网络后重试"
                )
                if attempt == 0:
                    time.sleep(1)
                continue
            except requests.exceptions.ConnectionError as e:
                raise QwenError(
                    "network", f"网络连接失败，请检查网络: {e}"
                ) from e
            except requests.exceptions.RequestException as e:
                raise QwenError(
                    "network", f"网络请求异常: {e}"
                ) from e

            # HTTP 状态码处理
            code = resp.status_code

            if code == 200:
                logger.info("API 响应成功，长度=%d 字符", len(resp.text))
                logger.debug("原始响应: %s", resp.text[:1000])
                return _parse_response(resp.text)

            if code in (401, 403):
                raise QwenError(
                    "auth", "API Key 无效或无权限，请在设置中检查"
                )
            if code == 429:
                raise QwenError(
                    "rate_limit", "请求过于频繁，请稍后重试"
                )
            if 400 <= code < 500:
                err_msg = _extract_error_message(resp.text)
                raise QwenError(
                    "bad_response",
                    f"服务返回错误 (HTTP {code}): {err_msg}",
                )

            # 5xx：可重试
            last_error = QwenError(
                "bad_response",
                f"服务暂时不可用 (HTTP {code})，正在重试…",
            )
            if attempt == 0:
                time.sleep(1)

        # 重试耗尽
        if last_error:
            raise last_error
        raise QwenError("bad_response", "未知错误")


# ── 响应解析（纯函数，便于单测）──────────────────────────


def _normalize_bbox(bbox) -> list | None:
    """将各种 bbox 格式统一转为 4 角点格式 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]。

    支持的输入格式：
    - [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]  四角点（直接返回）
    - [x1, y1, x2, y2]                  矩形两角 → 展开为四角
    - [[x1, y1, x2, y2]]                单元素嵌套 → 展开
    - [[x1,y1],[x2,y2]]                 两点（左上+右下）→ 展开

    Returns:
        四角点列表，或 None（无法解析）。
    """
    if not isinstance(bbox, list) or len(bbox) == 0:
        return None

    # 展平一层嵌套（处理 [[x1,y1,x2,y2]] 这种）
    flat = bbox
    if len(bbox) == 1 and isinstance(bbox[0], list):
        flat = bbox[0]

    # 情况 A：四个两元素点 [[x,y],[x,y],[x,y],[x,y]]
    if (len(flat) == 4
            and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in flat)
            and all(isinstance(v, (int, float)) for p in flat for v in p)):
        return [[float(p[0]), float(p[1])] for p in flat]

    # 情况 B：两个两元素点 [[x1,y1],[x2,y2]] → 左上 + 右下，展开为四角
    if (len(flat) == 2
            and all(isinstance(p, (list, tuple)) and len(p) == 2 for p in flat)
            and all(isinstance(v, (int, float)) for p in flat for v in p)):
        x1, y1 = float(flat[0][0]), float(flat[0][1])
        x2, y2 = float(flat[1][0]), float(flat[1][1])
        # 确保 x1≤x2, y1≤y2
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        if x2 <= x1 or y2 <= y1:
            return None  # 零宽度或零高度，丢弃
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

    # 情况 C：矩形四值 [x1, y1, x2, y2]（左上、右下）
    if (len(flat) == 4
            and all(isinstance(v, (int, float)) for v in flat)):
        x1, y1, x2, y2 = float(flat[0]), float(flat[1]), float(flat[2]), float(flat[3])
        if x1 > x2:
            x1, x2 = x2, x1
        if y1 > y2:
            y1, y2 = y2, y1
        if x2 <= x1 or y2 <= y1:
            return None  # 零宽度或零高度，丢弃
        return [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

    return None


def _parse_response(response_text: str) -> list:
    """解析千问 API 响应，提取 JSON 行数组。

    解析策略（按优先级）：
    1. 提取 chat/completions 格式的 choices[0].message.content
    2. 剥离 markdown 代码块
    3. 尝试 json.loads 整个内容 → 若是对象则提取 "lines" 或第一个数组值
    4. 若失败则定位 [ ... ] 截取数组
    5. 字段校验（宽松模式：缺字段兜底，不因单行格式问题丢弃全部）
    """
    # ── 1. 从 chat/completions 提取 content ──
    content_text = response_text
    try:
        outer = json.loads(response_text)
        if isinstance(outer, dict):
            choices = outer.get("choices", [])
            if choices and isinstance(choices, list):
                msg = choices[0].get("message", {})
                if isinstance(msg, dict):
                    content_text = msg.get("content", response_text)
    except json.JSONDecodeError:
        pass

    # ── 2. 剥离 markdown 代码块 ──
    cleaned = str(content_text).strip()
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r'\n?\s*```$', '', cleaned)

    # ── 3. 尝试解析整个内容为 JSON ──
    data = None
    parse_error = None
    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as e:
        parse_error = e

    # 若整体解析成功且为对象，提取 lines 数组
    if isinstance(data, dict):
        # 优先 "lines" 键
        if "lines" in data and isinstance(data["lines"], list):
            data = data["lines"]
        else:
            # 取第一个值是数组的键
            found = False
            for v in data.values():
                if isinstance(v, list):
                    data = v
                    found = True
                    break
            if not found:
                raise QwenError("parse", f"模型返回的 JSON 对象中未找到行数组。原始内容: {cleaned[:300]}")
    elif isinstance(data, list):
        pass  # 直接就是数组，OK
    else:
        # 整体解析失败 → 尝试 [ ... ] 截取
        start = cleaned.find('[')
        end = cleaned.rfind(']')
        if start == -1 or end == -1 or start >= end:
            raise QwenError(
                "parse",
                f"模型返回格式异常：未找到 JSON 数组。原始内容: {cleaned[:300]}"
            )
        try:
            data = json.loads(cleaned[start:end + 1])
        except json.JSONDecodeError as e:
            raise QwenError(
                "parse",
                f"模型返回 JSON 解析失败: {e}。原始内容: {cleaned[:300]}"
            ) from e

    if not isinstance(data, list):
        raise QwenError("parse", f"解析结果不是数组: {type(data)}。原始内容: {cleaned[:300]}")

    # ── 4. 字段校验（宽松，缺字段兜底）──
    validated = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = item.get("text", "") or ""
        bbox = item.get("bbox", []) or []
        translation = item.get("translation", "") or ""

        # text 必须非空
        if not text or not isinstance(text, str) or not text.strip():
            continue

        # bbox 校验（自动适配矩形/四角等多种格式）
        normalized_bbox = _normalize_bbox(bbox)
        if normalized_bbox is None:
            continue

        # translation 缺失 → 用 text
        if not translation or not isinstance(translation, str) or not translation.strip():
            translation = text

        validated.append({
            "text": str(text).strip(),
            "bbox": normalized_bbox,
            "translation": str(translation).strip(),
        })

    if not validated:
        raise QwenError(
            "parse",
            f"模型返回 {len(data)} 行，但全部未通过字段校验（需 text 非空 + bbox 为 4 点坐标）。"
            f"首条原文: {str(data[0])[:200] if data else '空'}"
        )

    return validated


def _extract_error_message(response_text: str) -> str:
    """从错误响应中提取可读消息。"""
    try:
        err = json.loads(response_text)
        if isinstance(err, dict):
            return err.get("error", {}).get("message", response_text[:200])
    except (json.JSONDecodeError, AttributeError):
        pass
    return response_text[:200]
