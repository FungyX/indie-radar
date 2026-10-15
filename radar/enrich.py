"""Collects everything we know about one Steam game."""
from datetime import date

from . import gamalytic, steam, youtube


def game_profile(appid: int, settings: dict, today: date, with_youtube: bool = True) -> dict | None:
    details = steam.app_details(appid)
    if not details:
        return None
    name = details.get("name", f"App {appid}")
    release = details.get("release_date") or {}
    g = {
        "appid": appid,
        "name": name,
        "url": steam.store_url(appid),
        "header": details.get("header_image"),
        "developers": details.get("developers") or [],
        "short_description": details.get("short_description"),
        "coming_soon": bool(release.get("coming_soon")),
        "release_text": release.get("date") or "TBA",
        "genres": [x["description"] for x in details.get("genres") or []],
        "gamalytic_url": gamalytic.page_url(appid),
    }
    g["followers"] = steam.followers(appid)
    ratio = settings.get("wishlists_per_follower", 10)
    g["est_wishlists"] = int(g["followers"] * ratio) if g["followers"] else None

    basic = gamalytic.basic(appid)
    g["tags"] = (basic.get("tags") or [])[:5] or g["genres"][:4]

    # Private: only rendered into the email, stripped from everything public (see public_profile).
    g["gamalytic"] = gamalytic.wishlist_data(appid)

    g["demo"] = steam.demo_info(details)
    if g["demo"] and g["demo"]["date"]:
        g["demo"]["days_live"] = (today - g["demo"]["date"]).days
    g["trailer"] = steam.trailer_info(details)
    studios = (details.get("developers") or []) + (details.get("publishers") or [])
    g["youtube"] = youtube.find_trailers(name, appid, studios) if with_youtube else None
    return g


def best_wishlists(g: dict, public: bool = False) -> tuple[int | None, str]:
    """The wishlist number to show, and where it came from. Public pages never get Gamalytic's."""
    if not public and (g.get("gamalytic") or {}).get("wishlists"):
        return int(g["gamalytic"]["wishlists"]), "Gamalytic"
    if g.get("est_wishlists"):
        return g["est_wishlists"], "est. from followers"
    return None, ""


def public_profile(g: dict | None) -> dict | None:
    return {k: v for k, v in g.items() if k != "gamalytic"} if g else g
