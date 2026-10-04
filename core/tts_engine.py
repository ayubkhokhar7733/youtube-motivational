"""
tts_engine.py — Robust TTS with retry logic and voice speed optimisation.
Generates a full voiceover MP3 + word-level SRT subtitle file for the script.
"""
import asyncio
import os
import time
import config


def _get_voice():
    return getattr(config, "VOICE_NAME", "en-US-JennyNeural")


def generate_voiceover(scenes, max_retries: int = 3):
    """
    Concatenate all scene narrations into one text block, synthesise speech,
    generate an SRT file, and return:
        (audio_path, srt_path, timings, actual_duration_seconds)
    """
    full_text = " ".join(scene.get("narration", "").strip() for scene in scenes)
    full_text  = full_text.strip()

    if not full_text:
        raise ValueError("No narration text found in scenes.")

    audio_path = os.path.join(config.TEMP_DIR, "full_voiceover.mp3")
    srt_path   = os.path.join(config.TEMP_DIR, "subtitles.srt")

    # Try edge-tts with retries
    success = False
    for attempt in range(max_retries):
        if _try_edge_tts(full_text, audio_path, srt_path):
            success = True
            break
        wait = 2 ** attempt
        print(f"[tts_engine] edge-tts attempt {attempt + 1} failed, retrying in {wait}s...")
        time.sleep(wait)

    # Fallback to gTTS if edge-tts keeps failing
    if not success:
        print("[tts_engine] edge-tts exhausted, trying gTTS fallback...")
        success = _try_gtts(full_text, audio_path, srt_path, scenes)

    if not success:
        raise RuntimeError("All TTS backends failed. Check your internet connection.")

    # Measure the actual audio duration
    actual_duration = _measure_audio_duration(audio_path)
    if actual_duration <= 0:
        # Last-resort estimate: 150 words per minute
        word_count = len(full_text.split())
        actual_duration = (word_count / 150) * 60

    # Build timing list (used by the composer for scene alignment)
    timings = []
    current_time = 0.0
    for i, scene in enumerate(scenes):
        timings.append({
            "scene_index": i,
            "start_sec":   current_time,
            "duration_sec": scene.get("duration_sec", 10),
            "text":         scene.get("narration", ""),
        })
        current_time += scene.get("duration_sec", 10)

    return audio_path, srt_path, timings, actual_duration


def _measure_audio_duration(audio_path: str) -> float:
    """Return the duration of an MP3 file in seconds using moviepy."""
    try:
        from moviepy import AudioFileClip as _AFC
        clip = _AFC(audio_path)
        dur  = clip.duration
        clip.close()
        return float(dur)
    except Exception:
        return 0.0


def _try_edge_tts(text: str, audio_path: str, srt_path: str) -> bool:
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(_edge_tts_generate(text, audio_path, srt_path))
        finally:
            loop.close()
        if os.path.exists(audio_path) and os.path.getsize(audio_path) > 1000:
            return True
    except Exception as e:
        print(f"[tts_engine] edge-tts error: {e}")
    return False


async def _edge_tts_generate(text: str, audio_path: str, srt_path: str):
    import edge_tts
    voice = _get_voice()

    # Save audio and stream word boundaries simultaneously for microsecond sync
    rate = getattr(config, "VOICE_RATE", "+10%")
    communicate = edge_tts.Communicate(text, voice, rate=rate, boundary="WordBoundary")
    submaker = edge_tts.SubMaker()
    word_events = []

    with open(audio_path, "wb") as audio_file:
        async for chunk in communicate.stream():
            if chunk.get("type") == "audio":
                audio_file.write(chunk.get("data", b""))
            elif chunk.get("type") in ("SentenceBoundary", "WordBoundary"):
                submaker.feed(chunk)
                if chunk.get("type") == "WordBoundary" and chunk.get("text"):
                    offset_s = float(chunk.get("offset", 0)) / 10_000_000.0
                    dur_s = float(chunk.get("duration", 0)) / 10_000_000.0
                    word_events.append({
                        "text": str(chunk.get("text", "")).strip(),
                        "start": offset_s,
                        "end": offset_s + max(0.08, dur_s),
                    })

    # Group single words into 3-4 word broadcast phrases so viewers can read comfortably
    if word_events:
        srt_lines = []
        phrase_words = []
        phrase_start = 0.0
        phrase_end = 0.0
        cue_idx = 1

        for ev in word_events:
            w = ev["text"]
            if not w:
                continue
            if not phrase_words:
                phrase_start = ev["start"]
            phrase_words.append(w)
            phrase_end = ev["end"]

            current_len = sum(len(x) for x in phrase_words) + len(phrase_words) - 1
            ends_punct = w[-1] in ".!?,;:"
            if len(phrase_words) >= 4 or current_len >= 24 or (ends_punct and len(phrase_words) >= 2):
                srt_lines.append(str(cue_idx))
                srt_lines.append(f"{_fmt_srt(phrase_start)} --> {_fmt_srt(phrase_end)}")
                srt_lines.append(" ".join(phrase_words))
                srt_lines.append("")
                cue_idx += 1
                phrase_words = []

        if phrase_words:
            srt_lines.append(str(cue_idx))
            srt_lines.append(f"{_fmt_srt(phrase_start)} --> {_fmt_srt(phrase_end)}")
            srt_lines.append(" ".join(phrase_words))
            srt_lines.append("")

        srt_content = "\n".join(srt_lines)
    else:
        srt_content = submaker.get_srt()

    # If SubMaker produced empty SRT, generate fallback SRT from text
    if not srt_content or len(srt_content.strip()) < 10:
        words = text.split()
        total_dur = max(5.0, len(words) / 2.5)
        words_per_sec = len(words) / total_dur
        srt_lines = []
        chunk_size = 4
        for i in range(0, len(words), chunk_size):
            chunk_words = words[i:i + chunk_size]
            start_s = i / words_per_sec
            end_s = min(total_dur, (i + len(chunk_words)) / words_per_sec)
            idx = (i // chunk_size) + 1
            srt_lines.append(str(idx))
            srt_lines.append(f"{_fmt_srt(start_s)} --> {_fmt_srt(end_s)}")
            srt_lines.append(" ".join(chunk_words))
            srt_lines.append("")
        srt_content = "\n".join(srt_lines)

    with open(srt_path, "w", encoding="utf-8") as f:
        f.write(srt_content)


def _try_gtts(text: str, audio_path: str, srt_path: str, scenes: list) -> bool:
    try:
        from gtts import gTTS
        tts = gTTS(text=text, lang="en", slow=False)
        tts.save(audio_path)

        # Build a basic SRT from scene timing estimates
        srt_lines = []
        current_time = 0.0
        for i, scene in enumerate(scenes):
            dur = scene.get("duration_sec", 10)
            srt_lines.append(str(i + 1))
            srt_lines.append(f"{_fmt_srt(current_time)} --> {_fmt_srt(current_time + dur)}")
            srt_lines.append(scene.get("narration", ""))
            srt_lines.append("")
            current_time += dur

        with open(srt_path, "w", encoding="utf-8") as f:
            f.write("\n".join(srt_lines))
        return True
    except Exception as e:
        print(f"[tts_engine] gTTS error: {e}")
    return False


def _fmt_srt(seconds: float) -> str:
    h  = int(seconds // 3600)
    m  = int((seconds % 3600) // 60)
    s  = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"
