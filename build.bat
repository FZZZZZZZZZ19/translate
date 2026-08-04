@echo off
REM ScreenCaptureOCR Translator 打包脚本
REM 使用方法：双击运行，或在命令行中执行 build.bat

echo ============================================
echo ScreenCaptureOCR Translator - PyInstaller 打包
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
echo [1/3] 清理旧构建...
if exist build rmdir /s /q build
if exist dist rmdir /s /q dist

echo [2/3] 开始打包（onedir 模式，可能需要几分钟）...
echo.
pyinstaller --clean --noconfirm --onedir --windowed --name ScreenCaptureTranslator main.py

if errorlevel 1 (
    echo.
    echo [错误] 打包失败，请查看上方输出。
    pause
    exit /b 1
)

echo.
echo [3/3] 精简体积：移除不需要的 Qt 组件...

set "INTERNAL=dist\ScreenCaptureTranslator\_internal"
set "QT5BIN=%INTERNAL%\PyQt5\Qt5\bin"
set "QT5PLUGINS=%INTERNAL%\PyQt5\Qt5\plugins"

REM --- 移除大型不需要的 DLL（节省 ~32MB）---
if exist "%QT5BIN%\opengl32sw.dll"      del "%QT5BIN%\opengl32sw.dll"      & echo   删除 opengl32sw.dll (20MB)
if exist "%QT5BIN%\d3dcompiler_47.dll"  del "%QT5BIN%\d3dcompiler_47.dll"  & echo   删除 d3dcompiler_47.dll (4MB)
if exist "%QT5BIN%\Qt5Quick.dll"        del "%QT5BIN%\Qt5Quick.dll"        & echo   删除 Qt5Quick.dll (4MB)
if exist "%QT5BIN%\Qt5Qml.dll"          del "%QT5BIN%\Qt5Qml.dll"          & echo   删除 Qt5Qml.dll (3.5MB)
if exist "%QT5BIN%\libGLESv2.dll"       del "%QT5BIN%\libGLESv2.dll"       & echo   删除 libGLESv2.dll (3.3MB)
if exist "%QT5BIN%\Qt5Network.dll"      del "%QT5BIN%\Qt5Network.dll"      & echo   删除 Qt5Network.dll (1.3MB)
if exist "%QT5BIN%\Qt5QmlModels.dll"    del "%QT5BIN%\Qt5QmlModels.dll"    & echo   删除 Qt5QmlModels.dll
if exist "%QT5BIN%\Qt5DBus.dll"         del "%QT5BIN%\Qt5DBus.dll"         & echo   删除 Qt5DBus.dll
if exist "%QT5BIN%\Qt5Svg.dll"          del "%QT5BIN%\Qt5Svg.dll"          & echo   删除 Qt5Svg.dll
if exist "%QT5BIN%\Qt5WebSockets.dll"   del "%QT5BIN%\Qt5WebSockets.dll"   & echo   删除 Qt5WebSockets.dll
if exist "%QT5BIN%\libEGL.dll"          del "%QT5BIN%\libEGL.dll"          & echo   删除 libEGL.dll

REM --- 移除不需要的 Qt 插件（节省 ~3MB）---
if exist "%QT5PLUGINS%\platforms\qwebgl.dll"    del "%QT5PLUGINS%\platforms\qwebgl.dll"
if exist "%QT5PLUGINS%\platforms\qminimal.dll"   del "%QT5PLUGINS%\platforms\qminimal.dll"
if exist "%QT5PLUGINS%\platforms\qoffscreen.dll"  del "%QT5PLUGINS%\platforms\qoffscreen.dll"

REM 只保留常用图片格式（jpeg/gif/ico/png）
for %%f in (qwebp qtiff qicns qwbmp qtga qsvg) do (
    if exist "%QT5PLUGINS%\imageformats\%%f.dll" del "%QT5PLUGINS%\imageformats\%%f.dll"
)

REM 移除不需要的 iconengines / platformthemes / generic
if exist "%QT5PLUGINS%\iconengines"   rmdir /s /q "%QT5PLUGINS%\iconengines"
if exist "%QT5PLUGINS%\platformthemes" rmdir /s /q "%QT5PLUGINS%\platformthemes"
if exist "%QT5PLUGINS%\generic"       rmdir /s /q "%QT5PLUGINS%\generic"

REM 移除 Qt 翻译文件（不需要）
if exist "%INTERNAL%\PyQt5\Qt5\translations" rmdir /s /q "%INTERNAL%\PyQt5\Qt5\translations"

echo.
echo ============================================
echo 打包完成！
echo.
echo 输出目录: dist\ScreenCaptureTranslator\
echo 可执行文件: dist\ScreenCaptureTranslator\ScreenCaptureTranslator.exe
echo.
echo 体积检查：
dir dist\ScreenCaptureTranslator\ /s 2>nul | findstr "File(s)"
echo.
echo 请将整个 dist\ScreenCaptureTranslator 目录复制到目标机器运行。
echo ============================================

pause
