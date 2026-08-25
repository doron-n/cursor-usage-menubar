# -*- mode: python ; coding: utf-8 -*-
import os

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))

datas = collect_data_files("certifi")
hidden = collect_submodules("cursor_usage_menubar") + [
    "rumps",
    "AppKit",
    "Foundation",
    "objc",
    "certifi",
    "PyObjCTools",
    "CoreFoundation",
]

a = Analysis(
    [os.path.join(ROOT, "run.py")],
    pathex=[ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hidden,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Cursor Usage",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name="Cursor Usage",
)
app_version = os.environ.get("CURSOR_USAGE_VERSION", "1.0.0")
app = BUNDLE(
    coll,
    name="Cursor Usage.app",
    icon=None,
    bundle_identifier="com.cursor-usage.menubar",
    info_plist={
        "CFBundleName": "Cursor Usage",
        "CFBundleDisplayName": "Cursor Usage",
        "CFBundleShortVersionString": app_version,
        "CFBundleVersion": app_version,
        "NSHighResolutionCapable": True,
        "NSAppleEventsUsageDescription": "Opens the Cursor dashboard in your browser.",
    },
)
