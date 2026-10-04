# -*- coding: utf-8 -*-
import json
import re
import time
from openai import OpenAI
import config

# Edge-TTS speaks at roughly 155 words/min = 2.6 words/sec at default rate.
_WPS = 2.6   # words per second


def _build_prompt(target, min_words, target_words, scene_count):
    words_per_scene = round(target_words / scene_count)
    scene_dur       = round(target / scene_count)
    is_short        = target <= 45

    cta_instruction = (
        "=== SCENE CLOSING (SHORT-FORM / 30-SECOND RULES) ===\n"
        "STRICTLY FORBIDDEN: DO NOT include boilerplate CTAs like 'Like this video', 'Like, share, and subscribe', or 'Subscribe for more'.\n"
        "At this short duration, end on a powerful mic-drop payoff, provocative final thought, or lingering observation that leaves the viewer thinking.\n"
        if is_short else
        "=== SCENE CLOSING (LONG-FORM RULES) ===\n"
        "End with a thought-provoking conclusion and a natural, conversational call to follow for more discoveries.\n"
    )

    return (
        "You are an elite YouTube documentary writer creating high-retention, premium scripts for a sophisticated history & science channel.\n\n"

        f"VIDEO TARGET: {target} seconds of spoken narration.\n"
        f"WORD COUNT REQUIREMENT: Total narration across ALL {scene_count} scenes must be between {min_words} and {target_words} words.\n"
        f"STRUCTURE: {scene_count} scenes, approximately {words_per_scene} words each, approximately {scene_dur} seconds each.\n\n"

        "==========================================================\n"
        "CRITICAL RULE 1: BANNED OPENING CLICHES (DO NOT USE)\n"
        "==========================================================\n"
        "The following opening tropes are STRICTLY FORBIDDEN under all circumstances:\n"
        "  ❌ 'Most people don't know that...'\n"
        "  ❌ 'Few people realize...'\n"
        "  ❌ 'What if everything you knew about X was wrong?'\n"
        "  ❌ 'What if I told you...'\n"
        "  ❌ 'Did you know that...'\n"
        "  ❌ 'Have you ever wondered...'\n"
        "  ❌ 'You won't believe...'\n"
        "  ❌ 'Here is the uncomfortable truth nobody talks about...'\n"
        "  ❌ 'In this video, we will explore...'\n"
        "These are lazy AI cliches that cause immediate viewer drop-off.\n\n"

        "==========================================================\n"
        "CRITICAL RULE 2: MANDATORY HOOK ARCHETYPES (USE ONE)\n"
        "==========================================================\n"
        "Scene 1 MUST open with ONE of these 3 compelling styles:\n"
        "  1. VIVID CONCRETE MOMENT (In-Media-Res): Drop the viewer straight into a sensory physical scene or event in progress.\n"
        "  2. COLD SURPRISING FACT: State a staggering, impossible-sounding fact directly and plainly without warmup words.\n"
        "  3. DIRECT PROVOCATIVE MYSTERY: Present an eerie discrepancy or unsolved anomaly with crisp, direct phrasing.\n\n"

        "==========================================================\n"
        "FEW-SHOT HOOK EXAMPLES (STUDY BEFORE WRITING):\n"
        "==========================================================\n"
        "Topic: Bronze Age Collapse\n"
        "  ❌ BAD:  'What if everything you knew about the Bronze Age collapse was wrong? Civilizations fell in 1200 BCE.'\n"
        "  ✅ GOOD: 'In 1200 BCE, eight flourishing Mediterranean empires were reduced to smoking rubble in less than fifty years—and not a single survivor recorded who attacked them.'\n\n"
        "Topic: The Taos Hum\n"
        "  ❌ BAD:  'Most people don't know that the Taos Hum is a mysterious sound driving residents crazy.'\n"
        "  ✅ GOOD: 'Only two percent of the people in Taos can hear the low diesel engine drone humming beneath their floors, but for those who do, the vibration never stops.'\n\n"
        "Topic: Tunguska Event\n"
        "  ❌ BAD:  'Did you know in 1908 an explosion happened in Siberia? You won't believe how big it was.'\n"
        "  ✅ GOOD: 'Eighty million pine trees were flattened outward in a perfect radial circle across eight hundred square miles of Siberian taiga—without leaving a single crater.'\n\n"
        "Topic: CRISPR Gene Editing\n"
        "  ❌ BAD:  'Have you ever wondered how DNA editing works? CRISPR is changing medicine.'\n"
        "  ✅ GOOD: 'Inside a single drop of fluid, a microscopic enzyme scans three billion letters of genetic code, isolates one mutated syllable, and snips it clean.'\n\n"

        "==========================================================\n"
        "CRITICAL RULE 3: FACTUAL ACCURACY & STATISTICAL CAUTION\n"
        "==========================================================\n"
        "- Be strictly conservative and verified with historical statistics, physical dimensions, blast areas, and casualties.\n"
        "- NEVER invent, misremember, or exaggerate numbers (e.g. Tunguska affected ~800 square miles / 2,150 km², NOT tens of thousands).\n"
        "- When exact figures are debated or uncertain, use accepted conservative estimates or qualitative scale terms ('hundreds of square miles', 'dozens of settlements') to maintain total editorial credibility.\n\n"

        f"{cta_instruction}\n"

        "SCENE GUIDELINES:\n"
        f"- Each scene = 2-3 flowing sentences, approximately {words_per_scene} words.\n"
        "- Write polished, cinematic narration as spoken by a calm, authoritative documentary narrator.\n"
        "- In 'keywords', provide 2-3 concrete visual camera terms describing physical imagery (e.g. 'smoking stone ruins ancient city', 'microscope slide glowing cell', 'radar screen waveform monitor'). Avoid dates, numbers, abstract nouns, and ambiguous words.\n\n"

        "Return ONLY valid JSON (no markdown, no extra text):\n"
        "{\n"
        '  "title": "Compelling SEO-friendly video title",\n'
        '  "scenes": [\n'
        '    {\n'
        f'      "narration": "Full narration text for this scene (~{words_per_scene} words). Write 2-3 complete sentences.",\n'
        '      "keywords": "concrete visual search terms for stock footage",\n'
        f'      "duration_sec": {scene_dur},\n'
        '      "text_overlay": {\n'
        '        "text": "Key phrase to display on screen",\n'
        '        "start_sec": 1,\n'
        '        "duration_sec": 3\n'
        '      }\n'
        '    }\n'
        '  ]\n'
        '}\n\n'
        "text_overlay is optional - include only for 2-3 most impactful scenes. Omit for others.\n\n"
        f"FINAL REMINDER: Total word count across all {scene_count} scenes must be "
        f"{min_words} to {target_words} words. Count them before responding."
    )


