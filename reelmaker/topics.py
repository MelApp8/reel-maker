"""Sorts a trend into geopolitics, football, entertainment or crime using its headlines and Wikipedia summary."""
import re

from . import config

KEYWORDS = {
    "geopolitics": [
        "president", "prime minister", "minister", "government", "election", "elections", "parliament", "congress",
        "senate", "sanctions", "tariff", "tariffs", "treaty", "summit", "diplomat", "diplomatic", "embassy", "nato",
        "united nations", "military", "troops", "army", "missile", "missiles", "airstrike", "airstrikes", "ceasefire",
        "war", "invasion", "border", "rebels", "coup", "protest", "protests", "protesters", "unrest", "riot", "riots",
        "clashes", "uprising", "crackdown", "martial law", "regime", "nuclear", "white house", "kremlin", "foreign policy",
        "politician", "political", "politics", "geopolitical", "governor", "republican", "republicans", "democrat",
        "democrats", "midterm", "midterms", "campaign", "trump", "vance", "biden", "putin", "zelensky", "netanyahu", "xi jinping", "modi", "refugees", "strike", "demonstrators", "opposition",
    ],
    "football": [
        "football", "footballer", "soccer", "nfl", "premier league", "la liga", "serie a", "bundesliga", "ligue 1",
        "champions league", "europa league", "uefa", "fifa", "world cup", "mls", "quarterback", "touchdown",
        "super bowl", "striker", "midfielder", "goalkeeper", "defender", "fc", "transfer window", "penalty kick",
        "head coach", "wide receiver", "running back", "linebacker",
    ],
    "entertainment": [
        "actor", "actress", "singer", "rapper", "musician", "songwriter", "album", "song", "film",
        "movie", "box office", "trailer", "netflix", "disney", "hbo", "hulu", "prime video", "episode",
        "sitcom", "reality", "celebrity", "media personality", "comedian", "concert", "grammy",
        "oscar", "oscars", "emmy", "emmys", "premiere", "hollywood", "bollywood", "kardashians",
        "influencer", "youtuber", "podcast", "talk show", "television", "tv",
    ],
    "crime": [
        "arrested", "arrest", "charged", "charges", "murder", "murdered", "homicide", "police", "sheriff", "fbi",
        "suspect", "suspects", "trial", "courtroom", "supreme court", "federal court", "judge", "jury", "verdict", "guilty", "sentenced", "sentence",
        "prison", "jail", "indicted", "indictment", "lawsuit", "fraud", "robbery", "heist", "shooting", "stabbing",
        "kidnapping", "manhunt", "investigation", "detectives", "crime", "criminal", "smuggling", "cartel", "scam",
    ],
}
OTHER_SPORTS = ["nba", "basketball", "mlb", "baseball", "world series", "nhl", "hockey", "tennis", "atp", "wta",
                "ufc", "mma", "boxing", "golf", "pga", "nascar", "formula 1", "f1", "cricket", "ipl", "wnba", "ncaa basketball",
                "rugby", "rugby league", "rugby union", "nrl", "world rugby", "volleyball", "athletics"]
LABELS = {"geopolitics": "Politics & world", "football": "Football", "entertainment": "Entertainment", "crime": "Crime"}
HASHTAGS = {"geopolitics": ["#worldnews", "#politics", "#geopolitics"], "football": ["#football", "#soccer", "#nfl"],
            "entertainment": ["#entertainment", "#celebrity", "#entertainmentnews"], "crime": ["#crime", "#truecrime", "#crimenews"]}


# Searches that are about a website, a puzzle or a price rather than a story
GENERIC = {"news", "today", "nyt", "hints", "wordle", "connections", "strands", "crossword", "weather", "horoscope",
           "lottery", "powerball", "mega", "stock", "stocks", "price", "prices", "login", "app", "score", "scores"}


def _count(text, words):
    return sum(len(re.findall(rf"\b{re.escape(w)}\b", text)) for w in words)


def classify(trend, ctx=None):
    """The best-fitting allowed category, or None when the trend fits none of them."""
    if set(re.findall(r"[a-z]+", trend["topic"].lower())) & GENERIC:
        return None
    news = " ".join([trend["topic"]] + [a["title"] + " " + a.get("summary", "")
                                         for a in ((ctx or {}).get("articles") or trend["news"])]).lower()
    wiki = ((ctx or {}).get("wiki") or {}).get("extract", "")[:300].lower()
    scores = {}
    for cat in config.CATEGORIES:
        words = KEYWORDS.get(cat, [])
        scores[cat] = _count(news, words) + 2 * _count(wiki, words)  # the Wikipedia intro says who someone is
    best = max(scores, key=scores.get, default=None)
    if not best or scores[best] < 1:
        return None
    if _count(news, OTHER_SPORTS) + 2 * _count(wiki, OTHER_SPORTS) >= scores[best]:
        return None  # basketball, tennis, UFC and other non-football sports
    return best
