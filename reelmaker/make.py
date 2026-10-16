"""The daily job: trends -> script -> stock clips -> rendered reel + post text."""
import datetime as dt
import json
import re

from . import config, media, render, script, trends


def slugify(text):
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:50] or "reel"


def write_post_text(s, path):
    lines = [
        "TITLE", s["title"], "",
        "CAPTION (paste into Instagram / TikTok / YouTube description)", s["caption_full"], "",
        "HASHTAGS", " ".join(s["hashtags"]), "",
        "TAGS (YouTube tags box, comma separated)", ", ".join(s["tags"]), "",
    ]
    if s.get("credits"):
        lines += ["VIDEO CREDITS"] + [f"- {c}" for c in s["credits"]] + [""]
    if s.get("sources"):
        lines += ["NEWS SOURCES (for your own fact check)"] + [f"- {n['title']} ({n['source']}) {n['url']}" for n in s["sources"]]
    path.write_text("\n".join(lines), encoding="utf-8")


def make_reel(trend, rank, day_dir, custom=False):
    print(f"[{rank}] {trend['topic']} ({trend.get('traffic') or 'n/a'} searches)")
    s = script.write_script(trend)
    clips = media.find_clips(s["video_queries"], n=min(4, len(s["slides"])))
    if not clips:
        print("  - no stock clips (add PEXELS_API_KEY to .env); using an animated background")
    prefix = "my" if custom else f"{rank:02d}"
    out_dir = day_dir / f"{prefix}-{slugify(trend['topic'])}"
    out_dir.mkdir(parents=True, exist_ok=True)
    reel, cover = render.render(s, clips, out_dir, rank=0 if custom else rank)
    s["credits"] = [f"{c['credit']} {c['page']}".strip() for c in clips]
    s.update({"rank": rank, "custom": custom, "date": day_dir.name, "video": reel.name, "cover": cover.name,
              "created_at": dt.datetime.now().isoformat(timespec="seconds")})
    (out_dir / "meta.json").write_text(json.dumps(s, indent=2, ensure_ascii=False), encoding="utf-8")
    write_post_text(s, out_dir / "post.txt")
    print(f"  -> {reel}")
    return out_dir


def make_daily(count=None, geo=None, feed_file=None, topics=None):
    count = count or config.REELS_PER_DAY
    if topics:
        items = [{"topic": t, "traffic": "", "news": []} for t in topics]
    else:
        items = trends.get_trends(geo=geo, count=count, feed_file=feed_file)
    if not items:
        raise SystemExit("No usable trending topics found right now.")
    day_dir = config.OUTPUT_DIR / dt.date.today().isoformat()
    made = []
    for rank, trend in enumerate(items[:count], start=1):
        try:
            made.append(make_reel(trend, rank, day_dir, custom=bool(topics)))
        except Exception as e:
            print(f"  ! failed: {e}")
    return made
