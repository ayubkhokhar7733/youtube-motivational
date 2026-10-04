#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
pipeline.py — Headless CLI pipeline for automated YouTube video creation.

Integrates:
- Topic selector & anti-collision queue (topic_selector.py)
- Script generator (core/script_generator.py)
- Media searcher & fallback pool (core/media_searcher.py)
- Neural TTS voiceover & word-level subtitles (core/tts_engine.py)
- Video composer & audio mixer (core/video_composer.py)
- SEO Metadata generator following §4b prompt (metadata_generator.py)
- Thumbnail generator (thumbnail_gen.py)
- Shorts extractor for 9:16 vertical repurposing (shorts_extractor.py)
- YouTube Uploader with verified AI disclosure (youtube_uploader.py)

Usage:
    py pipeline.py --auto-topic
    py pipeline.py --auto-topic --upload --privacy private
    py pipeline.py --topic "The Voynich Manuscript" --duration 60
    py pipeline.py --topic "Ancient Rome" --dry-run
"""

import os
import sys
import argparse
import json
import time
import traceback
from datetime import datetime

# Ensure UTF-8 output across Windows, Linux, and CI runners
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

import config
from core.script_generator import generate_script, segment_transcript_to_scenes
from core.media_searcher import fetch_all_media
from core.tts_engine import generate_voiceover
from core.video_composer import compose_video, cleanup_temp
from core.time_estimator import TimeEstimator
import core.youtube_extractor as youtube_extractor

import topic_selector
import metadata_generator
import thumbnail_gen
import shorts_extractor
import youtube_uploader


def parse_args():
    parser = argparse.ArgumentParser(
        description="Headless video generation pipeline for automated YouTube channels."
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Topic for the video. If omitted or --auto-topic, pulls next balanced topic from queue.",
    )
    parser.add_argument(
        "--auto-topic",
        action="store_true",
        help="Automatically pick the next topic from data/topic_queue.json with rotation & anti-collision.",
    )
    parser.add_argument(
        "--url",
        type=str,
        default=None,
        help="YouTube video URL to download audio from and repurpose into a motivational video.",
    )
    parser.add_argument(
        "--bulk-urls",
        type=str,
        nargs="+",
        default=None,
        help="List of YouTube video URLs to process in bulk queue.",
    )
    parser.add_argument(
        "--url-file",
        type=str,
        default=None,
        help="Path to a text file containing YouTube URLs (one per line) for bulk processing.",
    )
    parser.add_argument(
        "--speaker-name",
        type=str,
        default=None,
        help="Explicit motivational speaker name override (e.g. 'David Goggins').",
    )
    parser.add_argument(
        "--speaker-image",
        type=str,
        default=None,
        help="Path to speaker avatar/photo image to display in the speaker badge.",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=None,
        help=f"Target duration in seconds (default: {config.TOTAL_TARGET_DURATION}s).",
    )
    parser.add_argument(
        "--aspect",
        type=str,
        choices=["landscape", "portrait", "square"],
        default=None,
        help="Aspect ratio preset: landscape (16:9), portrait (9:16), or square (1:1).",
    )
    parser.add_argument(
        "--voice",
        type=str,
        default=None,
        help="Voice identifier for Edge-TTS (e.g. 'en-US-GuyNeural', 'en-US-JennyNeural').",
    )
    parser.add_argument(
        "--media-pref",
        type=str,
        choices=["video_first", "image_only", "video_only"],
        default=None,
        help="Preference for background media sourcing.",
    )
    parser.add_argument(
        "--zoom",
        action="store_true",
        default=False,
        help="Enable Ken Burns dynamic zoom on still images (slower on CPU).",
    )
    parser.add_argument(
        "--no-zoom",
        action="store_true",
        default=False,
        help="Explicitly disable Ken Burns zoom effect.",
    )
    parser.add_argument(
        "--no-shorts",
        action="store_true",
        help="Skip extracting 9:16 vertical Shorts.",
    )
    parser.add_argument(
        "--upload",
        action="store_true",
        help="Upload the generated video and custom thumbnail to YouTube.",
    )
    parser.add_argument(
        "--upload-shorts",
        action="store_true",
        help="Also upload extracted Shorts to YouTube.",
    )
    parser.add_argument(
        "--privacy",
        type=str,
        choices=["private", "unlisted", "public"],
        default="private",
        help="YouTube upload privacy status (default: private).",
    )
    parser.add_argument(
        "--logo",
        type=str,
        default=None,
        help="Path to channel logo/watermark image.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Custom directory to store output assets.",
    )
    parser.add_argument(
        "--keep-temp",
        action="store_true",
        help="Do not clean up temporary media/audio files after rendering.",
    )
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Extract audio, metadata, and transcription from YouTube URL only (skips stock media sourcing & video rendering).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Generate script, metadata, thumbnail and test segments without full video rendering or upload.",
    )
    parser.add_argument(
        "--mock-script",
        action="store_true",
        help="Use built-in mock generators instead of calling Groq API.",
    )
    return parser.parse_args()


def log(msg: str):
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] {msg}", flush=True)


def _generate_mock_script(topic: str) -> dict:
    return {
        "title": f"The Secrets of {topic.title()}",
        "scenes": [
            {
                "narration": f"What if the most fascinating truth about {topic} has been hidden in plain sight for centuries?",
                "keywords": f"{topic} history mystery",
                "duration_sec": 7,
                "text_overlay": {
                    "text": "The Hidden Truth",
                    "start_sec": 1,
                    "duration_sec": 3,
                },
            },
            {
                "narration": f"Scholars and researchers have uncovered remarkable evidence showing how {topic} transformed our understanding of the world.",
                "keywords": f"{topic} discovery science",
                "duration_sec": 8,
            },
            {
                "narration": f"Every artifact and record left behind tells an extraordinary story of innovation, ambition, and human curiosity.",
                "keywords": f"{topic} artifacts ancient",
                "duration_sec": 8,
            },
            {
                "narration": "Like this video if you learned something new, and subscribe for more deep dives into forgotten history.",
                "keywords": f"{topic} books learning",
                "duration_sec": 6,
            },
        ],
    }


def run_pipeline(
    topic: str = None,
    auto_topic: bool = False,
    url: str = None,
    speaker_name: str = None,
    speaker_image: str = None,
    duration: int = None,
    aspect: str = None,
    voice: str = None,
    media_pref: str = None,
    enable_zoom: bool = False,
    extract_shorts_enabled: bool = True,
    upload_to_youtube: bool = False,
    upload_shorts_enabled: bool = False,
    privacy: str = "private",
    logo_path: str = None,
    output_dir: str = None,
    keep_temp: bool = False,
    dry_run: bool = False,
    mock_script: bool = False,
    audio_only: bool = False,
) -> dict:
    """
    Executes the complete end-to-end video automation pipeline.
    Supports both Topic Generation mode and Motivational YouTube Audio Repurposing mode.
    """
    start_time = time.time()

    # ── 1. Configuration Setup & Overrides ──────────────────────────────────
    config.reload()

    if duration is not None:
        config.TOTAL_TARGET_DURATION = int(duration)
    aspect_label = aspect or config.DEFAULT_ASPECT
    if aspect is not None and aspect in config.ASPECT_PRESETS:
        preset = config.ASPECT_PRESETS[aspect]
        config.VIDEO_WIDTH = preset["width"]
        config.VIDEO_HEIGHT = preset["height"]
    if voice is not None:
        config.VOICE_NAME = voice
    if media_pref is not None and media_pref in config.VALID_MEDIA_PREFS:
        config.MEDIA_PREFERENCE = media_pref

    # Check CI environment — default to fast render in CI unless explicitly forced
    is_ci = os.environ.get("CI", "").lower() in ("true", "1")
    if is_ci and not enable_zoom:
        config.ENABLE_ZOOM = False
    else:
        config.ENABLE_ZOOM = enable_zoom

    if output_dir:
        config.OUTPUT_DIR = output_dir
        os.makedirs(config.OUTPUT_DIR, exist_ok=True)

    # Clean working temp directory before starting
    cleanup_temp()

    speaker_badge_overlay = None
    detected_speaker = speaker_name or ""

    # ── 2. Motivational YouTube Audio Repurposing Branch ────────────────────
    if url:
        log(f"📥 [Motivational Flow] Ingesting YouTube video: {url}")
        yt_data = youtube_extractor.extract_youtube_audio_and_metadata(url, output_dir=config.TEMP_DIR)
        audio_path = yt_data["audio_path"]
        source_title = yt_data["title"]
        source_desc = yt_data["description"]
        source_tags = yt_data["tags"]
        source_duration = float(yt_data.get("duration") or 60.0)
        voice_duration = source_duration

        # Transcription with Groq Whisper
        log("🎙️ [Motivational Flow] Transcribing speech audio with Groq Whisper...")
        trans_data = youtube_extractor.transcribe_audio_groq(audio_path)
        transcript = trans_data["transcript"]
        srt_path = trans_data["srt_path"]
        script_time = trans_data.get("transcription_time_sec", 0.0)

        # Speaker detection & badge overlay
        log("👤 [Motivational Flow] Detecting speaker & creating photo badge overlay...")
        speaker_info = youtube_extractor.detect_speaker_info(source_title, source_desc, transcript)
        detected_speaker = speaker_name or speaker_info.get("name", "Motivational Leader")
        speaker_role = speaker_info.get("role", "")
        log(f"   Detected Speaker: {detected_speaker} ({speaker_role})")

        # ── Test Mode: Extract Audio & Transcribe Only ──
        if audio_only:
            log("⚡ [Test Mode] Skipping video rendering as requested — saving extracted audio & metadata...")
            import shutil
            clean_name = re.sub(r"[^\w\-]", "_", source_title)[:40]
            final_audio_name = f"audio_{yt_data['video_id']}_{clean_name}.mp3"
            final_audio_path = os.path.join(config.OUTPUT_DIR, final_audio_name)
            shutil.copy2(audio_path, final_audio_path)

            # Also save transcript to output
            transcript_txt_path = os.path.join(config.OUTPUT_DIR, f"transcript_{yt_data['video_id']}.txt")
            with open(transcript_txt_path, "w", encoding="utf-8") as tf:
                tf.write(f"Title: {source_title}\nSpeaker: {detected_speaker}\nDuration: {source_duration}s\n\n--- Transcript ---\n{transcript}\n")

            total_elapsed = time.time() - start_time
            file_mb = os.path.getsize(final_audio_path) / (1024 * 1024)
            log(f"🎉 [Test Mode] Audio extracted successfully in {total_elapsed:.1f}s!")
            log(f"   📁 Audio File: {final_audio_path} ({file_mb:.2f} MB, {source_duration:.1f}s)")
            log(f"   👤 Speaker: {detected_speaker}")
            log(f"   📝 Transcript snippet: {transcript[:180]}...")

            return {
                "status": "success",
                "mode": "audio_only_test",
                "title": source_title,
                "speaker": detected_speaker,
                "audio_path": final_audio_path,
                "transcript_path": transcript_txt_path,
                "srt_path": srt_path,
                "duration_sec": source_duration,
                "file_size_mb": round(file_mb, 2),
                "transcript_words": len(transcript.split()),
                "total_elapsed_sec": round(total_elapsed, 2),
            }

        avatar_src = speaker_image or yt_data.get("thumbnail_url")
        speaker_badge_overlay = youtube_extractor.generate_speaker_badge_overlay(
            speaker_name=detected_speaker,
            speaker_role=speaker_role,
            avatar_image_path=avatar_src,
            width=config.VIDEO_WIDTH,
            height=config.VIDEO_HEIGHT,
        )

        # Motivational scene segmentation
        log("🎬 [Motivational Flow] Segmenting transcript into dynamic visual beats...")
        script = segment_transcript_to_scenes(
            transcript=transcript,
            total_duration=voice_duration,
            title=source_title,
            speaker_name=detected_speaker,
        )
        scenes = script["scenes"]
        scene_count = len(scenes)
        total_words = len(transcript.split())

        # Altered SEO metadata spinning
        log("🏷️ [Motivational Flow] Generating altered high-CTR metadata...")
        meta_start = time.time()
        metadata = metadata_generator.spin_motivational_metadata(
            original_title=source_title,
            original_description=source_desc,
            original_tags=source_tags,
            transcript=transcript,
            speaker_name=detected_speaker,
            mock=mock_script,
        )
        meta_time = time.time() - meta_start
        final_youtube_title = metadata["title"]
        topic_category = "Motivational"
        topic = final_youtube_title
        topic_item = {"topic": final_youtube_title, "category": topic_category, "speaker": detected_speaker}
        tts_time = 0.0

    # ── 2b. Standard Topic Generation Branch ────────────────────────────────
    else:
        # Topic Resolution
        topic_item = {}
        if not topic or auto_topic:
            topic_item = topic_selector.get_next_topic()
            topic = topic_item.get("topic", "The Power of Relentless Focus")
            topic_category = topic_item.get("category", "General")
            log(f"🎯 Auto-selected topic from queue: '{topic}' [Category: {topic_category}]")
        else:
            topic_category = "General"
            topic_item = {"topic": topic, "category": topic_category, "keywords": topic}
            log(f"🚀 Starting pipeline for topic: '{topic}'")

        log(
            f"⚙️ Config: Target Duration={config.TOTAL_TARGET_DURATION}s | "
            f"Resolution={config.VIDEO_WIDTH}x{config.VIDEO_HEIGHT} | "
            f"Voice={config.VOICE_NAME} | MediaPref={config.MEDIA_PREFERENCE} | Zoom={config.ENABLE_ZOOM}"
        )

        # Script Generation (Groq / Llama-3.3)
        log("📝 [Stage 1/6] Generating script...")
        script_start = time.time()
        if mock_script:
            log("💡 Using mock script (bypassing Groq API call).")
            script = _generate_mock_script(topic)
        else:
            script = generate_script(topic)
        script_time = time.time() - script_start

        title = script.get("title", topic.title())
        scenes = script.get("scenes", [])
        scene_count = len(scenes)
        total_words = sum(len(s.get("narration", "").split()) for s in scenes)
        log(f"✅ Script ready in {script_time:.1f}s: \"{title}\" ({scene_count} scenes, ~{total_words} words)")

        # SEO Metadata Generation
        log("🏷️ [Stage 2/6] Generating high-SEO YouTube metadata...")
        meta_start = time.time()
        metadata = metadata_generator.generate_metadata(script, topic=topic, mock=mock_script)
        meta_time = time.time() - meta_start
        final_youtube_title = metadata.get("title", title)
        log(f"✅ SEO Metadata ready in {meta_time:.1f}s: \"{final_youtube_title}\" (Pattern: {metadata.get('pattern_used', 'standard')})")

        # Voiceover & Subtitles (Edge-TTS)
        log("🎙️ [Stage 5/6] Generating neural voiceover & word-level subtitles...")
        tts_start = time.time()
        audio_path, srt_path, timings, voice_duration = generate_voiceover(scenes)
        tts_time = time.time() - tts_start
        log(f"✅ Voiceover generated in {tts_time:.1f}s: {voice_duration:.1f}s of audio")

    # ── Media Sourcing (Pexels / Pixabay) ─────────────────────────────────
    log(f"🎬 Sourcing media clips and images for {scene_count} scenes in parallel...")
    media_start = time.time()
    search_topic = f"{detected_speaker} workout discipline" if url else topic
    media_items = fetch_all_media(
        scenes=scenes,
        topic=search_topic,
        log_cb=log,
    )
    media_time = time.time() - media_start

    video_clip_count = sum(sum(1 for _, mt in pool if mt == "video") for pool in media_items)
    image_count = sum(sum(1 for _, mt in pool if mt == "image") for pool in media_items)
    log(f"✅ Media downloaded in {media_time:.1f}s: {video_clip_count} video clips, {image_count} images")

    # Find a strong background image for thumbnail
    best_bg_image = None
    for pool in media_items:
        for path, mtype in pool:
            if mtype == "image" and not path.endswith("_fallback.jpg") and os.path.exists(path):
                best_bg_image = path
                break
        if best_bg_image:
            break

    # ── Thumbnail Generation ─────────────────────────────────────────────
    log("🖼️ Generating high-CTR thumbnail...")
    thumb_start = time.time()
    badge_label = detected_speaker.upper() if (url and detected_speaker) else metadata.get("category", "MOTIVATION")
    thumbnail_path = thumbnail_gen.generate_thumbnail(
        topic=final_youtube_title or topic,
        background_image_path=best_bg_image,
        badge_text=badge_label,
    )
    thumb_time = time.time() - thumb_start
    log(f"✅ Thumbnail ready in {thumb_time:.1f}s: {thumbnail_path}")

    output_video_path = None
    render_time = 0.0
    if dry_run:
        log("🟡 Dry run mode enabled — skipping video encoding.")
    else:
        log("🎞️ Composing and encoding final MP4 video...")
        render_start = time.time()
        # Repurposed YouTube videos already contain full music+speech audio; only add bg music for synthetic TTS topics
        bg_music_to_use = None if url else config.BG_MUSIC_PATH
        output_video_path = compose_video(
            scenes=scenes,
            media_items=media_items,
            srt_path=srt_path,
            voiceover_path=audio_path,
            voiceover_duration=voice_duration,
            logo_path=logo_path,
            title=final_youtube_title,
            speaker_badge_path=speaker_badge_overlay,
            bg_music_path=bg_music_to_use,
        )
        render_time = time.time() - render_start
        log(f"✅ Video successfully encoded in {render_time:.1f}s: {output_video_path}")

        # Save sidecar metadata JSON alongside video
        if output_video_path:
            meta_save = {
                "title": final_youtube_title,
                "description": metadata.get("description", ""),
                "tags": metadata.get("tags", []),
                "category": metadata.get("category", "Education"),
                "topic_category": topic_category,
                "pattern_used": metadata.get("pattern_used"),
                "thumbnail_path": thumbnail_path,
                "video_path": output_video_path,
                "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            }
            meta_json_path = output_video_path.rsplit(".", 1)[0] + "_metadata.json"
            try:
                with open(meta_json_path, "w", encoding="utf-8") as f:
                    json.dump(meta_save, f, indent=2)
                with open(os.path.join(config.OUTPUT_DIR, "latest_metadata.json"), "w", encoding="utf-8") as f:
                    json.dump(meta_save, f, indent=2)
            except Exception as e:
                log(f"⚠️ Failed saving sidecar metadata JSON: {e}")

    # ── 8. Shorts Extraction (§4d) ──────────────────────────────────────────
    shorts_list = []
    if extract_shorts_enabled:
        log("📱 Extracting vertical 9:16 Shorts from video output...")
        try:
            if output_video_path and os.path.exists(output_video_path):
                shorts_list = shorts_extractor.extract_shorts(
                    video_path=output_video_path,
                    script=script,
                    srt_path=srt_path,
                    max_shorts=2,
                    dry_run=dry_run,
                )
                log(f"✅ Extracted {len(shorts_list)} vertical Shorts.")
            elif dry_run:
                shorts_list = shorts_extractor.extract_shorts(
                    video_path=best_bg_image or thumbnail_path,  # stub for dry run
                    script=script,
                    srt_path=srt_path,
                    max_shorts=2,
                    dry_run=True,
                )
        except Exception as e:
            log(f"⚠️ Shorts extraction warning: {e}")

    # ── 9. YouTube Upload & Compliance Flag Injection ────────────────────────
    upload_result = None
    if upload_to_youtube and not dry_run and output_video_path and os.path.exists(output_video_path):
        log("🚀 [Upload] Uploading long-form video to YouTube...")
        try:
            upload_result = youtube_uploader.upload_video(
                video_path=output_video_path,
                title=final_youtube_title,
                description=metadata.get("description", ""),
                tags=metadata.get("tags", []),
                category=metadata.get("category", "Education"),
                topic_category=topic_category,
                thumbnail_path=thumbnail_path,
                privacy_status=privacy,
                contains_synthetic_media=True,
            )
            log(f"🎉 Video uploaded successfully: {upload_result.get('video_url')}")
            if upload_result.get("playlist_id"):
                log(f"📑 Added to playlist: \"{topic_category}\" (ID: {upload_result.get('playlist_id')})")
        except Exception as e:
            log(f"❌ YouTube upload error: {e}")
            if upload_to_youtube and not dry_run:
                raise e

    # ── 9b. Shorts YouTube Upload ────────────────────────────────────────────
    if upload_to_youtube and upload_shorts_enabled and not dry_run and shorts_list:
        log(f"📱 [Upload] Uploading {len(shorts_list)} extracted vertical Shorts to YouTube...")
        for idx, short_item in enumerate(shorts_list, 1):
            short_video_path = short_item.get("video_path")
            if short_video_path and os.path.exists(short_video_path):
                short_title = short_item.get("title", f"{topic[:50]} #Shorts")
                log(f"   🚀 Uploading Short {idx}/{len(shorts_list)}: \"{short_title}\"...")
                try:
                    short_upload_res = youtube_uploader.upload_video(
                        video_path=short_video_path,
                        title=short_title,
                        description=short_item.get("description", ""),
                        tags=short_item.get("tags", ["Shorts", "YouTubeShorts"]),
                        category=short_item.get("category", "Education"),
                        topic_category="Shorts",
                        thumbnail_path=None,
                        privacy_status=privacy,
                        contains_synthetic_media=True,
                    )
                    short_item["upload_result"] = short_upload_res
                    log(f"   🎉 Short {idx} uploaded successfully: {short_upload_res.get('video_url')}")
                except Exception as e:
                    log(f"   ⚠️ Short {idx} upload warning: {e}")

    # ── 10. Post-processing & Memory Record ──────────────────────────────────
    total_elapsed = time.time() - start_time

    # Record used topic in history only if upload succeeded or upload was not requested
    youtube_id = upload_result.get("video_id") if upload_result else None
    if topic_item:
        if not upload_to_youtube or youtube_id or dry_run:
            topic_selector.mark_topic_used(topic_item, video_title=final_youtube_title, youtube_id=youtube_id)
        else:
            log("⚠️ Topic was NOT marked as used because upload did not succeed.")

    # Record run in TimeEstimator history
    try:
        TimeEstimator.add_run(
            aspect_ratio=aspect_label,
            target_duration=config.TOTAL_TARGET_DURATION,
            media_preference=config.MEDIA_PREFERENCE,
            enable_zoom=config.ENABLE_ZOOM,
            scene_count=scene_count,
            video_clip_count=video_clip_count,
            total_time_seconds=total_elapsed,
        )
    except Exception as e:
        log(f"⚠️ Failed to update generation history: {e}")

    if not keep_temp and not dry_run:
        cleanup_temp()
        log("🧹 Temporary build artifacts cleaned up.")

    result = {
        "status": "success",
        "topic": topic,
        "title": final_youtube_title,
        "metadata": metadata,
        "thumbnail_path": thumbnail_path,
        "video_path": output_video_path,
        "upload": upload_result,
        "shorts": shorts_list,
        "duration_sec": voice_duration,
        "scene_count": scene_count,
        "word_count": total_words,
        "video_clips_used": video_clip_count,
        "images_used": image_count,
        "timings": {
            "script_gen_sec": round(script_time, 2),
            "metadata_gen_sec": round(meta_time, 2),
            "media_fetch_sec": round(media_time, 2),
            "thumbnail_gen_sec": round(thumb_time, 2),
            "tts_gen_sec": round(tts_time, 2),
            "render_sec": round(render_time, 2),
            "total_elapsed_sec": round(total_elapsed, 2),
        },
    }

    log(f"🎉 Pipeline finished in {total_elapsed:.1f}s!")
    return result


def main():
    args = parse_args()
    try:
        enable_zoom_flag = args.zoom and not args.no_zoom

        # Check for URL list if bulk, file, or single
        url_list = []
        if args.url:
            url_list.append(args.url)
        elif args.bulk_urls:
            url_list.extend(args.bulk_urls)
        elif args.url_file and os.path.exists(args.url_file):
            with open(args.url_file, "r", encoding="utf-8") as f:
                for line in f:
                    clean_u = line.strip()
                    if clean_u and not clean_u.startswith("#"):
                        url_list.append(clean_u)

        if url_list:
            log(f"📋 Queued {len(url_list)} YouTube video(s) for motivational repurposing...")
            results = []
            for i, target_url in enumerate(url_list, 1):
                log(f"\n=======================================================")
                log(f"🎬 Processing Video [{i}/{len(url_list)}]: {target_url}")
                log(f"=======================================================")
                res = run_pipeline(
                    url=target_url,
                    speaker_name=args.speaker_name,
                    speaker_image=args.speaker_image,
                    duration=args.duration,
                    aspect=args.aspect,
                    voice=args.voice,
                    media_pref=args.media_pref,
                    enable_zoom=enable_zoom_flag,
                    extract_shorts_enabled=not args.no_shorts,
                    upload_to_youtube=args.upload,
                    upload_shorts_enabled=args.upload_shorts,
                    privacy=args.privacy,
                    logo_path=args.logo,
                    output_dir=args.output_dir,
                    keep_temp=args.keep_temp,
                    dry_run=args.dry_run,
                    mock_script=args.mock_script,
                    audio_only=args.audio_only,
                )
                results.append(res)
            print("\n--- Batch Pipeline Summary ---")
            print(json.dumps(results, indent=2))
            sys.exit(0)

        # Standard Topic Flow
        result = run_pipeline(
            topic=args.topic,
            auto_topic=args.auto_topic,
            duration=args.duration,
            aspect=args.aspect,
            voice=args.voice,
            media_pref=args.media_pref,
            enable_zoom=enable_zoom_flag,
            extract_shorts_enabled=not args.no_shorts,
            upload_to_youtube=args.upload,
            upload_shorts_enabled=args.upload_shorts,
            privacy=args.privacy,
            logo_path=args.logo,
            output_dir=args.output_dir,
            keep_temp=args.keep_temp,
            dry_run=args.dry_run,
            mock_script=args.mock_script,
        )
        print("\n--- Pipeline Summary ---")
        print(json.dumps(result, indent=2))
        sys.exit(0)
    except Exception as e:
        log(f"❌ Pipeline failed: {e}")
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
