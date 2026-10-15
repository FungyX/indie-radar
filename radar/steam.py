import re
from datetime import datetime

from .net import get

APPDETAILS = "https://store.steampowered.com/api/appdetails"
ISO_DURATION_RE = re.compile(r"PT(?:(\d+)H)?(?:(\d+)M)?(?:([\d.]+)S)?")


def store_url(appid: int) -> str:
    return f"https://store.steampowered.com/app/{appid}/"


def app_details(appid: int) -> dict | None:
    r = get(APPDETAILS, params={"appids": appid, "cc": "us", "l": "english"})
    entry = (r.json() or {}).get(str(appid)) or {}
    return entry.get("data") if entry.get("success") else None


def search(name: str) -> int | None:
    """Best Steam app id for a game name, or None."""
    r = get("https://store.steampowered.com/api/storesearch/", params={"term": name, "cc": "us", "l": "en"})
    items = (r.json() or {}).get("items") or []
    if not items:
        return None
    want = normalize(name)
    for item in items:
        if normalize(item.get("name", "")) == want:
            return int(item["id"])
    # Only trust a fuzzy hit when the names clearly overlap.
    first = items[0]
    if want and (want in normalize(first.get("name", "")) or normalize(first.get("name", "")) in want):
        return int(first["id"])
    return None


def followers(appid: int) -> int | None:
    """Community hub member count = the 'followers' number Steam shows."""
    try:
        r = get(f"https://steamcommunity.com/games/{appid}/memberslistxml/", params={"xml": 1})
    except Exception:
        return None
    m = re.search(r"<memberCount>([\d,]+)</memberCount>", r.text)
    return int(m.group(1).replace(",", "")) if m else None


def parse_steam_date(text: str):
    for fmt in ("%d %b, %Y", "%b %d, %Y", "%d %B, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except (ValueError, AttributeError):
            pass
    return None


def demo_info(details: dict) -> dict | None:
    demos = details.get("demos") or []
    if not demos:
        return None
    demo_id = demos[0].get("appid")
    info = {"appid": demo_id, "date_text": None, "date": None, "url": store_url(demo_id)}
    try:
        d = app_details(demo_id)
    except Exception:
        d = None
    if d:
        text = (d.get("release_date") or {}).get("date") or ""
        info["date_text"] = text or None
        info["date"] = parse_steam_date(text)
    return info


def _duration_seconds(mpd_url: str) -> float | None:
    try:
        r = get(mpd_url, timeout=20)
    except Exception:
        return None
    m = re.search(r'mediaPresentationDuration="([^"]+)"', r.text)
    if not m:
        return None
    h, mi, s = ISO_DURATION_RE.match(m.group(1)).groups()
    return int(h or 0) * 3600 + int(mi or 0) * 60 + float(s or 0)


def format_duration(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    seconds = int(round(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def trailer_info(details: dict) -> dict | None:
    movies = details.get("movies") or []
    if not movies:
        return None
    main = next((m for m in movies if m.get("highlight")), movies[0])
    mpd = main.get("dash_h264") or main.get("dash_av1")
    seconds = _duration_seconds(mpd) if mpd else None
    return {"name": main.get("name"), "count": len(movies), "seconds": seconds,
            "length": format_duration(seconds)}


def normalize(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()
