# PyInstaller spec for the standalone Windows build.
#
#   pip install pyinstaller
#   pyinstaller packaging/ghostread.spec --noconfirm
#
# Produces dist/GhostRead.exe: one file, no console window, no Python needed on
# the target machine. Paths are anchored to this file, so it does not matter
# which directory you run it from.

import os

block_cipher = None

HERE = SPECPATH                      # injected by PyInstaller: this file's folder
ROOT = os.path.dirname(HERE)         # the project root, where ghostread/ lives

a = Analysis(
    [os.path.join(HERE, "launcher.py")],
    pathex=[ROOT],
    binaries=[],
    datas=[],
    hiddenimports=["pymupdf", "PIL.ImageTk", "PIL.Image", "PIL.ImageOps"],
    hookspath=[],
    runtime_hooks=[],
    excludes=[
        "numpy",
        "matplotlib",
        "scipy",
        "pandas",
        "pytest",
        "setuptools",
        "unittest",
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
    name="GhostRead",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    console=False,          # GUI app: no black console window behind the overlay
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
