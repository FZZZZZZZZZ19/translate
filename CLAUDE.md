# CLAUDE.md —— ScreenCaptureOCR Translator 开发交接规格（v1.1）

> 本文件是 Claude Code 开发本项目的**唯一权威技术规格**。开始开发前通读全文；规格不明时优先按本文「备选方案」降级，并将决策记录到 `02-项目开发记录.md`。
> 上级文档：`00-开发规划书.md`（v1.1）、`01-开发计划.md`（v1.1）。
> **v1.1 核心变更：移除 EasyOCR/PyTorch，识别+翻译+坐标全部由千问视觉模型一次调用完成（「一条路服务」），依赖仅 PyQt5/keyboard/requests，打包体积 ≤60MB。**

---

## 1. 项目一句话

Windows 常驻托盘工具：全局快捷键 → 全屏选区（鼠标拖矩形）→ 选区图上传千问视觉模型（qwen-vl 系列，用户自备 Key），**一次调用**返回每行「英文原文 + 包围盒坐标 + 中文译文」→ 译文覆盖层绘制回屏幕原文位置 → 按 ESC 退出；再按快捷键重复。

## 2. 技术栈（固定，不得更换）

| 项 | 值 |
|---|---|
| 语言 | Python 3.11（64 位，独立 venv） |
| GUI | PyQt5（>=5.15.10） |
| AI 识别+翻译 | 千问 DashScope 视觉模型（OpenAI 兼容端点；默认 `qwen-vl-plus`） |
| HTTP | requests（>=2.31，复用 Session） |
| 热键/ESC | keyboard（>=0.13.5） |
| 截屏 | QScreen.grabWindow(0) |
| 图片处理 | **仅 Qt 内置**（QImage 缩放 / QBuffer 编码 PNG→base64） |
| 打包 | PyInstaller onedir + windowed，目标 ≤60MB |
| 测试 | pytest（仅核心纯函数） |

**依赖红线**：运行时依赖仅 `PyQt5 / keyboard / requests`。**严禁**引入 easyocr、torch、torchvision、paddleocr、opencv、Pillow、numpy、scipy 等任何库（体积与复杂度约束）。

## 3. 目录结构（必须遵守）

```
translate/
├── main.py                    # 入口：QApplication、托盘、热键注册、状态机
├── app/
│   ├── __init__.py
│   ├── config.py              # 配置读写
│   ├── hotkey.py              # 全局热键 + ESC 监听
│   ├── screen.py              # 截屏 + 坐标/DPI 换算 + 图片裁剪/缩放/编码（唯一坐标换算点）
│   ├── selection_overlay.py   # 选区遮罩窗口
│   ├── result_overlay.py      # 译文覆盖层窗口
│   ├── qwen_client.py         # 千问客户端：识别+翻译+坐标一条龙（核心模块）
│   ├── pipeline.py            # 流程编排 + QThread worker
│   └── settings_dialog.py     # 设置对话框
├── assets/icon.ico
├── requirements.txt
├── ocr_translator.spec
├── build.bat
├── README.md
└── （文档：00-开发规划书.md / 01-开发计划.md / CLAUDE.md / 02-项目开发记录.md）
```

## 4. 模块规格（逐模块）

### 4.1 `main.py`

```python
def main() -> int
```

- 创建 QApplication **之前**设置：`QApplication.setAttribute(Qt.AA_EnableHighDpiScaling)`、`Qt.AA_UseHighDpiPixmaps`；`QApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)`。
- 创建 `AppController`（pipeline.py）单例：注册热键、托盘、设置窗口。
- 托盘：QSystemTrayIcon（icon.ico 或动态绘制兜底；先检查 `QSystemTrayIcon.isSystemTrayAvailable()`），菜单：**截图翻译**、**设置**、**退出**；双击托盘 = 触发截图翻译。
- `QApplication.setQuitOnLastWindowClosed(False)`；退出时 unregister 全部热键钩子 + join worker 线程，确保无残留。

### 4.2 `app/config.py`

