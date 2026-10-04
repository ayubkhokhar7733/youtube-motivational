# -*- coding: utf-8 -*-
"""
core/youtube_extractor.py — YouTube Audio & Metadata Downloader, Groq Whisper Transcriber,
and Speaker Attribution Badge Generator for the Motivational Video Engine.
"""

import os
import sys
import json
import re
import time
import subprocess
import requests
from PIL import Image, ImageDraw, ImageFont, ImageOps
import imageio_ffmpeg
from openai import OpenAI
import config

# ---------------------------------------------------------------------------
# 1. YouTube Audio & Metadata Extraction (yt-dlp)
# ---------------------------------------------------------------------------

def extract_youtube_audio_and_metadata(url: str, output_dir: str = None) -> dict:
    """
    Downloads audio track and extracts comprehensive metadata from a YouTube URL.
    Returns: dict with audio_path, title, description, tags, uploader, duration, thumbnail_url, video_id.
    """
    import yt_dlp

    if not output_dir:
        output_dir = config.TEMP_DIR
    os.makedirs(output_dir, exist_ok=True)

    print(f"[youtube_extractor] Fetching audio & metadata from: {url}")

    # yt-dlp configuration to fetch highest quality audio converted to mp3
    ydl_opts = {
        "format": "bestaudio/best",
        "outtmpl": os.path.join(output_dir, "%(id)s_source.%(ext)s"),
        "ffmpeg_location": imageio_ffmpeg.get_ffmpeg_exe(),
        "postprocessors": [{
            "key": "FFmpegExtractAudio",
            "preferredcodec": "mp3",
            "preferredquality": "192",
        }],
        "quiet": False,
        "no_warnings": True,
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        video_id = info.get("id", "source_video")
        title = info.get("title", "Motivational Speech")
        description = info.get("description", "")
        tags = info.get("tags", [])
        uploader = info.get("uploader", "Motivational Speaker")
        duration = info.get("duration", 0)
        thumbnail_url = info.get("thumbnail", "")

        expected_audio_path = os.path.join(output_dir, f"{video_id}_source.mp3")
        if not os.path.exists(expected_audio_path):
            # Fallback search for any newly created mp3 in output_dir
            candidates = [
                os.path.join(output_dir, f)
                for f in os.listdir(output_dir)
                if f.startswith(video_id) and f.endswith(".mp3")
            ]
            if candidates:
                expected_audio_path = candidates[0]
            else:
                raise FileNotFoundError(f"Failed to extract audio MP3 for video ID: {video_id}")

    print(f"[youtube_extractor] Downloaded audio: {expected_audio_path} ({duration}s, {os.path.getsize(expected_audio_path) / 1024 / 1024:.2f} MB)")

    return {
        "audio_path": expected_audio_path,
        "video_id": video_id,
        "title": title,
        "description": description,
        "tags": tags,
        "uploader": uploader,
        "duration": duration,
        "thumbnail_url": thumbnail_url,
        "webpage_url": url,
    }


# ---------------------------------------------------------------------------
# 2. Audio Compression for Groq API (25 MB limit safeguard)
# ---------------------------------------------------------------------------

def compress_audio_if_needed(audio_path: str, max_mb: float = 24.0) -> str:
    """
    Checks audio file size. If over max_mb, converts to 64kbps mono MP3
    which preserves voice clarity while drastically reducing file size (~0.48 MB/min).
    """
    if not os.path.exists(audio_path):
        return audio_path

    size_mb = os.path.getsize(audio_path) / (1024 * 1024)
    if size_mb <= max_mb:
        return audio_path

    print(f"[youtube_extractor] Audio size ({size_mb:.2f} MB) exceeds {max_mb} MB. Compressing for Whisper API...")
    compressed_path = audio_path.rsplit(".", 1)[0] + "_compressed.mp3"
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()

    cmd = [
        ffmpeg_exe, "-y", "-nostdin",
        "-i", audio_path,
        "-ac", "1",
        "-ar", "16000",
        "-b:a", "64k",
        compressed_path
    ]
    res = subprocess.run(cmd, capture_output=True, stdin=subprocess.DEVNULL)
    if res.returncode == 0 and os.path.exists(compressed_path):
        new_size_mb = os.path.getsize(compressed_path) / (1024 * 1024)
        print(f"[youtube_extractor] Audio compressed to {new_size_mb:.2f} MB.")
        return compressed_path

    return audio_path


# ---------------------------------------------------------------------------
# 3. Speech Transcription via Groq Whisper API (Word-Level Sync)
# ---------------------------------------------------------------------------

def _sec_to_srt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds - int(seconds)) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def transcribe_audio_groq(audio_path: str, srt_output_path: str = None) -> dict:
    """
    Transcribes audio using Groq Whisper API (whisper-large-v3).
    Returns transcript text, millisecond word timestamps, segments, and writes .srt subtitles.
    """
    import config
    config.reload()
    api_key = config.GROQ_API_KEY
    if not api_key:
        raise ValueError("GROQ_API_KEY is not configured in .env or user_settings.json.")

    client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)

    usable_audio = compress_audio_if_needed(audio_path)

    print(f"[youtube_extractor] Transcribing speech with Groq Whisper (whisper-large-v3)...")
    start_t = time.time()

    with open(usable_audio, "rb") as f:
        response = client.audio.transcriptions.create(
            model="whisper-large-v3",
            file=f,
            response_format="verbose_json",
            timestamp_granularities=["word", "segment"],
        )

    transcription_time = time.time() - start_t
    print(f"[youtube_extractor] Whisper transcription completed in {transcription_time:.1f}s.")

    transcript_text = getattr(response, "text", "") or ""
    segments = getattr(response, "segments", []) or []
    words = getattr(response, "words", []) or []

    if not srt_output_path:
        srt_output_path = os.path.join(config.TEMP_DIR, "subtitles.srt")
    os.makedirs(os.path.dirname(srt_output_path), exist_ok=True)

    # Build word-level / short-phrase SRT chunks for fast dynamic subtitle display
    srt_blocks = []
    block_idx = 1

    if words:
        # Group words into 3-4 word rapid subtitle bursts
        current_burst = []
        for i, w in enumerate(words):
            w_text = w.get("word", "") if isinstance(w, dict) else getattr(w, "word", "")
            w_start = w.get("start", 0.0) if isinstance(w, dict) else getattr(w, "start", 0.0)
            w_end = w.get("end", 0.0) if isinstance(w, dict) else getattr(w, "end", 0.0)

            current_burst.append((w_start, w_end, w_text.strip()))
            is_terminal = w_text.strip().endswith((".", "?", "!", ":", ";"))
            
            # Check for vocal pause
            has_pause = False
            if i + 1 < len(words):
                next_w = words[i + 1]
                next_start = next_w.get("start", 0.0) if isinstance(next_w, dict) else getattr(next_w, "start", 0.0)
                if next_start - w_end > 0.4:
                    has_pause = True

            if len(current_burst) >= 3 or is_terminal or has_pause or i == len(words) - 1:
                b_start = current_burst[0][0]
                b_end = current_burst[-1][1]
                b_text = " ".join(item[2] for item in current_burst).strip()
                if b_text:
                    srt_blocks.append(f"{block_idx}\n{_sec_to_srt_time(b_start)} --> {_sec_to_srt_time(b_end)}\n{b_text}\n")
                    block_idx += 1
                current_burst = []
    elif segments:
        for seg in segments:
            s_start = seg.get("start", 0.0) if isinstance(seg, dict) else getattr(seg, "start", 0.0)
            s_end = seg.get("end", 0.0) if isinstance(seg, dict) else getattr(seg, "end", 0.0)
            s_text = (seg.get("text", "") if isinstance(seg, dict) else getattr(seg, "text", "")).strip()
            if s_text:
                srt_blocks.append(f"{block_idx}\n{_sec_to_srt_time(s_start)} --> {_sec_to_srt_time(s_end)}\n{s_text}\n")
                block_idx += 1

    with open(srt_output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(srt_blocks))

    print(f"[youtube_extractor] Saved {len(srt_blocks)} subtitle entries to {srt_output_path}")

    return {
        "transcript": transcript_text,
        "srt_path": srt_output_path,
        "segments": segments,
        "words": words,
        "transcription_time_sec": transcription_time,
    }


