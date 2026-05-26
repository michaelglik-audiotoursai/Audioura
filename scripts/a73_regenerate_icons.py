#!/usr/bin/env python3
"""A#73 — regenerate iOS app icons with a #A93105 (brick-red) background.

Reads the current AppIcon master (which has a transparent background),
composites it onto a solid #A93105 canvas, and regenerates all 15 size
variants required by Contents.json. Output PNGs are RGB (no alpha) per
App Store requirements.

Run from: ~/Development/Audioura-build/
Usage:    python3 development/scripts/a73_regenerate_icons.py
Requires: Pillow (`pip3 install --user Pillow`)
"""
from __future__ import annotations
from pathlib import Path
import sys

try:
    from PIL import Image
except ImportError:
    sys.exit(
        "ERROR: Pillow is not installed. Run:\n"
        "    pip3 install --user Pillow\n"
        "then re-run this script."
    )

# Run from repo root (~/Development/Audioura-build/). Resolve appiconset relative to that.
REPO_ROOT = Path(__file__).resolve().parent.parent.parent
APPICON_DIR = REPO_ROOT / "audio_tour_app" / "ios" / "Runner" / "Assets.xcassets" / "AppIcon.appiconset"
MASTER_FILE = APPICON_DIR / "Icon-App-1024x1024@1x.png"

# A#73 background — #A93105 (brick red)
BG_RGB = (169, 49, 5)

# (filename, pixel size) — must match Contents.json
VARIANTS: list[tuple[str, int]] = [
    ("Icon-App-20x20@1x.png",       20),
    ("Icon-App-20x20@2x.png",       40),
    ("Icon-App-20x20@3x.png",       60),
    ("Icon-App-29x29@1x.png",       29),
    ("Icon-App-29x29@2x.png",       58),
    ("Icon-App-29x29@3x.png",       87),
    ("Icon-App-40x40@1x.png",       40),
    ("Icon-App-40x40@2x.png",       80),
    ("Icon-App-40x40@3x.png",      120),
    ("Icon-App-60x60@2x.png",      120),
    ("Icon-App-60x60@3x.png",      180),
    ("Icon-App-76x76@1x.png",       76),
    ("Icon-App-76x76@2x.png",      152),
    ("Icon-App-83.5x83.5@2x.png",  167),
    ("Icon-App-1024x1024@1x.png", 1024),
]


def main() -> None:
    if not APPICON_DIR.is_dir():
        sys.exit(f"ERROR: appiconset directory not found at {APPICON_DIR}")
    if not MASTER_FILE.is_file():
        sys.exit(f"ERROR: master icon not found at {MASTER_FILE}")

    print(f"A#73 icon regeneration")
    print(f"  appiconset: {APPICON_DIR}")
    print(f"  master:     {MASTER_FILE.name}")
    print(f"  background: #A93105  RGB{BG_RGB}")
    print()

    # Load master once and composite onto a fresh tan canvas at 1024.
    # The master has a transparent background; we keep its full opaque pixels
    # and fill everything else with #A93105.
    src = Image.open(MASTER_FILE).convert("RGBA")
    canvas_1024 = Image.new("RGBA", src.size, BG_RGB + (255,))
    canvas_1024.alpha_composite(src)
    # iOS App Store rejects icons with alpha channels — flatten to RGB.
    master_rgb = canvas_1024.convert("RGB")

    written = 0
    for name, size in VARIANTS:
        out_path = APPICON_DIR / name
        if size == master_rgb.size[0]:
            img = master_rgb
        else:
            img = master_rgb.resize((size, size), Image.LANCZOS)
        img.save(out_path, format="PNG", optimize=True)
        print(f"  wrote {name:<32} {size:>4}x{size}  {out_path.stat().st_size:>7,} bytes")
        written += 1

    print()
    print(f"OK: wrote {written}/{len(VARIANTS)} icon files.")
    print("Next: cd audio_tour_app && flutter clean && flutter pub get,")
    print("      then ./build_install_launch.sh.")


if __name__ == "__main__":
    main()