```python
@dataclass
class OverlayStyle:
    bg_color: str = "#FFFFFF"
    text_color: str = "#000000"
    padding: int = 4
    min_font_size: int = 9

@dataclass
class AppConfig:
    api_key: str = ""
    model: str = "qwen-vl-plus"
    hotkey: str = "ctrl+alt+t"
    overlay: OverlayStyle = ...
    max_image_side: int = 2048   # 上传图最长边上限 px
    api_base: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"

class ConfigManager:
    def __init__(self, path: str)   # 默认 %APPDATA%/ScreenCaptureOCR/config.json
    def load(self) -> AppConfig      # 损坏/缺字段→默认值，不抛异常
    def save(self, cfg: AppConfig)   # 原子写（.tmp 再 rename）
```

- API Key 明文存本地 JSON（项目要求），**禁止**写日志、**禁止**硬编码；`config.json` 入 .gitignore。

### 4.3 `app/hotkey.py`

```python
class GlobalHotkey:
    def __init__(self, on_trigger: Callable, on_esc: Callable)
    def register(self, combo: str) -> tuple[bool, str]
    def unregister(self) -> None
```

- `keyboard.add_hotkey(combo, cb)` 注册触发；`keyboard.add_hotkey('esc', cb)` 监听 ESC；suppress=False。
- 回调在钩子线程运行，**必须** `QTimer.singleShot(0, fn)` 切主线程后再碰 Qt 对象。
- 重新注册：先 unregister 再 add，避免叠加。register 失败（键位冲突）返回可读错误。

### 4.4 `app/screen.py`（唯一坐标换算点 + 图片处理）

```python
def grab_fullscreen() -> QPixmap        # primaryScreen().grabWindow(0)，保留 devicePixelRatio
class ScreenMapper:
    def __init__(self)                  # 主屏 geometry + devicePixelRatio
    def logical_to_physical(self, x: int, y: int, w: int, h: int) -> QRect
    def physical_to_logical(self, rect: QRect) -> QRect
    def crop_qimage(self, pm: QPixmap, logical_rect: QRect) -> QImage   # 按物理像素裁剪，返回 RGB QImage
    @staticmethod
    def downscale_image(img: QImage, max_side: int) -> tuple[QImage, float]
        # 最长边 > max_side 时等比缩放（Qt.SmoothTransformation）；返回 (缩放后图, 缩放比=原边长/新边长)
    @staticmethod
    def qimage_to_base64_png(img: QImage) -> str   # QBuffer → PNG → base64；返回 "data:image/png;base64,..."
```

- grabWindow 返回物理像素尺寸；选区窗口坐标为逻辑像素（Qt 自动缩放）。换算只走本模块。
- `crop_qimage`：`pm.toImage()` → `image.copy(物理rect)`。
- `downscale_image`：`img.scaled(w, h, Qt.KeepAspectRatio, Qt.SmoothTransformation)`；`scale = max(orig_w/新w, orig_h/新h)`（等比缩放时两者一致）。
- `qimage_to_base64_png`：`QBuffer` + `image.save(buf, "PNG")` + `base64.b64encode`。**不要引入 Pillow**。
- 多屏：MVP 主屏，代码预留 `screens()` 枚举注释。

### 4.5 `app/selection_overlay.py`

```python
class SelectionOverlay(QWidget):
    selection_done = pyqtSignal(QRect)   # 逻辑坐标（normalized）
    cancelled = pyqtSignal()
    def __init__(self, mapper: ScreenMapper, screenshot: QPixmap)  # 截图底图垫底
    def start(self) -> None              # showFullScreen + 置顶 + 抢焦点 + CrossCursor
    # paintEvent：先 drawPixmap 底图，再盖半透明黑 rgba(0,0,0,120)，选区内不暗 + 白色 2px 边框 + 实时尺寸 + 顶部提示「拖拽选择区域 · ESC 取消」
    # mousePress/Move/Release：QRect(start, cur).normalized()（左上角开拉）；松开 emit selection_done
    # ESC/右键：emit cancelled；单击（移动 <3px）提示无效选区，保持遮罩
```

### 4.6 `app/qwen_client.py`（v1.1 核心模块）

