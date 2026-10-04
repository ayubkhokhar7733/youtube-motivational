#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
thumbnail_gen.py — Automated High-CTR YouTube Thumbnail Generator.

Features:
- Pillow-based 1280x720 (16:9) image creation.
- Uses downloaded stock image or media frame as background, with fallback to textured gradient.
- Applies cinematic dark vignette / contrast backdrop for maximum text legibility.
- Renders high-impact bold typography (2-4 punchy words) with outline, shadow, and accent badges.
"""

import os
import sys
import re
import random
import argparse
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageFilter

# UTF-8 stream handling
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config

THUMB_WIDTH = 1280
THUMB_HEIGHT = 720


def _extract_short_hook_text(topic: str) -> str:
    """Extract 2-4 punchy words suitable for a high-CTR thumbnail."""
    clean = re.sub(r'[:\-–—].*$', '', topic).strip()  # remove subtitle
    words = clean.split()
    if len(words) <= 4:
        return clean.upper()
    
    # Filter common filler words for punchier phrasing
    punchy = [w for w in words if w.lower() not in ("the", "a", "an", "of", "and", "in", "to", "how", "what", "why")]
    if punchy:
        return " ".join(punchy[:3]).upper()
    return " ".join(words[:3]).upper()


def _get_font(size: int):
    font_path = config.FONT_PATH
    if os.path.exists(font_path):
        try:
            return ImageFont.truetype(font_path, size)
        except Exception:
            pass
    # Windows system font fallbacks
    for name in ["impact.ttf", "arialbd.ttf", "segoeuib.ttf", "tahoma.ttf"]:
        try:
            return ImageFont.truetype(name, size)
        except Exception:
            pass
    return ImageFont.load_default()


def _create_fallback_background() -> Image.Image:
    """Create a dark, moody cinematic gradient background."""
    img = Image.new("RGB", (THUMB_WIDTH, THUMB_HEIGHT), (15, 20, 32))
    draw = ImageDraw.Draw(img)

    # Diagonal radial/glow effect
    for r in range(400, 0, -10):
        alpha = int(35 * (1.0 - r / 400))
        color = (25 + alpha, 35 + alpha * 2, 60 + alpha * 3)
        draw.ellipse([800 - r, 360 - r, 800 + r, 360 + r], fill=color)

    # Add dark vignette
    return img


def generate_thumbnail(
    topic: str,
    output_path: str = None,
    background_image_path: str = None,
    overlay_text: str = None,
    badge_text: str = "HISTORICAL MYSTERY",
) -> str:
    """
    Generates a YouTube thumbnail and saves it to output_path.
    Returns the absolute path to the generated JPEG.
    """
    if not output_path:
        safe_topic = re.sub(r'[^a-zA-Z0-9]+', '-', topic).strip('-').lower()[:40]
        output_path = os.path.join(config.OUTPUT_DIR, f"thumb_{safe_topic}.jpg")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. Prepare Base Background
    if background_image_path and os.path.exists(background_image_path):
        try:
            bg = Image.open(background_image_path).convert("RGB")
            # Crop to 16:9
            bg_ratio = bg.width / bg.height
            target_ratio = THUMB_WIDTH / THUMB_HEIGHT
            if bg_ratio > target_ratio:
                new_w = int(bg.height * target_ratio)
                left = (bg.width - new_w) // 2
                bg = bg.crop((left, 0, left + new_w, bg.height))
            else:
                new_h = int(bg.width / target_ratio)
                top = (bg.height - new_h) // 2
                bg = bg.crop((0, top, bg.width, top + new_h))
            bg = bg.resize((THUMB_WIDTH, THUMB_HEIGHT), Image.LANCZOS)
            # Enhance contrast & color saturation
            bg = ImageEnhance.Contrast(bg).enhance(1.25)
            bg = ImageEnhance.Color(bg).enhance(1.20)
        except Exception:
            bg = _create_fallback_background()
    else:
        bg = _create_fallback_background()

    # 2. Add Dark Gradient Overlay on left/bottom for text contrast
    overlay = Image.new("RGBA", (THUMB_WIDTH, THUMB_HEIGHT), (0, 0, 0, 0))
    ov_draw = ImageDraw.Draw(overlay)

    # Gradient from left to right (70% dark to 0% dark)
    for x in range(int(THUMB_WIDTH * 0.75)):
        progress = x / (THUMB_WIDTH * 0.75)
        alpha = int(220 * (1.0 - progress ** 1.5))
        ov_draw.line([(x, 0), (x, THUMB_HEIGHT)], fill=(10, 14, 22, alpha))

    # Bottom vignette bar
    for y in range(THUMB_HEIGHT - 120, THUMB_HEIGHT):
        progress = (y - (THUMB_HEIGHT - 120)) / 120
        alpha = int(160 * progress)
        ov_draw.line([(0, y), (THUMB_WIDTH, y)], fill=(0, 0, 0, alpha))

    bg = Image.alpha_composite(bg.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(bg)

    # 3. Add Category / Hook Badge
    badge_font = _get_font(28)
    badge_x = 60
    badge_y = 50
    badge_text = badge_text.upper()
    badge_bbox = draw.textbbox((0, 0), badge_text, font=badge_font)
    badge_w = badge_bbox[2] - badge_bbox[0] + 30
    badge_h = badge_bbox[3] - badge_bbox[1] + 16

    # Red accent pill
    draw.rounded_rectangle(
        [badge_x, badge_y, badge_x + badge_w, badge_y + badge_h],
        radius=6,
        fill=(220, 38, 38),  # YouTube Red
    )
    draw.text((badge_x + 15, badge_y + 8), badge_text, fill="white", font=badge_font)

    # 4. Add Large High-Impact Headline Text
    hook_text = overlay_text or _extract_short_hook_text(topic)
    main_font_size = 76
    font = _get_font(main_font_size)

    # Wrap words into 2-3 lines
    words = hook_text.split()
    lines = []
    curr = []
    for w in words:
        curr.append(w)
        test_line = " ".join(curr)
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] > (THUMB_WIDTH * 0.60):
            if len(curr) > 1:
                curr.pop()
                lines.append(" ".join(curr))
                curr = [w]
            else:
                lines.append(test_line)
                curr = []
    if curr:
        lines.append(" ".join(curr))
    lines = lines[:3]  # maximum 3 lines

    # Draw bold text with thick outline and drop shadow
    start_y = 160
    line_spacing = main_font_size + 18
    shadow_offset = 6
    outline_width = 4

    colors = ["#FFDC32", "#FFFFFF", "#FFDC32"]  # Yellow and white alternating

    for idx, line in enumerate(lines):
        y = start_y + (idx * line_spacing)
        x = 60
        text_color = colors[idx % len(colors)]

        # Drop shadow
        draw.text((x + shadow_offset, y + shadow_offset), line, fill=(0, 0, 0), font=font)

        # Thick black outline
        for dx in range(-outline_width, outline_width + 1):
            for dy in range(-outline_width, outline_width + 1):
                if dx != 0 or dy != 0:
                    draw.text((x + dx, y + dy), line, fill=(0, 0, 0), font=font)

        # Foreground text
        draw.text((x, y), line, fill=text_color, font=font)

    # 5. Add Left Accent Glow Bar
    draw.rectangle([0, 0, 12, THUMB_HEIGHT], fill=(255, 220, 50))  # Accent Yellow bar

    # 6. Save as High-Quality JPEG
    bg.save(output_path, "JPEG", quality=95, optimize=True)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="YouTube Thumbnail Generator CLI.")
    parser.add_argument("--topic", type=str, default="The Antikythera Mechanism", help="Video topic.")
    parser.add_argument("--text", type=str, default=None, help="Custom bold overlay text.")
    parser.add_argument("--bg", type=str, default=None, help="Path to background image.")
    parser.add_argument("--output", type=str, default=None, help="Output image path.")
    parser.add_argument("--badge", type=str, default="FORBIDDEN HISTORY", help="Badge text.")

    args = parser.parse_args()

    out_file = generate_thumbnail(
        topic=args.topic,
        output_path=args.output,
        background_image_path=args.bg,
        overlay_text=args.text,
        badge_text=args.badge,
    )
    print(f"✅ Thumbnail successfully generated: {out_file}")


if __name__ == "__main__":
    main()
