# ScreenCaptureOCR Translator —— 屏幕截图 AI 翻译工具

Windows 桌面常驻托盘工具：按下全局快捷键 → 拖拽矩形选区 → AI 自动识别英文并翻译为中文 → 译文覆盖回屏幕上原文位置 → 按 ESC 退出。

> **v1.1**：采用通义千问视觉模型（qwen-vl 系列），一次 API 调用同时完成「英文识别 + 中文翻译 + 文本坐标」，打包体积仅约 50MB。

---

## 功能演示

1. 双击启动，托盘图标出现在任务栏通知区域。
2. 按下默认快捷键 `Ctrl+Alt+T`，屏幕变暗进入选区模式。
3. 拖拽鼠标框选需要翻译的英文区域，松开鼠标。
4. 等待 3-8 秒，中文译文直接覆盖在原文位置。
5. 阅读完毕后按 `ESC` 退出覆盖层。
6. 可重复操作，连续使用。

---

## 安装

### 方式一：下载打包好的 exe（推荐）

1. 从发布页面下载 `ScreenCaptureTranslator.zip`
2. 解压到任意目录（**不要**解压到系统临时目录或需要管理员权限的目录）
3. 双击 `ScreenCaptureTranslator.exe` 启动

### 方式二：从源码运行

要求：Python 3.8+（64 位）

```bash
# 克隆或下载项目
cd translate

# 创建虚拟环境并安装依赖
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt

# 运行
python main.py
```

---

## 首次使用（必须配置 API Key）

本工具不自带 API Key，需要用户自行提供**阿里云百炼（DashScope）**的 API Key：

1. 访问 [阿里云百炼控制台](https://bailian.console.aliyun.com/)
2. 注册/登录阿里云账号
3. 在「模型广场」开通 qwen-vl-plus（或其他视觉模型）
4. 在「API Key 管理」创建 API Key
5. 右键托盘图标 → **设置** → 填入 API Key → 保存

### 可用模型

| 模型 | 说明 | 适用场景 |
|---|---|---|
| `qwen-vl-plus`（默认） | 均衡性价比 | 日常使用推荐 |
| `qwen-vl-max` | 最强精度 | 复杂排版/小字体 |
| `qwen2.5-vl-72b-instruct` | 开源旗舰 | 高精度需求 |
| `qwen3-vl-plus` | 最新一代 | 尝鲜 |

> 具体可用模型以阿里云百炼控制台为准。如果默认模型不可用，请在设置中修改为其他支持的模型名。

---

## 费用说明

- 每次截图翻译消耗图片 token + 少量文本 token。
- 以 `qwen-vl-plus` 为例，单次操作约消耗 500-2000 token，费用约 ¥0.001-0.004。
- 详细计费：https://help.aliyun.com/document_detail/dashscope/price.html

---

## 常见问题

### Q: 托盘图标不显示？

部分 Windows 环境需要手动启用托盘图标：任务栏设置 → 选择哪些图标显示在任务栏上 → 找到 ScreenCaptureTranslator → 打开。

### Q: 热键无效？

- 确保以**普通用户权限**运行（不要以管理员运行）
- 快捷键可能被其他软件占用，在设置中更换组合键
- 某些安全软件可能拦截键盘钩子，尝试将程序加入白名单

### Q: 翻译失败/报错？

- **API Key 无效** → 检查 API Key 是否正确，是否已在百炼控制台开通视觉模型
- **网络连接失败** → 检查网络，DashScope 需要外网访问
- **服务超时** → 稍后重试，或切换到更快的模型
- **模型返回异常** → 尝试更换模型

### Q: 覆盖层位置偏移？

- 如果使用 125%/150% 缩放，覆盖层会自动适配 DPI
- 轻微偏移（≤5px）属正常，背景块有 4px 边距可覆盖

### Q: 断网能用吗？

不能。本工具依赖云端 AI，需要联网。这是为压缩打包体积（500MB+ → 50MB）所做的取舍。

### Q: 如何卸载？

删除解压目录即可，无注册表、无残留文件。配置文件在 `%APPDATA%\ScreenCaptureOCR\` 可一并删除。

---

## 技术栈

| 项 | 值 |
|---|---|
| 语言 | Python 3.8+ |
| GUI | PyQt5 |
| AI | 千问 DashScope（qwen-vl 系列） |
| 热键 | keyboard |
| 打包 | PyInstaller (onedir) |
| 体积 | ≈ 50MB |

---

## 开发

```bash
# 运行测试
python -m pytest tests/ -v

# 打包
build.bat
```

项目文档：
- `00-开发规划书.md` —— 方案与验收
- `01-开发计划.md` —— 批次任务
- `CLAUDE.md` —— 技术规格
- `02-项目开发记录.md` —— 开发记录

---

## License

MIT
