"""Turns a trending topic into on-screen captions, a title, a post caption, hashtags and tags."""
import json
import re
import urllib.request

from . import config

GENERIC_HASHTAGS = ["#trending", "#trendingnow", "#viral", "#reels", "#explore", "#fyp", "#news", "#todaynews"]


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
    sents = re.split(r"(?<=[.!?])\s+", re.sub(r"\s*\([^)]*\)", "", text or "").strip())
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
        caption += f"\n\nFollow {config.HANDLE} for a new trend every day."
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
    slides = [{"kicker": "QUICK EXPLAINER", "text": f"Why is everyone searching {name} right now?"}]
    if wiki:
        slides.append({"kicker": "WHO / WHAT", "text": _first_sentences(wiki["extract"], 160)})
    if articles:
        a = articles[0]
        slides.append({"kicker": "WHAT HAPPENED", "text": _shorten(a["title"], 115)})
        if a.get("summary") and a["summary"][:40].lower() not in a["title"].lower():
            slides.append({"kicker": "THE DETAILS", "text": _first_sentences(a["summary"], 160)})
    if len(articles) > 1 and len(slides) < 5:
        slides.append({"kicker": "ALSO", "text": _shorten(articles[1]["title"], 115)})
    slides.append({"kicker": "YOUR TAKE?", "text": "Comment below and follow for a new trend every day"})
    lead = articles[0]["title"] if articles else f"{name} is one of today's top searches."
    words = [w for w in re.findall(r"[A-Za-z0-9]+", name) if len(w) > 2]
    return _finish({
        "title": _shorten(f"Why is everyone searching {name} today?", 90),
        "slides": slides,
        "caption": f"{name} is trending right now \U0001F525\n\n{_shorten(lead, 200)}\n\n"
                   f"What do you think? Tell me in the comments \U0001F447",
        "hashtags": [_hashtag(w) for w in words] + ["#breakingnews"],
        "tags": [name, f"{name} news", f"{name} today", f"{name} explained", f"why is {name} trending",
                 "trending now", "trending news", "news today", "shorts", "reels"] + words,
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
        "Write a short vertical reel (about 20 seconds, 5 caption slides) explaining a trending Google search "
        "to people who have no idea what it is.\n\n"
        f"Search term: {name}\nSearches today: {trend.get('traffic') or 'unknown'}\n"
        f"Background (Wikipedia): {wiki['extract'] if wiki else '(no article found)'}\n"
        f"Today's news:\n{news}\n\n"
        "Slides: 1) a hook that makes people stop scrolling, 2) who or what this is, 3) what happened today, "
        "4) the most interesting detail or why it matters, 5) ask viewers what they think and to follow for daily trends. "
        "Use only facts from the background and news above, never invent numbers, quotes or outcomes. "
        "Write like a friendly news creator: short, clear sentences, no hype words like 'shocking'."
    )


def claude_script(trend, ctx, name):
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": _prompt(trend, ctx, name)}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined this topic")
    return json.loads(next(b.text for b in response.content if b.type == "text"))


def github_models_script(trend, ctx, name):
    """Free AI writing inside GitHub Actions (uses the workflow's own token, no signup)."""
    body = {
        "model": config.get("GITHUB_MODEL", "openai/gpt-4.1-mini"),
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": "Reply with JSON only, matching this JSON schema: " + json.dumps(SCHEMA)},
            {"role": "user", "content": _prompt(trend, ctx, name)},
        ],
    }
    req = urllib.request.Request(
        "https://models.github.ai/inference/chat/completions", data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {config.get('GITHUB_TOKEN')}", "Content-Type": "application/json",
                 "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode())
    return json.loads(data["choices"][0]["message"]["content"])


def write_script(trend, ctx=None):
    name = display_name(trend, ctx)
    writers = []
    if config.ANTHROPIC_API_KEY:
        writers.append(("Claude", claude_script))
    if config.get("GITHUB_TOKEN"):
        writers.append(("GitHub Models", github_models_script))
    for label, writer in writers:
        try:
            script = writer(trend, ctx, name)
            if len(script.get("slides", [])) >= 3:
                script["slides"] = script["slides"][:6]
                script["writer"] = label
                print(f"  - script written by {label}")
                return _finish(script, trend, ctx, name)
        except Exception as e:
            print(f"  ! {label} script failed ({e})")
    print("  - script built from Wikipedia and news (no AI)")
    return template_script(trend, ctx, name)
