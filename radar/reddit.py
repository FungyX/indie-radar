"""Reads new posts through Reddit's public RSS feeds (the JSON API refuses anonymous requests)."""
import html
import re
import xml.etree.ElementTree as ET
from datetime import datetime

from .net import get

ATOM = {"a": "http://www.w3.org/2005/Atom"}
REDDIT_UA = "indie-radar/0.1 (personal daily digest; github actions)"
STEAM_APP_RE = re.compile(r"store\.steampowered\.com/app/(\d+)")
TAG_RE = re.compile(r"<[^>]+>")
# Cheap pre-filter: a post must talk about wishlists before Claude reads it.
STATS_HINT_RE = re.compile(r"wish\s?list|\bWLs?\b", re.IGNORECASE)


def html_to_text(fragment: str) -> str:
    fragment = re.sub(r"(?i)<br\s*/?>|</p>|</li>|</h\d>", "\n", fragment)
    text = html.unescape(TAG_RE.sub("", fragment))
    text = text.split("submitted by", 1)[0]  # RSS footer with author/links
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n\s*\n+", "\n\n", text).strip()


def fetch_subreddit(sub: str, limit: int = 100) -> list[dict]:
    r = get(f"https://www.reddit.com/r/{sub}/new/.rss", params={"limit": limit},
            headers={"User-Agent": REDDIT_UA})
    root = ET.fromstring(r.content)
    posts = []
    for e in root.findall("a:entry", ATOM):
        content = e.findtext("a:content", default="", namespaces=ATOM)
        link = e.find("a:link", ATOM)
        published = e.findtext("a:published", namespaces=ATOM) or e.findtext("a:updated", namespaces=ATOM)
        title = html.unescape(e.findtext("a:title", default="", namespaces=ATOM))
        posts.append({
            "id": e.findtext("a:id", default="", namespaces=ATOM),
            "subreddit": sub,
            "title": title,
            "author": e.findtext("a:author/a:name", default="", namespaces=ATOM).removeprefix("/u/"),
            "url": link.get("href") if link is not None else "",
            "published": datetime.fromisoformat(published),
            "text": html_to_text(content),
            "steam_appids": sorted({int(x) for x in STEAM_APP_RE.findall(html.unescape(content) + " " + title)}),
        })
    return posts


def mentions_stats(post: dict) -> bool:
    return bool(STATS_HINT_RE.search(post["title"] + "\n" + post["text"]))
