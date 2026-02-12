#!/usr/bin/env python3
"""Build WattNode GUI artifacts for Linux.

Outputs:
- dist/WattNode            (PyInstaller one-file executable)
- dist/WattNode.AppImage   (optional, when appimagetool is available)
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APPDIR = ROOT / "AppDir"
APPIMAGE_TOOL = shutil.which("appimagetool")


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    subprocess.run(cmd, cwd=ROOT, check=True)


def ensure_desktop_entry() -> Path:
    desktop = APPDIR / "wattnode.desktop"
    desktop.write_text(
        "\n".join(
            [
                "[Desktop Entry]",
                "Type=Application",
                "Name=WattNode",
                "Comment=WattNode desktop GUI",
                "Exec=AppRun",
                "Icon=wattnode",
                "Categories=Utility;Network;",
                "Terminal=false",
                "",
            ]
        ),
        encoding="utf-8",
    )
    return desktop


def stage_appdir() -> None:
    if APPDIR.exists():
        shutil.rmtree(APPDIR)
    (APPDIR / "usr" / "bin").mkdir(parents=True, exist_ok=True)
    (APPDIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(
        parents=True, exist_ok=True
    )

    binary_src = DIST / "WattNode"
    binary_dst = APPDIR / "usr" / "bin" / "WattNode"
    shutil.copy2(binary_src, binary_dst)

    logo_src = ROOT / "assets" / "logo.png"
    logo_dst = APPDIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "wattnode.png"
    shutil.copy2(logo_src, logo_dst)

    apprun = APPDIR / "AppRun"
    apprun.write_text("#!/bin/sh\nexec \"$APPDIR/usr/bin/WattNode\" \"$@\"\n", encoding="utf-8")
    apprun.chmod(0o755)

    ensure_desktop_entry()


def build_pyinstaller() -> None:
    run(
        [
            "python3",
            "-m",
            "PyInstaller",
            "--noconfirm",
            "--clean",
            "--onefile",
            "--name",
            "WattNode",
            "--add-data",
            "assets/logo.png:assets",
            "wattnode_gui.py",
        ]
    )


def build_appimage() -> Path | None:
    if not APPIMAGE_TOOL:
        print("! appimagetool not found; skip AppImage packaging")
        return None

    stage_appdir()
    output = DIST / "WattNode.AppImage"
    run([APPIMAGE_TOOL, str(APPDIR), str(output)])
    print(f"✓ AppImage created: {output}")
    return output


def main() -> None:
    print("Building Linux artifacts for WattNode GUI...")
    build_pyinstaller()
    print(f"✓ Binary created: {DIST / 'WattNode'}")
    build_appimage()
    print("Done.")


if __name__ == "__main__":
    main()