BANNED_HOOK_PREFIXES = (
    "most people don't know",
    "most people do not know",
    "few people realize",
    "what if everything you knew",
    "what if i told you",
    "did you know",
    "have you ever wondered",
    "you won't believe",
    "here is the uncomfortable truth",
    "in this video",
)


def _validate_and_clean_script(script, target, min_words, attempt, max_retries):
    """Programmatically checks for forbidden cliches and cleans boilerplate CTAs."""
    scenes = script.get("scenes", [])
    if not scenes:
        raise ValueError("Script contains no scenes.")

    hook_narration = scenes[0].get("narration", "").strip().lower()
    for prefix in BANNED_HOOK_PREFIXES:
        if hook_narration.startswith(prefix) and attempt < max_retries:
            raise ValueError(f"Script opened with forbidden cliche ('{prefix}...'). Retrying for a stronger hook.")

    # For short videos, strip accidental boilerplate CTA endings
    if target <= 45 and len(scenes) >= 1:
        last_scene = scenes[-1]
        narration = last_scene.get("narration", "")
        cleaned_narration = re.sub(
            r"(?i)\s*(like(?:,\s*share,)?\s*and\s*subscribe|like\s*this\s*video\s*if\s*you|subscribe\s*for\s*more(?:\s*content|\s*science|\s*history)?).*$",
            "",
            narration
        ).strip()
        if cleaned_narration and len(cleaned_narration) > 15:
            last_scene["narration"] = cleaned_narration


