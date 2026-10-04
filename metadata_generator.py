#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
metadata_generator.py — High-SEO YouTube Metadata Generation Engine.

Follows the exact prompt architecture specified in MASTER_PLAN.md §4b.
Generates:
1. Optimized Title (60-70 chars, rotating across patterns a/b/c/d/e).
2. Comprehensive SEO Description (150-300 words with standalone hook & search paragraph).
3. 15-20 Targeted & Long-Tail Tags.
4. YouTube Category Classification (Education, Science & Technology, or Entertainment).
5. Logs pattern usage to `data/title_pattern_history.json` for CTR & rotation tracking.
"""

import os
import sys
import json
import time
import re
import random
import argparse
from datetime import datetime

# UTF-8 output configuration
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
PATTERN_HISTORY_FILE = os.path.join(DATA_DIR, "title_pattern_history.json")

os.makedirs(DATA_DIR, exist_ok=True)

# The 5 proven title patterns from MASTER_PLAN.md §4b
TITLE_PATTERNS = {
    "a": "Curiosity gap: 'The [Topic] Detail Nobody Talks About'",
    "b": "Number/list: '5 [Topic] Facts That Sound Fake (But Aren't)'",
    "c": "Question hook: 'Why Did [Historical Event] Actually Happen?'",
    "d": "Myth-bust: 'The Truth About [Common Belief] Is Not What You Think'",
    "e": "Stakes/scale: 'The [Topic] That Changed Everything'",
}

# The EXACT prompt template from MASTER_PLAN.md §4b
SYSTEM_PROMPT_TEMPLATE = """You are a YouTube SEO specialist creating high-retention video metadata for a US English-speaking audience. Given the video script below, generate:

1. TITLE (60-70 characters max):
   - Use ONE of these proven patterns, rotate across videos, never repeat the same pattern twice in a row:
     a) Curiosity gap: "The [Topic] Detail Nobody Talks About"
     b) Number/list: "5 [Topic] Facts That Sound Fake (But Aren't)"
     c) Question hook: "Why Did [Topic] Actually Happen?"
     d) Myth-bust: "The Truth About [Topic] Is Not What You Think"
     e) Stakes/scale: "The [Topic] That Changed Everything"
   - Must accurately reflect the script content — no clickbait that isn't paid off in the video
   - Front-load the specific noun/topic in the first 40 characters (helps both CTR and search)
   - No ALL CAPS, no more than one emoji if any

2. DESCRIPTION (150-300 words):
   - First 2 sentences must work standalone (shown in search/suggested previews) — restate the hook, don't just repeat the title
   - Include 3-5 sentences summarizing what's actually covered (real content summary, not vague teasing)
   - Include a natural-language paragraph with likely search terms a curious viewer would type (not a keyword-stuffed list)
   - End with a one-line channel note and upload schedule reminder
   - Do NOT use engagement-bait phrases like "like and subscribe" as the primary CTA — one soft mention max

3. TAGS (15-20 tags):
   - Mix of broad and specific tags matching the exact topic, figures, and concepts
   - Include 2-3 long-tail phrases matching how someone would actually search ("why did X happen", "truth about X")
   - No unrelated trending tags just for reach — must match actual content

4. CATEGORY: classify as one of [Education, Science & Technology, Entertainment, People & Blogs] based on content

