import os
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_THUMB = os.path.join(BASE_DIR, "assets", "orig_thumb_-qkpDZ1XPOs.jpg")
OUT_DIR = os.path.join(BASE_DIR, "output", "thumbnails")
os.makedirs(OUT_DIR, exist_ok=True)

FONT_EXTRABOLD = os.path.join(BASE_DIR, "assets", "Montserrat-ExtraBold.ttf")


def draw_mic_icon(draw, cx, cy, size=22, color=(212, 24, 32, 255)):
    """Draws a crisp podcast studio microphone icon with clean capsule + U-cradle spacing."""
    # Upper mic capsule
    cap_w = size * 0.48
    cap_h = size * 0.86
    cx0 = cx - cap_w / 2
    cy0 = cy - size * 0.62
    cx1 = cx + cap_w / 2
    cy1 = cy0 + cap_h
    draw.rounded_rectangle([cx0, cy0, cx1, cy1], radius=int(cap_w / 2), fill=color)

    # U-cradle arc wrapping lower half of capsule with clear spacing
    stroke = max(3, round(size * 0.12))
    arc_r = size * 0.44
    arc_top = cy0 + cap_h * 0.35
    arc_bot = cy1 + size * 0.22
    draw.arc([cx - arc_r, arc_top, cx + arc_r, arc_bot], start=0, end=180, fill=color, width=stroke)

    # Stem and flat stand base
    stem_top = arc_bot - 1
    stem_bot = stem_top + size * 0.26
    draw.line([(cx, stem_top), (cx, stem_bot)], fill=color, width=stroke)
    base_half = size * 0.32
    draw.line([(cx - base_half, stem_bot), (cx + base_half, stem_bot)], fill=color, width=stroke)


def draw_clean_headline(draw, pos, text, font, fill, contour_px=0, contour_color=(12, 16, 26, 240), shadow_offset=(5, 7)):
    """Renders crisp headline typography matching studio reference: heavy shadow, optional subtle contour."""
    x, y = pos
    sx, sy = shadow_offset
    # Crisp directional drop shadow (bottom-right)
    draw.text((x + sx, y + sy), text, font=font, fill=(5, 8, 16, 235))
    draw.text((x + sx + 2, y + sy + 3), text, font=font, fill=(5, 8, 16, 150))

    if contour_px > 0:
        draw.text(
            (x, y),
            text,
            font=font,
            fill=fill,
            stroke_width=contour_px,
            stroke_fill=contour_color,
        )
    else:
        draw.text((x, y), text, font=font, fill=fill)


