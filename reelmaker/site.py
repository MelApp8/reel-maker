"""Builds a static, phone-friendly website of your reels (published daily with GitHub Pages)."""
import datetime as dt
import json
import os
import shutil
from pathlib import Path

from PIL import Image, ImageDraw

from . import config
from .server import list_reels

PAGE = Path(__file__).with_name("index.html")

MANIFEST = {
    "name": "Reel Maker", "short_name": "Reels", "start_url": "./", "scope": "./", "display": "standalone",
    "background_color": "#0f1115", "theme_color": "#0f1115",
    "icons": [{"src": "icon-192.png", "sizes": "192x192", "type": "image/png"},
              {"src": "icon-512.png", "sizes": "512x512", "type": "image/png", "purpose": "any maskable"}],
}


def make_icon(size, path):
    img = Image.new("RGB", (size, size), (15, 17, 21))
    d = ImageDraw.Draw(img)
    pad = size * 0.2
    d.rounded_rectangle((pad, pad * 0.8, size - pad, size - pad * 0.8), radius=size * 0.08, fill=(255, 212, 0))
    tri = [(size * 0.42, size * 0.36), (size * 0.42, size * 0.64), (size * 0.64, size * 0.5)]
    d.polygon(tri, fill=(15, 17, 21))
    img.save(path)


def write_app_files(dest):
    dest = Path(dest)
    dest.mkdir(parents=True, exist_ok=True)
    (dest / "manifest.webmanifest").write_text(json.dumps(MANIFEST, indent=2), encoding="utf-8")
    for size in (192, 512):
        if not (dest / f"icon-{size}.png").exists():
            make_icon(size, dest / f"icon-{size}.png")


def prune(keep_days):
    cutoff = (dt.date.today() - dt.timedelta(days=keep_days - 1)).isoformat()
    for day in config.OUTPUT_DIR.glob("*"):
        if day.is_dir() and day.name < cutoff:
            shutil.rmtree(day, ignore_errors=True)


def build(dest="site", keep_days=7):
    dest = Path(dest)
    config.OUTPUT_DIR.mkdir(exist_ok=True)
    prune(keep_days)
    shutil.rmtree(dest, ignore_errors=True)
    write_app_files(dest)
    reels = []
    for r in list_reels():
        src = config.OUTPUT_DIR / r["id"]
        out = dest / "reels" / r["id"]
        out.mkdir(parents=True, exist_ok=True)
        for name in (r.get("video", "reel.mp4"), r.get("cover", "cover.jpg"), "post.txt"):
            if (src / name).exists():
                shutil.copy2(src / name, out / name)
        for key, name in (("video_url", r.get("video", "reel.mp4")), ("cover_url", r.get("cover", "cover.jpg")),
                          ("post_url", "post.txt")):
            r[key] = f"reels/{r['id']}/{name}"
        reels.append(r)
    (dest / "data").mkdir(exist_ok=True)
    (dest / "data" / "reels.json").write_text(json.dumps({"reels": reels}, ensure_ascii=False), encoding="utf-8")

    repo = os.environ.get("GITHUB_REPOSITORY", "")
    info = {"updated": dt.datetime.now(dt.timezone.utc).strftime("%d %b %Y, %H:%M UTC"),
            "run_url": f"https://github.com/{repo}/actions/workflows/daily-reels.yml" if repo else ""}
    html = PAGE.read_text(encoding="utf-8").replace(
        "<script>\nconst $", f"<script>window.REEL_STATIC = {json.dumps(info)};</script>\n<script>\nconst $", 1)
    (dest / "index.html").write_text(html, encoding="utf-8")
    (dest / ".nojekyll").write_text("")
    print(f"Site with {len(reels)} reel(s) written to {dest}/")
    return dest