# ---------------------------------------------------------------------------
# 4. Speaker Identification & Photo Badge Generation
# ---------------------------------------------------------------------------

KNOWN_SPEAKERS = {
    "david goggins": {"name": "David Goggins", "title": "Ultra-Endurance Athlete & Author"},
    "jocko willink": {"name": "Jocko Willink", "title": "Retired Navy SEAL Commander & Author"},
    "steve jobs": {"name": "Steve Jobs", "title": "Visionary & Apple Co-Founder"},
    "kobe bryant": {"name": "Kobe Bryant", "title": "5x NBA Champion & Mamba Mentality"},
    "jordan peterson": {"name": "Jordan Peterson", "title": "Clinical Psychologist & Author"},
    "denzel washington": {"name": "Denzel Washington", "title": "Academy Award Winning Actor"},
    "arnold schwarzenegger": {"name": "Arnold Schwarzenegger", "title": "Champion Bodybuilder & Leader"},
    "les brown": {"name": "Les Brown", "title": "Legendary Motivational Speaker"},
    "eric thomas": {"name": "Eric Thomas", "title": "Hip Hop Preacher & Speaker"},
    "marcus aurelius": {"name": "Marcus Aurelius", "title": "Stoic Philosopher & Roman Emperor"},
    "andrew huberman": {"name": "Andrew Huberman", "title": "Neuroscientist & Professor"},
    "elon musk": {"name": "Elon Musk", "title": "Engineer & Entrepreneur"},
}