def create_hd_recreation(output_path: str):
    W, H = 1920, 1080
    src = Image.open(SRC_THUMB).convert("RGB")

    # Upscale source portrait cleanly to Full HD 1920x1080
    src_hd = src.resize((W, H), Image.Resampling.LANCZOS)

    # Subtle clarity & portrait polish for sharp Full HD face & hair texture
    src_hd = ImageEnhance.Sharpness(src_hd).enhance(1.25)
    src_hd = ImageEnhance.Contrast(src_hd).enhance(1.04)
    src_hd = ImageEnhance.Color(src_hd).enhance(1.03)

    # Clean vertical studio slate-blue gradient matching reference right canvas
    y_coords = np.linspace(0, 1, H)
    stops_y = np.array([0.0, 0.22, 0.45, 0.72, 1.0])
    stops_r = np.array([211, 154, 104, 76, 53])
    stops_g = np.array([224, 172, 124, 95, 73])
    stops_b = np.array([240, 202, 156, 127, 106])

    grad_r = np.interp(y_coords, stops_y, stops_r).astype(np.uint8)
    grad_g = np.interp(y_coords, stops_y, stops_g).astype(np.uint8)
    grad_b = np.interp(y_coords, stops_y, stops_b).astype(np.uint8)

    grad_col = np.stack([grad_r, grad_g, grad_b], axis=1)
    grad_arr = np.broadcast_to(grad_col[:, None, :], (H, W, 3)).copy()
    canvas_bg = Image.fromarray(grad_arr, mode="RGB").convert("RGBA")

    # Feather portrait cleanly BEFORE x=805 (so 0 pixels of the old text/silver band remain)
    mask_x = np.linspace(0, W - 1, W)
    alpha_x = np.clip((800.0 - mask_x) / (800.0 - 705.0), 0.0, 1.0)
    alpha_x = 0.5 - 0.5 * np.cos(np.pi * alpha_x)
    alpha_2d = (np.broadcast_to(alpha_x[None, :], (H, W)) * 255).astype(np.uint8)
    portrait_mask = Image.fromarray(alpha_2d, mode="L")

    composed = Image.composite(src_hd.convert("RGBA"), canvas_bg, portrait_mask)

    # Clean horizontal silver/metallic highlight band behind "EL TONTO" (y: 486..652)
    band_y0, band_y1 = 486, 652
    band_h = band_y1 - band_y0
    band_arr = np.zeros((H, W, 4), dtype=np.uint8)
    band_alpha_x = np.clip((mask_x - 620.0) / (890.0 - 620.0), 0.0, 1.0)
    band_alpha_x = 0.5 - 0.5 * np.cos(np.pi * band_alpha_x)

    band_colors = np.zeros((band_h, W, 4), dtype=np.uint8)
    for row in range(band_h):
        t = row / max(1, band_h - 1)
        lum = int(204 + 24 * np.sin(np.pi * t))
        a_row = (band_alpha_x * 215).astype(np.uint8)
        band_colors[row, :, 0] = lum
        band_colors[row, :, 1] = min(255, lum + 3)
        band_colors[row, :, 2] = min(255, lum + 7)
        band_colors[row, :, 3] = a_row

    band_arr[band_y0:band_y1, :, :] = band_colors
    composed = Image.alpha_composite(composed, Image.fromarray(band_arr, mode="RGBA"))

    # Crisp Typography Layer at Full HD 1920x1080
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)

    font_white = ImageFont.truetype(FONT_EXTRABOLD, 134)
    font_red = ImageFont.truetype(FONT_EXTRABOLD, 140)
    font_yellow = ImageFont.truetype(FONT_EXTRABOLD, 128)
    font_badge = ImageFont.truetype(FONT_EXTRABOLD, 38)

    center_x = 1350
    lines = [
        ("EL ARTE DE", font_white, (255, 255, 255, 255), 148, 0, (6, 8)),
        ("HACERSE", font_white, (255, 255, 255, 255), 312, 0, (6, 8)),
        ("EL TONTO", font_red, (242, 14, 14, 255), 488, 3, (7, 9)),
        ("A LOS 60 AÑOS", font_yellow, (255, 224, 38, 255), 676, 4, (7, 9)),
    ]

    for text, fnt, color, y_pos, c_px, soff in lines:
        bbox = draw.textbbox((0, 0), text, font=fnt)
        lw = bbox[2] - bbox[0]
        x_pos = center_x - lw // 2 - bbox[0]
        draw_clean_headline(
            draw,
            (x_pos, y_pos),
            text,
            font=fnt,
            fill=color,
            contour_px=c_px,
            contour_color=(12, 16, 24, 235),
            shadow_offset=soff,
        )

    # Upgraded Channel Authority Speaker Badge: Crimson Red Pill + White Text & Mic + Gold Outline
    badge_text = "DRA. NAZARETH CASTELLANOS"
    tbbox = draw.textbbox((0, 0), badge_text, font=font_badge)
    tw = tbbox[2] - tbbox[0]
    th = tbbox[3] - tbbox[1]

    pill_h = 84
    mic_area_w = 72
    pad_left = 22
    pad_right = 34
    pill_w = pad_left + mic_area_w + tw + pad_right

    px0 = center_x - pill_w // 2
    py0 = 884
    px1 = px0 + pill_w
    py1 = py0 + pill_h

    # Soft pill drop shadow
    shadow_pill = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    sp_draw = ImageDraw.Draw(shadow_pill)
    sp_draw.rounded_rectangle([px0 + 4, py0 + 8, px1 + 4, py1 + 8], radius=pill_h // 2, fill=(0, 0, 0, 175))
    shadow_pill = shadow_pill.filter(ImageFilter.GaussianBlur(radius=6))
    composed = Image.alpha_composite(composed, shadow_pill)

    # Red Pill Body with Crisp Gold Rim
    draw.rounded_rectangle(
        [px0, py0, px1, py1],
        radius=pill_h // 2,
        fill=(212, 22, 30, 255),
        outline=(255, 224, 64, 240),
        width=3,
    )

    # White circular emblem + Crimson Mic icon
    mic_cx = px0 + pad_left + 27
    mic_cy = (py0 + py1) // 2
    draw.ellipse([mic_cx - 27, mic_cy - 27, mic_cx + 27, mic_cy + 27], fill=(255, 255, 255, 255))
    draw_mic_icon(draw, mic_cx, mic_cy, size=24, color=(212, 22, 30, 255))

    # Crisp Pure White Bold Speaker Name
    tx = px0 + pad_left + mic_area_w + 4
    ty = py0 + (pill_h - th) // 2 - tbbox[1]
    draw.text((tx + 2, ty + 2), badge_text, font=font_badge, fill=(75, 0, 0, 190))
    draw.text((tx, ty), badge_text, font=font_badge, fill=(255, 255, 255, 255))

    final = Image.alpha_composite(composed, txt_layer).convert("RGB")
    final.save(output_path, "JPEG", quality=96, subsampling=0)
    print(f"Created Full HD thumbnail: {output_path} ({final.size[0]}x{final.size[1]}, {os.path.getsize(output_path)/1024:.1f} KB)")


if __name__ == "__main__":
    out_file = os.path.join(OUT_DIR, "thumb_-qkpDZ1XPOs_hd.jpg")
    create_hd_recreation(out_file)