```python
@dataclass
class VisionLine:
    text: str                 # 识别出的英文原文
    bbox: list[list[int]]     # 四角点 [[x1,y1],[x2,y2],[x3,y3],[x4,y4]]，屏幕绝对物理坐标（已换算）
    translation: str          # 中文译文（缺失时=text 兜底）

class QwenError(Exception):
    def __init__(self, code: str, message: str)   # code ∈ {auth, rate_limit, timeout, network, parse, bad_response}

class QwenClient:
    def __init__(self, cfg: AppConfig)
    def recognize_and_translate(self, image: QImage, offset_x: int, offset_y: int) -> list[VisionLine]
```

`recognize_and_translate` 步骤：
1. **缩放**：`screen.downscale_image(image, cfg.max_image_side)` → (upload_img, scale)。
2. **编码**：`screen.qimage_to_base64_png(upload_img)` → data URI。
3. **请求**：`POST {cfg.api_base}/chat/completions`，headers：`Authorization: Bearer <key>`、`Content-Type: application/json`。
   body：
   ```json
   {
     "model": "qwen-vl-plus",
     "messages": [{"role": "system", "content": "你是屏幕文本识别与翻译引擎。"},
                   {"role": "user", "content": [
                       {"type": "text", "text": PROMPT},
                       {"type": "image_url", "image_url": {"url": "data:image/png;base64,..."}}
                   ]}],
     "temperature": 0.1,
     "response_format": {"type": "json_object"}
   }
   ```
   PROMPT（注意必须含「json」字样，response_format 硬性要求）：
   ```
   请识别图片中的所有英文文本行，并将每一行翻译为简体中文。
   图片尺寸为 {w}x{h} 像素（w/h 为上传图尺寸）。
   严格按以下 json 数组格式输出，不要输出任何其他内容：
   [{"text": "英文原文", "bbox": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]], "translation": "中文译文"}]
   要求：
   1. bbox 为每行文字的四个角点像素坐标，顺序：左上、右上、右下、左下；坐标须在 0~{w} 与 0~{h} 范围内，且完整包裹整行文字。
   2. 逐行输出，不要合并或遗漏任何一行。
   3. translation 为简体中文，专业、准确、简洁。
   ```
4. **解析**（parse 纯函数，便于单测）：
   - 剥离 markdown 代码块（去掉开头的 ```json / ``` 与结尾的 ```）；定位首个 `[` 与末个 `]` 截取；`json.loads`。
   - 失败 → 重试 1 次（重新请求）；仍失败 → `QwenError('parse', '模型返回格式异常')`。
   - 每项校验：`text` 非空；`bbox` 为 4 个 [x,y]；坐标非负且在 [0, upload_w]×[0, upload_h] 内；面积 > 0；否则丢弃该行。
   - `translation` 缺失/空 → 用 `text` 兜底。
5. **坐标换算链**（顺序不可错）：`屏幕绝对物理坐标 = 模型bbox × scale + (offset_x, offset_y)`，其中 offset 为选区左上角在**屏幕物理坐标**中的位置（由 pipeline 传入）。
6. **错误分类**：401/403 → `QwenError('auth', 'API Key 无效或无权限，请在设置中检查')`；429 → `('rate_limit', '请求过于频繁，请稍后重试')`；超时 → `('timeout', 'AI 服务响应超时，请检查网络后重试')`；连接错误 → `('network', '网络连接失败，请检查网络')`；其他 4xx/5xx → `('bad_response', f'服务返回错误 HTTP {code}')`。超时与 5xx 重试 1 次（间隔 1s），4xx 不重试。
- 使用 `requests.Session`（连接复用）；`timeout=(10, 60)`。
- 空行输入直接返回 []（不发请求）；**不上传空图**（选区 <3px 在 overlay 层已拦截）。

### 4.7 `app/result_overlay.py`

```python
class OverlayItem:
    physical_rect: QRect   # 屏幕物理坐标包围盒（由 bbox 四角点取外接矩形 + padding 由渲染侧处理）
    text: str              # 中文译文
class ResultOverlay(QWidget):
    def __init__(self, mapper: ScreenMapper)
    def show_translations(self, items: list[OverlayItem]) -> None
    def clear(self) -> None
