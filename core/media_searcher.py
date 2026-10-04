"""
media_searcher.py — Parallel media downloading with a rich clip pool.

Strategy:
  - For every scene, fetch up to 3 video clips AND up to 3 images in parallel
  - All downloads go into a shared "media pool"
  - The video composer then slices the pool into fast 2-4 s cuts for each scene
    instead of looping the same clip over and over
"""
import os
import requests
from requests.adapters import HTTPAdapter
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from PIL import Image, ImageDraw, ImageFont
import config

PIXABAY_URL       = "https://pixabay.com/api/"
PIXABAY_VIDEO_URL = "https://pixabay.com/api/videos/"
PEXELS_URL        = "https://api.pexels.com/v1/search"
PEXELS_VIDEO_URL  = "https://api.pexels.com/videos/search"

# Thread-safe persistent session with connection pooling and standard browser headers
_session = requests.Session()
_adapter = HTTPAdapter(pool_connections=20, pool_maxsize=20, max_retries=2)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)
_session.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,video/*,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
})

# Thread-safe lock for file system writes
_fs_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Orientation helpers
# ---------------------------------------------------------------------------

def _api_orientation():
    """Return (pixabay_orient, pexels_orient) strings based on current config."""
    if config.VIDEO_WIDTH > config.VIDEO_HEIGHT:
        return "horizontal", "landscape"
    elif config.VIDEO_WIDTH < config.VIDEO_HEIGHT:
        return "vertical", "portrait"
    else:
        return "horizontal", "square"


# ---------------------------------------------------------------------------
# Video search
# ---------------------------------------------------------------------------

def search_videos_pixabay(query, per_page=5):
    if not config.PIXABAY_API_KEY:
        print("[media-searcher] [WARN] PIXABAY_API_KEY is not configured or empty!")
        return []
    pix_orient, _ = _api_orientation()
    params = {
        "key":         config.PIXABAY_API_KEY,
        "q":           query,
        "video_type":  "all",
        "orientation": pix_orient,
        "per_page":    max(3, per_page),
        "safesearch":  "true",
    }
    try:
        resp = _session.get(PIXABAY_VIDEO_URL, params=params, timeout=12)
        if resp.status_code == 200:
            urls = []
            target_w = 1280 if config.VIDEO_WIDTH > config.VIDEO_HEIGHT else 720
            for hit in resp.json().get("hits", []):
                videos = hit.get("videos", {})
                available = []
                for quality in ("medium", "small", "large", "tiny"):
                    v = videos.get(quality)
                    if v and v.get("url"):
                        width = v.get("width") or (
                            1920 if quality == "large"  else
                            1280 if quality == "medium" else
                            960  if quality == "small"  else 640)
                        available.append((width, v["url"]))
                if available:
                    available.sort(key=lambda x: abs(x[0] - target_w))
                    urls.append(available[0][1])
            return urls
        else:
            print(f"[media-searcher] [WARN] Pixabay Video API returned HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"[media-searcher] [WARN] Pixabay Video request failed: {e}")
    return []


def search_videos_pexels(query, per_page=5):
    if not config.PEXELS_API_KEY:
        print("[media-searcher] [WARN] PEXELS_API_KEY is not configured or empty!")
        return []
    _, pex_orient = _api_orientation()
    headers = {"Authorization": config.PEXELS_API_KEY}
    params  = {"query": query, "per_page": max(1, per_page), "orientation": pex_orient, "size": "medium"}
    try:
        resp = _session.get(PEXELS_VIDEO_URL, headers=headers, params=params, timeout=12)
        if resp.status_code == 200:
            urls = []
            target_w = 1280 if config.VIDEO_WIDTH > config.VIDEO_HEIGHT else 720
            for vid in resp.json().get("videos", []):
                files = vid.get("video_files", [])
                if files:
                    files_sorted = sorted(files, key=lambda f: abs(f.get("width", 0) - target_w))
                    for f in files_sorted:
                        if f.get("link"):
                            urls.append(f["link"])
                            break
            return urls
        else:
            print(f"[media-searcher] [WARN] Pexels Video API returned HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"[media-searcher] [WARN] Pexels Video request failed: {e}")
    return []


# ---------------------------------------------------------------------------
# Image search
# ---------------------------------------------------------------------------

def search_images_pixabay(query, per_page=5):
    if not config.PIXABAY_API_KEY:
        return []
    pix_orient, _ = _api_orientation()
    params = {
        "key":         config.PIXABAY_API_KEY,
        "q":           query,
        "image_type":  "photo",
        "orientation": pix_orient,
        "per_page":    max(3, per_page),
        "safesearch":  "true",
        "min_width":   1280,
        "min_height":  720,
    }
    try:
        resp = _session.get(PIXABAY_URL, params=params, timeout=12)
        if resp.status_code == 200:
            urls = []
            for hit in resp.json().get("hits", []):
                img_url = hit.get("largeImageURL") or hit.get("webformatURL")
                if img_url:
                    urls.append(img_url)
            return urls
        else:
            print(f"[media-searcher] [WARN] Pixabay Image API returned HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"[media-searcher] [WARN] Pixabay Image request failed: {e}")
    return []


def search_images_pexels(query, per_page=5):
    if not config.PEXELS_API_KEY:
        return []
    _, pex_orient = _api_orientation()
    headers = {"Authorization": config.PEXELS_API_KEY}
    params  = {"query": query, "per_page": max(1, per_page), "orientation": pex_orient, "size": "large"}
    try:
        resp = _session.get(PEXELS_URL, headers=headers, params=params, timeout=12)
        if resp.status_code == 200:
            urls = []
            for photo in resp.json().get("photos", []):
                src = photo.get("src", {})
                img_url = src.get("large") or src.get("large2x") or src.get("original")
                if img_url:
                    urls.append(img_url)
            return urls
        else:
            print(f"[media-searcher] [WARN] Pexels Image API returned HTTP {resp.status_code}: {resp.text[:120]}")
    except Exception as e:
        print(f"[media-searcher] [WARN] Pexels Image request failed: {e}")
    return []


# ---------------------------------------------------------------------------
# Download helpers
# ---------------------------------------------------------------------------

def _download_file(url, filepath, timeout=30):
    for attempt in range(2):
        try:
            resp = _session.get(url, timeout=timeout, stream=True)
            if resp.status_code == 200:
                with _fs_lock:
                    os.makedirs(os.path.dirname(filepath), exist_ok=True)
                with open(filepath, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=131072):
                        if chunk:
                            f.write(chunk)
                return True
            else:
                print(f"[media-searcher] [WARN] File download HTTP {resp.status_code} for {url[:80]}")
        except Exception as e:
            if attempt == 0:
                continue
            print(f"[media-searcher] [WARN] File download error for {url[:80]}: {e}")
    return False


def download_video(url, scene_index, slot=0):
    filepath = os.path.join(config.TEMP_DIR, f"scene_{scene_index:02d}_vid_{slot}.mp4")
    if _download_file(url, filepath, timeout=60):
        if os.path.exists(filepath) and os.path.getsize(filepath) > 50_000:
            return filepath
    return None


def download_image(url, scene_index, slot=0):
    ext = url.split("?")[0].rsplit(".", 1)[-1].lower()
    if ext not in ("jpg", "jpeg", "png", "webp"):
        ext = "jpg"
    filepath = os.path.join(config.TEMP_DIR, f"scene_{scene_index:02d}_img_{slot}.{ext}")
    if _download_file(url, filepath, timeout=20):
        return filepath
    return None



# ---------------------------------------------------------------------------
# Fallback image generator
# ---------------------------------------------------------------------------

def generate_fallback_image(scene_index, text):
    width, height = config.VIDEO_WIDTH, config.VIDEO_HEIGHT
    filepath = os.path.join(config.TEMP_DIR, f"scene_{scene_index:02d}_fallback.jpg")

    from PIL import Image as _Img
    img  = _Img.new("RGB", (width, height), (18, 22, 34))
    draw = ImageDraw.Draw(img)

    font = None
    if os.path.exists(config.FONT_PATH):
        try:
            font = ImageFont.truetype(config.FONT_PATH, max(48, width // 30))
        except Exception:
            pass
    if font is None:
        font = ImageFont.load_default()

    words = text.split()
    lines, line = [], ""
    for word in words:
        test = (line + " " + word).strip()
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] - bbox[0] > width - 120:
            lines.append(line)
            line = word
        else:
            line = test
    if line:
        lines.append(line)
    lines = lines[:5]

    total_h = len(lines) * 72
    y = (height - total_h) // 2
    for ln in lines:
        bbox = draw.textbbox((0, 0), ln, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x + 2, y + 2), ln, fill=(0, 0, 0), font=font)
        draw.text((x, y), ln, fill=(220, 230, 250), font=font)
        y += 72

    draw.rectangle([0, height - 70, width, height], fill=(30, 40, 65))
    draw.text((40, height - 50), "AI Video Generator",
              fill=(88, 166, 255), font=ImageFont.load_default())

    img.save(filepath, quality=90)
    return filepath, "image"


# ---------------------------------------------------------------------------
# Visual query extraction & disambiguation
# ---------------------------------------------------------------------------

DISAMBIGUATION_MAP = {
    "blast": "meteor explosion forest",
    "explosion": "fire explosion disaster",
    "collapse": "ancient ruins destruction",
    "flood": "rushing water river flood",
    "oddities": "vintage historical artifacts",
    "curiosities": "antique mystery documents",
    "event": "dramatic storm clouds sky",
    "plague": "medieval historical village",
    "dancing": "medieval town crowd",
    "manuscript": "ancient book parchment",
    "voynich": "mysterious old parchment",
    "tunguska": "siberian meteor explosion forest",
    "molasses": "surging dark flood wave",
}

NOISE_WORDS = {
    "1908", "1919", "1518", "2026", "facts", "fact", "truth", "secrets", "secret",
    "nobody", "talks", "about", "did", "you", "know", "sound", "fake", "shocking",
    "unexplained", "mystery", "mysteries", "history", "top", "5", "why", "happened",
    "what", "really", "happened", "when", "overnight", "actually", "basic", "story",
    "detail", "details", "behind", "explore", "explores", "untold", "stories", "daily"
}

VISUAL_NOUNS_POOL = [
    "meteor", "asteroid", "fire", "forest", "smoke", "sky", "stars", "space", "earth",
    "ruins", "stone", "temple", "water", "river", "flood", "trees", "mountain", "ocean",
    "clouds", "storm", "sun", "ancient", "desert", "ice", "snow", "cave", "ship", "sea",
    "parchment", "writing", "astronomy", "universe", "planet", "galaxy", "laboratory"
]


def extract_visual_search_queries(raw_kw: str, narration: str, topic: str) -> list:
    """
    Extracts concrete, disambiguated, visual-only search queries from scene content
    to ensure stock libraries return highly relevant footage rather than celebratory/unrelated clips.
    """
    import re
    queries = []

    # 1. Clean raw keywords
    words = re.sub(r"[^a-zA-Z\s]", " ", (raw_kw or "").lower()).split()
    clean_kw = [w for w in words if w not in NOISE_WORDS and len(w) > 2]
    
    disambiguated = []
    for w in clean_kw:
        if w in DISAMBIGUATION_MAP:
            disambiguated.append(DISAMBIGUATION_MAP[w])
        else:
            disambiguated.append(w)
    
    if disambiguated:
        primary_q = " ".join(disambiguated[:3])
        if primary_q and primary_q not in queries:
            queries.append(primary_q)

    # 2. Extract visual nouns from scene narration
    narr_words = re.sub(r"[^a-zA-Z\s]", " ", (narration or "").lower()).split()
    matched_visuals = [w for w in narr_words if w in VISUAL_NOUNS_POOL]
    seen_vis = set()
    matched_visuals = [x for x in matched_visuals if not (x in seen_vis or seen_vis.add(x))]
    
    if matched_visuals:
        narr_q = " ".join(matched_visuals[:3])
        if narr_q and narr_q not in queries:
            queries.append(narr_q)

    # 3. Disambiguated topic keywords
    top_words = re.sub(r"[^a-zA-Z\s]", " ", (topic or "").lower()).split()
    clean_top = [w for w in top_words if w not in NOISE_WORDS and len(w) > 2]
    top_disambiguated = [DISAMBIGUATION_MAP.get(w, w) for w in clean_top]
    if top_disambiguated:
        top_q = " ".join(top_disambiguated[:3])
        if top_q and top_q not in queries:
            queries.append(top_q)

    for guaranteed in ("ancient megalith ruins stone", "ancient civilization history mystery", "ancient architecture aerial landscape"):
        if guaranteed not in queries:
            queries.append(guaranteed)

    return queries


# ---------------------------------------------------------------------------
# Per-scene pool fetcher — downloads MULTIPLE clips + images for each scene
# ---------------------------------------------------------------------------

def fetch_media_pool_for_scene(scene_index, keywords, scene_text, topic="", max_videos=1, max_images=1):
    """
    Returns a list of (filepath, media_type) tuples — a rich pool of media
    for this scene. Videos come first, then images.
    Tries primary and fallback disambiguated queries to guarantee high scene relevance.
    """
    pref = getattr(config, "MEDIA_PREFERENCE", "video_first")
    pool = []

    # Get ordered candidate queries
    search_queries = extract_visual_search_queries(keywords, scene_text, topic)

    # ── Fetch videos ──────────────────────────────────────────────────────
    if pref in ("video_first", "video_only"):
        seen_urls = set()
        for q in search_queries:
            if len(pool) >= max_videos:
                break
            video_urls = search_videos_pexels(q, per_page=max_videos + 2)
            if len(video_urls) < max_videos:
                video_urls += search_videos_pixabay(q, per_page=max_videos + 2)
            
            for url in video_urls:
                if url not in seen_urls and len(pool) < max_videos:
                    seen_urls.add(url)
                    path = download_video(url, scene_index, slot=len(pool))
                    if path:
                        pool.append((path, "video"))
                        break

    # ── Fetch images (always, unless video_only) ──────────────────────────
    if pref in ("video_first", "image_only"):
        seen_img = set()
        img_count = 0
        for q in search_queries:
            if img_count >= max_images:
                break
            img_urls = search_images_pexels(q, per_page=max_images + 2)
            if len(img_urls) < max_images:
                img_urls += search_images_pixabay(q, per_page=max_images + 2)
            
            for url in img_urls:
                if url not in seen_img and img_count < max_images:
                    seen_img.add(url)
                    path = download_image(url, scene_index, slot=20 + img_count)
                    if path:
                        pool.append((path, "image"))
                        img_count += 1
                        break

    if not pool:
        pool.append(generate_fallback_image(scene_index, scene_text))

    return pool


# ---------------------------------------------------------------------------
# Parallel all-scenes fetcher — returns list of pools, one per scene
# ---------------------------------------------------------------------------

def fetch_all_media(scenes, topic, log_cb=None, progress_cb=None, progress_start=12, progress_end=40):
    """
    Download a rich media pool for every scene in parallel.

    Returns: list of pools, where each pool is a list of (filepath, media_type)
             tuples. The video composer picks from the pool for fast cuts.
    """
    scene_count = len(scenes)
    results     = [None] * scene_count
    used_kw     = set()
    kw_lock     = threading.Lock()

    pex_ok = bool(config.PEXELS_API_KEY)
    pix_ok = bool(config.PIXABAY_API_KEY)
    key_msg = (
        f"[media] API Key Diagnostics: "
        f"Pexels={'PRESENT (' + config.PEXELS_API_KEY[:4] + '...)' if pex_ok else '❌ MISSING'}, "
        f"Pixabay={'PRESENT (' + config.PIXABAY_API_KEY[:4] + '...)' if pix_ok else '❌ MISSING'}"
    )
    print(key_msg)
    if log_cb:
        log_cb(key_msg)

    def _fetch_one(idx):
        scene = scenes[idx]
        kw    = scene.get("keywords", topic) or topic
        text  = scene.get("narration", "")

        with kw_lock:
            if kw in used_kw:
                kw = f"{kw} {topic}"
            used_kw.add(kw)

        pool = fetch_media_pool_for_scene(idx, kw, text, topic=topic)
        if log_cb:
            vids = sum(1 for p, mt in pool if mt == "video")
            imgs = sum(1 for p, mt in pool if mt == "image" and not p.endswith("_fallback.jpg"))
            fbs  = sum(1 for p, mt in pool if p.endswith("_fallback.jpg"))
            log_cb(f"[media] Scene {idx + 1}/{scene_count}: {vids} clips, {imgs} photos, {fbs} fallbacks ({kw[:30]})")
        return idx, pool

    max_workers = min(8, scene_count)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {executor.submit(_fetch_one, i): i for i in range(scene_count)}
        done_count = 0
        for future in as_completed(futures):
            try:
                idx, pool = future.result()
                results[idx] = pool
            except Exception as e:
                idx = futures[future]
                results[idx] = [generate_fallback_image(idx, scenes[idx].get("narration", ""))]
                if log_cb:
                    log_cb(f"[warn] Scene {idx + 1} media failed, using fallback: {e}")
            done_count += 1
            if progress_cb:
                pct = progress_start + int((progress_end - progress_start) * done_count / scene_count)
                progress_cb(pct)

    for i, r in enumerate(results):
        if r is None:
            results[i] = [generate_fallback_image(i, scenes[i].get("narration", ""))]

    # Summarise for log
    total_videos = sum(sum(1 for p, mt in pool if mt == "video") for pool in results)
    total_images = sum(sum(1 for p, mt in pool if mt == "image" and not p.endswith("_fallback.jpg")) for pool in results)
    total_fallbacks = sum(sum(1 for p, mt in pool if p.endswith("_fallback.jpg")) for pool in results)

    if log_cb:
        log_cb(f"[ok] Media pool ready — {total_videos} video clips, {total_images} photos, {total_fallbacks} fallbacks across {scene_count} scenes")

    # Safety guard: Never proceed to render or upload a blank video if 0 real media was fetched!
    if total_videos == 0 and total_images == 0:
        err = (
            f"CRITICAL: 0 stock videos and 0 stock photos were downloaded! "
            f"All {scene_count} scenes returned fallback text slides. "
            f"Pexels Key present: {pex_ok}, Pixabay Key present: {pix_ok}. "
            f"Please verify PEXELS_API_KEY and PIXABAY_API_KEY in your GitHub Secrets!"
        )
        if log_cb:
            log_cb(f"❌ {err}")
        raise RuntimeError(err)

    return results
