import os
import sys
from PIL import Image, ImageDraw, ImageFont

TEMPLATE_PATH = r"d:\youtube-automation-flows\motivational-flow\temp\clean_v1_plate.jpg"
FONT_TREBUCHET = r"C:\Windows\Fonts\trebucbd.ttf"
OUTPUT_DIR = r"d:\youtube-automation-flows\motivational-flow\output\thumbnails"
os.makedirs(OUTPUT_DIR, exist_ok=True)

COLOR_YELLOW = (254, 218, 98, 255)   # #FEDA62
COLOR_RED = (244, 52, 56, 255)       # #F43438
COLOR_WHITE = (255, 255, 255, 255)
COLOR_SHADOW = (0, 0, 0, 240)

def render_thumbnail(
    title_lines,
    highlight_line_idx=2,
    speaker_lines=("NAZARETH", "CASTELLANOS"),
    output_filename="thumb.jpg",
    font_size_main=76,
    font_size_speaker=68,
    y_start=130
):
    base = Image.open(TEMPLATE_PATH).convert("RGBA")
    w, h = base.size
    
    txt_layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    draw = ImageDraw.Draw(txt_layer)
    
    font_main = ImageFont.truetype(FONT_TREBUCHET, font_size_main)
    font_speaker = ImageFont.truetype(FONT_TREBUCHET, font_size_speaker)
    
    center_x = 865
    y_current = y_start
    line_spacing = 14
    
    for idx, line in enumerate(title_lines):
        line = line.strip().upper()
        if not line:
            continue
        color = COLOR_RED if idx == highlight_line_idx else COLOR_YELLOW
        bbox = font_main.getbbox(line)
        line_w = bbox[2] - bbox[0]
        line_h = bbox[3] - bbox[1]
        x_pos = center_x - line_w // 2
        
        # Deep drop shadow
        for ox, oy in [(3, 4), (4, 5), (5, 6), (2, 3)]:
            draw.text((x_pos + ox, y_current + oy), line, font=font_main, fill=COLOR_SHADOW)
        # Black outline
        for ox in [-2, -1, 1, 2]:
            for oy in [-2, -1, 1, 2]:
                draw.text((x_pos + ox, y_current + oy), line, font=font_main, fill=(15, 10, 10, 220))
        # Foreground text
        draw.text((x_pos, y_current), line, font=font_main, fill=color)
        y_current += line_h + line_spacing

    # Speaker tag
    if speaker_lines:
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
    out_path = os.path.join(OUTPUT_DIR, output_filename)
    final.save(out_path, "JPEG", quality=95)
    print(f"Generated: {out_path}")
    return out_path

VIDEOS_CONFIG = [
    {
        "id": "0z_cqFdncrE",
        "file": "thumb_0z_cqFdncrE_habitacion.jpg",
        "title_lines": ["¿POR QUÉ OLVIDAS", "AL ENTRAR A UNA", "HABITACIÓN?"],
        "highlight_idx": 2,
        "speaker": ["NAZARETH", "CASTELLANOS"],
        "font_size": 74,
        "y_start": 130
    },
    {
        "id": "UviitFGauks",
        "file": "thumb_UviitFGauks_olvidas_leido.jpg",
        "title_lines": ["¿POR QUÉ OLVIDAS", "TODO LO QUE", "LEES?"],
        "highlight_idx": 2,
        "speaker": ["NAZARETH", "CASTELLANOS"],
        "font_size": 76,
        "y_start": 130
    },
    {
        "id": "GzLAt0dRXx8",
        "file": "thumb_GzLAt0dRXx8_camina_cerebro.jpg",
        "title_lines": ["CAMINA 20 MINUTOS", "Y MIRA TU", "CEREBRO"],
        "highlight_idx": 2,
        "speaker": ["NAZARETH", "CASTELLANOS"],
        "font_size": 72,
        "y_start": 130
    },
    {
        "id": "TScApOCz26M",
        "file": "thumb_TScApOCz26M_senales_cerebro.jpg",
        "title_lines": ["3 SEÑALES DE QUE", "TU CEREBRO PIDE", "AYUDA URGENTE"],
        "highlight_idx": 2,
        "speaker": ["NAZARETH", "CASTELLANOS"],
        "font_size": 72,
        "y_start": 130
    },
    {
        "id": "rjtLmdpyPK0",
        "file": "thumb_rjtLmdpyPK0_frotar_manos.jpg",
        "title_lines": ["FROTA TUS MANOS", "DURANTE 30 SEGUNDOS", "Y MIRA ESTO"],
        "highlight_idx": 2,
        "speaker": ["NAZARETH", "CASTELLANOS"],
        "font_size": 68,
        "y_start": 135
    },
    {
        "id": "rBEj6P5DX5M",
        "file": "thumb_rBEj6P5DX5M_soltar_aprobacion.jpg",
        "title_lines": ["DEJA DE BUSCAR", "APROBACIÓN AJENA", "Y SÉ LIBRE"],
        "highlight_idx": 2,
        "speaker": ["SABIDURÍA", "DIARIA"],
        "font_size": 72,
        "y_start": 130
    },
    {
        "id": "7lAo07dCaH8",
        "file": "thumb_7lAo07dCaH8_renacer_60.jpg",
        "title_lines": ["15 CLAVES PARA", "RENACER DESPUÉS", "DE LOS 60"],
        "highlight_idx": 2,
        "speaker": ["SABIDURÍA", "DIARIA"],
        "font_size": 72,
        "y_start": 130
    },
    {
        "id": "3uvKz0WZsdc",
        "file": "thumb_3uvKz0WZsdc_respira_lento.jpg",
        "title_lines": ["RESPIRA LENTO", "DURANTE 60 SEGUNDOS", "Y CALMA TU MENTE"],
        "highlight_idx": 2,
        "speaker": ["NAZARETH", "CASTELLANOS"],
        "font_size": 68,
        "y_start": 135
    }
]

if __name__ == "__main__":
    generated_files = []
    for item in VIDEOS_CONFIG:
        path = render_thumbnail(
            title_lines=item["title_lines"],
            highlight_line_idx=item["highlight_idx"],
            speaker_lines=item["speaker"],
            output_filename=item["file"],
            font_size_main=item["font_size"],
            y_start=item["y_start"]
        )
        generated_files.append(path)
    print(f"\nSuccessfully rendered {len(generated_files)} high-CTR thumbnails!")
