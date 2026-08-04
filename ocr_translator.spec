# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec —— ScreenCaptureOCR Translator (v1.1).

onedir + windowed 模式，目标打包体积 ≤60MB。
"""

from PyInstaller.utils.hooks import collect_all

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('assets', 'assets'),  # icon.ico 等资源（若存在）
    ],
    hiddenimports=[
        'PyQt5.QtCore',
        'PyQt5.QtGui',
        'PyQt5.QtWidgets',
        'keyboard',
        'requests',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        # 排除不需要的 Qt 模块以减小体积
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
    ],
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data)

# collect_all 收集 PyQt5 和 keyboard 的隐式依赖
qt_datas, qt_binaries, qt_hiddenimports = collect_all('PyQt5')

exe = EXE(
    pyz,
    a.scripts,
    a.binaries + qt_binaries,
    a.datas + qt_datas,
    [],
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
    icon='assets/icon.ico',  # 若不存在则忽略
)

coll = COLLECT(
    exe,
    a.binaries + qt_binaries,
    a.zipfiles,
    a.datas + qt_datas,
    strip=True,
    upx=True,
    upx_exclude=[],
    name='ScreenCaptureTranslator',
)
