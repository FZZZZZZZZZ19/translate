# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec —— ScreenCaptureOCR Translator (v1.2).

onefile 模式，生成单个 exe，可直接分发到任何 Windows 10/11 机器。
目标体积 ≤80MB（onefile 自解压开销约 10-15MB）。
"""

from PyInstaller.utils.hooks import collect_all

# ── 不需要的 DLL（减小体积）──────────────────────────────
_UNWANTED_DLLS = {
    # Qt 渲染/图形（本应用仅用 QWidget 绘制，不需要）
    'opengl32sw.dll',       # ~20MB 软件 OpenGL
    'd3dcompiler_47.dll',   # ~4MB Direct3D 编译器
    'libGLESv2.dll',        # ~3.3MB OpenGL ES
    'libEGL.dll',           # EGL 接口
    # Qt 模块 DLL（excludes 已排除对应 Python 模块）
    'Qt5Quick.dll',         # ~4MB
    'Qt5Qml.dll',           # ~3.5MB
    'Qt5QmlModels.dll',
    'Qt5QmlWorkerScript.dll',
    'Qt5QuickWidgets.dll',
    'Qt5QuickTemplates2.dll',
    'Qt5QuickControls2.dll',
    'Qt5QuickShapes.dll',
    'Qt5Network.dll',       # ~1.3MB
    'Qt5DBus.dll',
    'Qt5Svg.dll',
    'Qt5WebSockets.dll',
    'Qt5VirtualKeyboard.dll',
    'Qt5OpenGL.dll',
    'Qt5Multimedia.dll',
    'Qt5MultimediaWidgets.dll',
    'Qt5MultimediaQuick.dll',
    'Qt53DRender.dll',
    'Qt53DCore.dll',
    'Qt53DInput.dll',
    'Qt53DLogic.dll',
    'Qt53DAnimation.dll',
    'Qt53DExtras.dll',
    'Qt5Gamepad.dll',
    'Qt5SerialPort.dll',
    'Qt5SerialBus.dll',
    'Qt5Bluetooth.dll',
    'Qt5Nfc.dll',
    'Qt5Positioning.dll',
    'Qt5PositioningQuick.dll',
    'Qt5Location.dll',
    'Qt5Sensors.dll',
    'Qt5WebEngine.dll',
    'Qt5WebEngineCore.dll',
    'Qt5WebEngineWidgets.dll',
    'Qt5WebChannel.dll',
    'Qt5TextToSpeech.dll',
    'Qt5XmlPatterns.dll',
    'Qt5Designer.dll',
    'Qt5DesignerComponents.dll',
    'Qt5Help.dll',
    'Qt5Test.dll',
    'Qt5Script.dll',
    'Qt5ScriptTools.dll',
    'Qt5RemoteObjects.dll',
    'Qt5Sql.dll',
    'Qt5PrintSupport.dll',
    'Qt5WinExtras.dll',
    'Qt5Purchasing.dll',
    'Qt5DataVisualization.dll',
    'Qt5Charts.dll',
    'Qt5Scxml.dll',
    'Qt5Pdf.dll',
    'Qt5PdfWidgets.dll',
    'Qt5SvgWidgets.dll',
}

# ── 不需要的 Qt 插件子目录/文件（减小体积）───────────────
_UNWANTED_PLUGINS = {
    # 图片格式：只保留 jpeg / gif / ico / png
    'qwebp', 'qtiff', 'qicns', 'qwbmp', 'qtga', 'qsvg',
    # 平台：只保留 qwindows
    'qwebgl', 'qminimal', 'qoffscreen', 'qdirect2d',
    # 不需要的插件目录
    'iconengines',
    'platformthemes',
    'generic',
}

_UNWANTED_DIRS = {
    'translations',  # Qt 翻译文件
}

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=[
        # PyQt5 核心
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        # keyboard 及其原生钩子
        'keyboard',
        'keyboard._keyboard_event',
        # requests 及其依赖链
        'requests',
        'urllib3',
        'urllib3.util',
        'urllib3.util.retry',
        'charset_normalizer',
        'certifi',
        'idna',
        # 标准库隐式依赖
        'json',
        'logging',
        'base64',
        'io',
        'http.client',
        'email.mime',
        'queue',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # ── 排除不需要的 PyQt5 子模块（与 DLL 过滤对应）──
        'PyQt5.QtBluetooth',
        'PyQt5.QtDBus',
        'PyQt5.QtDesigner',
        'PyQt5.QtHelp',
        'PyQt5.QtLocation',
        'PyQt5.QtMultimedia',
        'PyQt5.QtMultimediaWidgets',
        'PyQt5.QtNetwork',
        'PyQt5.QtNfc',
        'PyQt5.QtOpenGL',
        'PyQt5.QtPositioning',
        'PyQt5.QtPrintSupport',
        'PyQt5.QtQml',
        'PyQt5.QtQuick',
        'PyQt5.QtQuickWidgets',
        'PyQt5.QtRemoteObjects',
        'PyQt5.QtScript',
        'PyQt5.QtScriptTools',
        'PyQt5.QtSensors',
        'PyQt5.QtSerialPort',
        'PyQt5.QtSql',
        'PyQt5.QtSvg',
        'PyQt5.QtTest',
        'PyQt5.QtTextToSpeech',
        'PyQt5.QtWebChannel',
        'PyQt5.QtWebEngine',
        'PyQt5.QtWebEngineCore',
        'PyQt5.QtWebEngineWidgets',
        'PyQt5.QtWebSockets',
        'PyQt5.QtXml',
        'PyQt5.QtXmlPatterns',
        'PyQt5.QtWinExtras',
        'PyQt5.QtCharts',
        'PyQt5.QtDataVisualization',
        'PyQt5.QtPurchasing',
        'PyQt5.Qt3DCore',
        'PyQt5.Qt3DRender',
        'PyQt5.Qt3DInput',
        'PyQt5.Qt3DLogic',
        'PyQt5.Qt3DAnimation',
        'PyQt5.Qt3DExtras',
        'PyQt5.QtGamepad',
        'PyQt5.QtSerialBus',
        'PyQt5.QtScxml',
        'PyQt5.QtPdf',
        'PyQt5.QtPdfWidgets',
        'PyQt5.QtSvgWidgets',
        # ── 标准库中不用的 ──
        'tkinter',
        'unittest',
        'test',
        'pydoc',
        'distutils',
        'setuptools',
        'pip',
        'wheel',
    ],
    noarchive=False,
)

from PyInstaller.building.datastruct import TOC

pyz = PYZ(a.pure, a.zipped_data)

# ── 收集 PyQt5 所有依赖（二进制 DLL + 插件数据）─────────
qt_datas, qt_binaries, _qt_hiddenimports = collect_all('PyQt5')

# ── TOC 规范化：2 元组 → 3 元组（添加类型标记）───────────
def _normalize_toc(entries, default_type):
    """将 2 元组 (name, path) 转为 3 元组 (name, path, type)。"""
    result = []
    for entry in entries:
        if len(entry) == 2:
            result.append((entry[0], entry[1], default_type))
        else:
            result.append(entry)
    return result

qt_binaries = _normalize_toc(qt_binaries, 'BINARY')
qt_datas = _normalize_toc(qt_datas, 'DATA')

# ── 过滤不需要的 DLL（节省 ~50MB）─────────────────────────
def _filter_binaries(entries):
    """过滤 DLL。"""
    return [e for e in entries if e[0] not in _UNWANTED_DLLS]

qt_binaries = _filter_binaries(qt_binaries)

# ── 过滤不需要的 Qt 插件（节省 ~5MB）──────────────────────
def _should_keep_plugin(name: str) -> bool:
    """检查插件路径是否应保留。"""
    for unwanted in _UNWANTED_PLUGINS:
        if unwanted in name:
            return False
    for d in _UNWANTED_DIRS:
        if d in name.split('/'):
            return False
    return True

qt_datas = [e for e in qt_datas if _should_keep_plugin(e[0])]

# ── 合并所有依赖 ──────────────────────────────────────────
# a.binaries：Analysis 阶段发现的二进制（Python DLL、keyboard .pyd 等）
# qt_binaries：PyQt5 Qt5/bin/*.dll（已过滤）
all_binaries = TOC(a.binaries)
all_binaries.extend(TOC(qt_binaries))

# a.datas：Analysis 阶段发现的数据文件（如有）
# qt_datas：PyQt5 Qt5/plugins/* + translations 等（已过滤）
all_datas = TOC(a.datas)
all_datas.extend(TOC(qt_datas))

# ── onefile EXE（无 COLLECT）─────────────────────────────
exe = EXE(
    pyz,
    a.scripts,
    all_binaries,
    a.zipfiles,
    all_datas,
    name='ScreenCaptureTranslator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=True,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # windowed：无控制台黑窗
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/icon.ico',  # 若不存在则忽略，程序会动态绘制
)
