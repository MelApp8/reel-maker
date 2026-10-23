"""Free, no-key sources: Wikipedia/Wikimedia Commons and Openverse for photos, news pages for context."""
import hashlib
import html
import json
import re
import urllib.parse
import urllib.request

from . import config

UA = "ReelMaker/1.0 (personal reel generator; https://github.com/MelApp8/reel-maker)"
BROWSER_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
WIKI_API = "https://en.wikipedia.org/w/api.php"
SKIP_FILES = re.compile(r"(logo|icon|flag|map|seal|coat_of_arms|signature|symbol|wordmark|locator|diagram|chart|"
                        r"commons-|wiki|edit-clear|question_book|ambox|crystal|nuvola|padlock|disambig)", re.I)


def _get(url, ua=UA, timeout=20):
    req = urllib.request.Request(url, headers={"User-Agent": ua, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return resp.read()


def _get_json(url):
    return json.loads(_get(url).decode("utf-8"))


def _strip_html(text):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", "", text or ""))).strip()


def _words(text):
    return {w for w in re.findall(r"[a-z0-9]+", text.lower()) if len(w) > 2}


# ---------- Wikipedia ----------

def wikipedia(topic):
    """Best-matching article: {'title', 'extract', 'url', 'files': [File:..]} or None."""
    q = urllib.parse.urlencode({"action": "query", "format": "json", "list": "search", "srsearch": topic, "srlimit": 5})
    results = _get_json(f"{WIKI_API}?{q}").get("query", {}).get("search", [])
    want = _words(topic)
    for r in results:
        # The article title must contain most of the topic's words, so "jaylin williams" doesn't match "Williams College"
        have = _words(r["title"])
        if not want or len(want & have) < max(1, round(len(want) * 0.6)):
            continue
        q = urllib.parse.urlencode({
            "action": "query", "format": "json", "redirects": 1, "titles": r["title"],
            "prop": "extracts|pageimages|images|info", "exintro": 1, "explaintext": 1, "exchars": 700,
            "piprop": "name", "imlimit": 40, "inprop": "url"})
        page = next(iter(_get_json(f"{WIKI_API}?{q}").get("query", {}).get("pages", {}).values()), {})
        extract = (page.get("extract") or "").strip()
        if not extract or "may refer to" in extract[:200]:
            continue
        files = []
        if page.get("pageimage"):
            files.append("File:" + page["pageimage"])
        files += [i["title"] for i in page.get("images", []) if i["title"] not in files]
        return {"title": page.get("title", r["title"]), "extract": extract, "url": page.get("fullurl", ""), "files": files}
    return None


def commons_images(files, limit=5):
    files = [f for f in files if re.search(r"\.(jpe?g|png|webp)$", f, re.I) and not SKIP_FILES.search(f)][:20]
    if not files:
        return []
    q = urllib.parse.urlencode({"action": "query", "format": "json", "titles": "|".join(files),
                                "prop": "imageinfo", "iiprop": "url|size|mime|extmetadata", "iiurlwidth": 1400})
    pages = _get_json(f"{WIKI_API}?{q}").get("query", {}).get("pages", {})
    by_title = {p.get("title"): p for p in pages.values()}
    out = []
    for f in files:  # keep the article's order: lead image first
        info = (by_title.get(f) or {}).get("imageinfo", [{}])[0]
        if not info or info.get("width", 0) < 500 or info.get("height", 0) < 400:
            continue
        meta = info.get("extmetadata", {})
        lic = _strip_html(meta.get("LicenseShortName", {}).get("value", ""))
        if not lic or "fair use" in lic.lower() or "non-free" in lic.lower():
            continue
        artist = _strip_html(meta.get("Artist", {}).get("value", ""))[:60] or "Wikimedia Commons"
        out.append({"url": info.get("thumburl") or info["url"], "credit": f"{artist} / {lic}",
                    "page": info.get("descriptionurl", ""), "source": "Wikimedia Commons"})
        if len(out) >= limit:
            break
    return out


# ---------- Openverse (CC-licensed photos, commercial use allowed) ----------

def openverse_images(query, limit=4):
    if not _words(query):  # too short to check photos against (e.g. "jd"), so don't risk unrelated pictures
        return []
    q = urllib.parse.urlencode({"q": query, "license_type": "commercial", "page_size": 20, "mature": "false"})
    data = json.loads(_get(f"https://api.openverse.org/v1/images/?{q}", timeout=40).decode("utf-8"))
    want = _words(query)
    out = []
    for r in data.get("results", []):
        if (r.get("width") or 0) < 700 or (r.get("height") or 0) < 500:
            continue
        # Only photos actually labelled with the topic, so we never show the wrong person or place
        about = _words((r.get("title") or "") + " " + " ".join(t.get("name", "") for t in r.get("tags") or []))
        if not want <= about:
            continue
        lic = f"CC {r.get('license', '').upper()} {r.get('license_version', '')}".strip()
        if r.get("license") in ("cc0", "pdm"):
            lic = "Public domain"
        creator = (r.get("creator") or "Unknown")[:60]
        out.append({"url": r["url"], "credit": f"{creator} / {lic}", "page": r.get("foreign_landing_url", ""),
                    "source": r.get("source", "Openverse")})
        if len(out) >= limit:
            break
    return out


# ---------- News context ----------

def article_summary(url):
    """The page's own short description (og:description), used as factual context."""
    try:
        page = _get(url, ua=BROWSER_UA, timeout=12)[:400_000].decode("utf-8", "ignore")
    except Exception:
        return ""
    for pat in (r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)',
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:description',
                r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)'):
        m = re.search(pat, page, re.I)
        if m:
            text = _strip_html(m.group(1))
            if len(text) > 40:
                return text[:400]
    return ""


def images_for_articles(titles):
    """Lead photos from specific Wikipedia articles (used for news-style trends)."""
    out = []
    for t in titles:
        try:
            wiki = wikipedia(t)
            if wiki:
                out += commons_images(wiki["files"], limit=2)
        except Exception as e:
            print(f"  ! Wikipedia lookup for '{t}' failed: {e}")
        if len(out) >= 4:
            break
    return out


def gather(trend):
    """Everything we know about a trend: wiki summary, news descriptions and 3-5 photos."""
    ctx = {"wiki": None, "articles": [], "images": []}
    try:
        ctx["wiki"] = wikipedia(trend["topic"])
    except Exception as e:
        print(f"  ! Wikipedia lookup failed: {e}")
    for n in trend["news"][:3]:
        desc = article_summary(n["url"]) if n.get("url") else ""
        ctx["articles"].append({**n, "summary": desc})
    if ctx["wiki"]:
        try:
            ctx["images"] = commons_images(ctx["wiki"]["files"])
        except Exception as e:
            print(f"  ! Commons lookup failed: {e}")
    if len(ctx["images"]) < 3:
        try:
            ctx["images"] += openverse_images(trend["topic"], limit=4 - len(ctx["images"]))
        except Exception as e:
            print(f"  ! Openverse lookup failed: {e}")
    return ctx


def download_images(images):
    config.CACHE_DIR.mkdir(exist_ok=True)
    ok = []
    for img in images:
        dest = config.CACHE_DIR / (hashlib.sha1(img["url"].encode()).hexdigest()[:16] + ".img")
        try:
            if not dest.exists():
                dest.write_bytes(_get(img["url"], timeout=40))
            ok.append({**img, "path": str(dest)})
        except Exception as e:
            print(f"  ! image download failed: {e}")
    return ok
