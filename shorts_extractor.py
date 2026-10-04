#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
shorts_extractor.py — Auto-extract vertical 9:16 YouTube Shorts from long-form videos.

Follows MASTER_PLAN.md §4d:
- Extracts 2-4 high-retention segments (30-60s) from long-form video output.
- Re-formats to 9:16 vertical (1080x1920).
- Generates optimized Shorts metadata with #Shorts hashtags.
- Prepares clips for scheduled multi-upload without repeating full generation costs.
"""

import os
import sys
import re
import json
import uuid
import argparse
from moviepy import (
    VideoFileClip, CompositeVideoClip, TextClip,
    ColorClip, ImageClip
)

# UTF-8 output configuration
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import config

SHORTS_WIDTH = 1080
SHORTS_HEIGHT = 1920


def _parse_srt_segment(srt_path: str, start_time: float, end_time: float, max_words: int = 3) -> list:
    """Extract, re-index and group word-level subtitles falling within [start_time, end_time]."""
    if not srt_path or not os.path.exists(srt_path):
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
        s_sec = _srt_str_to_sec(m.group(1))
        e_sec = _srt_str_to_sec(m.group(2))
        text = " ".join(lines[2:]).strip()

        # Check overlap
        if e_sec > start_time and s_sec < end_time:
            words = text.split()
            if not words:
                continue
            if len(words) == 1:
                rel_s = max(0.0, s_sec - start_time)
                rel_e = min(end_time - start_time, e_sec - start_time)
                if rel_e > rel_s:
                    raw_words.append((rel_s, rel_e, words[0]))
            else:
                dur = max(0.1, e_sec - s_sec)
                per_w = dur / len(words)
                for idx, w in enumerate(words):
                    w_s = s_sec + idx * per_w
                    w_e = s_sec + (idx + 1) * per_w
                    if w_e > start_time and w_s < end_time:
                        rel_s = max(0.0, w_s - start_time)
                        rel_e = min(end_time - start_time, w_e - start_time)
                        if rel_e > rel_s:
                            raw_words.append((rel_s, rel_e, w))

    if not raw_words:
        return []

    # Group into 2-3 word rapid-fire chunks for vertical mobile viewing, respecting punctuation and pauses
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


def _srt_str_to_sec(t: str) -> float:
    h, m, s = t.split(":")
    s, ms = s.split(",")
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def _make_shorts_subtitle_clips(subs: list, duration: float) -> list:
    """Large, vibrant double-outlined subtitles formatted for vertical mobile viewing."""
    clips = []
    font_path = config.FONT_PATH if os.path.exists(config.FONT_PATH) else "arialbd.ttf"
    font_size = 56  # prominent for vertical screens
    
    try:
        from PIL import ImageFont, ImageDraw, Image
        import numpy as np
        font = ImageFont.truetype(font_path, font_size)
    except Exception:
        from PIL import ImageFont, ImageDraw, Image
        import numpy as np
        font = ImageFont.load_default()

    y_pos = int(SHORTS_HEIGHT * 0.65)

    for g_start, g_end, text in subs:
        if g_start >= duration:
            break
        g_end = min(g_end, duration)
        if g_end <= g_start + 0.1:
            continue
        try:
            display_text = text.upper()
            img_dummy = Image.new("RGBA", (1, 1))
            draw_dummy = ImageDraw.Draw(img_dummy)
            bbox = draw_dummy.textbbox((0, 0), display_text, font=font, stroke_width=6)
            
            pad = 14
            w = (bbox[2] - bbox[0]) + pad * 2
            h = (bbox[3] - bbox[1]) + pad * 2
            
            img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
            draw = ImageDraw.Draw(img)
            
            x = pad - bbox[0]
            y = pad - bbox[1]
            
            # Outer white border (6px stroke) + Inner black stroke (3px) + Yellow fill
            draw.text((x, y), display_text, font=font, fill="black", stroke_width=6, stroke_fill="white")
            draw.text((x, y), display_text, font=font, fill="#FFDC32", stroke_width=3, stroke_fill="black")
            
            frame = np.array(img)
            x_pos = (SHORTS_WIDTH - w) // 2
            
            clip = (
                ImageClip(frame)
                .with_position((x_pos, y_pos))
                .with_start(g_start)
                .with_duration(g_end - g_start)
            )
            clips.append(clip)
        except Exception as e:
            print(f"[shorts_extractor] Subtitle clip error: {e}")

    return clips


def _identify_segments(scenes: list, total_duration: float, max_shorts: int = 3) -> list:
    """
    Identifies high-impact candidate time windows [start, end, title_hook] from script scenes.
    """
    segments = []
    if not scenes:
        # Fallback split into 30s chunks
        chunk_dur = min(40.0, total_duration)
        segments.append((0.0, chunk_dur, "Shocking Historical Fact"))
        if total_duration > 60:
            segments.append((chunk_dur, min(total_duration, chunk_dur + 40.0), "The Untold Mystery"))
        return segments

    # 1. Hook Short (First scenes totaling 30-45s)
    cum_dur = 0.0
    hook_end = 0.0
    for scene in scenes:
        dur = scene.get("duration_sec", 8)
        if cum_dur + dur <= 50.0:
            cum_dur += dur
            hook_end = cum_dur
        else:
            break
    if hook_end >= 20.0:
        hook_title = scenes[0].get("text_overlay", {}).get("text") or "The Hidden Fact Nobody Knows"
        segments.append((0.0, min(total_duration, hook_end), hook_title))

    # 2. Middle Climax Short
    if len(scenes) >= 4 and total_duration >= 70.0:
        mid_idx = len(scenes) // 2
        mid_start = sum(s.get("duration_sec", 8) for s in scenes[:mid_idx])
        mid_dur = sum(s.get("duration_sec", 8) for s in scenes[mid_idx:mid_idx + 3])
        mid_end = min(total_duration, mid_start + min(45.0, max(25.0, mid_dur)))
        if mid_end - mid_start >= 20.0:
            mid_title = scenes[mid_idx].get("text_overlay", {}).get("text") or "What Scientists Just Discovered"
            segments.append((mid_start, mid_end, mid_title))

    # Limit to max requested shorts
    return segments[:max_shorts]


def extract_shorts(
    video_path: str,
    script: dict = None,
    srt_path: str = None,
    output_dir: str = None,
    max_shorts: int = 3,
    dry_run: bool = False,
) -> list:
    """
    Extracts 2-4 vertical Shorts (1080x1920) from long-form video.
    Returns a list of dicts with short metadata and video filepaths.
    """
    if not os.path.exists(video_path):
        raise FileNotFoundError(f"Source video not found: {video_path}")

    if not output_dir:
        output_dir = os.path.join(config.OUTPUT_DIR, "shorts")
    os.makedirs(output_dir, exist_ok=True)

    src_clip = VideoFileClip(video_path)
    total_duration = src_clip.duration
    scenes = script.get("scenes", []) if script else []

    candidate_segments = _identify_segments(scenes, total_duration, max_shorts=max_shorts)
    extracted_shorts = []

    base_topic = script.get("title", "Mystery") if script else "History Facts"

    for idx, (start_t, end_t, segment_hook) in enumerate(candidate_segments, 1):
        seg_duration = end_t - start_t
        uid = str(uuid.uuid4())[:5]
        safe_name = re.sub(r'[^a-zA-Z0-9]+', '-', segment_hook).strip('-').lower()[:30]
        out_filename = f"short_{idx}_{safe_name}_{uid}.mp4"
        out_filepath = os.path.join(output_dir, out_filename)

        # Metadata for this Short
        short_title = f"{segment_hook[:55]} #Shorts"
        short_desc = (
            f"{segment_hook}. Did you know this fascinating detail about {base_topic}?\n\n"
            f"Watch the full story on our channel! Subscribe for daily history & science facts.\n\n"
            f"#Shorts #History #Science #Facts #DidYouKnow"
        )
        short_tags = ["Shorts", "YouTubeShorts", "History", "Science", "DidYouKnow", "Facts", base_topic.lower()]

        item_meta = {
            "index": idx,
            "title": short_title,
            "description": short_desc,
            "tags": short_tags,
            "category": "Education",
            "start_time_sec": round(start_t, 2),
            "end_time_sec": round(end_t, 2),
            "duration_sec": round(seg_duration, 2),
            "video_path": out_filepath if not dry_run else None,
            "status": "ready" if not dry_run else "dry_run",
        }

        if dry_run:
            print(f"🟡 [shorts_extractor] Dry run: Identified Short {idx} ({start_t:.1f}s - {end_t:.1f}s, {seg_duration:.1f}s): {short_title}")
            extracted_shorts.append(item_meta)
            continue

        print(f"🎬 [shorts_extractor] Extracting Short {idx}/{len(candidate_segments)} ({start_t:.1f}s - {end_t:.1f}s)...")

        # Extract subclip
        sub = src_clip.subclipped(start_t, end_t)

        # Re-center and crop/scale to 1080x1920 (9:16)
        sw, sh = sub.size
        target_w, target_h = SHORTS_WIDTH, SHORTS_HEIGHT
        src_ratio = sw / sh
        target_ratio = target_w / target_h

        if abs(src_ratio - target_ratio) > 0.01:
            if src_ratio > target_ratio:
                new_w = int(sh * target_ratio)
                x1 = (sw - new_w) // 2
                sub_cropped = sub.cropped(x1=x1, width=new_w)
            else:
                new_h = int(sw / target_ratio)
                y1 = (sh - new_h) // 2
                sub_cropped = sub.cropped(y1=y1, height=new_h)
            sub_916 = sub_cropped.resized((target_w, target_h))
        else:
            sub_916 = sub.resized((target_w, target_h))

        # Add vertical burned-in subtitles if srt exists
        layers = [sub_916]
        if srt_path and os.path.exists(srt_path):
            segment_subs = _parse_srt_segment(srt_path, start_t, end_t)
            sub_clips = _make_shorts_subtitle_clips(segment_subs, seg_duration)
            layers.extend(sub_clips)

        final_short = CompositeVideoClip(layers, size=(target_w, target_h)).with_duration(seg_duration)

        # Write output video
        final_short.write_videofile(
            out_filepath,
            codec="libx264",
            audio_codec="aac",
            fps=config.FPS,
            preset="ultrafast",
            bitrate="4000k",
            threads=4,
            logger=None,
        )

        # Cleanup handles
        for c in [final_short, sub_916, sub]:
            try:
                c.close()
            except Exception:
                pass

        print(f"✅ Short {idx} successfully created: {out_filepath}")
        extracted_shorts.append(item_meta)

    src_clip.close()
    return extracted_shorts


def main():
    parser = argparse.ArgumentParser(description="YouTube Shorts Extractor CLI.")
    parser.add_argument("--video", type=str, required=True, help="Path to input long-form MP4.")
    parser.add_argument("--srt", type=str, default=None, help="Path to subtitles SRT file.")
    parser.add_argument("--output-dir", type=str, default=None, help="Output directory for shorts.")
    parser.add_argument("--max", type=int, default=3, help="Max number of shorts to extract.")
    parser.add_argument("--dry-run", action="store_true", help="Identify candidate segments without rendering video.")

    args = parser.parse_args()

    dummy_script = {
        "title": "The Secrets of Ancient Alexandria",
        "scenes": [
            {"duration_sec": 12, "text_overlay": {"text": "The Lost Knowledge"}},
            {"duration_sec": 15, "text_overlay": {"text": "Over 500,000 Scrolls"}},
            {"duration_sec": 15, "text_overlay": {"text": "The Real Destruction"}},
        ],
    }

    results = extract_shorts(
        video_path=args.video,
        script=dummy_script,
        srt_path=args.srt,
        output_dir=args.output_dir,
        max_shorts=args.max,
        dry_run=args.dry_run,
    )

    print("\n--- Extracted Shorts Metadata ---")
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
