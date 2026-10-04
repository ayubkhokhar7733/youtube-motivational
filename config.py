import os
import json
from dotenv import load_dotenv

load_dotenv()

# ── Version ───────────────────────────────────────────────────────────────────
APP_VERSION = "1.6"   # bump this on every code change

USER_SETTINGS_PATH = os.path.join(os.path.dirname(__file__), "user_settings.json")


def load_user_settings():
    if os.path.exists(USER_SETTINGS_PATH):
        try:
            with open(USER_SETTINGS_PATH, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_user_settings(settings):
    with open(USER_SETTINGS_PATH, "w") as f:
        json.dump(settings, f, indent=2)


ASPECT_PRESETS = {
    "landscape": {"width": 1920, "height": 1080, "label": "Landscape 16:9"},
    "portrait":  {"width": 1080, "height": 1920, "label": "Portrait 9:16 (Shorts)"},
    "square":    {"width": 1080, "height": 1080, "label": "Square 1:1"},
}
DEFAULT_ASPECT = "landscape"
DEFAULT_DURATION = 60

VALID_VOICES = [
    "en-US-ChristopherNeural",
    "en-US-GuyNeural",
    "en-US-JennyNeural",
    "en-US-AriaNeural",
    "en-US-DavisNeural",
    "en-GB-SoniaNeural",
    "en-GB-RyanNeural",
    "en-AU-NatashaNeural",
    "en-AU-WilliamNeural",
    "en-CA-ClaraNeural",
]

# Motivational Channel Defaults
DEFAULT_CATEGORY = "motivational"
DEFAULT_VOICE = "en-US-GuyNeural"


VALID_MEDIA_PREFS = ("video_first", "image_only", "video_only")
VALID_SUBTITLE_COLORS = ("white", "yellow", "cyan")


def reload():
    u = load_user_settings()

    global GROQ_API_KEY, PIXABAY_API_KEY, PEXELS_API_KEY
    global VIDEO_WIDTH, VIDEO_HEIGHT, TOTAL_TARGET_DURATION
    global MEDIA_PREFERENCE, ENABLE_ZOOM
    global VOICE_NAME, BG_MUSIC_VOLUME, SUBTITLE_COLOR

    _groq = os.getenv("GROQ_API_KEY") or u.get("groq_api_key") or ""
    GROQ_API_KEY    = _groq.strip() if _groq else ""
    _pixabay = os.getenv("PIXABAY_API_KEY") or u.get("pixabay_api_key") or ""
    PIXABAY_API_KEY = _pixabay.strip() if _pixabay else ""
    _pexels = os.getenv("PEXELS_API_KEY") or u.get("pexels_api_key") or ""
    PEXELS_API_KEY  = _pexels.strip() if _pexels else ""

    aspect = u.get("aspect_ratio", DEFAULT_ASPECT)
    preset = ASPECT_PRESETS.get(aspect, ASPECT_PRESETS[DEFAULT_ASPECT])
    VIDEO_WIDTH  = preset["width"]
    VIDEO_HEIGHT = preset["height"]
    TOTAL_TARGET_DURATION = int(u.get("target_duration", DEFAULT_DURATION))

    # New settings
    mp = u.get("media_preference", "video_first")
    MEDIA_PREFERENCE = mp if mp in VALID_MEDIA_PREFS else "video_first"

    ENABLE_ZOOM = bool(u.get("enable_zoom", True))

    vn = u.get("voice_name", "en-US-JennyNeural")
    VOICE_NAME = vn if vn in VALID_VOICES else "en-US-JennyNeural"

    BG_MUSIC_VOLUME = max(0.0, min(0.5, float(u.get("bg_music_volume", 0.10))))

    sc = u.get("subtitle_color", "white")
    SUBTITLE_COLOR = sc if sc in VALID_SUBTITLE_COLORS else "white"


reload()

# ── Fixed constants ────────────────────────────────────────────────────────
FPS = 24

INTRO_DURATION  = 4
OUTRO_DURATION  = 5
SCENE_MIN_DURATION = 5
SCENE_MAX_DURATION = 12

OUTPUT_DIR  = os.path.join(os.path.dirname(__file__), "output")
TEMP_DIR    = os.path.join(os.path.dirname(__file__), "temp")
ASSETS_DIR  = os.path.join(os.path.dirname(__file__), "assets")
FONT_PATH   = os.path.join(ASSETS_DIR, "font.ttf")
INTRO_PATH  = os.path.join(ASSETS_DIR, "intro.mp4")
OUTRO_PATH  = os.path.join(ASSETS_DIR, "outro.mp4")
MUSIC_DIR   = os.path.join(ASSETS_DIR, "music")

os.makedirs(OUTPUT_DIR, exist_ok=True)
os.makedirs(TEMP_DIR, exist_ok=True)
