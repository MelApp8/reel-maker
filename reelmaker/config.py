"""Settings, read from a .env file next to the app (or real environment variables)."""
import os
from pathlib import Path

APP_DIR = Path(__file__).resolve().parent.parent
OUTPUT_DIR = APP_DIR / "output"
FONTS_DIR = APP_DIR / "fonts"
MUSIC_DIR = APP_DIR / "music"
CACHE_DIR = APP_DIR / ".cache"


def _load_dotenv():
    env_file = APP_DIR / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv()


def get(name, default=""):
    return os.environ.get(name, default)


ANTHROPIC_API_KEY = get("ANTHROPIC_API_KEY")
GEO = get("TRENDS_GEO", "US")            # country code for Google Trends: US, IN, GB, CA, AU...
REELS_PER_DAY = int(get("REELS_PER_DAY", "3"))
DAILY_TIME = get("DAILY_TIME", "08:00")   # local time the web app makes the day's reels; empty = off
HANDLE = get("HANDLE", "")                # your @handle, shown as a small watermark
REEL_SECONDS = float(get("REEL_SECONDS", "20"))
# Topics containing these words are skipped (tragedies don't make good monetized reels).
BLOCKLIST = [w.strip().lower() for w in get(
    "BLOCKLIST",
    "died,dies,death,dead,killed,shooting,shot,murder,crash,obituary,funeral,suicide,"
    "attack,victim,missing,arrested,war,earthquake,abuse",
).split(",") if w.strip()]

W, H, FPS = 1080, 1920, 30
