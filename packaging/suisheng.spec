# PyInstaller 配置（macOS 与 Windows 共用）：pyinstaller packaging/suisheng.spec
# 产物：macOS dist/随声.app；Windows dist/Suisheng/（再由 Inno Setup 做安装程序）
import sys
import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

ROOT = Path(SPECPATH).parent
MAC, WIN = sys.platform == "darwin", sys.platform == "win32"
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]

datas, binaries, hidden = [], [], []
pkgs = ["livecaption", "sherpa_onnx", "opencc", "pypinyin", "ToJyutping", "soundfile", "_soundfile_data"]
pkgs += ["catap"] if MAC else ["pyaudiowpatch"] if WIN else []
for pkg in pkgs:
    try:
        d, b, h = collect_all(pkg)
    except Exception:                                   # noqa: BLE001  某平台没有这个包
        continue
    datas += d; binaries += b; hidden += h
hidden += ["livecaption.ui.app", "livecaption.main", "PySide6.QtNetwork"]

a = Analysis(
    [str(ROOT / "packaging" / "entry.py")],
    pathex=[str(ROOT)],
    binaries=binaries, datas=datas, hiddenimports=hidden,
    excludes=["tkinter", "mlx", "mlx_lm", "mlx_audio", "torch", "transformers", "scipy", "matplotlib",
              "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtPdf", "PySide6.QtSvgWidgets",
              "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtConcurrent",
              "PySide6.QtDBus", "PySide6.QtXml", "PySide6.QtDesigner", "PySide6.QtHelp", "PySide6.QtUiTools"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Suisheng", console=False, upx=False,
          icon=str(ROOT / ("app/icon/AppIcon.icns" if MAC else "packaging/AppIcon.ico")))
extra = []
if WIN:   # Windows 另带一个控制台版：命令行测试 / 排查问题用（suisheng-cli.exe --file x.wav --no-ui）
    extra.append(EXE(pyz, a.scripts, [], exclude_binaries=True, name="suisheng-cli", console=True, upx=False,
                     icon=str(ROOT / "packaging/AppIcon.ico")))
coll = COLLECT(exe, *extra, a.binaries, a.datas, name="Suisheng", upx=False)
if MAC:
    app = BUNDLE(
        coll, name="随声.app", icon=str(ROOT / "app/icon/AppIcon.icns"), bundle_identifier="com.livecaption.app",
        version=VERSION,
        info_plist={
            "CFBundleName": "随声", "CFBundleDisplayName": "随声",
            "CFBundleShortVersionString": VERSION, "CFBundleVersion": VERSION,
            "LSMinimumSystemVersion": "14.2",
            "NSHighResolutionCapable": True,
            "NSAudioCaptureUsageDescription": "抓取系统正在播放的声音，用于生成实时字幕（全部在本机处理）。",
        },
    )
