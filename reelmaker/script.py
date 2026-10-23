"""Turns a trending topic into on-screen captions, a title, a post caption, hashtags and tags."""
import json
import re

from . import config

GENERIC_HASHTAGS = ["#news", "#latestnews", "#todaynews", "#reels", "#explore", "#fyp", "#viral"]


def _hashtag(text):
    words = re.findall(r"[A-Za-z0-9]+", text)
    return "#" + "".join(w[:1].upper() + w[1:] for w in words) if words else ""


def _shorten(text, limit=95):
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut.rstrip(",;:-") + "..."


def display_name(trend, ctx):
    wiki = (ctx or {}).get("wiki")
    if wiki:
        return re.sub(r"\s*\(.*?\)$", "", wiki["title"])
    t = trend["topic"]
    return t if any(c.isupper() for c in t) else t.title()


def _first_sentences(text, limit=150):
    sents = re.split(r"(?<!\bNo)(?<!\bMr)(?<!\bMs)(?<!\bDr)(?<!\bSt)(?<!\bJr)(?<!\bvs)(?<!\bU\.S)(?<=[.!?])\s+", re.sub(r"\s*\([^)]*\)", "", text or "").strip())
    out = ""
    for sent in sents:
        if out and len(out) + len(sent) > limit:
            break
        out = (out + " " + sent).strip()
    if len(out) <= limit:
        return out
    clause = out[:limit].rsplit(",", 1)[0]
    return clause if len(clause) > limit * 0.5 else _shorten(out, limit)


def _finish(script, trend, ctx, name):
    """Fill fields shared by every script writer and keep hashtags/tags tidy."""
    tags = list(dict.fromkeys([t.strip() for t in script.get("tags", []) if t.strip()]))
    hashtags = [h if h.startswith("#") else "#" + h for h in script.get("hashtags", [])]
    hashtags = [h for h in hashtags if re.fullmatch(r"#\w+", h)]
    hashtags = list(dict.fromkeys([_hashtag(name)] + hashtags + GENERIC_HASHTAGS))[:15]
    caption = script["caption"].strip()
    if config.HANDLE and config.HANDLE not in caption:
        caption += f"\n\nFollow {config.HANDLE} for more."
    for sl in script["slides"]:
        sl["kicker"] = _shorten(sl.get("kicker", "").upper(), 30)
        sl["text"] = _shorten(sl["text"], 170)
    script.update({
        "topic": name,
        "traffic": trend.get("traffic", ""),
        "hashtags": hashtags,
        "tags": tags[:15],
        "caption_full": caption + "\n\n" + " ".join(hashtags),
        "sources": [{"title": n["title"], "source": n["source"], "url": n["url"]} for n in trend["news"][:3]],
    })
    if ctx and ctx.get("wiki"):
        script["sources"].append({"title": ctx["wiki"]["title"], "source": "Wikipedia", "url": ctx["wiki"]["url"]})
    return script


def template_script(trend, ctx=None, name=None):
    """No AI available: builds the story from Wikipedia and the news pages themselves."""
    name = name or display_name(trend, ctx)
    traffic, news = trend.get("traffic", ""), trend["news"]
    articles = (ctx or {}).get("articles") or [{**n, "summary": ""} for n in news]
    wiki = (ctx or {}).get("wiki")
    slides = []
    if articles:  # lead with the news itself
        a = articles[0]
        slides.append({"kicker": "WHAT'S HAPPENING", "text": _shorten(a["title"], 115)})
    if wiki:
        slides.append({"kicker": f"WHO IS {name.upper()}" if len(name) < 22 else "THE BACKGROUND",
                       "text": _first_sentences(wiki["extract"], 160)})
    if articles:
        a = articles[0]
        if a.get("summary") and a["summary"][:40].lower() not in a["title"].lower():
            slides.append({"kicker": "THE DETAILS", "text": _first_sentences(a["summary"], 160)})
    if len(articles) > 1 and len(slides) < 4:
        slides.append({"kicker": "ALSO", "text": _shorten(articles[1]["title"], 115)})
    if not slides:
        slides.append({"kicker": "IN THE NEWS", "text": name})
    slides.append({"kicker": "YOUR TAKE?", "text": "What do you think? Comment below and follow for more"})
    lead = articles[0]["title"] if articles else name
    summary = articles[0].get("summary", "") if articles else ""
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name) if len(w) > 2]
    return _finish({
        "title": _shorten(lead if name.lower() in lead.lower() else f"{name}: {lead}", 95),
        "slides": slides,
        "caption": f"{_shorten(lead, 200)}\n\n" + (f"{_first_sentences(summary, 220)}\n\n" if summary else "")
                   + "What do you think? Tell me in the comments \U0001F447",
        "hashtags": [_hashtag(w) for w in words] + ["#breakingnews"],
        "tags": [name, f"{name} news", f"{name} today", f"{name} explained", f"{name} latest",
                 "latest news", "news today", "shorts", "reels"] + words,
    }, trend, ctx, name)


SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Video title, under 80 characters, curiosity-driven but true"},
        "slides": {"type": "array", "description": "Exactly 5 on-screen captions, in order",
                   "items": {"type": "object",
                             "properties": {"kicker": {"type": "string", "description": "2-4 word label, uppercase"},
                                            "text": {"type": "string", "description": "One plain sentence, under 100 characters"}},
                             "required": ["kicker", "text"], "additionalProperties": False}},
        "caption": {"type": "string", "description": "Instagram/TikTok caption: 3-4 short lines with a few emojis, ending in a question"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "8-12 relevant hashtags"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "10-15 YouTube search tags"},
    },
    "required": ["title", "slides", "caption", "hashtags", "tags"],
    "additionalProperties": False,
}


def _prompt(trend, ctx, name):
    wiki = (ctx or {}).get("wiki")
    arts = (ctx or {}).get("articles") or trend["news"]
    news = "\n".join(f"- {a['title']} ({a['source']})" + (f"\n  Summary: {a['summary']}" if a.get("summary") else "")
                     for a in arts) or "- (none)"
    return (
        "Write a short vertical reel (about 20 seconds, 5 caption slides) telling people what is happening "
        "in this news story, for viewers who have not heard about it yet.\n\n"
        f"Topic: {name}\n"
        f"Background (Wikipedia): {wiki['extract'] if wiki else '(no article found)'}\n"
        f"Today's news:\n{news}\n\n"
        "Slides: 1) what is happening, told as a hook that makes people stop scrolling, 2) who or what this is, "
        "3) the key details, 4) the most interesting detail or why it matters, 5) ask viewers what they think. "
        "Never mention that it is trending, search numbers or rankings. "
        "Use only facts from the background and news above, never invent numbers, quotes or outcomes. "
        "Write like a friendly news creator: short, clear sentences, no hype words like 'shocking'."
    )


def _parse_json(text):
    text = text.strip()
    m = re.search(r"\{.*\}", text, re.S)  # tolerate ```json fences or chatter around the object
    return json.loads(m.group(0) if m else text)


def _claude_json(prompt, schema):
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined this topic")
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def ai_json(prompt, schema):
    """Ask whichever AI is available. Returns (result, label) or (None, None)."""
    writers = []
    if config.ANTHROPIC_API_KEY:
        writers.append(("Claude", _claude_json))
    for label, writer in writers:
        try:
            return writer(prompt, schema), label
        except Exception as e:
            print(f"  ! {label} failed ({e})")
    return None, None


IMAGE_SCHEMA = {
    "type": "object",
    "properties": {"articles": {"type": "array", "items": {"type": "string"},
                                "description": "2-3 exact English Wikipedia article titles whose photos fit this story"}},
    "required": ["articles"], "additionalProperties": False,
}


def photo_articles(trend):
    """For news-style trends with no article of their own, ask AI which Wikipedia articles would picture it."""
    news = "\n".join(f"- {n['title']}" for n in trend["news"][:3])
    result, _ = ai_json(
        f"Trending search: {trend['topic']}\nHeadlines:\n{news}\n\nName 2-3 existing English Wikipedia articles "
        "(exact titles) about the main people, organisations or places in this story, most relevant first. "
        "Their lead photos will illustrate a short news reel.", IMAGE_SCHEMA)
    return (result or {}).get("articles", [])[:3]


def write_script(trend, ctx=None):
    name = display_name(trend, ctx)
    script, label = ai_json(_prompt(trend, ctx, name), SCHEMA)
    if script and len(script.get("slides", [])) >= 3:
        script["slides"] = script["slides"][:6]
        script["writer"] = label
        print(f"  - script written by {label}")
        return _finish(script, trend, ctx, name)
    print("  - script built from Wikipedia and news (no AI)")
    return template_script(trend, ctx, name)