def generate_script(topic, max_retries=3):
    target = config.TOTAL_TARGET_DURATION

    target_words = int(target * _WPS)
    min_words    = int(target * _WPS * 0.80)
    scene_count  = max(3, round(target / 9))

    client = OpenAI(
        base_url="https://api.groq.com/openai/v1",
        api_key=config.GROQ_API_KEY,
    )

    last_error = None
    for attempt in range(max_retries + 1):
        try:
            if attempt > 0:
                wait = 2 ** attempt
                print(f"[script_generator] Retrying in {wait}s (attempt {attempt + 1})...")
                time.sleep(wait)

            prompt = _build_prompt(target, min_words, target_words, scene_count)

            GROQ_MODELS = [
                "openai/gpt-oss-120b",
                "groq/compound",
                "openai/gpt-oss-20b",
                "qwen/qwen3.8-27b",
            ]

            response = None
            last_model_error = None
            for model_name in GROQ_MODELS:
                for use_json_mode in [True, False]:
                    try:
                        kwargs = {
                            "model": model_name,
                            "messages": [
                                {"role": "system", "content": prompt},
                                {"role": "user",   "content": f"Write a YouTube video script about: {topic}"},
                            ],
                            "temperature": 0.75,
                            "max_tokens": 6000,
                        }
                        if use_json_mode:
                            kwargs["response_format"] = {"type": "json_object"}

                        response = client.chat.completions.create(**kwargs)
                        if response and response.choices and response.choices[0].message.content:
                            break
                    except Exception as me:
                        last_model_error = me
                        err_str = str(me).lower()
                        if "json_validate_failed" in err_str and use_json_mode:
                            # Groq strict server JSON validator rejected format; retry without response_format
                            continue
                        # If model not found, rate-limited, or failed, try next model
                        break
                if response and response.choices and response.choices[0].message.content:
                    break

            if not response:
                raise RuntimeError(f"All Groq models failed. Last error: {last_model_error}")

            content = response.choices[0].message.content.strip()

            json_match = re.search(r'\{.*\}', content, re.DOTALL)
            if json_match:
                content = json_match.group()

            script = json.loads(content)

            if "scenes" not in script or not isinstance(script["scenes"], list):
                raise ValueError("Missing or invalid 'scenes' list in JSON")
            if len(script["scenes"]) < 2:
                raise ValueError(f"Too few scenes: {len(script['scenes'])}")

            for scene in script["scenes"]:
                scene.setdefault("narration", "")
                scene.setdefault("keywords", topic)
                scene.setdefault("duration_sec", round(target / len(script["scenes"])))
                scene["duration_sec"] = max(4, min(20, int(scene["duration_sec"])))

            _validate_and_clean_script(script, target, min_words, attempt, max_retries)

            actual_words = sum(len(s["narration"].split()) for s in script["scenes"])
            est_secs     = round(actual_words / _WPS)

            print(f"[script_generator] Attempt {attempt + 1}: "
                  f"{len(script['scenes'])} scenes, {actual_words} words "
                  f"-> est {est_secs}s (target={target}s, min={min_words} words)")

            if actual_words < min_words and attempt < max_retries:
                if attempt >= 1 and actual_words >= target_words * 0.50:
                    print(f"[script_generator] Accepting script on attempt {attempt + 1} with {actual_words} words.")
                else:
                    shortage = min_words - actual_words
                    raise ValueError(
                        f"Word count too low: {actual_words} (need >={min_words}). "
                        f"Short by {shortage} words. Retrying."
                    )

            # Trim only if significantly over budget
            if actual_words > target_words * 1.30:
                ratio = target_words / actual_words
                for scene in script["scenes"]:
                    words = scene["narration"].split()
                    keep  = max(10, round(len(words) * ratio))
                    if len(words) > keep:
                        scene["narration"] = " ".join(words[:keep])
                actual_words = sum(len(s["narration"].split()) for s in script["scenes"])

            # Scale scene duration_sec to match actual spoken duration
            actual_duration = actual_words / _WPS
            total_scene_dur = sum(s["duration_sec"] for s in script["scenes"])
            if total_scene_dur > 0:
                scale = actual_duration / total_scene_dur
                for s in script["scenes"]:
                    s["duration_sec"] = max(4, min(20, round(s["duration_sec"] * scale)))

            script.setdefault("title", topic.title())
            return script

        except (json.JSONDecodeError, ValueError, KeyError) as e:
            last_error = e
            print(f"[script_generator] Attempt {attempt + 1} failed: {e}")
        except Exception as e:
            last_error = e
            print(f"[script_generator] Attempt {attempt + 1} unexpected error: {e}")

    raise RuntimeError(
        f"Script generation failed after {max_retries + 1} attempts: {last_error}"
    )


