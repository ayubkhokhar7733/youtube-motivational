import os
import sys
import numpy as np
from PIL import Image, ImageDraw, ImageFont, ImageFilter, ImageEnhance
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import google.auth.transport.requests

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SRC_THUMB = os.path.join(BASE_DIR, "data", "incoming_audio", "xQNt8eJmyOQ_thumb.jpg")
OUT_DIR = os.path.join(BASE_DIR, "output", "thumbnails")
os.makedirs(OUT_DIR, exist_ok=True)

OUT_PATH = os.path.join(OUT_DIR, "thumb_SE48oVlBvek_hd.jpg")
FONT_EXTRABOLD = os.path.join(BASE_DIR, "assets", "Montserrat-ExtraBold.ttf")

def generate_hd_thumbnail(output_path=OUT_PATH):
    W, H = 1920, 1080
    src = Image.open(SRC_THUMB).convert("RGB")
    src_hd = src.resize((W, H), Image.Resampling.LANCZOS)

    # 1. Enhance Portrait: clarity, crisp hair texture, vivid jacket
    enh_sharp = ImageEnhance.Sharpness(src_hd).enhance(1.35)
    enh_contrast = ImageEnhance.Contrast(enh_sharp).enhance(1.05)
    enh_color = ImageEnhance.Color(enh_contrast).enhance(1.06)
    portrait_polished = enh_color

    # 2. Studio background gradient for right canvas
    y_coords = np.linspace(0, 1, H)
    stops_y = np.array([0.0, 0.28, 0.55, 0.80, 1.0])
    stops_r = np.array([168, 140, 110, 68, 38])
    stops_g = np.array([148, 124, 104, 76, 48])
    stops_b = np.array([130, 110, 94, 69, 45])

    grad_r = np.interp(y_coords, stops_y, stops_r).astype(np.uint8)
    grad_g = np.interp(y_coords, stops_y, stops_g).astype(np.uint8)
    grad_b = np.interp(y_coords, stops_y, stops_b).astype(np.uint8)

    grad_col = np.stack([grad_r, grad_g, grad_b], axis=1)
    grad_arr = np.broadcast_to(grad_col[:, None, :], (H, W, 3)).copy()
    canvas_bg = Image.fromarray(grad_arr)

    # 3. Feather portrait cleanly before text
    mask_x = np.linspace(0, W - 1, W)
    alpha_x = np.clip((830.0 - mask_x) / (830.0 - 680.0), 0.0, 1.0)
    alpha_x = 0.5 - 0.5 * np.cos(np.pi * alpha_x)
    alpha_2d = (np.broadcast_to(alpha_x[None, :], (H, W)) * 255).astype(np.uint8)
    portrait_mask = Image.fromarray(alpha_2d)

    composed = Image.composite(portrait_polished.convert("RGBA"), canvas_bg.convert("RGBA"), portrait_mask)

    # 4. Olive horizontal highlight band behind 'CUANDO' (y: 468..622, height 154px)
    band_y0, band_y1 = 468, 622
    band_h = band_y1 - band_y0
    band_alpha_x = np.clip((mask_x - 670.0) / (880.0 - 670.0), 0.0, 1.0)
    band_alpha_x = 0.5 - 0.5 * np.cos(np.pi * band_alpha_x)

    band_arr = np.zeros((H, W, 4), dtype=np.uint8)
    band_colors = np.zeros((band_h, W, 4), dtype=np.uint8)
    for row in range(band_h):
        t = row / max(1, band_h - 1)
        # Gentle edge antialiasing on top/bottom of band
        edge_alpha = np.sin(np.pi * t) ** 0.12
        gr = int(92 + 5 * np.sin(np.pi * t))
        gg = int(106 + 7 * np.sin(np.pi * t))
        gb = int(68 + 4 * np.sin(np.pi * t))
        a_row = (band_alpha_x * 230 * edge_alpha).astype(np.uint8)
        band_colors[row, :, 0] = gr
        band_colors[row, :, 1] = gg
        band_colors[row, :, 2] = gb
        band_colors[row, :, 3] = a_row

    band_arr[band_y0:band_y1, :, :] = band_colors
    band_img = Image.fromarray(band_arr).filter(ImageFilter.GaussianBlur(radius=2))
    composed = Image.alpha_composite(composed, band_img)

    # 5. Crisp Typography Layer
    txt_layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)

    font_l1 = ImageFont.truetype(FONT_EXTRABOLD, 126)
    font_l2 = ImageFont.truetype(FONT_EXTRABOLD, 136)
    font_l3 = ImageFont.truetype(FONT_EXTRABOLD, 142)
    font_badge = ImageFont.truetype(FONT_EXTRABOLD, 38)

    center_x = 1350

    def draw_3d_text(text, font, fill, y_pos, stroke_w=5, stroke_col=(12, 14, 18, 255)):
        bbox = font.getbbox(text)
        tw = bbox[2] - bbox[0]
        tx = center_x - tw // 2
        for step in range(1, 9):
            ox = int(step * 1.1)
            oy = int(step * 1.3)
            draw.text((tx + ox, y_pos + oy), text, font=font, fill=(5, 6, 10, 240))
        draw.text((tx, y_pos), text, font=font, fill=fill, stroke_width=stroke_w, stroke_fill=stroke_col)

    draw_3d_text("ESCUCHA ESTO", font_l1, (255, 255, 255, 255), 312, stroke_w=5)
    draw_3d_text("CUANDO", font_l2, (255, 255, 255, 255), 470, stroke_w=5)
    draw_3d_text("DESPIERTES", font_l3, (255, 224, 20, 255), 634, stroke_w=5)

    # 6. Studio Podcast Mic Pill Badge
    badge_text = "DRA. NAZARETH CASTELLANOS"
    bb = font_badge.getbbox(badge_text)
    btw = bb[2] - bb[0]
    bth = bb[3] - bb[1]

    pill_pad_x = 36
    pill_pad_y = 18
    mic_space = 52
    pill_w = btw + pill_pad_x * 2 + mic_space
    pill_h = bth + pill_pad_y * 2 + 8
    pill_x1 = W - 50
    pill_x0 = pill_x1 - pill_w
    pill_y0 = H - 175
    pill_y1 = pill_y0 + pill_h

    # Shadow behind badge pill
    pill_shadow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ps_draw = ImageDraw.Draw(pill_shadow)
    ps_draw.rounded_rectangle([pill_x0 + 4, pill_y0 + 5, pill_x1 + 4, pill_y1 + 5], radius=int(pill_h // 2), fill=(0, 0, 0, 160))
    pill_shadow_blurred = pill_shadow.filter(ImageFilter.GaussianBlur(radius=5))
    composed = Image.alpha_composite(composed, pill_shadow_blurred)

    # Pill Body
    pill_bg = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    p_draw = ImageDraw.Draw(pill_bg)
    p_draw.rounded_rectangle([pill_x0, pill_y0, pill_x1, pill_y1], radius=int(pill_h // 2), fill=(84, 106, 64, 240))
    composed = Image.alpha_composite(composed, pill_bg)

    # Microphone Icon inside Pill
    mic_cx = pill_x0 + 44
    mic_cy = (pill_y0 + pill_y1) // 2
    size = 26
    cap_w = size * 0.48
    cap_h = size * 0.88
    draw.rounded_rectangle([mic_cx - cap_w/2, mic_cy - size*0.62, mic_cx + cap_w/2, mic_cy - size*0.62 + cap_h], radius=int(cap_w/2), fill=(255, 255, 255, 255))
    draw.arc([mic_cx - size*0.44, mic_cy - size*0.22, mic_cx + size*0.44, mic_cy + size*0.44], start=0, end=180, fill=(255, 255, 255, 255), width=3)
    draw.line([(mic_cx, mic_cy + size*0.44), (mic_cx, mic_cy + size*0.72)], fill=(255, 255, 255, 255), width=3)
    draw.line([(mic_cx - size*0.35, mic_cy + size*0.72), (mic_cx + size*0.35, mic_cy + size*0.72)], fill=(255, 255, 255, 255), width=3)

    # Badge text
    draw.text((pill_x0 + 76, pill_y0 + pill_pad_y - 2), badge_text, font=font_badge, fill=(255, 255, 255, 255))

    final = Image.alpha_composite(composed, txt_layer).convert("RGB")
    final.save(output_path, quality=96)
    print(f"✅ Generated Full HD Thumbnail: {output_path}")
    return output_path

def upload_thumbnail_to_youtube(video_id="SE48oVlBvek", thumb_file=OUT_PATH):
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and "=" in line and not line.startswith("#"):
                    k, v = line.split("=", 1)
                    os.environ[k.strip()] = v.strip()

    cid = os.environ.get("YOUTUBE_CLIENT_ID")
    csec = os.environ.get("YOUTUBE_CLIENT_SECRET")
    rtoken = os.environ.get("YOUTUBE_REFRESH_TOKEN")

    creds = Credentials(
        token=None,
        refresh_token=rtoken,
        token_uri="https://oauth2.googleapis.com/token",
        client_id=cid,
        client_secret=csec
    )
    req = google.auth.transport.requests.Request()
    creds.refresh(req)
    youtube = build("youtube", "v3", credentials=creds)

    print(f"Uploading new High-Quality HD thumbnail to YouTube video {video_id}...")
    request = youtube.thumbnails().set(
        videoId=video_id,
        media_body=MediaFileUpload(thumb_file, mimetype="image/jpeg")
    )
    response = request.execute()
    print("✅ Successfully updated thumbnail on YouTube!")
    print(response)

if __name__ == "__main__":
    vid = sys.argv[1] if len(sys.argv) > 1 else "SE48oVlBvek"
    out = generate_hd_thumbnail()
    upload_thumbnail_to_youtube(video_id=vid, thumb_file=out)
