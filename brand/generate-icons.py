#!/usr/bin/env python3
"""Generate OmniAide app icons for desktop, web and mobile from the brand SVGs."""
from __future__ import annotations

import json
import shutil
import struct
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BRAND = ROOT / "brand"
ROUNDED = BRAND / "omniaide-icon.svg"
SQUARE = BRAND / "omniaide-icon-square.svg"


def render(svg: Path, out: Path, size: int) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        base = Path(tmp) / "base.png"
        subprocess.run(["sips", "-s", "format", "png", str(svg), "--out", str(base)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["sips", "-z", str(size), str(size), str(base), "--out", str(out)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def write_ico(pngs: list[Path], out: Path) -> None:
    images = [(p, p.read_bytes()) for p in pngs]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = 6 + 16 * len(images)
    entries = []
    for path, data in images:
        size = 0 if path.stem.endswith("256") else int(path.stem.split("-")[-1])
        entries.append(struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset))
        offset += len(data)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(header + b"".join(entries) + b"".join(data for _, data in images))


def generate_iconset(svg: Path, out_dir: Path, entries: list[tuple[str, int]]) -> None:
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "icon.iconset"
        iconset.mkdir()
        for name, size in entries:
            render(svg, iconset / name, size)
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(out_dir)],
                       check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def main() -> None:
    # Desktop
    desktop = ROOT / "desktop"
    for size in (1024, 512, 256, 128, 64, 32):
        render(ROUNDED, desktop / "assets" / f"icon-{size}.png", size)
    shutil.copyfile(desktop / "assets" / "icon-1024.png", desktop / "assets" / "icon.png")
    render(ROUNDED, desktop / "assets" / "tray-icon.png", 32)
    (desktop / "build").mkdir(exist_ok=True)
    generate_iconset(ROUNDED, desktop / "build" / "icon.icns", [
        ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
        ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
        ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
        ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
        ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
    ])
    ico_sizes = (16, 32, 48, 64, 128, 256)
    ico_tmp = Path(tempfile.mkdtemp())
    ico_pngs = []
    for size in ico_sizes:
        p = ico_tmp / f"icon-{size}.png"
        render(ROUNDED, p, size)
        ico_pngs.append(p)
    write_ico(ico_pngs, desktop / "build" / "icon.ico")
    shutil.rmtree(ico_tmp, ignore_errors=True)

    # Web frontend
    public = ROOT / "frontend" / "public"
    public.mkdir(exist_ok=True)
    shutil.copyfile(ROUNDED, public / "favicon.svg")
    render(ROUNDED, public / "favicon-32.png", 32)
    render(ROUNDED, public / "apple-touch-icon.png", 180)
    render(ROUNDED, public / "icon-192.png", 192)
    render(ROUNDED, public / "icon-512.png", 512)

    # Mobile iOS
    ios_dir = ROOT / "mobile" / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
    contents = json.loads((ios_dir / "Contents.json").read_text())
    for item in contents.get("images", []):
        filename = item.get("filename")
        if not filename:
            continue
        scale = float(item.get("scale", "1x").rstrip("x"))
        base = float(item.get("size", "1024x1024").split("x")[0])
        render(SQUARE, ios_dir / filename, int(base * scale))

    # Mobile macOS
    macos_dir = ROOT / "mobile" / "macos" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
    contents = json.loads((macos_dir / "Contents.json").read_text())
    for item in contents.get("images", []):
        filename = item.get("filename")
        if not filename:
            continue
        scale = float(item.get("scale", "1x").rstrip("x"))
        base = float(item.get("size", "1024x1024").split("x")[0])
        render(SQUARE, macos_dir / filename, int(base * scale))

    # Mobile Android
    android = ROOT / "mobile" / "android" / "app" / "src" / "main" / "res"
    for folder, size in (("mipmap-mdpi", 48), ("mipmap-hdpi", 72), ("mipmap-xhdpi", 96),
                         ("mipmap-xxhdpi", 144), ("mipmap-xxxhdpi", 192)):
        render(SQUARE, android / folder / "ic_launcher.png", size)

    # Mobile web
    web = ROOT / "mobile" / "web"
    render(SQUARE, web / "favicon.png", 32)
    render(SQUARE, web / "icons" / "Icon-192.png", 192)
    render(SQUARE, web / "icons" / "Icon-512.png", 512)
    render(SQUARE, web / "icons" / "Icon-maskable-192.png", 192)
    render(SQUARE, web / "icons" / "Icon-maskable-512.png", 512)

    print("icons generated")


if __name__ == "__main__":
    main()