# ---------------------------------------------------------------------------
# Transcript to Motivational Visual Scenes Converter
# ---------------------------------------------------------------------------

MOTIVATIONAL_VISUAL_KEYWORDS = [
    "athlete workout gym barbell sweat",
    "man running rain night street",
    "shadow boxing heavy bag training",
    "mountain climber summit cliff sunrise",
    "focused eyes intense look close up",
    "calisthenics pullups muscular back",
    "solitary runner empty highway fog",
    "boxing gloves wrapped hands focus",
    "storm clouds dark lightning timelapse",
    "man looking at city skyline night",
    "running stadium stairs exhaustion push",
    "stopwatch timer track athlete sprint",
    "deadlift chalk barbell powerlifting",
    "cold shower morning discipline routine",
    "heavy ocean waves storm rough sea",
    "man walking alone woods misty dawn",
    "fire embers glowing dark slow motion",
    "basketball player shooting empty court night",
    "military training obstacle mud soldier",
    "deep breathing athlete meditate focus",
]


def segment_transcript_to_scenes(transcript: str, total_duration: float, title: str = "Motivational Speech", speaker_name: str = "") -> dict:
    """
    Takes a transcribed motivational speech and divides it into dynamic visual scene beats
    with physical visual keywords tailored for stock footage sourcing (Pexels / Pixabay).
    Matches 100% of the total_duration.
    """
    import config
    config.reload()

    # Target scene length ~ 5 to 7 seconds for dynamic cutting
    scene_dur = 6.0
    scene_count = max(4, int(total_duration / scene_dur))
    actual_dur_per_scene = total_duration / scene_count

    # Split transcript into sentences or clauses
    raw_sentences = [s.strip() for s in re.split(r'[.!?]+', transcript) if s.strip()]
    if not raw_sentences:
        raw_sentences = [transcript or "Stay disciplined, stay focused, and never give up."]

    # Group sentences into scene buckets
    scenes = []
    sent_idx = 0
    words = transcript.split()
    words_per_bucket = max(5, int(len(words) / scene_count)) if words else 10

    current_time = 0.0
    for i in range(scene_count):
        # Pick motivational visual keyword pool
        kw_idx = i % len(MOTIVATIONAL_VISUAL_KEYWORDS)
        kw = MOTIVATIONAL_VISUAL_KEYWORDS[kw_idx]

        # Extract text snippet for this beat
        chunk_words = []
        while sent_idx < len(raw_sentences) and len(" ".join(chunk_words).split()) < words_per_bucket:
            chunk_words.append(raw_sentences[sent_idx])
            sent_idx += 1

        narration_text = " ".join(chunk_words) if chunk_words else (raw_sentences[i % len(raw_sentences)])

        # Ensure last scene reaches exact total_duration
        if i == scene_count - 1:
            dur = max(2.0, round(total_duration - current_time, 2))
        else:
            dur = round(actual_dur_per_scene, 2)

        scenes.append({
            "narration": narration_text,
            "keywords": kw,
            "duration_sec": dur,
            "start_sec": round(current_time, 2),
        })
        current_time += dur

    print(f"[script_generator] Segmented {total_duration:.1f}s speech into {len(scenes)} visual scene beats (~{actual_dur_per_scene:.1f}s each).")
    return {
        "title": title,
        "speaker_name": speaker_name,
        "scenes": scenes,
    }

