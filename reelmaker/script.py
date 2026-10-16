"""Turns a trending topic into on-screen captions, a title, a post caption, hashtags and tags."""
import json
import re

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


def _finish(script, trend):
    """Fill fields shared by both script writers and keep hashtags/tags tidy."""
    topic = trend["topic"]
    tags = list(dict.fromkeys([t.strip() for t in script.get("tags", []) if t.strip()]))
    hashtags = [h if h.startswith("#") else "#" + h for h in script.get("hashtags", [])]
    hashtags = [h for h in hashtags if re.fullmatch(r"#\w+", h)]
    hashtags = list(dict.fromkeys([_hashtag(topic)] + hashtags + GENERIC_HASHTAGS))[:15]
    caption = script["caption"].strip()
    if config.HANDLE and config.HANDLE not in caption:
        caption += f"\n\nFollow {config.HANDLE} for a new trend every day."
    script.update({
        "topic": topic,
        "traffic": trend.get("traffic", ""),
        "hashtags": hashtags,
        "tags": tags[:15],
        "caption_full": caption + "\n\n" + " ".join(hashtags),
        "sources": [{"title": n["title"], "source": n["source"], "url": n["url"]} for n in trend["news"][:3]],
    })
    return script


def template_script(trend):
    """Works with no AI key: builds the reel from the trend's own news headlines."""
    topic, traffic, news = trend["topic"], trend.get("traffic", ""), trend["news"]
    slides = [{"kicker": "EVERYONE IS SEARCHING" if traffic else "LET'S TALK ABOUT", "text": topic}]
    if traffic:
        slides.append({"kicker": "TRENDING TODAY", "text": f"{traffic} searches and climbing"})
    for n in news[:3]:
        slides.append({"kicker": (n["source"] or "IN THE NEWS").upper()[:28], "text": _shorten(n["title"])})
    if len(slides) < 3:
        slides.append({"kicker": "RIGHT NOW", "text": f"Everyone is talking about {topic}"})
    slides.append({"kicker": "YOUR TAKE?", "text": "Comment below and follow for daily trends"})
    lead = news[0]["title"] if news else f"{topic} is blowing up on search today."
    words = [w for w in re.findall(r"[A-Za-z0-9]+", topic) if len(w) > 2]
    return _finish({
        "title": _shorten(f"{topic}: why everyone is searching it today" if traffic else f"{topic}: what you need to know", 90),
        "slides": slides,
        "caption": f"{topic} is trending right now \U0001F525\n\n{_shorten(lead, 200)}\n\n"
                   f"What do you think? Tell me in the comments \U0001F447",
        "hashtags": [_hashtag(w) for w in words] + ["#breakingnews"],
        "tags": [topic, f"{topic} news", f"{topic} today", f"{topic} explained", f"what happened {topic}",
                 "trending now", "trending news", "viral news", "news today", "shorts", "reels"] + words,
        "video_queries": [topic] + words + ["news", "city night", "people phone"],
    }, trend)


SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "description": "Video title, under 90 characters, curiosity-driven, no clickbait lies"},
        "slides": {"type": "array", "description": "4 to 6 on-screen captions, in order",
                   "items": {"type": "object",
                             "properties": {"kicker": {"type": "string", "description": "2-4 word label, uppercase"},
                                            "text": {"type": "string", "description": "Under 90 characters"}},
                             "required": ["kicker", "text"], "additionalProperties": False}},
        "caption": {"type": "string", "description": "Instagram/TikTok post caption, 2-4 short lines with emojis, ending in a question"},
        "hashtags": {"type": "array", "items": {"type": "string"}, "description": "8-12 relevant hashtags"},
        "tags": {"type": "array", "items": {"type": "string"}, "description": "10-15 YouTube search tags"},
        "video_queries": {"type": "array", "items": {"type": "string"},
                          "description": "4 short stock-footage search terms that visually fit (no names of people)"},
    },
    "required": ["title", "slides", "caption", "hashtags", "tags", "video_queries"],
    "additionalProperties": False,
}


def claude_script(trend):
    import anthropic

    client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    headlines = "\n".join(f"- {n['title']} ({n['source']})" for n in trend["news"]) or "- (no headlines given)"
    prompt = (
        f"Write a short vertical reel (about {int(config.REEL_SECONDS)} seconds) about this trending Google search.\n"
        f"Topic: {trend['topic']}\nSearch volume: {trend.get('traffic') or 'unknown'}\nToday's headlines:\n{headlines}\n\n"
        "Only state facts the headlines support; if unsure, frame it as what people are searching for. "
        "First slide is a scroll-stopping hook, last slide asks viewers to comment and follow."
    )
    response = client.beta.messages.create(
        model="claude-opus-5-5",
        max_tokens=4000,
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        output_config={"effort": "low", "format": {"type": "json_schema", "schema": SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    if response.stop_reason == "refusal":
        raise RuntimeError("Claude declined this topic")
    text = next(b.text for b in response.content if b.type == "text")
    script = json.loads(text)
    script["slides"] = script["slides"][:6]
    script["video_queries"] = script["video_queries"] + [trend["topic"], "news"]
    return _finish(script, trend)


def write_script(trend):
    if config.ANTHROPIC_API_KEY:
        try:
            return claude_script(trend)
        except Exception as e:
            print(f"  ! AI script failed ({e}); using the built-in template")
    return template_script(trend)
