"""Daily trending searches from the public Google Trends RSS feed (free, no key)."""
import re
import urllib.request
import xml.etree.ElementTree as ET

from . import config

FEED_URL = "https://trends.google.com/trending/rss?geo={geo}"
NS = {"ht": "https://trends.google.com/trending/rss"}
UA = "Mozilla/5.0 (reel-maker; personal use)"


def fetch_feed(geo):
    req = urllib.request.Request(FEED_URL.format(geo=geo), headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=20) as resp:
        return resp.read()


def parse_feed(xml_bytes):
    root = ET.fromstring(xml_bytes)
    trends = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        if not title:
            continue
        news = []
        for n in item.findall("ht:news_item", NS):
            headline = (n.findtext("ht:news_item_title", default="", namespaces=NS) or "").strip()
            if headline:
                news.append({
                    "title": _clean(headline),
                    "source": (n.findtext("ht:news_item_source", default="", namespaces=NS) or "").strip(),
                    "url": (n.findtext("ht:news_item_url", default="", namespaces=NS) or "").strip(),
                })
        trends.append({
            "topic": title,
            "traffic": (item.findtext("ht:approx_traffic", default="", namespaces=NS) or "").strip(),
            "news": news,
        })
    return trends


def _clean(text):
    text = re.sub(r"<[^>]+>", "", text)
    return (text.replace("&#39;", "'").replace("&quot;", '"').replace("&amp;", "&")
            .replace("&nbsp;", " ").strip())


def is_allowed(trend):
    text = (trend["topic"] + " " + " ".join(n["title"] for n in trend["news"])).lower()
    words = set(re.findall(r"[a-z']+", text))
    return not any(b in words for b in config.BLOCKLIST)


def get_trends(geo=None, count=3, feed_file=None):
    """Return the top `count` safe trending topics. `feed_file` lets you test offline."""
    data = open(feed_file, "rb").read() if feed_file else fetch_feed(geo or config.GEO)
    trends = [t for t in parse_feed(data) if is_allowed(t)]
    trends.sort(key=lambda t: -int(re.sub(r"\D", "", t["traffic"]) or 0))  # biggest searches first
    return trends[:count]
