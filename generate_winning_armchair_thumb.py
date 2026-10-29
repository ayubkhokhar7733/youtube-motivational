import os
import sys
import re
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PLATE_PATH = os.path.join(SCRIPT_DIR, "assets", "clean_armchair_plate.jpg")
OUTPUT_DIR = os.path.join(SCRIPT_DIR, "output", "thumbnails")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# Winning Color Palette
COLOR_YELLOW = (255, 218, 50, 255)     # High-Impact Vibrant Gold / Yellow
COLOR_WHITE  = (255, 255, 255, 255)    # Pure Crisp White
COLOR_RED    = (215, 38, 42, 255)      # Rich Crimson / Red Pill
COLOR_SHADOW = (15, 10, 5, 240)        # Deep contrast shadow


def _get_font(size: int, prefer_heavy: bool = True):
    """Cross-platform font loader that works on Windows, macOS, and Linux (GitHub Actions)."""
    candidates = []
    if sys.platform == "win32":
        if prefer_heavy:
            candidates.extend([
                r"C:\Windows\Fonts\ariblk.ttf",
                r"C:\Windows\Fonts\trebucbd.ttf",
                r"C:\Windows\Fonts\impact.ttf",
                r"C:\Windows\Fonts\arialbd.ttf",
            ])
        else:
            candidates.extend([
                r"C:\Windows\Fonts\trebucbd.ttf",
                r"C:\Windows\Fonts\arialbd.ttf",
            ])
    else:
        # Linux / Ubuntu in GitHub Actions
        candidates.extend([
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ])

    # Repo bundled font fallbacks
    candidates.extend([
        os.path.join(SCRIPT_DIR, "assets", "font_bold.ttf"),
        os.path.join(SCRIPT_DIR, "assets", "font_headline.ttf"),
        os.path.join(SCRIPT_DIR, "assets", "font.ttf"),
    ])

    for p in candidates:
        if p and os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                continue

    return ImageFont.load_default()


def draw_microphone_icon(draw, center_x, center_y, size=18, color=(255, 255, 255, 255)):
    """Draws a crisp podcast microphone icon."""
    bw = size * 0.55
    bh = size * 1.1
    x0 = center_x - bw / 2
    y0 = center_y - bh / 2 - 2
    x1 = center_x + bw / 2
    y1 = y0 + bh
    draw.rounded_rectangle([x0, y0, x1, y1], radius=int(bw / 2), fill=color)

    # Arc / U-stand below mic capsule
    arc_box = [center_x - size * 0.65, y0 + 3, center_x + size * 0.65, y1 + size * 0.4]
    draw.arc(arc_box, start=0, end=180, fill=color, width=3)

    # Stand vertical pole and base
    stem_top = y1 + size * 0.4
    stem_bot = stem_top + size * 0.45
    draw.line([(center_x, stem_top), (center_x, stem_bot)], fill=color, width=3)
    draw.line([(center_x - size * 0.4, stem_bot), (center_x + size * 0.4, stem_bot)], fill=color, width=3)