```

- 窗口属性：`Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.WindowTransparentForInput | Qt.WindowDoesNotAcceptFocus` + `setAttribute(Qt.WA_TranslucentBackground)`；全屏（主屏逻辑几何）。
- `show_translations`：clear → 存 items → update → **全部就绪后一次性 show**（防闪烁）。
- paintEvent：对每个 item：
  1. 背景块：`physical_rect` 经 mapper 转逻辑，`fillRect(rect.adjusted(-padding,-padding,padding,padding), QColor(bg_color))`。
  2. 译文：`_fit_font(text, max_w, max_h)` 从 16pt 起递减：中文按字符折行（`Qt.TextWordWrap` 中文默认按字符）、英文按词；`QFontMetrics.boundingRect` 测量高度；超限则字号 -1，至 min_font_size 仍放不下则截断加省略号。
  3. 绘制：`Qt.AlignHCenter | Qt.AlignVCenter | Qt.TextWordWrap`、`QPainter.TextAntialiasing`、text_color。
- ESC 由 hotkey 全局监听触发 `clear()` + `hide()`；覆盖层本身不拦截鼠标。

### 4.8 `app/pipeline.py`

```python
class AppController(QObject):
    status_message = pyqtSignal(str)
    def __init__(self, cfg: ConfigManager, mapper: ScreenMapper)
    def start_screen_flow(self) -> None    # 仅 IDLE 响应，防重入
    # 状态：IDLE → SELECTING → RECOGNIZING → OVERLAYING → IDLE

class PipelineWorker(QThread):
    done = pyqtSignal(list)      # list[OverlayItem]
    failed = pyqtSignal(str)     # 中文错误信息
    def run(self) -> None        # qwen_client.recognize_and_translate(cropped_qimage, offset_x, offset_y) → 构造 OverlayItem → emit done
```

- 防重入：非 IDLE 状态收到热键 → 托盘提示「正在处理中」。
- 每次流程开始：result_overlay.clear()（隐藏旧层）→ 截屏 → 显示 SelectionOverlay → 选区完成 → 启 worker。
- 失败：failed → 托盘气泡 → 回 IDLE（覆盖层不残留）。
- 完成：done → 主线程 show_translations → OVERLAYING（ESC 回调 → IDLE）。
- 退出：requestInterruption + wait(3000) 再退出，防 QThread destroyed 崩溃。

### 4.9 `app/settings_dialog.py`

```python
class SettingsDialog(QDialog):
    def __init__(self, cfg: ConfigManager, hotkey: GlobalHotkey, parent=None)
```

- 控件：API Key（Password + 显示 checkbox）、模型**可编辑 QComboBox**（qwen-vl-plus / qwen-vl-max / qwen2.5-vl-72b-instruct / qwen3-vl-plus；用户可手输其他模型名）、快捷键（聚焦后 keyboard hook 捕获组合键，显示 keyboard.format_hotkey）、背景色/文字色（QColorDialog）、padding、最小字号、最大边长（spinbox）。
- 保存：cfg.save + hotkey.register(新键)（失败回滚并提示）→ 托盘「设置已保存」。

## 5. 状态机与信号总览

```
IDLE ──热键──▶ SELECTING ──选区完成──▶ RECOGNIZING(识别+翻译) ──完成──▶ OVERLAYING ──ESC──▶ IDLE
 │                │                             │                          │
 └──失败──▶ 托盘提示 ──▶ IDLE        （任一步失败：failed → 托盘气泡 → IDLE）