def detect_speaker_info(video_title: str, video_desc: str, transcript: str) -> dict:
    """
    Identifies the primary motivational speaker using pattern matching and Groq LLM.
    """
    # 1. Fast match against known popular motivational speakers
    combined_search = f"{video_title} {video_desc[:300]}".lower()
    for key, info in KNOWN_SPEAKERS.items():
        if key in combined_search:
            return {
                "name": info["name"],
                "role": info["title"],
                "confidence": 1.0,
            }

    # 2. Use Groq LLM for intelligent extraction if not an instant match
    try:
        import config
        config.reload()
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=config.GROQ_API_KEY)
        
        prompt = (
            "You are an expert in motivational speeches and personal development podcasts.\n"
            "Given the video title, description, and transcript snippet below, identify:\n"
            "1. The primary speaker's full name (e.g. 'David Goggins', 'Steve Jobs', 'Kobe Bryant', 'Jordan Peterson').\n"
            "2. A short 2-4 word professional descriptor (e.g. 'Author & Athlete', 'Visionary & Entrepreneur', 'Stoic Philosopher').\n"
            "If the speaker is unknown or anonymous, return 'Motivational Speaker'.\n\n"
            f"TITLE: {video_title}\n"
            f"DESCRIPTION SNIPPET: {video_desc[:400]}\n"
            f"TRANSCRIPT SNIPPET: {transcript[:500]}\n\n"
            "Return strictly valid JSON: {\"speaker_name\": \"...\", \"role\": \"...\"}"
        )
        resp = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.2,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content.strip())
        return {
            "name": data.get("speaker_name", "Motivational Speaker"),
            "role": data.get("role", "Inspirational Leader"),
            "confidence": 0.85,
        }
    except Exception as e:
        print(f"[youtube_extractor] LLM speaker detection fallback: {e}")
        # Regex search for common naming patterns: "Speaker: [Name]" or "[Name] - Motivational Video"
        match = re.search(r'(?:speaker|speech by|with)\s*[:\-–—]\s*([A-Za-z\s]+)', video_title, re.IGNORECASE)
        if match:
            return {"name": match.group(1).strip().title(), "role": "Motivational Leader", "confidence": 0.6}
        return {"name": "Motivational Leader", "role": "Inspiring Speech", "confidence": 0.5}


