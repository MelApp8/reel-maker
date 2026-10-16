"""
python -m reelmaker make            make today's reels from Google Trends
python -m reelmaker make --topic "World Series"   make a reel about any topic you choose
python -m reelmaker site            build the phone website (used by the daily GitHub run)
python -m reelmaker serve           open the app in your browser (download, share, auto-make daily)
"""
import argparse

from . import config


def main():
    p = argparse.ArgumentParser(prog="reelmaker")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make", help="make today's reels")
    m.add_argument("--count", type=int, default=config.REELS_PER_DAY)
    m.add_argument("--geo", default=config.GEO, help="country code, e.g. US, IN, GB")
    m.add_argument("--topic", action="append", help="use your own topic instead of trends (repeatable)")
    m.add_argument("--feed-file", help="read a saved Google Trends RSS file instead of fetching (for testing)")
    w = sub.add_parser("site", help="build the phone-friendly website of your reels")
    w.add_argument("--out", default="site")
    w.add_argument("--keep-days", type=int, default=7)
    s = sub.add_parser("serve", help="run the web app")
    s.add_argument("--port", type=int, default=8765)
    s.add_argument("--lan", action="store_true", help="let your phone on the same Wi-Fi open it")
    a = p.parse_args()

    if a.cmd == "make":
        from .make import make_daily
        made = make_daily(count=a.count, geo=a.geo, feed_file=a.feed_file, topics=a.topic)
        print(f"\nDone: {len(made)} reel(s) in {config.OUTPUT_DIR}")
    elif a.cmd == "site":
        from .site import build
        build(a.out, a.keep_days)
    else:
        from .server import serve
        serve(port=a.port, lan=a.lan)


if __name__ == "__main__":
    main()
