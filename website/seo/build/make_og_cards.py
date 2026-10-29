#!/usr/bin/env python3
"""make_og_cards.py — LOCAL-812.

Generates a 1200x630 Open Graph / Twitter card per tour from a branded
template — NO stock photos. Palette from WEBSITE_BRIEF_audioura_com.md:
deep indigo background + warm amber accent, large rounded sans-serif.

Each card shows: the Audioura wordmark, the tour title (wrapped), the city +
country, and the duration/stops line, over a subtle indigo gradient with an
amber "soundwave" motif (geometry only, drawn with PIL — no external images).
"""
import json
import os

from PIL import Image, ImageDraw, ImageFont

HERE = os.path.dirname(os.path.abspath(__file__))
TOURS = json.load(open(os.path.join(HERE, "tours_data.json"), encoding="utf-8"))
OUT_DIR = os.path.join(HERE, "..", "assets", "og")
os.makedirs(OUT_DIR, exist_ok=True)

W, H = 1200, 630
INDIGO = (26, 23, 58)        # deep indigo base
INDIGO_HI = (46, 42, 96)     # lighter indigo for gradient top
AMBER = (245, 176, 65)       # warm amber accent
CREAM = (247, 245, 240)      # near-white text
MUTED = (182, 178, 205)      # muted lavender for secondary text

ROUND_BOLD = "/System/Library/Fonts/Supplemental/Arial Rounded Bold.ttf"
UNICODE = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
ARIAL = "/System/Library/Fonts/Supplemental/Arial.ttf"


def font(size, bold=True):
    for path in ([ROUND_BOLD] if bold else []) + [UNICODE, ARIAL]:
        try:
            return ImageFont.truetype(path, size)
        except Exception:
            continue
    return ImageFont.load_default()


def wrap(draw, text, fnt, max_w):
    words = text.split()
    lines, cur = [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if draw.textlength(trial, font=fnt) <= max_w:
            cur = trial
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def gradient_bg():
    img = Image.new("RGB", (W, H), INDIGO)
    top, bot = INDIGO_HI, INDIGO
    for y in range(H):
        f = y / H
        r = int(top[0] + (bot[0] - top[0]) * f)
        g = int(top[1] + (bot[1] - top[1]) * f)
        b = int(top[2] + (bot[2] - top[2]) * f)
        for x in range(0, W, W):  # one span per row
            pass
        ImageDraw.Draw(img).line([(0, y), (W, y)], fill=(r, g, b))
    return img


def draw_soundwave(draw, x0, y0, width, height, color):
    """A simple amber equalizer-bar motif — pure geometry, evokes audio."""
    import math
    bars = 34
    gap = width / bars
    bw = gap * 0.5
    for i in range(bars):
        # smooth pseudo-random heights via layered sines (deterministic)
        h = (0.35 + 0.65 * abs(math.sin(i * 0.7) * math.cos(i * 0.31))) * height
        x = x0 + i * gap
        y = y0 + (height - h)
        draw.rounded_rectangle([x, y, x + bw, y0 + height],
                               radius=bw / 2, fill=color)


def make_card(tour):
    img = gradient_bg()
    d = ImageDraw.Draw(img)

    # amber top accent bar
    d.rectangle([0, 0, W, 10], fill=AMBER)

    # Wordmark
    d.text((64, 54), "AUDIOURA", font=font(44), fill=AMBER)
    d.text((66, 108), "Where stories guide you", font=font(24, bold=False),
           fill=MUTED)

    # Soundwave motif bottom-right
    draw_soundwave(d, 760, 430, 376, 120, (245, 176, 65))

    # Title (wrapped) — use the natural H1 without the "— N …" suffix tail
    title = tour["h1"]
    tf = font(60)
    lines = wrap(d, title, tf, W - 128)
    # shrink if too many lines
    while len(lines) > 4 and tf.size > 40:
        tf = font(tf.size - 4)
        lines = wrap(d, title, tf, W - 128)
    y = 210
    for ln in lines:
        d.text((64, y), ln, font=tf, fill=CREAM)
        y += int(tf.size * 1.18)

    # City + duration strip
    sub = "%s, %s" % (tour["city"], tour["country"])
    meta = "%d stops · %d min" % (tour["stops_count"], tour["duration_min"])
    d.text((64, 540), sub, font=font(30), fill=AMBER)
    d.text((64, 584), meta, font=font(24, bold=False), fill=MUTED)

    out = os.path.join(OUT_DIR, "%s.png" % tour["slug"])
    img.save(out, "PNG", optimize=True)
    return out


def make_default_card():
    """Generic card for the /tours/ index, city hubs and pricing."""
    img = gradient_bg()
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 10], fill=AMBER)
    d.text((64, 54), "AUDIOURA", font=font(44), fill=AMBER)
    draw_soundwave(d, 760, 430, 376, 120, AMBER)
    big = font(72)
    for i, ln in enumerate(["Audio tours", "for curious travelers"]):
        d.text((64, 230 + i * 92), ln, font=big, fill=CREAM)
    d.text((64, 540), "Where stories guide you", font=font(32), fill=AMBER)
    d.text((64, 588), "audioura.com", font=font(24, bold=False), fill=MUTED)
    out = os.path.join(OUT_DIR, "default.png")
    img.save(out, "PNG", optimize=True)
    return out


def main():
    for t in TOURS:
        p = make_card(t)
        print("  %-10s %s" % ("%d KB" % (os.path.getsize(p) // 1024),
                              os.path.basename(p)))
    p = make_default_card()
    print("  %-10s %s" % ("%d KB" % (os.path.getsize(p) // 1024),
                          os.path.basename(p)))


if __name__ == "__main__":
    main()
