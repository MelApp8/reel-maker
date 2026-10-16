"""Royalty-free background video: Pexels first, then Pixabay, then a generated background."""
import hashlib
import json
import urllib.parse
import urllib.request

from . import config

UA = "Mozilla/5.0 (reel-maker; personal use)"


def _get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _download(url, dest):
    if dest.exists() and dest.stat().st_size > 0:
        return dest
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=120) as resp, open(dest, "wb") as f:
        while chunk := resp.read(1 << 16):
            f.write(chunk)
    return dest


def _pexels(query, n):
    if not config.PEXELS_API_KEY:
        return []
    q = urllib.parse.urlencode({"query": query, "orientation": "portrait", "size": "medium", "per_page": 15})
    data = _get_json(f"https://api.pexels.com/videos/search?{q}", {"Authorization": config.PEXELS_API_KEY})
    clips = []
    for v in data.get("videos", []):
        files = [f for f in v.get("video_files", [])
                 if f.get("height") and f.get("width") and f["height"] >= f["width"] and f["height"] >= 1280
                 and f.get("file_type") == "video/mp4"]
        if not files:
            continue
        best = min(files, key=lambda f: abs(f["height"] - 1920))
        clips.append({"url": best["link"], "duration": v.get("duration", 10),
                      "credit": f"{v.get('user', {}).get('name', 'Pexels')} on Pexels", "page": v.get("url", "")})
        if len(clips) >= n:
            break
    return clips


def _pixabay(query, n):
    if not config.PIXABAY_API_KEY:
        return []
    q = urllib.parse.urlencode({"key": config.PIXABAY_API_KEY, "q": query[:100], "per_page": 20, "safesearch": "true"})
    data = _get_json(f"https://pixabay.com/api/videos/?{q}")
    clips = []
    for hit in data.get("hits", []):
        sizes = hit.get("videos", {})
        best = sizes.get("large") or sizes.get("medium")
        if not best or not best.get("url"):
            continue
        clips.append({"url": best["url"], "duration": hit.get("duration", 10),
                      "credit": f"{hit.get('user', 'Pixabay')} on Pixabay", "page": hit.get("pageURL", "")})
        if len(clips) >= n:
            break
    return clips


def find_clips(queries, n=4):
    """Try each search query in order until we have `n` clips. Returns local files + credits."""
    config.CACHE_DIR.mkdir(exist_ok=True)
    found, seen = [], set()
    for query in queries:
        for source in (_pexels, _pixabay):
            try:
                results = source(query, n)
            except Exception as e:  # a bad key or network hiccup shouldn't stop the reel
                print(f"  ! {source.__name__[1:]} search failed for '{query}': {e}")
                results = []
            for clip in results:
                if clip["url"] in seen:
                    continue
                seen.add(clip["url"])
                name = hashlib.sha1(clip["url"].encode()).hexdigest()[:16] + ".mp4"
                try:
                    clip["path"] = str(_download(clip["url"], config.CACHE_DIR / name))
                except Exception as e:
                    print(f"  ! download failed: {e}")
                    continue
                found.append(clip)
                if len(found) >= n:
                    return found
    return found
