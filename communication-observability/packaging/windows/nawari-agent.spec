# Build on Windows x64 only. PyInstaller does not cross-compile Windows binaries.
from pathlib import Path

repo = Path(SPECPATH).parents[1]

a = Analysis(
    [str(repo / "services" / "endpoint" / "cli.py")],
    pathex=[str(repo)],
    binaries=[],
    datas=[],
    hiddenimports=[
        "servicemanager",
        "win32event",
        "win32service",
        "win32serviceutil",
        "win32timezone",
    ],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="nawari-agent",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    target_arch="x86_64",
)
