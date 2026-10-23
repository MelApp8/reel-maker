"""The daily job: trends -> photos and context -> script -> rendered reel + post text."""
import datetime as dt
import json
import re
import shutil

from . import config, render, script, sources, trends


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
    ctx = sources.gather(trend)
    photos = sources.download_images(ctx["images"])
    if not photos:
        print("  - skipped: no free-to-use photos found for this topic")
        return None
    print(f"  - {len(photos)} photo(s); Wikipedia: {ctx['wiki']['title'] if ctx['wiki'] else 'none'}")
    s = script.write_script(trend, ctx)
    prefix = "my" if custom else f"{rank:02d}"
    out_dir = day_dir / f"{prefix}-{slugify(s['topic'])}"
    out_dir.mkdir(parents=True, exist_ok=True)
    reel, cover = render.render(s, photos, out_dir, rank=0 if custom else rank)
    s["credits"] = [f"{p['credit']} ({p['source']}) {p['page']}".strip() for p in photos]
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
        items = trends.get_trends(geo=geo, count=count * 4, feed_file=feed_file)
    if not items:
        raise SystemExit("No usable trending topics found right now.")
    day_dir = config.OUTPUT_DIR / dt.date.today().isoformat()
    if not topics:  # a fresh trends run replaces today's earlier trend reels
        for old in day_dir.glob("[0-9][0-9]-*"):
            shutil.rmtree(old, ignore_errors=True)
    made = []
    for trend in items:
        if len(made) >= count:
            break
        try:
            out = make_reel(trend, len(made) + 1, day_dir, custom=bool(topics))
            if out:
                made.append(out)
        except Exception as e:
            print(f"  ! failed: {e}")
    return made
