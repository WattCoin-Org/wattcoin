#!/usr/bin/env python3
"""Build WattNode GUI artifacts for Linux.

Outputs:
- dist/WattNode            (PyInstaller one-file executable)
- dist/WattNode.AppImage   (optional, when appimagetool is available)
"""

from __future__ import annotations

import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from typing import NoReturn

ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
APPDIR = ROOT / "AppDir"
APPIMAGE_TOOL = shutil.which("appimagetool")


def fail(msg: str) -> NoReturn:
    print(f"✗ {msg}", file=sys.stderr)
    raise SystemExit(1)


def run(cmd: list[str]) -> None:
    print("+", " ".join(cmd))
    try:
        subprocess.run(cmd, cwd=ROOT, check=True)
    except subprocess.CalledProcessError as exc:
        fail(f"Command failed ({exc.returncode}): {' '.join(cmd)}")


def ensure_exists(path: Path, label: str) -> None:
    if not path.exists():
        fail(f"Missing required {label}: {path}")


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
        try:
            shutil.rmtree(APPDIR)
        except OSError as exc:
            fail(f"Failed to clean AppDir: {exc}")

    try:
        (APPDIR / "usr" / "bin").mkdir(parents=True, exist_ok=True)
        (APPDIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps").mkdir(
            parents=True, exist_ok=True
        )
    except OSError as exc:
        fail(f"Failed to create AppDir structure: {exc}")

    binary_src = DIST / "WattNode"
    ensure_exists(binary_src, "binary")
    binary_dst = APPDIR / "usr" / "bin" / "WattNode"

    logo_src = ROOT / "assets" / "logo.png"
    ensure_exists(logo_src, "logo")
    logo_dst = APPDIR / "usr" / "share" / "icons" / "hicolor" / "256x256" / "apps" / "wattnode.png"

    try:
        shutil.copy2(binary_src, binary_dst)
        shutil.copy2(logo_src, logo_dst)

        apprun = APPDIR / "AppRun"
        apprun.write_text("#!/bin/sh\nexec \"$APPDIR/usr/bin/WattNode\" \"$@\"\n", encoding="utf-8")
        apprun.chmod(0o755)

        ensure_desktop_entry()
    except OSError as exc:
        fail(f"Failed during AppDir staging: {exc}")


def build_pyinstaller() -> None:
    if importlib.util.find_spec("PyInstaller") is None:
        fail("PyInstaller is not installed. Install with: pip install pyinstaller")

    ensure_exists(ROOT / "wattnode_gui.py", "GUI entrypoint")
    ensure_exists(ROOT / "assets" / "logo.png", "logo")

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

    tool_path = Path(APPIMAGE_TOOL)
    if not tool_path.exists() or not tool_path.is_file():
        fail(f"Invalid appimagetool path: {tool_path}")

    stage_appdir()
    output = DIST / "WattNode.AppImage"
    run([str(tool_path), str(APPDIR), str(output)])
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
