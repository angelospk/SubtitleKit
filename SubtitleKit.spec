# -*- mode: python ; coding: utf-8 -*-

"""
PyInstaller spec file for SubtitleKit desktop app
"""

block_cipher = None

a = Analysis(
    ['src/subtitlekit/ui/desktop.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src/subtitlekit/ui/locales/*.json', 'subtitlekit/ui/locales'),
    ],
    hiddenimports=[
        'subtitlekit',
        'subtitlekit.core',
        'subtitlekit.tools',
        'subtitlekit.ui',
        'subtitlekit.updater',
        'requests',
        'packaging',
        'packaging.version',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'ipywidgets',  # Not needed for desktop
        'jupyter',
        'notebook',
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='SubtitleKit',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # No console window
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,  # Add icon path here if you create one
)
