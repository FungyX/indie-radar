"""Gamalytic data.

- basic(): their public API without a key, used for Steam tags.
- site_data(): the data behind the public game page (gamalytic.com/game/<id>): outstanding
  wishlists, daily wishlist gain, top wishlist rank. Shown only in your private email,
  never on the public dashboard (their terms forbid redistributing the data).
- premium(): their paid API, only used when GAMALYTIC_API_KEY is set.
"""
import os
from datetime import datetime, timezone

from .net import get

BASE = "https://api.gamalytic.com"


def page_url(appid: int) -> str:
    return f"https://gamalytic.com/game/{appid}"


def _number(value):
    # Hidden values come back as `true`; bool is an int subclass, so exclude it explicitly.
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) else None


def basic(appid: int) -> dict:
    try:
        r = get(f"{BASE}/steam-games/list", params={"appids": appid, "fields": "name,tags,unreleased,developers"})
        result = (r.json() or {}).get("result") or []
        return result[0] if result else {}
    except Exception:
        return {}


def site_data(appid: int) -> dict | None:
    try:
        r = get(f"https://gamalytic.com/api/game-details/{appid}",
                headers={"Accept": "application/json", "Referer": page_url(appid)})
        data = (r.json() or {}).get("data") or {}
    except Exception:
        return None
    predictions = data.get("predictions") or {}
    result = {
        "wishlists": _number(data.get("wishlists")),
        "daily_gain": _number(predictions.get("gain")),
        "top_rank": _number(data.get("topWish")),
        "month1_sales": _number(predictions.get("m1")),
        "history": [],
    }
    return result if result["wishlists"] else None


def premium(appid: int) -> dict | None:
    """Wishlist estimate + history from the paid API. None when no key is configured or the call fails."""
    key = os.environ.get("GAMALYTIC_API_KEY")
    if not key:
        return None
    try:
        r = get(f"{BASE}/game/{appid}", headers={"api-key": key},
                params={"fields": "wishlists,followers,history", "include_pre_release_history": "true"})
        data = r.json() or {}
    except Exception:
        return None
    history = []
    for h in data.get("history") or []:
        if h.get("timeStamp") and _number(h.get("wishlists")) is not None:
            day = datetime.fromtimestamp(h["timeStamp"] / 1000, tz=timezone.utc).date().isoformat()
            history.append({"date": day, "wishlists": int(h["wishlists"])})
    if not _number(data.get("wishlists")):
        return None
    return {"wishlists": data["wishlists"], "daily_gain": None, "top_rank": None,
            "month1_sales": None, "history": history}


def wishlist_data(appid: int) -> dict | None:
    return premium(appid) or site_data(appid)
