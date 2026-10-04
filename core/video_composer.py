"""
video_composer.py — Optimised video assembly pipeline.

Key improvements:
- Pool-based clip distribution: each scene has multiple videos + images
- Fast professional pacing: 2-4 s cuts instead of one long looping clip
- Images mixed in as 1.5-2 s flash cuts between video clips
- Subtitles rendered at true screen-bottom with semi-transparent backing bar
- concatenate_videoclips uses method="compose" for proper layering
- FFmpeg: ultrafast preset, 4 threads
- Background music fades in/out for a clean mix
"""

import os
import re
import math
import random
import shutil
import subprocess
import uuid
import threading
import numpy as np
from PIL import Image
from moviepy import (
    VideoFileClip, AudioFileClip,
    CompositeVideoClip, CompositeAudioClip,
    concatenate_videoclips,
    TextClip, ColorClip, ImageClip, VideoClip, afx,
)
import config
import imageio_ffmpeg


# ---------------------------------------------------------------------------
# Image helpers
# ---------------------------------------------------------------------------

def _crop_to_fill(img, target_w, target_h):
    w, h = img.size
    target_ratio = target_w / target_h
    img_ratio    = w / h
    if img_ratio > target_ratio:
        new_w = int(h * target_ratio)
        new_h = h
    else:
        new_w = w
        new_h = int(w / target_ratio)
    left = (w - new_w) // 2
    top  = (h - new_h) // 2
    return img.crop((left, top, left + new_w, top + new_h))


# ---------------------------------------------------------------------------
# Direct FFmpeg chunk generators (Zero-Memory Visual Track Architecture)
# ---------------------------------------------------------------------------

_chunk_counter = 0