Output as JSON: {{"title": "...", "description": "...", "tags": [...], "category": "...", "pattern_used": "{preferred_pattern}"}}"""


def load_pattern_history() -> list:
    if os.path.exists(PATTERN_HISTORY_FILE):
        try:
            with open(PATTERN_HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("pattern_history", [])
        except Exception:
            pass
    return []


def save_pattern_history(history: list):
    with open(PATTERN_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"pattern_history": history}, f, indent=2, ensure_ascii=False)


def get_next_preferred_pattern() -> str:
    """Returns the next pattern code (a/b/c/d/e) to enforce non-repeating rotation."""
    history = load_pattern_history()
    pattern_keys = ["a", "b", "c", "d", "e"]
    if not history:
        return random.choice(pattern_keys)

    last_pattern = history[-1].get("pattern_used", "")
    available = [p for p in pattern_keys if p != last_pattern]
    return random.choice(available)


def log_pattern_usage(pattern: str, title: str, topic: str):
    history = load_pattern_history()
    history.append({
        "pattern_used": pattern,
        "title": title,
        "topic": topic,
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    if len(history) > 500:
        history = history[-500:]
    save_pattern_history(history)


def clean_topic_for_pattern(topic: str) -> str:
    """Cleans a topic string for embedding into pattern templates."""
    clean = topic.strip()
    # If topic has a colon with a long subtitle, use the main topic name if sufficiently descriptive
    if ":" in clean:
        parts = clean.split(":", 1)
        main_part = parts[0].strip()
        if len(main_part) >= 12:
            clean = main_part
    return clean


def strip_leading_article(text: str) -> str:
    """Strips leading 'the', 'a', 'an' (case-insensitive) to prevent 'The The' duplications."""
    return re.sub(r'^(the|a|an)\s+', '', text.strip(), flags=re.IGNORECASE)


def truncate_title(title: str, max_length: int = 70) -> str:
    """
    Intelligently shortens a title to max_length characters without mid-word splits.
    Eliminates duplicate articles and removes trailing punctuation cleanly.
    """
    title = " ".join(title.split()).strip()
    # Fix duplicate leading articles
    title = re.sub(r'^(the\s+)+the\b', 'The', title, flags=re.IGNORECASE)
    title = re.sub(r'^(a\s+)+a\b', 'A', title, flags=re.IGNORECASE)
    
    if len(title) <= max_length:
        return title
    
    # Try cutting at natural phrase breaks if the prefix is well-formed
    for delim in [": ", " - ", " – ", " — "]:
        if delim in title:
            prefix = title.split(delim)[0].strip()
            if 30 <= len(prefix) <= max_length:
                return prefix

    # Cut at word boundary without cutting mid-word
    cut = title[:max_length].rsplit(" ", 1)[0].rstrip(" ,;:-—")
    return cut


def build_pattern_title(pattern: str, topic: str) -> str:
    """Constructs a deterministic high-CTR title according to the chosen pattern."""
    base_topic = clean_topic_for_pattern(topic)
    topic_no_art = strip_leading_article(base_topic)
    
    titles_map = {
        "a": f"The {topic_no_art} Detail Nobody Talks About",
        "b": f"5 {topic_no_art} Facts That Sound Fake (But Aren't)",
        "c": f"Why Did {base_topic} Actually Happen?",
        "d": f"The Truth About {base_topic} Is Not What You Think",
        "e": f"The {topic_no_art} That Changed Everything",
    }
    raw_title = titles_map.get(pattern, titles_map["a"])
    return truncate_title(raw_title, max_length=70)


def _generate_mock_metadata(script: dict, topic: str, preferred_pattern: str) -> dict:
    """Generates structured SEO metadata strictly following §4b rules without API calls."""
    clean_topic = topic.strip() or script.get("title", "Historical Discovery")
    title = build_pattern_title(preferred_pattern, clean_topic)

    # Script summary extraction
    scenes = script.get("scenes", [])
    script_text = " ".join(s.get("narration", "") for s in scenes)
    summary_snippet = script_text[:250] if script_text else f"A deep dive into the fascinating history and science of {clean_topic}."

    description = (
        f"What really happened with {clean_topic}? While most people know the basic story, "
        f"the deeper truth reveals a far more complex and surprising reality.\n\n"
        f"In this video, we explore the crucial details behind {clean_topic}. {summary_snippet} "
        f"From ancient archives to modern scientific breakthroughs, the evidence shows why this event continues to challenge historians and scientists today.\n\n"
        f"For curious minds exploring forgotten history, ancient technology, and unexplained science mysteries, "
        f"understanding the true story of {clean_topic} offers fresh perspective on how historical discoveries shape our world.\n\n"
        f"Quiet Curiosities explores the untold stories of history, science, and the unexplained. New videos uploaded daily."
    )

    short_topic = clean_topic.split(":")[0].split(" - ")[0].strip().lower()
    tags = [
        "history facts",
        "science facts",
        "educational documentary",
        "ancient history",
        "did you know",
        short_topic,
        f"history of {short_topic}",
        f"truth about {short_topic}",
        f"why did {short_topic} happen",
        f"secrets of {short_topic}",
        "unexplained mysteries",
        "historical discoveries",
        "science explainer",
        "forgotten history",
        "fascinating facts",
    ]

    category = "Education"
    if any(k in clean_topic.lower() for k in ["space", "quantum", "physics", "science", "biology", "ozone", "computer"]):
        category = "Science & Technology"

    return {
        "title": title,
        "description": description.strip(),
        "tags": tags[:18],
        "category": category,
        "pattern_used": preferred_pattern,
    }


def generate_metadata(script: dict, topic: str = "", mock: bool = False) -> dict:
    """
    Generates YouTube metadata (Title, Description, Tags, Category) for a video script.
    
    Adheres strictly to the prompt engineering in MASTER_PLAN.md §4b.
    """
    preferred_pattern = get_next_preferred_pattern()
    clean_topic = topic or script.get("title", "")

    import config
    config.reload()
    api_key = str(config.GROQ_API_KEY or "").strip("\ufeff \r\n\t")

    # Use mock fallback if requested or if Groq key is unavailable
    if mock or not api_key or api_key.startswith("gsk_placeholder") or "your_" in api_key:
        metadata = _generate_mock_metadata(script, clean_topic, preferred_pattern)
        log_pattern_usage(metadata.get("pattern_used", preferred_pattern), metadata["title"], clean_topic)
        return metadata

    # Format script for Groq prompt
    script_repr = f"TOPIC: {clean_topic}\n\nSCENES:\n"
    for i, s in enumerate(script.get("scenes", []), 1):
        script_repr += f"Scene {i}: {s.get('narration', '')}\n"

    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(preferred_pattern=preferred_pattern)

    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
        GROQ_MODELS = [
            "openai/gpt-oss-120b",
            "openai/gpt-oss-20b",
            "groq/compound-mini",
        ]

        response = None
        for model_name in GROQ_MODELS:
            try:
                response = client.chat.completions.create(
                    model=model_name,
                    messages=[
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": f"Generate YouTube SEO metadata for this script:\n\n{script_repr}"},
                    ],
                    temperature=0.7,
                    max_tokens=2000,
                    response_format={"type": "json_object"},
                )
                break
            except Exception as me:
                err_str = str(me).lower()
                if any(x in err_str for x in ["does not exist", "model_not_found", "decommissioned", "json_validate_failed"]):
                    continue
                raise me

        if not response:
            raise RuntimeError("No available Groq model could generate metadata.")

        content = response.choices[0].message.content.strip()
        data = json.loads(content)

        # Validate fields
        raw_title = data.get("title", build_pattern_title(preferred_pattern, clean_topic))
        title = truncate_title(raw_title, max_length=70)
        description = data.get("description", "")
        tags = data.get("tags", ["history", "science", clean_topic])
        category = data.get("category", "Education")
        pattern = data.get("pattern_used", preferred_pattern)

        result = {
            "title": title,
            "description": description,
            "tags": tags,
            "category": category,
            "pattern_used": pattern,
        }

        log_pattern_usage(pattern, title, clean_topic)
        return result

    except Exception as e:
        print(f"[metadata_generator] Groq metadata generation failed, using structured fallback: {e}")
        fallback = _generate_mock_metadata(script, clean_topic, preferred_pattern)
        log_pattern_usage(fallback.get("pattern_used", preferred_pattern), fallback["title"], clean_topic)
        return fallback


# ---------------------------------------------------------------------------
# Motivational Speech Metadata Spinner
# ---------------------------------------------------------------------------

def spin_motivational_metadata(
    original_title: str = "",
    original_description: str = "",
    original_tags: list = None,
    speaker_name: str = "",
    transcript: str = "",
    mock: bool = False,
    **kwargs,
) -> dict:
    """
    Takes the original YouTube video title, description, tags, and speech transcript,
    and generates an altered, high-performing title variant, enhanced description,
    and targeted motivational tags.
    """
    if "raw_title" in kwargs and not original_title:
        original_title = kwargs["raw_title"]
    if "raw_description" in kwargs and not original_description:
        original_description = kwargs["raw_description"]
    if "raw_tags" in kwargs and original_tags is None:
        original_tags = kwargs["raw_tags"]
    if original_tags is None:
        original_tags = []

    import config
    config.reload()
    api_key = config.GROQ_API_KEY

    clean_speaker = speaker_name.strip() if speaker_name else "Motivational Leader"

    def _fallback_spin():
        templates = [
            f"{clean_speaker}: The Uncomfortable Truth Nobody Wants To Hear",
            f"{clean_speaker}: The One Rule That Changes Everything",
            f"{clean_speaker}: Why 99% Of People Never Succeed (Fix This)",
            f"{clean_speaker}: Do This Every Morning And Watch Your Life Change",
            f"{clean_speaker}: The Brutal Reality Of Success And Discipline",
        ]
        spun_title = truncate_title(random.choice(templates), max_length=70)
        spun_desc = (
            f"Powerful motivational speech featuring {clean_speaker} on mindset, relentless discipline, and overcoming adversity.\n\n"
            f"\"If you want to change your life, you have to be willing to do the things everyone else avoids.\"\n\n"
            f"Speaker: {clean_speaker}\n"
            f"Music: Copyright-free ambient motivational soundtrack.\n\n"
            f"Daily motivational speeches and mindset inspiration. Subscribe for your daily reminder to stay focused and keep pushing."
        )
        base_tags = [
            clean_speaker.lower(),
            f"{clean_speaker.lower()} motivation",
            f"{clean_speaker.lower()} speech",
            "motivation",
            "motivational speech",
            "discipline",
            "mental toughness",
            "mindset",
            "success motivation",
            "morning motivation",
            "self improvement",
            "life advice",
            "best motivational video",
        ]
        return {
            "title": spun_title,
            "description": spun_desc,
            "tags": base_tags[:18],
            "category": "People & Blogs",
            "speaker_name": clean_speaker,
        }

    if mock or not api_key or api_key.startswith("gsk_placeholder") or "your_" in api_key:
        return _fallback_spin()

    try:
        from openai import OpenAI
        client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)

        prompt = (
            "You are an elite YouTube strategist specializing in high-performing motivational speech channels (like Motiversity, Ben Lionel Scott, Be Inspired).\n"
            "Given the original video title, description, and transcript snippet below, generate:\n\n"
            "1. TITLE (50-68 characters max):\n"
            "   - Re-write the original title to be distinct and fresh, but targeting the exact same emotional appeal and viewer curiosity.\n"
            f"   - ALWAYS front-load the speaker's name: '{clean_speaker}: [Punchy Hook / Insight]'\n"
            "   - Clean formatting: Capitalize First Letters, no ALL CAPS, no emojis.\n"
            "   - High CTR, direct, intense, urgent.\n\n"
            "2. DESCRIPTION (150-250 words):\n"
            "   - First 2 sentences must hook the viewer and summarize the core lesson.\n"
            "   - Highlight a powerful quote extracted from the transcript.\n"
            f"   - Give clear editorial credit: 'Speaker: {clean_speaker}'.\n"
            "   - Add 3-4 lines of natural search queries for people seeking discipline, focus, and motivation.\n"
            "   - End with a clean channel note.\n\n"
            "3. TAGS (15-20 tags):\n"
            f"   - Mix of specific tags ({clean_speaker}, {clean_speaker} speech, {clean_speaker} motivation) and top motivational search queries.\n\n"
            "4. CATEGORY: 'People & Blogs' or 'Education'.\n\n"
            f"ORIGINAL TITLE: {original_title}\n"
            f"ORIGINAL DESCRIPTION SNIPPET: {original_description[:400]}\n"
            f"SPEAKER: {clean_speaker}\n"
            f"TRANSCRIPT SNIPPET: {transcript[:500]}\n\n"
            "Output strictly valid JSON:\n"
            "{\"title\": \"...\", \"description\": \"...\", \"tags\": [...], \"category\": \"...\"}"
        )

        resp = client.chat.completions.create(
            model="openai/gpt-oss-120b",
            messages=[{"role": "user", "content": prompt}],
            temperature=0.7,
            response_format={"type": "json_object"},
        )
        data = json.loads(resp.choices[0].message.content.strip())
        raw_title = data.get("title", "")
        if not raw_title:
            return _fallback_spin()

        title = truncate_title(raw_title, max_length=70)
        desc = data.get("description", "")
        tags = data.get("tags", [clean_speaker, "motivation", "discipline"])
        cat = data.get("category", "People & Blogs")

        print(f"[metadata_generator] Spun altered title: \"{title}\" (from \"{original_title[:45]}...\")")
        return {
            "title": title,
            "description": desc,
            "tags": tags[:18],
            "category": cat,
            "speaker_name": clean_speaker,
        }
    except Exception as e:
        print(f"[metadata_generator] LLM metadata spinning failed: {e}. Using fallback.")
        return _fallback_spin()


def main():
    parser = argparse.ArgumentParser(description="YouTube SEO Metadata Generator CLI.")
    parser.add_argument("--topic", type=str, default="The Antikythera Mechanism", help="Topic to generate metadata for.")
    parser.add_argument("--mock", action="store_true", help="Run with mock/offline generation.")

    args = parser.parse_args()

    dummy_script = {
        "title": args.topic,
        "scenes": [
            {"narration": f"What if the ancient Greeks built a computer 2,000 years before modern technology existed? The Antikythera Mechanism was found in a shipwreck."},
            {"narration": "X-ray scans revealed over thirty precision bronze gears capable of predicting astronomical positions and eclipses decades in advance."},
            {"narration": "Historians now believe classical civilization was far closer to an industrial revolution than previously imagined."},
        ],
    }

    metadata = generate_metadata(dummy_script, topic=args.topic, mock=args.mock)
    print("\n--- Generated YouTube Metadata ---")
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
