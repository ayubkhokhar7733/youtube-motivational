#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
topic_selector.py — Topic selection, rotation, and anti-collision system.

Features:
- Maintains a topic queue in `data/topic_queue.json`.
- Enforces category diversity (prevents repeating the same category back-to-back).
- Checks past 90-day history (`data/topic_history.json`) using fuzzy string similarity
  to prevent topic repetition or near-duplicate concepts.
- Auto-refills the queue with Groq AI brainstormed topics when count drops below threshold.
- Supports standalone CLI usage and programmatic integration.
"""

import os
import sys
import json
import time
import re
import random
import difflib
import argparse
from datetime import datetime

# UTF-8 encoding configuration for standard output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

DATA_DIR = os.path.join(os.path.dirname(__file__), "data")
QUEUE_FILE = os.path.join(DATA_DIR, "topic_queue.json")
HISTORY_FILE = os.path.join(DATA_DIR, "topic_history.json")

os.makedirs(DATA_DIR, exist_ok=True)

CATEGORIES = [
    "Ancient Megaliths & Engineering",
    "Ancient Technology & Inventions",
    "Archaeological Anomalies",
    "Lost Civilizations & Cities",
]

# Built-in evergreen fallback topics if AI brainstorm is unavailable offline
FALLBACK_TOPIC_BANK = [
    {"topic": "The Antikythera Mechanism: The 2,000-Year-Old Analog Computer", "category": "Ancient History", "keywords": "antikythera mechanism ancient greece computer archaeology"},
    {"topic": "The Wow! Signal: The 72-Second Deep Space Mystery", "category": "Space & Astronomy", "keywords": "wow signal radio telescope astronomy alien signal"},
    {"topic": "The Dancing Plague of 1518: Mass Hysteria in Strasbourg", "category": "Historical Anomalies", "keywords": "dancing plague 1518 strasbourg medieval history hysteria"},
    {"topic": "The Voynich Manuscript: The Book Nobody Can Read", "category": "Unexplained Mysteries", "keywords": "voynich manuscript cipher medieval book unsolved mystery"},
    {"topic": "The Tunguska Event: The 1908 Siberian Explosion", "category": "Science & Natural Disasters", "keywords": "tunguska explosion siberia asteroid meteor 1908"},
    {"topic": "The Great Molasses Flood of 1919", "category": "Historical Anomalies", "keywords": "boston molasses flood 1919 disaster history"},
    {"topic": "How the Ozone Hole Was Discovered and Fixed", "category": "Scientific Discoveries", "keywords": "ozone layer chlorofluorocarbons atmospheric science montreal protocol"},
    {"topic": "The Bronze Age Collapse: When Civilization Disappeared Overnight", "category": "Ancient History", "keywords": "bronze age collapse sea peoples ancient egypt hittites"},
    {"topic": "The Mary Celeste: The Ghost Ship Found Floating Perfectly Intact", "category": "Unexplained Mysteries", "keywords": "mary celeste ghost ship abandoned maritime mystery"},
    {"topic": "The Discovery of Penicillin: The World-Changing Lab Mistake", "category": "Scientific Discoveries", "keywords": "alexander fleming penicillin discovery antibiotics medical science"},
    {"topic": "The Mystery of Gobekli Tepe: The World's Oldest Temple", "category": "Archaeology", "keywords": "gobekli tepe turkey neolithic archaeology ancient temple"},
    {"topic": "The Taos Hum: The Low-Frequency Sound Driving People Mad", "category": "Unexplained Mysteries", "keywords": "taos hum acoustic anomaly mystery sound new mexico"},
    {"topic": "The Library of Alexandria: How Knowledge Was Really Lost", "category": "Ancient History", "keywords": "library alexandria egypt ancient scrolls knowledge destruction"},
    {"topic": "The Great Smog of London 1952: The Fog That Killed Thousands", "category": "Historical Anomalies", "keywords": "great smog london 1952 environmental disaster clean air"},
    {"topic": "The Fermi Paradox: Where Is Everybody in the Universe?", "category": "Space & Astronomy", "keywords": "fermi paradox drake equation extraterrestrial life space astronomy"},
    {"topic": "The Roanoke Colony: What Really Happened to the Lost Settlers?", "category": "Lost Civilizations", "keywords": "roanoke colony croatoan lost settlers north carolina history"},
    {"topic": "The Poison Squad: The Men Who Ate Poison to Create the FDA", "category": "Historical Anomalies", "keywords": "poison squad harvey wiley fda food safety chemistry history"},
    {"topic": "The Klerksdorp Spheres: 3-Billion-Year-Old Natural Curiosities", "category": "Archaeology", "keywords": "klerksdorp spheres south africa geology out of place artifact"},
    {"topic": "The Wow of the Deep Sea: The Bloop and Mariana Trench Sounds", "category": "Unexplained Mysteries", "keywords": "bloop ocean acoustics mariana trench underwater sound mystery"},
    {"topic": "The Carrington Event of 1859: The Solar Storm That Fried Telegraphs", "category": "Space & Astronomy", "keywords": "carrington event solar flare geomagnetic storm telegraph history"},
]


def load_queue() -> list:
    if os.path.exists(QUEUE_FILE):
        try:
            with open(QUEUE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("queue", [])
        except Exception:
            pass
    return []


def save_queue(queue: list):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump({"queue": queue}, f, indent=2, ensure_ascii=False)


def load_history() -> list:
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data.get("history", [])
        except Exception:
            pass
    return []


def save_history(history: list):
    with open(HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump({"history": history}, f, indent=2, ensure_ascii=False)


def _similarity(s1: str, s2: str) -> float:
    """Calculate normalized token + sequence similarity ratio."""
    s1_clean = re.sub(r'[^a-zA-Z0-9 ]+', '', s1.lower()).strip()
    s2_clean = re.sub(r'[^a-zA-Z0-9 ]+', '', s2.lower()).strip()
    
    # 1. Sequence matcher
    seq_ratio = difflib.SequenceMatcher(None, s1_clean, s2_clean).ratio()
    
    # 2. Token overlap
    t1 = set(s1_clean.split())
    t2 = set(s2_clean.split())
    if t1 and t2:
        jaccard = len(t1 & t2) / len(t1 | t2)
    else:
        jaccard = 0.0
        
    return max(seq_ratio, jaccard)


def is_topic_recent_collision(topic: str, days_threshold: int = 90, similarity_threshold: float = 0.65) -> tuple:
    """
    Check if a topic collides with any video produced in the last `days_threshold` days.
    Returns (is_collision: bool, matched_topic: str, score: float).
    """
    history = load_history()
    now = time.time()
    cutoff_time = now - (days_threshold * 86400)

    for item in reversed(history):
        timestamp = item.get("timestamp", 0)
        if timestamp < cutoff_time:
            continue
        past_topic = item.get("topic", "")
        past_title = item.get("title", "")

        score_topic = _similarity(topic, past_topic)
        score_title = _similarity(topic, past_title)
        best_score = max(score_topic, score_title)

        if best_score >= similarity_threshold:
            return True, past_topic or past_title, best_score

    return False, None, 0.0


def refill_topic_queue(batch_size: int = 20, min_threshold: int = 5, force: bool = False) -> int:
    """
    Brainstorm new topics using Groq API (or fallback bank) and append to queue.
    """
    queue = load_queue()
    if len(queue) >= min_threshold and not force:
        return 0

    import config
    config.reload()
    api_key = config.GROQ_API_KEY

    new_topics = []

    # Attempt Groq API brainstorming if key is available
    if api_key and not api_key.startswith("gsk_placeholder") and "your_" not in api_key:
        try:
            from openai import OpenAI
            client = OpenAI(base_url="https://api.groq.com/openai/v1", api_key=api_key)
            prompt = (
                f"You are a lead topic researcher for an automated high-retention YouTube channel.\n"
                f"Brainstorm {batch_size} unique, high-retention video topic ideas that pair well with cinematic stock footage.\n"
                f"Distribute evenly across categories: {', '.join(CATEGORIES)}.\n"
                f"Focus on deep-dive curiosity, compelling storytelling, and powerful hooks.\n\n"
                f"Output strictly valid JSON:\n"
                f"{{\n"
                f'  "topics": [\n'
                f'    {{"topic": "Specific intriguing topic title", "category": "Category Name", "keywords": "3-5 search keywords"}}\n'
                f'  ]\n'
                f"}}"
            )
            GROQ_MODELS = [
                "openai/gpt-oss-120b",
                "llama-3.3-70b-versatile",
                "llama-3.1-70b-versatile",
                "qwen/qwen3.6-27b",
                "openai/gpt-oss-20b",
                "groq/compound",
            ]
            response = None
            for model_name in GROQ_MODELS:
                try:
                    response = client.chat.completions.create(
                        model=model_name,
                        messages=[
                            {"role": "system", "content": prompt},
                            {"role": "user", "content": f"Generate {batch_size} fresh history and science topics."},
                        ],
                        temperature=0.85,
                        response_format={"type": "json_object"},
                    )
                    break
                except Exception as me:
                    if "does not exist" in str(me) or "model_not_found" in str(me):
                        continue
                    raise me

            if response:
                content = response.choices[0].message.content.strip()
                data = json.loads(content)
                new_topics = data.get("topics", [])
        except Exception as e:
            print(f"[topic_selector] Groq brainstorm failed, using fallback bank: {e}")

    # If API unavailable or failed, use fallback catalog
    if not new_topics:
        existing_topics_set = {item.get("topic", "").lower() for item in queue}
        for item in FALLBACK_TOPIC_BANK:
            if item["topic"].lower() not in existing_topics_set:
                new_topics.append(item.copy())

    # Filter out collisions against past history and existing queue
    added_count = 0
    existing_topics_set = {item.get("topic", "").lower() for item in queue}

    for item in new_topics:
        topic_text = item.get("topic", "").strip()
        if not topic_text:
            continue
        if topic_text.lower() in existing_topics_set:
            continue
        is_collision, matched, score = is_topic_recent_collision(topic_text)
        if is_collision:
            continue

        queue.append({
            "topic": topic_text,
            "category": item.get("category", "History & Science"),
            "keywords": item.get("keywords", topic_text),
        })
        existing_topics_set.add(topic_text.lower())
        added_count += 1

    save_queue(queue)
    return added_count


def get_next_topic(category_avoid_limit: int = 2) -> dict:
    """
    Selects the next optimal topic from the queue:
    1. Ensures queue is sufficiently stocked (auto-refills if low).
    2. Avoids picking the same category as the last `category_avoid_limit` runs.
    3. Checks 90-day anti-collision.
    4. Removes topic from queue and returns topic dict.
    """
    refill_topic_queue(min_threshold=4)
    queue = load_queue()

    if not queue:
        # Last resort fallback if queue is empty
        selected = random.choice(FALLBACK_TOPIC_BANK).copy()
        return selected

    history = load_history()
    recent_categories = [h.get("category") for h in history[-category_avoid_limit:] if h.get("category")]

    # Find the best candidate in queue
    best_candidate_idx = None
    for idx, item in enumerate(queue):
        cat = item.get("category", "")
        topic = item.get("topic", "")

        # Skip if in recent categories and other options exist
        if cat in recent_categories and len(queue) > 1:
            continue

        # Check anti-collision against 90-day history
        is_collision, matched, _ = is_topic_recent_collision(topic)
        if is_collision:
            continue

        best_candidate_idx = idx
        break

    if best_candidate_idx is None:
        best_candidate_idx = 0

    selected = queue.pop(best_candidate_idx)
    save_queue(queue)
    return selected


def mark_topic_used(topic_item: dict, video_title: str = None, youtube_id: str = None):
    """
    Records a completed topic run in `data/topic_history.json`.
    """
    history = load_history()
    history.append({
        "topic": topic_item.get("topic", ""),
        "category": topic_item.get("category", "General"),
        "keywords": topic_item.get("keywords", ""),
        "title": video_title or topic_item.get("topic", ""),
        "youtube_id": youtube_id,
        "timestamp": time.time(),
        "date": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    # Keep up to 365 days of history (~1000 items)
    if len(history) > 1000:
        history = history[-1000:]
    save_history(history)


def main():
    parser = argparse.ArgumentParser(description="Topic selection and queue management CLI.")
    parser.add_argument("--next", action="store_true", help="Pop and return the next topic for video generation.")
    parser.add_argument("--peek", action="store_true", help="View the next topic without removing it from the queue.")
    parser.add_argument("--list", action="store_true", help="List all topics currently in the queue.")
    parser.add_argument("--refill", action="store_true", help="Force refill the topic queue with fresh brainstormed topics.")
    parser.add_argument("--history", action="store_true", help="Show recent topic history.")

    args = parser.parse_args()

    if args.refill:
        added = refill_topic_queue(batch_size=20, force=True)
        print(f"✅ Added {added} fresh topics to queue. Total in queue: {len(load_queue())}")
    elif args.list:
        queue = load_queue()
        print(f"\n--- Topic Queue ({len(queue)} topics) ---")
        for i, item in enumerate(queue, 1):
            print(f"{i:2d}. [{item.get('category', 'General')}] {item.get('topic')}")
    elif args.history:
        hist = load_history()
        print(f"\n--- Topic History ({len(hist)} entries) ---")
        for i, item in enumerate(hist[-15:], 1):
            print(f"{i:2d}. {item.get('date', 'Unknown')}: [{item.get('category')}] {item.get('topic')}")
    elif args.peek:
        queue = load_queue()
        if queue:
            print(json.dumps(queue[0], indent=2))
        else:
            print("Queue is currently empty.")
    else:
        topic = get_next_topic()
        print(json.dumps(topic, indent=2))


if __name__ == "__main__":
    main()
