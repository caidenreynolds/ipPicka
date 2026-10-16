# -*- mode: python ; coding: utf-8 -*-
import sys

is_windows = sys.platform == 'win32'

a = Analysis(
    ['ip_picka.py'],
    pathex=[], binaries=[], datas=[], hiddenimports=[],
    hookspath=[], hooksconfig={}, runtime_hooks=[], excludes=[],
    noarchive=False, optimize=0,
)
pyz = PYZ(a.pure)

# Windows produces a standalone executable with a requireAdministrator manifest.
# macOS uses a normal app bundle; only network changes request authorization.
exe = EXE(
    pyz, a.scripts,
    *([a.binaries, a.datas] if is_windows else [[]]),
    exclude_binaries=not is_windows,
    name='ipPicka', debug=False, bootloader_ignore_signals=False,
    strip=False, upx=True, console=False, disable_windowed_traceback=False,
    argv_emulation=False, target_arch=None, codesign_identity=None,
    entitlements_file=None, uac_admin=is_windows,
)
if not is_windows:
    coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=True,
                   upx_exclude=[], name='ipPicka')
    app = BUNDLE(coll, name='ipPicka.app', icon=None,
                 bundle_identifier='com.ziatech.ippicka')
