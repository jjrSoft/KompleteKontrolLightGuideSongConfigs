# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['komplete_kontrol_lightguide.py'],
    pathex=[],
    binaries=[],
    datas=[],
    hiddenimports=['mido.backends.rtmidi'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='komplete_kontrol_lightguide',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='komplete_kontrol_lightguide',
)
app = BUNDLE(
    coll,
    name='Komplete Kontrol Lightguide.app',
    icon='komplete_kontrol_lightguide.icns',
    bundle_identifier=None,
)