def render_winning_thumbnail(
    line1="NO HABLES",
    line2="DE TU VIDA",
    speaker_badge="DRA. NAZARETH CASTELLANOS",
    output_filename="thumb_winning_no_hables.jpg",
    font_size=108,
    line_spacing=18,
    center_x=900,
    y_start=240,
) -> str:
    """
    Renders high-CTR thumbnail matching the winning layout:
    - Line 1 in Golden Yellow (e.g. 'NO HABLES')
    - Line 2 in Crisp White (e.g. 'DE TU VIDA')
    - Microphone Pill Badge at the bottom right.
    """
    if not os.path.exists(PLATE_PATH):
        raise FileNotFoundError(f"Plate not found at: {PLATE_PATH}")

    base = Image.open(PLATE_PATH).convert("RGBA")
    w, h = base.size

    txt_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)

    font_main = _get_font(font_size, prefer_heavy=True)
    font_badge = _get_font(30, prefer_heavy=True)

    lines = [
        (line1.strip().upper(), COLOR_YELLOW),
        (line2.strip().upper(), COLOR_WHITE),
    ]

    measured = []
    total_text_h = 0
    max_w = 0
    for text, color in lines:
        if not text:
            continue
        bbox = font_main.getbbox(text)
        lw = bbox[2] - bbox[0]
        lh = bbox[3] - bbox[1]
        measured.append((text, color, lw, lh))
        max_w = max(max_w, lw)
        total_text_h += lh + line_spacing

    total_text_h -= line_spacing

    # 1. Subtle warm translucent horizontal ribbon behind text
    banner_pad_x = 50
    banner_pad_y = 25
    bx0 = max(525, center_x - max_w // 2 - banner_pad_x)
    by0 = y_start - banner_pad_y
    bx1 = min(w - 20, center_x + max_w // 2 + banner_pad_x)
    by1 = y_start + total_text_h + banner_pad_y

    banner_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(banner_layer)
    b_draw.rounded_rectangle([bx0, by0, bx1, by1], radius=20, fill=(110, 60, 25, 90))
    banner_blurred = banner_layer.filter(ImageFilter.GaussianBlur(radius=6))
    txt_layer = Image.alpha_composite(txt_layer, banner_blurred)
    draw = ImageDraw.Draw(txt_layer)

    # 2. Render Text with 3D drop shadow and crisp contour
    y_current = y_start
    for text, color, lw, lh in measured:
        x_pos = center_x - lw // 2

        # 3D Drop shadow
        for ox, oy in [(3, 4), (5, 6), (7, 8), (2, 3), (6, 5)]:
            draw.text((x_pos + ox, y_current + oy), text, font=font_main, fill=COLOR_SHADOW)

        # Edge contour
        for ox in [-3, -2, -1, 1, 2, 3]:
            for oy in [-3, -2, -1, 1, 2, 3]:
                if abs(ox) + abs(oy) <= 4:
                    draw.text((x_pos + ox, y_current + oy), text, font=font_main, fill=(20, 10, 5, 230))

        # Main text fill
        draw.text((x_pos, y_current), text, font=font_main, fill=color)
        y_current += lh + line_spacing

    # 3. Speaker Badge Pill at bottom right
    if speaker_badge:
        s_text = speaker_badge.strip().upper()
        s_bbox = font_badge.getbbox(s_text)
        s_w = s_bbox[2] - s_bbox[0]
        s_h = s_bbox[3] - s_bbox[1]

        icon_size = 22
        icon_gap = 12
        pill_pad_h = 24
        pill_pad_v = 12

        total_pill_w = pill_pad_h * 2 + icon_size + icon_gap + s_w
        total_pill_h = s_h + pill_pad_v * 2

        pill_x1 = w - 40
        pill_x0 = pill_x1 - total_pill_w
        pill_y0 = h - 110
        pill_y1 = pill_y0 + total_pill_h

        # Shadow
        draw.rounded_rectangle(
            [pill_x0 + 4, pill_y0 + 5, pill_x1 + 4, pill_y1 + 5],
            radius=int(total_pill_h / 2),
            fill=(0, 0, 0, 160)
        )

        # Red pill
        draw.rounded_rectangle(
            [pill_x0, pill_y0, pill_x1, pill_y1],
            radius=int(total_pill_h / 2),
            fill=COLOR_RED
        )

        # Mic icon
        mic_cx = pill_x0 + pill_pad_h + icon_size / 2
        mic_cy = pill_y0 + total_pill_h / 2
        draw_microphone_icon(draw, mic_cx, mic_cy, size=icon_size, color=COLOR_WHITE)

        # Speaker name
        s_tx = mic_cx + icon_size / 2 + icon_gap
        s_ty = pill_y0 + (total_pill_h - s_h) / 2 - 2
        draw.text((s_tx, s_ty), s_text, font=font_badge, fill=COLOR_WHITE)

    final = Image.alpha_composite(base, txt_layer).convert("RGB")
    out_path = os.path.join(OUTPUT_DIR, output_filename) if not os.path.isabs(output_filename) else output_filename
    final.save(out_path, "JPEG", quality=95)
    return out_path


if __name__ == "__main__":
    render_winning_thumbnail(
        line1="NO HABLES",
        line2="DE TU VIDA",
        output_filename="thumb_winning_no_hables.jpg"
    )
    print("Done")