def _make_video_chunk(video_path: str, duration: float) -> str:
    """Extracts an exact subclip chunk via direct FFmpeg subprocess with seamless looping. Returns file path."""
    global _chunk_counter
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        target_w, target_h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        
        _chunk_counter += 1
        base = os.path.splitext(os.path.basename(video_path))[0]
        chunk_path = os.path.join(
            os.path.dirname(video_path),
            f"{base}_cut_{_chunk_counter}_{int(duration * 10)}s.mp4"
        )

        vf = f"fps=30,scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"
        cmd = [
            ffmpeg_exe, "-y", "-nostdin",
            "-stream_loop", "-1",
            "-i", video_path,
            "-t", f"{duration:.3f}",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an", chunk_path
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
            return chunk_path
        return None
    except Exception as e:
        print(f"[video_composer] Video chunk error on {video_path}: {e}")
        return None


def _make_image_chunk(image_path: str, duration: float) -> str:
    """Converts a still image into a 30fps MP4 chunk via direct FFmpeg subprocess. Returns file path."""
    global _chunk_counter
    try:
        ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
        target_w, target_h = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
        
        _chunk_counter += 1
        base = os.path.splitext(os.path.basename(image_path))[0]
        chunk_path = os.path.join(
            os.path.dirname(image_path),
            f"{base}_img_{_chunk_counter}_{int(duration * 10)}s.mp4"
        )

        frames = max(1, int(30 * duration))
        vf = (
            f"scale={target_w*2}:{target_h*2},"
            f"zoompan=z='min(zoom+0.0008,1.08)':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={target_w}x{target_h}:fps=30"
        )
        cmd = [
            ffmpeg_exe, "-y", "-nostdin",
            "-loop", "1",
            "-i", image_path,
            "-t", f"{duration:.3f}",
            "-vf", vf,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an", chunk_path
        ]
        res = subprocess.run(cmd, capture_output=True, timeout=40, stdin=subprocess.DEVNULL)
        if res.returncode == 0 and os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
            return chunk_path
        # Fallback to static if zoompan errors
        vf_fallback = f"fps=30,scale={target_w}:{target_h}:force_original_aspect_ratio=increase,crop={target_w}:{target_h}"
        cmd_fallback = [
            ffmpeg_exe, "-y", "-nostdin",
            "-loop", "1",
            "-i", image_path,
            "-t", f"{duration:.3f}",
            "-vf", vf_fallback,
            "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
            "-an", chunk_path
        ]
        res2 = subprocess.run(cmd_fallback, capture_output=True, timeout=30, stdin=subprocess.DEVNULL)
        if res2.returncode == 0 and os.path.exists(chunk_path) and os.path.getsize(chunk_path) > 1000:
            return chunk_path
        return None
    except Exception as e:
        print(f"[video_composer] Image chunk error on {image_path}: {e}")
        return None


# ---------------------------------------------------------------------------
# Pool-based fast-cut builder
# ---------------------------------------------------------------------------

_CUT_VIDEO_MIN = 2.4
_CUT_VIDEO_MAX = 3.6
_CUT_IMAGE_MIN = 2.0
_CUT_IMAGE_MAX = 3.2


def _build_cuts_from_pool(pool, total_duration, enable_zoom=True, global_unused=None, used_set=None):
    """
    Given a pool of (path, media_type) tuples and a total duration to fill,
    returns a list of on-disk MP4 chunk file paths using strictly real footage.
    Prioritizes unseen assets so ZERO images or clips repeat in the video.
    """
    if used_set is None:
        used_set = set()

    valid_pool = [x for x in pool if os.path.exists(x[0]) and not x[0].endswith("_fallback.jpg")]
    if not valid_pool:
        valid_pool = [x for x in pool if os.path.exists(x[0])]

    if not valid_pool and global_unused:
        valid_pool = [x for x in global_unused if os.path.exists(x[0]) and not x[0].endswith("_fallback.jpg")]

    if not valid_pool:
        return []

    # Prioritize items in valid_pool that haven't been shown yet
    unseen_pool = [x for x in valid_pool if x[0] not in used_set]
    active_pool = unseen_pool if unseen_pool else valid_pool

    videos = [(p, mt) for p, mt in active_pool if mt == "video"]
    images = [(p, mt) for p, mt in active_pool if mt == "image"]

    sequence = []
    vi, ii = 0, 0
    while True:
        if vi < len(videos):
            sequence.append(videos[vi])
            vi += 1
        if ii < len(images):
            sequence.append(images[ii])
            ii += 1
        if vi >= len(videos) and ii >= len(images):
            break

    if not sequence:
        sequence = active_pool[:]

    chunk_paths = []
    elapsed = 0.0
    seq_idx = 0

    while elapsed < total_duration - 0.2:
        remaining = total_duration - elapsed
        
        # Pick next unused item
        item = None
        if seq_idx < len(sequence):
            item = sequence[seq_idx]
            seq_idx += 1
        elif global_unused:
            # Check global bank for any asset not yet shown
            unseen_global = [x for x in global_unused if x[0] not in used_set and os.path.exists(x[0])]
            if unseen_global:
                item = unseen_global[0]
            else:
                item = sequence[seq_idx % len(sequence)]
                seq_idx += 1
        else:
            item = sequence[seq_idx % len(sequence)]
            seq_idx += 1

        media_path, media_type = item

        if media_type == "video":
            cut_dur = min(
                round(random.uniform(_CUT_VIDEO_MIN, _CUT_VIDEO_MAX), 1),
                remaining
            )
            if cut_dur < 0.5:
                cut_dur = remaining
            ch = _make_video_chunk(media_path, cut_dur)
            if ch is None:
                img_candidates = [p for p, t in sequence if t == "image" and os.path.exists(p)]
                if img_candidates:
                    fallback_img = img_candidates[0]
                    ch = _make_image_chunk(fallback_img, cut_dur)
        else:
            cut_dur = min(
                round(random.uniform(_CUT_IMAGE_MIN, _CUT_IMAGE_MAX), 1),
                remaining
            )
            if cut_dur < 0.5:
                cut_dur = remaining
            ch = _make_image_chunk(media_path, cut_dur)

        if ch:
            chunk_paths.append(ch)
            used_set.add(media_path)
            elapsed += cut_dur
        else:
            if seq_idx > len(sequence) * 3:
                break

    # Fill any small remaining gap using unseen footage if available
    gap = total_duration - elapsed
    if gap > 0.1 and sequence:
        unseen_gap = [x for x in (global_unused or sequence) if x[0] not in used_set and os.path.exists(x[0])]
        gap_item = unseen_gap[0] if unseen_gap else sequence[0]
        media_path, media_type = gap_item
        if media_type == "video":
            ch = _make_video_chunk(media_path, gap) or _make_image_chunk(media_path, gap)
        else:
            ch = _make_image_chunk(media_path, gap)
        if ch:
            chunk_paths.append(ch)
            used_set.add(media_path)

    return chunk_paths


# ---------------------------------------------------------------------------
# SRT subtitle parsing
# ---------------------------------------------------------------------------

def _parse_srt(srt_path, max_words=4):
    """
    Parses an SRT file and returns a list of (start_sec, end_sec, text) chunks.
    Accurately handles word-level SRT (from edge-tts WordBoundary) and sentence-level SRT,
    grouping words into clean, natural 3-4 word phrases with zero timing drift.
    """
    if not os.path.exists(srt_path):
        return []
    with open(srt_path, "r", encoding="utf-8") as f:
        content = f.read()

    raw_words = []
    for block in re.split(r"\n\n+", content.strip()):
        lines = block.strip().split("\n")
        if len(lines) < 3:
            continue
        m = re.match(r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})", lines[1])
        if not m:
            continue
        start = _srt_to_sec(m.group(1))
        end   = _srt_to_sec(m.group(2))
        text  = " ".join(lines[2:]).strip()
        if not text:
            continue
        
        words = text.split()
        if len(words) == 1:
            raw_words.append((start, end, words[0]))
        else:
            # Multi-word block fallback (e.g. from gTTS or sentence boundary)
            dur = max(0.1, end - start)
            per_w = dur / len(words)
            for idx, w in enumerate(words):
                raw_words.append((start + idx * per_w, start + (idx + 1) * per_w, w))

    if not raw_words:
        return []

    # Group individual words into concise 3-4 word phrases, respecting punctuation and speech pauses
    timed_chunks = []
    current_group = []
    
    for idx, (w_start, w_end, word) in enumerate(raw_words):
        current_group.append((w_start, w_end, word))
        
        is_terminal = word.endswith((".", "?", "!", ":", ";"))
        has_pause_next = False
        if idx + 1 < len(raw_words):
            next_start = raw_words[idx + 1][0]
            if next_start - w_end > 0.35:
                has_pause_next = True
                
        if len(current_group) >= max_words or is_terminal or has_pause_next or (idx == len(raw_words) - 1):
            g_start = current_group[0][0]
            g_end = current_group[-1][1]
            if not is_terminal and not has_pause_next and idx + 1 < len(raw_words):
                next_start = raw_words[idx + 1][0]
                if 0 < next_start - g_end < 0.30:
                    g_end = next_start
            chunk_text = " ".join(item[2] for item in current_group)
            if chunk_text:
                timed_chunks.append((round(g_start, 3), round(g_end, 3), chunk_text))
            current_group = []

    return timed_chunks


