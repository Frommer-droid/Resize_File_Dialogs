# -*- coding: utf-8 -*-
import os
import sys
from pathlib import Path
from PyInstaller.utils.win32 import versioninfo

spec_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
sys.path.insert(0, spec_dir)
from binary_policy import prefer_qt_runtime

block_cipher = None
project_root = os.path.abspath(os.path.join(spec_dir, '..'))
smoke_mode = os.environ.get('RFD_FROZEN_SMOKE') == '1'

# ========================================================
# 🔧 CONFIGURATION SECTION
# ========================================================
APP_NAME = 'Resize_File_Dialogs_Smoke' if smoke_mode else 'Resize_File_Dialogs'
MAIN_SCRIPT = 'Build_Tools/frozen_smoke_entry.py' if smoke_mode else 'Resize_File_Dialogs.pyw'
ICON_FILE = 'logo.ico'

# List of hidden imports (modules that PyInstaller cannot detect)
HIDDEN_IMPORTS = [
    'win32api',
    'win32con',
    'win32gui',
]

# List of extra data files to include INSIDE the exe (src, dst)
# Note: For external config files, use post_build.py instead.
ADDED_FILES = [
    (os.path.join(project_root, 'VERSION'), '.'),
]
version_text = Path(project_root, 'VERSION').read_text(encoding='utf-8').strip()
version_parts = tuple(int(part) for part in version_text.split('.'))
if len(version_parts) != 3:
    raise RuntimeError(f'Expected MAJOR.MINOR.PATCH in VERSION: {version_text}')
version_tuple = (*version_parts, 0)
version_resource = versioninfo.VSVersionInfo(
    ffi=versioninfo.FixedFileInfo(filevers=version_tuple, prodvers=version_tuple),
    kids=[
        versioninfo.StringFileInfo([
            versioninfo.StringTable('040904B0', [
                versioninfo.StringStruct('CompanyName', 'Frommer-droid'),
                versioninfo.StringStruct('FileDescription', 'Resize_File_Dialogs'),
                versioninfo.StringStruct('FileVersion', version_text),
                versioninfo.StringStruct('ProductName', 'Resize_File_Dialogs'),
                versioninfo.StringStruct('ProductVersion', version_text),
            ])
        ]),
        versioninfo.VarFileInfo([versioninfo.VarStruct('Translation', [1033, 1200])]),
    ],
)
# ========================================================

# Resolve paths
script_path = os.path.join(project_root, MAIN_SCRIPT)
icon_path = os.path.join(project_root, ICON_FILE) if ICON_FILE else None

a = Analysis(
    [script_path],
    pathex=[project_root],
    binaries=[],
    datas=ADDED_FILES,
    hiddenimports=HIDDEN_IMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)
a.binaries = prefer_qt_runtime(a.binaries, Path(project_root))

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=smoke_mode,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_path,
    version=version_resource,
    uac_admin=not smoke_mode,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
