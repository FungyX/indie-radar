"""Finds a game's trailer on YouTube by reading the public search results page (no API key)."""
import json
import re

from .net import get
from .steam import format_duration, normalize

INITIAL_DATA_RE = re.compile(r"(?:var ytInitialData|window\[\"ytInitialData\"\])\s*=\s*(\{.*?\});</script>", re.S)


def _walk(node, key):
    if isinstance(node, dict):
        if key in node:
            yield node[key]
        for v in node.values():
            yield from _walk(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v, key)


def _text(obj) -> str:
    if not obj:
        return ""
    if "simpleText" in obj:
        return obj["simpleText"]
    return "".join(r.get("text", "") for r in obj.get("runs", []))


def _int(text: str) -> int | None:
    digits = re.sub(r"[^\d]", "", text or "")
    return int(digits) if digits else None


def _seconds(length: str) -> int | None:
    if not length:
        return None
    total = 0
    for part in length.split(":"):
        if not part.isdigit():
            return None
        total = total * 60 + int(part)
    return total


def search(query: str) -> list[dict]:
    r = get("https://www.youtube.com/results", params={"search_query": query},
            headers={"Cookie": "SOCS=CAI; CONSENT=YES+1"})
    m = INITIAL_DATA_RE.search(r.text)
    if not m:
        return []
    data = json.loads(m.group(1))
    videos = []
    for v in _walk(data, "videoRenderer"):
        if not isinstance(v, dict) or "videoId" not in v:
            continue
        length = _text(v.get("lengthText"))
        videos.append({
            "id": v["videoId"],
            "url": f"https://www.youtube.com/watch?v={v['videoId']}",
            "title": _text(v.get("title")),
            "channel": _text(v.get("ownerText")),
            "views": _int(_text(v.get("viewCountText"))),
            "length": length or None,
            "seconds": _seconds(length),
            "published": _text(v.get("publishedTimeText")) or None,
        })
    return videos


def find_trailers(game_name: str) -> dict | None:
    """Trailer videos whose title names the game. Returns the most viewed one plus totals."""
    try:
        videos = search(f"{game_name} trailer")
    except Exception:
        return None
    want = normalize(game_name)
    if not want:
        return None
    matches = [v for v in videos if want in normalize(v["title"]) and "trailer" in v["title"].lower()]
    if not matches:
        return None
    best = max(matches, key=lambda v: v["views"] or 0)
    return {
        "best": best,
        "count": len(matches),
        "total_views": sum(v["views"] or 0 for v in matches),
        "length": best["length"] or format_duration(best["seconds"]),
    }
