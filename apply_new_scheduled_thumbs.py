import os
import sys
from PIL import Image, ImageDraw, ImageFont
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
import google.auth.transport.requests

TEMPLATE_PATH = r"d:\youtube-automation-flows\motivational-flow\temp\clean_v1_plate.jpg"
FONT_TREBUCHET = r"C:\Windows\Fonts\trebucbd.ttf"
OUTPUT_DIR = r"d:\youtube-automation-flows\motivational-flow\output\thumbnails"

COLOR_YELLOW = (254, 218, 98, 255)
COLOR_RED = (244, 52, 56, 255)
COLOR_WHITE = (255, 255, 255, 255)
COLOR_SHADOW = (0, 0, 0, 240)

def render_thumb(title_lines, highlight_idx, speaker_lines, filename, font_size=72):
    base = Image.open(TEMPLATE_PATH).convert("RGBA")
    w, h = base.size
    txt_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    font_main = ImageFont.truetype(FONT_TREBUCHET, font_size)
    font_speaker = ImageFont.truetype(FONT_TREBUCHET, 68)

    center_x = 865
    y_current = 130
    line_spacing = 14

    for idx, line in enumerate(title_lines):
        line = line.strip().upper()
        color = COLOR_RED if idx == highlight_idx else COLOR_YELLOW
        bbox = font_main.getbbox(line)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x_pos = center_x - line_w // 2

        for ox, oy in [(3, 4), (4, 5), (5, 6), (2, 3)]:
            draw.text((x_pos + ox, y_current + oy), line, font=font_main, fill=COLOR_SHADOW)
        for ox in [-2, -1, 1, 2]:
            for oy in [-2, -1, 1, 2]:
                draw.text((x_pos + ox, y_current + oy), line, font=font_main, fill=(15, 10, 10, 220))
        draw.text((x_pos, y_current), line, font=font_main, fill=color)
        y_current += line_h + line_spacing

    y_speaker = max(y_current + 35, 490)
    for sline in speaker_lines:
        sline = sline.strip().upper()
        bbox = font_speaker.getbbox(sline)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x_pos = center_x - line_w // 2
        for ox, oy in [(3, 4), (4, 5)]:
            draw.text((x_pos + ox, y_speaker + oy), sline, font=font_speaker, fill=COLOR_SHADOW)
        for ox in [-2, -1, 1, 2]:
            for oy in [-2, -1, 1, 2]:
                draw.text((x_pos + ox, y_speaker + oy), sline, font=font_speaker, fill=(15, 10, 10, 220))
        draw.text((x_pos, y_speaker), sline, font=font_speaker, fill=COLOR_WHITE)
        y_speaker += line_h + 12

    final = Image.alpha_composite(base, txt_layer).convert("RGB")
    out_path = os.path.join(OUTPUT_DIR, filename)
    final.save(out_path, "JPEG", quality=95)
    return out_path

# Generate new thumbnails
p1 = render_thumb(
    title_lines=["¿POR QUÉ NUNCA", "TERMINAS LO QUE", "EMPIEZAS?"],
    highlight_idx=2,
    speaker_lines=["SABIDURÍA", "DIARIA"],
    filename="09_Oct24_Programado_No_Terminas_Nada.jpg",
    font_size=72
)

p2 = render_thumb(
    title_lines=["7 SEÑALES DE", "UNA MENTE Y", "CUERPO PODEROSO"],
    highlight_idx=2,
    speaker_lines=["SABIDURÍA", "DIARIA"],
    filename="10_Oct26_Programado_Mente_Cuerpo_Poderosos.jpg",
    font_size=72
)

# Connect to YouTube and upload thumbnails
with open(".env", "r", encoding="utf-8") as f:
    for line in f:
        line = line.strip()
        if line and "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

cid = os.environ.get("YOUTUBE_CLIENT_ID")
csec = os.environ.get("YOUTUBE_CLIENT_SECRET")
rtoken = os.environ.get("YOUTUBE_REFRESH_TOKEN")

creds = Credentials(token=None, refresh_token=rtoken, token_uri="https://oauth2.googleapis.com/token", client_id=cid, client_secret=csec)
creds.refresh(google.auth.transport.requests.Request())
youtube = build("youtube", "v3", credentials=creds)

uploads = [
    ("7lAo07dCaH8", os.path.join(OUTPUT_DIR, "08_Privado_15_Claves_Renacer_Despues_60.jpg")),
    ("h-IEgpt5Df4", p1),
    ("y_dWwctUC8Y", p2),
]

for vid, path in uploads:
    if os.path.exists(path):
        print(f"Uploading thumbnail for {vid} ({os.path.basename(path)})...")
        try:
            youtube.thumbnails().set(videoId=vid, media_body=MediaFileUpload(path, mimetype="image/jpeg")).execute()
            print(f"  Successfully attached thumbnail to {vid}!")
        except Exception as e:
            print(f"  Error uploading thumb for {vid}: {e}")