def _create_circular_avatar(image_path: str, size: int = 110) -> Image.Image:
    """Crops an image into a circle with anti-aliasing and a stylish accent border."""
    try:
        im = Image.open(image_path).convert("RGBA")
        # Center crop to square
        w, h = im.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = (h - min_dim) // 2
        im = im.crop((left, top, left + min_dim, top + min_dim))
        im = im.resize((size, size), Image.LANCZOS)
    except Exception:
        # Fallback to sleek geometric portrait badge
        im = Image.new("RGBA", (size, size), (24, 28, 38, 255))
        draw_im = ImageDraw.Draw(im)
        draw_im.ellipse([0, 0, size, size], fill=(40, 50, 75, 255))

    # Mask to pure circle
    mask = Image.new("L", (size, size), 0)
    draw_mask = ImageDraw.Draw(mask)
    draw_mask.ellipse([0, 0, size, size], fill=255)

    circle_img = ImageOps.fit(im, (size, size))
    circle_img.putalpha(mask)

    # Add vibrant 4px border ring (#FFDC32 / gold)
    border_img = Image.new("RGBA", (size + 8, size + 8), (0, 0, 0, 0))
    b_draw = ImageDraw.Draw(border_img)
    b_draw.ellipse([2, 2, size + 6, size + 6], outline=(255, 220, 50, 240), width=4)
    border_img.paste(circle_img, (4, 4), circle_img)

    return border_img


def generate_speaker_badge_overlay(
    speaker_name: str,
    speaker_role: str = "",
    avatar_image_path: str = None,
    output_path: str = None,
    width: int = 1920,
    height: int = 1080,
) -> str:
    """
    Renders a transparent 1080p overlay containing:
    1. Circular speaker avatar headshot at top-left.
    2. Polished dark pill capsule with:
       'SPEAKER' (accent gold)
       '{SPEAKER_NAME}' (bold white)
    Saves to output_path and returns absolute path.
    """
    if not output_path:
        output_path = os.path.join(config.TEMP_DIR, "speaker_badge_overlay.png")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 1. Base transparent 1920x1080 canvas
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)

    # Coordinates
    x_pos = 55
    y_pos = 50
    avatar_size = 96

    # Prepare Avatar
    avatar_img = _create_circular_avatar(avatar_image_path, size=avatar_size)
    avatar_w, avatar_h = avatar_img.size

    # Font handling
    font_path = config.FONT_PATH if os.path.exists(config.FONT_PATH) else "arialbd.ttf"
    try:
        font_label = ImageFont.truetype(font_path, 15)
        font_name = ImageFont.truetype(font_path, 26)
        font_role = ImageFont.truetype(font_path, 14)
    except Exception:
        font_label = ImageFont.load_default()
        font_name = ImageFont.load_default()
        font_role = ImageFont.load_default()

    display_name = speaker_name.upper().strip()
    name_bbox = draw.textbbox((0, 0), display_name, font=font_name)
    name_w = name_bbox[2] - name_bbox[0]

    # Calculate pill background size
    pill_padding_x = 24
    pill_w = max(220, name_w + avatar_w + pill_padding_x * 2 + 15)
    pill_h = avatar_h + 12

    # Draw rounded pill capsule backdrop (dark semi-transparent with thin border)
    pill_x1 = x_pos + avatar_w // 2
    pill_y1 = y_pos + (avatar_h - pill_h) // 2
    pill_x2 = pill_x1 + pill_w
    pill_y2 = pill_y1 + pill_h

    # Rounded rectangle capsule background
    draw.rounded_rectangle(
        [pill_x1, pill_y1, pill_x2, pill_y2],
        radius=26,
        fill=(12, 16, 24, 215),
        outline=(255, 220, 50, 160),
        width=2,
    )

    # Paste circular avatar on the left side overlapping the pill
    canvas.paste(avatar_img, (x_pos, y_pos), avatar_img)

    # Text coordinates inside pill
    text_x = x_pos + avatar_w + 18
    text_y_label = pill_y1 + 12
    text_y_name = text_y_label + 20

    # Draw "SPEAKER" badge
    draw.text((text_x, text_y_label), "SPEAKER", font=font_label, fill=(255, 220, 50, 255))

    # Draw Speaker Name
    draw.text((text_x, text_y_name), display_name, font=font_name, fill=(255, 255, 255, 255))

    # Optional role / bio
    if speaker_role:
        text_y_role = text_y_name + 30
        draw.text((text_x, text_y_role), speaker_role.upper()[:30], font=font_role, fill=(180, 195, 215, 220))

    canvas.save(output_path, "PNG")
    print(f"[youtube_extractor] Created speaker badge overlay at: {output_path}")
    return output_path
