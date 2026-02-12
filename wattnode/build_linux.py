#!/usr/bin/env python3
"""
Build WattNode Linux GUI artifacts.

Produces:
- dist/WattNode (one-file PyInstaller binary)
- dist/WattNode.AppImage (when appimagetool is available)

Run:
  python build_linux.py
"""

import os
import shutil
import stat
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.resolve()
DIST = ROOT / "dist"
APPDIR = ROOT / "AppDir"


def run(cmd):
    print("+", " ".join(map(str, cmd)))
    subprocess.run(cmd, check=True)


def ensure_pyinstaller():
    try:
        import PyInstaller  # noqa: F401
    except Exception:
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])


def build_onefile():
    data_sep = ":"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--onefile",
        "--windowed",
        "--name=WattNode",
        f"--add-data=assets{data_sep}assets",
        "wattnode_gui.py",
    ]
    png_icon = ROOT / "assets" / "logo.png"
    if png_icon.exists():
        cmd.append(f"--icon={png_icon}")
    run(cmd)


def make_apprun():
    apprun = APPDIR / "AppRun"
    apprun.write_text("#!/bin/sh\nexec \"$(dirname \"$0\")/usr/bin/WattNode\" \"$@\"\n", encoding="utf-8")
    apprun.chmod(apprun.stat().st_mode | stat.S_IEXEC)


def stage_appdir():
    if APPDIR.exists():
        shutil.rmtree(APPDIR)
    (APPDIR / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (APPDIR / "usr" / "share" / "applications").mkdir(parents=True, exist_ok=True)
    (APPDIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(parents=True, exist_ok=True)

    shutil.copy2(DIST / "WattNode", APPDIR / "usr" / "bin" / "WattNode")

    desktop = """[Desktop Entry]
Type=Application
Name=WattNode
Exec=WattNode
Icon=wattnode
Categories=Utility;
Terminal=false
"""
    (APPDIR / "wattnode.desktop").write_text(desktop, encoding="utf-8")
    (APPDIR / "usr" / "share" / "applications" / "wattnode.desktop").write_text(desktop, encoding="utf-8")

    icon_src = ROOT / "assets" / "logo.png"
    if icon_src.exists():
        shutil.copy2(icon_src, APPDIR / "wattnode.png")
        shutil.copy2(icon_src, APPDIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "wattnode.png")

    make_apprun()


def build_appimage():
    appimagetool = shutil.which("appimagetool")
    if not appimagetool:
        print("! appimagetool not found. Skipping AppImage packaging.")
        print("  Install: https://appimage.github.io/appimagetool/")
        return
    DIST.mkdir(exist_ok=True)
    out = DIST / "WattNode.AppImage"
    run([appimagetool, str(APPDIR), str(out)])
    print(f"✓ AppImage created: {out}")


def main():
    os.chdir(ROOT)
    print("=" * 50)
    print("WattNode Linux Build")
    print("=" * 50)
    ensure_pyinstaller()
    build_onefile()
    stage_appdir()
    build_appimage()
    print("\n✓ Linux build complete")
    print("- Binary: dist/WattNode")
    if (DIST / "WattNode.AppImage").exists():
        print("- AppImage: dist/WattNode.AppImage")


if __name__ == "__main__":
    main()
