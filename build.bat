@echo off
REM =====================================================
REM  ScreenCaptureOCR Translator - PyInstaller onefile 打包
REM  生成单个 exe，可直接分发到任何 Windows 10/11 机器
REM =====================================================

echo ============================================
echo ScreenCaptureOCR Translator - onefile 打包
echo ============================================
echo.

REM 激活虚拟环境
if exist "venv\Scripts\activate.bat" (
    call venv\Scripts\activate.bat
) else (
    echo [错误] 未找到 venv，请先创建虚拟环境并安装依赖
    echo   python -m venv venv
    echo   venv\Scripts\activate
    echo   pip install -r requirements.txt
    echo   pip install pyinstaller
    pause
    exit /b 1
)

REM 检查 PyInstaller
pip show pyinstaller >nul 2>&1
if errorlevel 1 (
    echo [提示] 安装 PyInstaller...
    pip install pyinstaller
)

echo.
echo [1/2] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/2] 开始 onefile 打包（使用 ocr_translator.spec，可能需要几分钟）...
echo.
pyinstaller --clean --noconfirm ocr_translator.spec

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上方输出。
    echo.
    echo 常见问题：
    echo   1. assets\icon.ico 不存在 → 可忽略，程序会动态绘制托盘图标
    echo   2. 缺少隐藏导入 → 在 spec 文件的 hiddenimports 中添加
    echo   3. 病毒软件拦截 → 临时关闭实时防护后重试
    pause
    exit /b 1
)

echo.
echo ============================================
echo 打包完成！
echo.
echo 输出文件: dist\ScreenCaptureTranslator.exe
echo.
echo 文件大小：
for %%f in (dist\ScreenCaptureTranslator.exe) do echo   %%~zf 字节 (%%~zf bytes^)
echo.
echo 将该 exe 发送给任何人即可使用（无需安装 Python 或其他依赖）。
echo 首次启动会解压到临时目录，启动稍慢（约 3-10 秒），之后正常。
echo.
echo 提示：某些杀毒软件可能误报 onefile exe，属正常现象。
echo ============================================

pause