```

## 6. 关键常量与默认值

| 常量 | 默认 | 位置 |
|---|---|---|
| 默认热键 | `ctrl+alt+t` | config.py |
| 默认模型 | `qwen-vl-plus` | config.py |
| API 端点 | `https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions` | config.py |
| 上传图最长边 | 2048 px | config.py（设置可改） |
| 覆盖层 padding | 4px | config.py |
| 最小字号 | 9pt | config.py |
| 温度 | 0.1 | qwen_client.py |
| 请求超时 | (10, 60)s | qwen_client.py |
| 重试 | 超时/5xx 重试 1 次 | qwen_client.py |
| bbox 校验 | 越界/面积 0 → 丢弃 | qwen_client.py |

## 7. 编码规范

- 全中文注释/docstring；公共函数类型标注；`from __future__ import annotations` 可用。
- 类 PascalCase、函数 snake_case、常量 UPPER_SNAKE；模块顶部三引号 docstring。
- UI 层不写业务逻辑；业务逻辑在 qwen_client/pipeline。
- 用 `logging`（文件 `%APPDATA%/ScreenCaptureOCR/app.log`，INFO）；禁止 print 残留；**禁止记录 API Key**。
- 禁止跨线程操作 QWidget/QPixmap；一切坐标换算走 screen.ScreenMapper。
- JSON 解析、坐标换算、字号自适应写成**纯函数**（便于 pytest）。

## 8. 开发顺序与验证（对应 01-开发计划.md v1.1 批次 A-F）

1. **批次 A**（骨架/托盘/热键/选区）：验证选区 PNG 输出。
2. **批次 B**（qwen_client 一条龙）：真实 Key 验证 text/bbox/translation 与坐标对位。
3. **批次 C**（配置/设置）：持久化 + 热键重注册。
4. **批次 D**（覆盖层/ESC/全流程）：真实界面验证。
5. **批次 E**（打磨/测试）：pytest 覆盖纯函数；DPI 实测。
6. **批次 F**（打包）：spec + 干净机验证 + README + 体积 ≤60MB。

每批完成：跑通验收 → 更新 `02-项目开发记录.md`（日期/完成项/验证结果/问题决策/遗留）→ commit（`feat: 批次X …`）。

## 9. 常见坑（开发时逐条对照）

1. **keyboard 回调线程**：回调里碰 Qt 对象会崩/静默失效 → 必须 QTimer.singleShot 切主线程。
2. **DPI 双倍像素**：grabWindow 物理像素 vs Qt 逻辑坐标，选区和覆盖层全部走 mapper，勿混用。
3. **覆盖层抢焦点**：漏 WindowTransparentForInput / WindowDoesNotAcceptFocus 会导致被覆盖软件失焦。
4. **模型返回的 bbox 是上传图像素**：必须先乘缩放比再加选区偏移，顺序颠倒则坐标全错。
5. **response_format=json_object 要求 prompt 含「json」**：PROMPT 已包含，不要删掉。
6. **模型可能输出 ```json 代码块包裹**：解析先剥代码块再取 [ ]。
7. **模型行数与原文不一致**：逐行独立覆盖，缺失行不覆盖、不错位；translation 缺失用 text 兜底。
8. **图片过大被 API 拒**：max_image_side 2048 兜底；超大屏选区注意缩放。
9. **QThread 退出崩溃**：退出时 join worker。
10. **托盘图标不显示**：isSystemTrayAvailable 检查 + 动态绘制 QIcon 兜底。
11. **键盘钩子残留**：退出时 unregister 全部钩子。
12. **依赖红线**：任何人（含未来维护者）不得引入 numpy/Pillow/opencv/easyocr/torch——体积目标是硬约束。
13. **模型名失效**：qwen-vl 系列以阿里云百炼控制台为准；设置中可手输模型名，README 说明。

## 10. 备选方案（技术选型遇阻时的降级路径）

| 主方案 | 降级路径 | 触发条件 |
|---|---|---|
| keyboard 全局热键 | pynput / ctypes RegisterHotKey + 低层钩子 | keyboard 在目标机权限下失灵 |
| QScreen.grabWindow(0) | PIL ImageGrab（会引入 Pillow，体积升级需记录） | grabWindow 多屏/缩放异常 |
| qwen-vl-plus 默认模型 | 用户手输其他千问视觉模型 / 换 qwen-vl-max | 模型效果或费用考量 |
| DashScope 兼容端点 | 用户自定义 api_base + 其他 OpenAI 兼容视觉服务 | 用户换供应商 |
| requests 直连 | openai SDK | 需要流式等高级能力（当前不需要） |

> 降级必须：记录到 `02-项目开发记录.md`；公开方法签名保持稳定（`QwenClient.recognize_and_translate(image, offset_x, offset_y) -> list[VisionLine]`）。

## 11. 完成定义（DoD）

一个批次完成必须同时满足：
1. 该批验收项全部实测通过（有运行证据：截图/日志）。
2. `02-项目开发记录.md` 已追加本批记录。
3. 代码已 commit（`feat: 批次X …`）。
4. 无新增未修复的 TODO/异常路径；依赖未越红线。