def _srt_to_sec(t):
    h, m, s = t.split(":")
    s, ms   = s.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


# ---------------------------------------------------------------------------
# Text overlays / subtitles (Zero-memory in-frame alpha blend)
# ---------------------------------------------------------------------------

def _prepare_subtitle_badges(srt_path, video_duration):
    """
    Pre-render high-contrast burned-in subtitles with double-outline (white border + black stroke + yellow fill).
    Returns a list of tuples: (g_start, g_end, s_rgb, s_alpha, x_pos, y_pos, h, w) for zero-memory frame blending.
    """
    chunks = _parse_srt(srt_path, max_words=4)
    badges = []
    font_path = config.FONT_PATH if os.path.exists(config.FONT_PATH) else "arialbd.ttf"
    font_size = max(38, min(64, min(config.VIDEO_WIDTH, config.VIDEO_HEIGHT) // 18))
    
    try:
        from PIL import ImageFont, ImageDraw, Image
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    y_pos = int(config.VIDEO_HEIGHT * 0.82)
    color_map = {"white": "#FFFFFF", "yellow": "#FFDC32", "cyan": "#00E5FF"}
    sub_color = color_map.get(getattr(config, "SUBTITLE_COLOR", "yellow"), "#FFDC32")

    for g_start, g_end, text in chunks:
        if g_start >= video_duration:
            break
        g_end = min(g_end, video_duration)
        if g_end <= g_start + 0.1:
            continue
        try:
            img_dummy = Image.new("RGBA", (1, 1))
            draw_dummy = ImageDraw.Draw(img_dummy)
            bbox = draw_dummy.textbbox((0, 0), text, font=font, stroke_width=6)
            
            pad = 12
            w = (bbox[2] - bbox[0]) + pad * 2
            h = (bbox[3] - bbox[1]) + pad * 2
            
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            x = pad - bbox[0]
            y = pad - bbox[1]
            
            # Outer white border (6px stroke) for high contrast on dark/light backdrops
            draw.text((x, y), text, font=font, fill="black", stroke_width=6, stroke_fill="white")
            # Inner black stroke (3px) + yellow fill for crisp typography
            draw.text((x, y), text, font=font, fill=sub_color, stroke_width=3, stroke_fill="black")
            
            # Clamp width to 90% of screen to prevent text overflow
            max_w = int(config.VIDEO_WIDTH * 0.90)
            if w > max_w:
                scale = max_w / w
                w = max_w
                h = max(1, int(h * scale))
                img = img.resize((w, h), Image.LANCZOS)

            arr = np.array(img, dtype=np.uint8)
            s_rgb = arr[:, :, :3]
            s_alpha = (arr[:, :, 3:4] / 255.0).astype(np.float32)
            x_pos = max(0, (config.VIDEO_WIDTH - w) // 2)
            
            badges.append((g_start, g_end, s_rgb, s_alpha, x_pos, y_pos, h, w))
        except Exception as e:
            print(f"[video_composer] subtitle badge error: {e}")

    print(f"[video_composer] Prepared {len(badges)} burned-in subtitle badges from {srt_path}")
    return badges


def _prepare_overlay_badges(scenes, video_duration):
    """
    Pre-render bold keyword overlays at 30% height with double-outline prominence.
    Returns a list of tuples: (abs_start, abs_end, o_rgb, o_alpha, x_pos, y_pos, h, w).
    """
    badges = []
    font_path = config.FONT_PATH if os.path.exists(config.FONT_PATH) else "arialbd.ttf"
    font_size = max(44, min(80, min(config.VIDEO_WIDTH, config.VIDEO_HEIGHT) // 12))
    try:
        from PIL import ImageFont, ImageDraw, Image
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        font = ImageFont.load_default()

    cumulative = 0.0

    for scene in scenes:
        to = scene.get("text_overlay")
        scene_dur = scene.get("duration_sec", 5)
        if to and to.get("text"):
            abs_start = cumulative + float(to.get("start_sec", 0))
            abs_end = abs_start + float(to.get("duration_sec", 2))
            abs_start = min(abs_start, video_duration - 0.1)
            abs_end = min(abs_end, video_duration)
            if abs_end > abs_start:
                try:
                    text = to["text"]
                    img_dummy = Image.new("RGBA", (1, 1))
                    draw_dummy = ImageDraw.Draw(img_dummy)
                    bbox = draw_dummy.textbbox((0, 0), text, font=font, stroke_width=6)
                    
                    pad = 12
                    w = (bbox[2] - bbox[0]) + pad * 2
                    h = (bbox[3] - bbox[1]) + pad * 2
                    
                    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
                    draw = ImageDraw.Draw(img)
                    
                    x = pad - bbox[0]
                    y = pad - bbox[1]
                    
                    # Outer white border (6px stroke) + Inner black stroke (3px) + Yellow fill
                    draw.text((x, y), text, font=font, fill="black", stroke_width=6, stroke_fill="white")
                    draw.text((x, y), text, font=font, fill="#FFDC32", stroke_width=3, stroke_fill="black")
                    
                    # Clamp width to 90% of screen
                    max_w = int(config.VIDEO_WIDTH * 0.90)
                    if w > max_w:
                        scale = max_w / w
                        w = max_w
                        h = max(1, int(h * scale))
                        img = img.resize((w, h), Image.LANCZOS)

                    arr = np.array(img, dtype=np.uint8)
                    o_rgb = arr[:, :, :3]
                    o_alpha = (arr[:, :, 3:4] / 255.0).astype(np.float32)
                    x_pos = max(0, (config.VIDEO_WIDTH - w) // 2)
                    y_pos = int(config.VIDEO_HEIGHT * 0.30)
                    
                    badges.append((abs_start, abs_end, o_rgb, o_alpha, x_pos, y_pos, h, w))
                except Exception as e:
                    print(f"[video_composer] overlay badge error: {e}")
        cumulative += scene_dur
    return badges


def _burn_subtitles_and_overlays(get_frame, t, subtitle_badges, overlay_badges):
    """Zero-memory frame transform that alpha-blends subtitles and overlays directly onto the video buffer."""
    frame = get_frame(t).copy()
    cw, ch = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    for start, end, s_rgb, s_alpha, x, y, h, w in subtitle_badges:
        if start <= t < end:
            x2 = min(cw, x + w)
            y2 = min(ch, y + h)
            aw, ah = x2 - x, y2 - y
            if aw > 0 and ah > 0:
                roi = frame[y:y2, x:x2].astype(np.float32)
                alpha = s_alpha[:ah, :aw]
                rgb = s_rgb[:ah, :aw]
                frame[y:y2, x:x2] = (roi * (1.0 - alpha) + rgb * alpha).astype(np.uint8)
            break
    for start, end, o_rgb, o_alpha, x, y, h, w in overlay_badges:
        if start <= t < end:
            x2 = min(cw, x + w)
            y2 = min(ch, y + h)
            aw, ah = x2 - x, y2 - y
            if aw > 0 and ah > 0:
                roi = frame[y:y2, x:x2].astype(np.float32)
                alpha = o_alpha[:ah, :aw]
                rgb = o_rgb[:ah, :aw]
                frame[y:y2, x:x2] = (roi * (1.0 - alpha) + rgb * alpha).astype(np.uint8)
            break
    return frame


def _make_logo_clip(logo_path, duration):
    try:
        with Image.open(logo_path) as lg:
            lg = lg.convert("RGBA")
            lg.thumbnail((config.VIDEO_WIDTH // 5, int(config.VIDEO_HEIGHT * 0.07)), Image.LANCZOS)
            logo_frame = np.array(lg)
        return (ImageClip(logo_frame)
                .with_duration(duration)
                .with_position(("right", "bottom")))
    except Exception:
        return None


# ---------------------------------------------------------------------------
# Main compose function
# ---------------------------------------------------------------------------

def compose_video(scenes, media_items, srt_path, voiceover_path, voiceover_duration,
                  logo_path=None, title="", progress_cb=None, speaker_badge_path=None,
                  bg_music_path=None, ticker_overlay_path=None, source_badge_path=None):
    """
    Assemble all scenes into a final MP4.

    media_items : list of pools — each pool is a list of (filepath, media_type)
                  tuples. One pool per scene (from fetch_all_media).
    progress_cb : optional callable(int) reporting 62→97 during encode
    """
    enable_zoom = getattr(config, "ENABLE_ZOOM", True)

    # ── Scale visual durations to match actual TTS audio ────────────────
    total_scene_dur = sum(s.get("duration_sec", 5) for s in scenes)
    time_factor     = voiceover_duration / max(1.0, total_scene_dur)

    all_cuts = []      # flat list of all individual sub-clips
    cumulative_dur = 0.0

    # Collect global pool of all verified real stock videos and photos
    global_real_pool = []
    for item in media_items:
        p_list = [item] if isinstance(item, tuple) else (item or [])
        for p, mt in p_list:
            if not p.endswith("_fallback.jpg") and os.path.exists(p):
                global_real_pool.append((p, mt))

    used_set = set()
    for i, scene in enumerate(scenes):
        remaining = voiceover_duration - cumulative_dur
        if remaining < 0.3:
            break

        scene_dur = min(scene.get("duration_sec", 5) * time_factor, remaining)
        if scene_dur < 0.5:
            break

        # Get the pool for this scene — may be a list of (path, type) or
        # a single tuple (backward compat)
        pool = media_items[i] if i < len(media_items) else []
        if isinstance(pool, tuple):
            pool = [pool]   # wrap single item in a list

        # Exclude fallback images if real media is available anywhere in the documentary
        real_pool = [x for x in pool if not x[0].endswith("_fallback.jpg") and os.path.exists(x[0])]
        if not real_pool and global_real_pool:
            # Borrow real clips from documentary pool so no scene ever shows a blank text slide
            offset = i % len(global_real_pool)
            real_pool = global_real_pool[offset:] + global_real_pool[:offset]
        
        effective_pool = real_pool if real_pool else pool

        cuts = _build_cuts_from_pool(
            effective_pool,
            scene_dur,
            enable_zoom=enable_zoom,
            global_unused=global_real_pool,
            used_set=used_set,
        )
        all_cuts.extend(cuts)
        cumulative_dur += scene_dur

    if not all_cuts:
        raise RuntimeError("No scene clips were created — check media_items list.")

    # ── Concatenate all visual chunks losslessly into unified visual track ──────
    concat_txt_path = os.path.join(config.TEMP_DIR, "concat_visual_track.txt")
    with open(concat_txt_path, "w", encoding="utf-8") as f:
        for p in all_cuts:
            abs_p = os.path.abspath(p).replace(os.sep, "/")
            f.write(f"file '{abs_p}'\n")

    full_visual_path = os.path.join(config.TEMP_DIR, "full_visual_track.mp4")
    ffmpeg_exe = imageio_ffmpeg.get_ffmpeg_exe()
    concat_cmd = [
        ffmpeg_exe, "-y", "-nostdin",
        "-f", "concat", "-safe", "0",
        "-i", concat_txt_path,
        "-c", "copy",
        full_visual_path
    ]
    res = subprocess.run(concat_cmd, capture_output=True, timeout=120, stdin=subprocess.DEVNULL)
    if res.returncode != 0 or not os.path.exists(full_visual_path) or os.path.getsize(full_visual_path) < 1000:
        raise RuntimeError(f"FFmpeg visual track concatenation failed: {res.stderr.decode('utf-8', errors='replace')}")

    # ── SEO-friendly output filename ─────────────────────────────────────
    safe_title      = re.sub(r'[^a-zA-Z0-9]+', '-', title).strip('-').lower()
    safe_title      = safe_title[:60] or "youtube-video"
    uid             = str(uuid.uuid4())[:6]
    output_filename = f"{safe_title}_{uid}.mp4"
    output_path     = os.path.join(config.OUTPUT_DIR, output_filename)
    os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # ── Direct FFmpeg Final Render (Ultra-fast, zero-memory, crash-proof) ──
    escaped_srt = os.path.abspath(srt_path).replace("\\", "/").replace(":", r"\:")
    color_hex = {"white": "&H00FFFFFF", "yellow": "&H0032DCFF", "cyan": "&H00FFFF00"}.get(
        getattr(config, "SUBTITLE_COLOR", "yellow"), "&H0032DCFF"
    )
    is_landscape = config.VIDEO_WIDTH > config.VIDEO_HEIGHT
    font_size = 20 if is_landscape else 17
    # Note: FFmpeg subtitles filter uses libass PlayResY=288 virtual coordinates.
    # MarginV=42 in landscape places subtitles cleanly above the lower-third ticker bar (~15% from bottom).
    # MarginV=68 in Shorts places subtitles in the lower third (~23% from bottom), clear of faces & YouTube UI.
    if ticker_overlay_path and os.path.exists(ticker_overlay_path):
        margin_v = 42 if is_landscape else 68
    else:
        margin_v = 28 if is_landscape else 62
    sub_style = (
        f"Fontname=Arial,Bold=1,Fontsize={font_size},PrimaryColour={color_hex},"
        f"OutlineColour=&H00000000,BorderStyle=1,Outline=3,Shadow=1,Alignment=2,MarginV={margin_v}"
    )
    vf_subtitles = f"subtitles='{escaped_srt}':force_style='{sub_style}'"

    # Background music handling (only applied if explicitly passed)
    vol = max(0.12, min(0.35, getattr(config, "BG_MUSIC_VOLUME", 0.18)))
    if bg_music_path and not os.path.exists(bg_music_path):
        bg_music_path = None

    render_cmd = [
        ffmpeg_exe, "-y", "-nostdin",
        "-i", full_visual_path,
        "-i", voiceover_path,
    ]

    input_idx = 2
    bg_input_idx = None
    badge_input_idx = None
    ticker_input_idx = None
    source_input_idx = None

    if bg_music_path and os.path.exists(bg_music_path) and vol > 0:
        render_cmd.extend(["-stream_loop", "-1", "-i", bg_music_path])
        bg_input_idx = input_idx
        input_idx += 1

    if speaker_badge_path and os.path.exists(speaker_badge_path):
        render_cmd.extend(["-loop", "1", "-i", speaker_badge_path])
        badge_input_idx = input_idx
        input_idx += 1

    if ticker_overlay_path and os.path.exists(ticker_overlay_path):
        render_cmd.extend(["-loop", "1", "-i", ticker_overlay_path])
        ticker_input_idx = input_idx
        input_idx += 1

    if source_badge_path and os.path.exists(source_badge_path):
        render_cmd.extend(["-loop", "1", "-i", source_badge_path])
        source_input_idx = input_idx
        input_idx += 1

    # Construct unified filter graph
    filter_parts = []
    v_stream = "0:v"

    if badge_input_idx is not None:
        filter_parts.append(f"[{v_stream}][{badge_input_idx}:v]overlay=0:0:eof_action=repeat[vwithbadge]")
        v_stream = "vwithbadge"

    if ticker_input_idx is not None:
        filter_parts.append(f"[{v_stream}][{ticker_input_idx}:v]overlay=0:0:eof_action=repeat[vwithticker]")
        v_stream = "vwithticker"

    if source_input_idx is not None:
        filter_parts.append(f"[{v_stream}][{source_input_idx}:v]overlay=0:0:eof_action=repeat[vwithsource]")
        v_stream = "vwithsource"

    filter_parts.append(f"[{v_stream}]{vf_subtitles}[vout]")

    if bg_input_idx is not None:
        filter_parts.append(
            f"[{bg_input_idx}:a]volume={vol:.2f},afade=t=in:st=0:d=1,afade=t=out:st={voiceover_duration - 2:.1f}:d=2[bg]"
        )
        filter_parts.append(f"[1:a][bg]amix=inputs=2:duration=first[aout]")
        render_cmd.extend([
            "-filter_complex", "; ".join(filter_parts),
            "-map", "[vout]",
            "-map", "[aout]",
        ])
    else:
        render_cmd.extend([
            "-filter_complex", "; ".join(filter_parts),
            "-map", "[vout]",
            "-map", "1:a",
        ])

    render_cmd.extend([
        "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-shortest",
        output_path
    ])

    print(f"[video_composer] Rendering final video with direct FFmpeg...")
    
    # ── Watchdog & Progress monitor ──────────────────────────────────────
    _tick_stop = threading.Event()
    _watchdog_error = []

    def _monitor():
        pct = 62
        last_size = -1
        stagnant_sec = 0
        max_total_sec = 600  # 10 minutes max render limit
        total_sec = 0
        
        while not _tick_stop.is_set():
            _tick_stop.wait(timeout=5)
            if _tick_stop.is_set():
                break
                
            total_sec += 5
            curr_size = os.path.getsize(output_path) if os.path.exists(output_path) else 0
            
            pct = min(pct + 2, 97)
            if progress_cb:
                progress_cb(pct)
                
            if total_sec > 30:
                if curr_size == last_size and curr_size > 0:
                    stagnant_sec += 5
                else:
                    stagnant_sec = 0
                last_size = curr_size
                
                if stagnant_sec >= 180:
                    msg = (
                        f"Watchdog detected render stall: output file {os.path.basename(output_path)} "
                        f"has not grown for 180s (stuck at {curr_size} bytes)."
                    )
                    print(f"\n[video_composer ERROR] {msg}")
                    _watchdog_error.append(msg)
                    _tick_stop.set()
                    break

            if total_sec >= max_total_sec:
                msg = f"Watchdog timeout: render exceeded maximum allowed time ({max_total_sec}s)."
                print(f"\n[video_composer ERROR] {msg}")
                _watchdog_error.append(msg)
                _tick_stop.set()
                break

    monitor_thread = threading.Thread(target=_monitor, daemon=True)
    monitor_thread.start()

    try:
        res = subprocess.run(render_cmd, capture_output=True, text=True, stdin=subprocess.DEVNULL)
        if res.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) < 1000:
            raise RuntimeError(f"Direct FFmpeg render failed (rc={res.returncode}): {res.stderr[-1000:]}")
    finally:
        _tick_stop.set()
        monitor_thread.join(timeout=5)

    if _watchdog_error:
        raise TimeoutError(_watchdog_error[0])

    print(f"[video_composer] Render complete: {output_path} ({os.path.getsize(output_path)/1024/1024:.2f} MB)")
    return output_path


# ---------------------------------------------------------------------------
# MoviePy stray temp-file cleanup
# ---------------------------------------------------------------------------

def _cleanup_mpy_temp_files():
    """Remove TEMP_MPY_wvf_snd.mp4 files that MoviePy drops in the cwd."""
    try:
        cwd = os.getcwd()
        for fname in os.listdir(cwd):
            if "TEMP_MPY_wvf_snd" in fname:
                try:
                    os.remove(os.path.join(cwd, fname))
                except Exception:
                    pass
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Background music loader
# ---------------------------------------------------------------------------

def _load_background_music(duration):
    if not os.path.exists(config.MUSIC_DIR):
        return None
    files = [f for f in os.listdir(config.MUSIC_DIR) if f.lower().endswith((".mp3", ".wav", ".m4a"))]
    if not files:
        return None
    try:
        music = AudioFileClip(os.path.join(config.MUSIC_DIR, files[0]))
        if music.duration < duration:
            music = music.with_effects([afx.AudioLoop(duration=duration)])
        else:
            music = music.subclipped(0, duration)
        return music
    except Exception:
        return None


def cleanup_temp():
    import gc
    gc.collect()
    if os.path.exists(config.TEMP_DIR):
        shutil.rmtree(config.TEMP_DIR, ignore_errors=True)
    os.makedirs(config.TEMP_DIR, exist_ok=True)
