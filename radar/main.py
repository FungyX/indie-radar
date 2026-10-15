"""Daily run: scan Reddit, analyze, enrich, snapshot followed games, render email + dashboard.

    python -m radar.main            # respects the time gate (for the scheduled workflow)
    python -m radar.main --force    # run now regardless of time / already-sent
"""
import argparse
import json
import os
import shutil
import time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import quote
from zoneinfo import ZoneInfo

from . import analyze, charts, config, private, reddit, render, steam, store
from .enrich import best_wishlists, game_profile, public_profile


def log(msg: str) -> None:
    print(msg, flush=True)


def set_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"{name}={value}\n")


def should_run(now_local: datetime, state: dict, settings: dict) -> bool:
    hh, mm = map(int, settings["daily_not_before"].split(":"))
    if (now_local.hour, now_local.minute) < (hh, mm):
        log(f"Too early ({now_local:%H:%M} local), skipping this trigger.")
        return False
    if state["last_daily_sent"] == now_local.date().isoformat():
        log("Today's report was already made, skipping.")
        return False
    return True


def issue_url(action: str, appid: int, name: str) -> str | None:
    repo = config.repo_slug()
    if not repo:
        return None
    title = f"{action} {appid} {name}"
    body = "Just press Submit. A workflow updates config/followed_games.txt and closes this issue."
    return f"https://github.com/{repo}/issues/new?title={quote(title)}&body={quote(body)}"


def age_text(published: datetime, now: datetime) -> str:
    hours = int((now - published).total_seconds() // 3600)
    return f"{hours}h ago" if hours >= 1 else "just now"


# ---------------------------------------------------------------- Reddit section

def collect_posts(state: dict, since: datetime, errors: list[str]) -> tuple[list[dict], int]:
    subs = config.subreddits()
    posts, ok, failed = [], 0, []
    # Subreddits Reddit refused (usually "too many requests") get one more try after a pause.
    for attempt, todo in enumerate((subs, failed)):
        if attempt == 1 and todo:
            log(f"Retrying {len(todo)} subreddit(s) after a pause")
            time.sleep(90)
        for sub in list(todo):
            try:
                fetched = reddit.fetch_subreddit(sub)
                ok += 1
            except Exception as exc:
                if attempt == 0:
                    failed.append(sub)
                else:
                    errors.append(f"Could not read r/{sub}: {exc}")
                continue
            posts += [p for p in fetched if p["published"] >= since and p["id"] not in state["seen_posts"]]
            time.sleep(10)  # anonymous RSS allows only a few requests per minute
    if subs and not ok:
        errors.append("Reddit refused every request. It may be blocking GitHub's servers, see README.")
    return posts, ok


def resolve_appid(post: dict, info: dict) -> int | None:
    if post["steam_appids"]:
        return post["steam_appids"][0]
    if info.get("game_name"):
        try:
            return steam.search(info["game_name"])
        except Exception:
            return None
    return None


def group_key(post: dict, info: dict) -> str:
    if info.get("_appid"):
        return f"app:{info['_appid']}"
    if info.get("game_name"):
        return "name:" + steam.normalize(info["game_name"])
    return "author:" + post["author"].lower()


def strategy_bars(info: dict) -> list[dict]:
    strategies = [s for s in info.get("strategies") or [] if isinstance(s, dict) and s.get("name")][:6]
    top = max((s.get("wishlists") or 0 for s in strategies), default=0)
    bars = []
    for s in sorted(strategies, key=lambda s: -(s.get("wishlists") or 0)):
        wl = s.get("wishlists") if isinstance(s.get("wishlists"), (int, float)) else None
        bars.append({"name": s["name"], "wishlists": int(wl) if wl else None,
                     "pct": max(3, round(100 * wl / top)) if wl and top else None,
                     "note": s.get("note")})
    return bars


def reddit_section(state, settings, today, now_utc, errors):
    since = now_utc - timedelta(hours=settings["lookback_hours"])
    posts, _ = collect_posts(state, since, errors)
    for p in posts:
        state["seen_posts"][p["id"]] = today.isoformat()
    candidates = [p for p in posts if reddit.mentions_stats(p)]
    log(f"{len(posts)} new posts, {len(candidates)} mention wishlists")

    def analyze_log(msg: str) -> None:
        log(msg)
        if msg.startswith("!"):  # problems also go into the report so you see them without the logs
            errors.append(msg.lstrip("! "))

    infos = analyze.analyze(candidates, settings, log=analyze_log)
    shared = [p for p in candidates if (infos.get(p["id"]) or {}).get("shares_stats")]
    passing = [p for p in shared
               if analyze.passes_threshold(infos[p["id"]], settings)
               and (infos[p["id"]].get("interest_score") or 0) >= settings["min_interest_score"]]
    log(f"{len(shared)} share stats, {len(passing)} pass the wishlist filter")

    # Same game posted to several subreddits -> one card.
    groups: dict[str, list[dict]] = {}
    for p in passing:
        info = infos[p["id"]]
        if info.get("game_name") and steam.normalize(info["game_name"]) == steam.normalize(p["title"]):
            info["game_name"] = None  # a post title isn't a game name
        info["_appid"] = resolve_appid(p, info)
        if not info["_appid"] and not info.get("game_name"):
            log(f"Skipping '{p['title'][:60]}': no identifiable game")
            continue
        groups.setdefault(group_key(p, info), []).append(p)

    cooldown = (today - timedelta(days=settings["repeat_game_cooldown_days"])).isoformat()
    items = []
    for group in groups.values():
        group.sort(key=lambda p: -(infos[p["id"]].get("interest_score") or 0))
        post, info = group[0], infos[group[0]["id"]]
        appid = info.get("_appid")
        if appid and state["reported_games"].get(str(appid), "") > cooldown:
            log(f"Skipping {info.get('game_name')} ({appid}): already reported recently")
            continue
        post = dict(post, age=age_text(post["published"], now_utc))
        items.append({
            "post": post, "info": info, "appid": appid,
            "score": int(info.get("interest_score") or 0),
            "also_in": sorted({f"r/{p['subreddit']}" for p in group[1:]} - {f"r/{post['subreddit']}"}),
            "bars": strategy_bars(info),
        })
    items.sort(key=lambda i: -i["score"])
    full_n = settings["max_full_cards"]
    full, compact = items[:full_n], items[full_n:full_n + 6]

    profiles = {}
    for item in full + compact:
        item["game"] = None
        if item["appid"]:
            try:
                item["game"] = game_profile(item["appid"], settings, today, with_youtube=item in full)
            except Exception as exc:
                errors.append(f"Steam lookup failed for {item['appid']}: {exc}")
        if item["game"]:
            profiles[item["appid"]] = item["game"]
            state["reported_games"][str(item["appid"])] = today.isoformat()
            item["follow_url"] = issue_url("follow", item["appid"], item["game"]["name"])
        else:
            item["follow_url"] = None

    stats = {"scanned": len(posts), "mentions": len(candidates), "shared": len(shared), "passed": len(items)}
    return full, compact, stats, profiles


# ---------------------------------------------------------------- Followed games

def _week_gain(pts: list[tuple[date, int]], value, today: date):
    earlier = [v for d, v in sorted(pts) if d <= today - timedelta(days=7)]
    return (value - earlier[-1]) if (earlier and value) else None


def followed_rows(followed: list[int], profiles: dict, snaps: list[dict], priv: dict,
                  today: date, public: bool) -> list[dict]:
    """Public rows (dashboard) use Steam followers only; private rows (email) use Gamalytic wishlists."""
    rows = []
    chart_dir = config.SITE_DIR if public else config.OUT_DIR
    for appid in followed:
        game = profiles.get(appid)
        if not game:
            continue
        gama = game.get("gamalytic") or {}
        gain_note = None
        if public:
            pts = [(date.fromisoformat(r["date"]), int(float(r["followers"])))
                   for r in store.history_for(snaps, appid) if r.get("followers")]
            value, label, note = game.get("followers"), "Steam followers", "Steam followers"
            gain = _week_gain(pts, value, today)
        else:
            value, source = best_wishlists(game)
            label = f"Wishlists ({source})" if source else "Wishlists"
            if source == "Gamalytic":
                pts = [(date.fromisoformat(d), v) for d, v in private.series(priv, appid)]
                note = "Gamalytic outstanding wishlists, recorded daily"
            else:
                pts = [(date.fromisoformat(r["date"]), int(float(r["est_wishlists"])))
                       for r in store.history_for(snaps, appid) if r.get("est_wishlists")]
                note = "estimated from Steam followers"
            gain = _week_gain(pts, value, today)
            if gain is None and gama.get("daily_gain"):
                gain, gain_note = round(gama["daily_gain"] * 7), "est. from daily rate"
        chart_rel = f"charts/{appid}.png"
        demo_date = game["demo"]["date"] if game.get("demo") else None
        has_chart = charts.wishlist_chart(pts, chart_dir / chart_rel, demo_date)
        since = min(pts)[0].strftime("%d %b %Y") if pts else today.strftime("%d %b %Y")
        rows.append({
            "game": public_profile(game) if public else game,
            "value": value, "value_label": label, "gain": gain, "gain_note": gain_note,
            "followers": game.get("followers"), "show_followers": not public,
            "daily_gain": None if public else gama.get("daily_gain"),
            "chart": f"{chart_rel}?v={today.isoformat()}" if has_chart else None,
            "chart_file": str(chart_dir / chart_rel) if has_chart else None,
            "chart_id": f"chart-{appid}",
            "chart_note": f"Since {since} · {note}",
            "unfollow_url": issue_url("unfollow", appid, game["name"]),
        })
    return rows


def public_report(report: dict, public_rows: list[dict]) -> dict:
    """Copy of the report safe to publish: no Gamalytic numbers anywhere."""
    def strip(items):
        return [dict(i, game=public_profile(i.get("game"))) for i in items]
    return dict(report, cards=strip(report["cards"]), compact=strip(report["compact"]),
                weekly=public_rows if report["weekly"] is not None else None)


# ---------------------------------------------------------------- main

def run(force: bool, rescan: bool = False) -> bool:
    settings = config.settings()
    tz = ZoneInfo(settings["timezone"])
    now_utc = datetime.now(timezone.utc)
    now_local = now_utc.astimezone(tz)
    today = now_local.date()
    state = store.load_state()

    if not force and not should_run(now_local, state, settings):
        return False
    if rescan:  # process today's posts and games again, e.g. after fixing a problem
        state["seen_posts"] = {k: v for k, v in state["seen_posts"].items() if v != today.isoformat()}
        state["reported_games"] = {k: v for k, v in state["reported_games"].items() if v != today.isoformat()}

    for d in (config.SITE_DIR, config.OUT_DIR):
        if d.exists():
            shutil.rmtree(d)
        d.mkdir(parents=True)
    errors: list[str] = []
    if private.missing_key_in_ci():
        errors.append("DATA_KEY secret is missing, so Gamalytic wishlist history isn't saved between runs. See README.")

    full, compact, stats, profiles = reddit_section(state, settings, today, now_utc, errors)

    # Snapshot followed games and recently reported ones, so history exists if you follow them later.
    followed = config.followed_games()
    track_since = (today - timedelta(days=settings["track_reported_games_days"])).isoformat()
    tracked = list(dict.fromkeys(followed + [int(a) for a, d in state["reported_games"].items() if d >= track_since]))
    snaps = store.load_snapshots()
    priv = private.load()
    for appid in tracked:
        if appid not in profiles:
            try:
                g = game_profile(appid, settings, today, with_youtube=False)
            except Exception as exc:
                errors.append(f"Steam lookup failed for followed game {appid}: {exc}")
                g = None
            if g:
                profiles[appid] = g
        if appid in profiles:
            g = profiles[appid]
            store.upsert_snapshot(snaps, today, g)
            gama = g.get("gamalytic") or {}
            for h in gama.get("history") or []:  # only with a paid key
                private.record(priv, appid, h["date"], h["wishlists"])
            if gama.get("wishlists"):
                private.record(priv, appid, today.isoformat(), gama["wishlists"])
        time.sleep(1)
    store.save_snapshots(snaps)
    private.save(priv)

    is_weekly = now_local.strftime("%A") == settings["weekly_day"] or os.environ.get("RADAR_WEEKLY") == "1"
    email_rows = followed_rows(followed, profiles, snaps, priv, today, public=False) if is_weekly else None
    site_rows = followed_rows(followed, profiles, snaps, priv, today, public=True)

    report = {
        "date": today.isoformat(),
        "date_text": now_local.strftime("%A, %d %b %Y"),
        "stats": stats,
        "cards": full,
        "compact": compact,
        "weekly": email_rows,
        "errors": errors,
        "ratio": settings["wishlists_per_follower"],
        "dashboard_url": config.site_url(),
    }

    # Private email: charts travel inside the email (cid:), never via the public site.
    (config.OUT_DIR / "email.html").write_text(render.email(report, cid=True), encoding="utf-8")
    (config.OUT_DIR / "email_preview.html").write_text(render.email(report), encoding="utf-8")
    inline = [{"file": r["chart_file"], "cid": r["chart_id"]} for r in (email_rows or []) if r["chart_file"]]
    (config.OUT_DIR / "inline.json").write_text(json.dumps(inline), encoding="utf-8")
    n = len(full) + len(compact)
    subject = f"Indie Radar · {now_local:%d %b} · {n} new post{'s' if n != 1 else ''}"
    if is_weekly:
        subject += " + weekly followed games"
    (config.OUT_DIR / "subject.txt").write_text(subject, encoding="utf-8")

    pub = public_report(report, site_rows)
    store.save_report(today, pub, render.email(pub, base="../", nav="../", public=True))
    build_site(site_rows, now_local)

    state["last_daily_sent"] = today.isoformat()
    store.save_state(state, today)
    for e in errors:
        log(f"! {e}")
    log(f"Report ready: {subject}")
    return True


def build_site(rows: list[dict], now_local: datetime) -> None:
    reports = store.list_reports()
    (config.SITE_DIR / "reports").mkdir(parents=True, exist_ok=True)
    for d in reports:
        shutil.copy(store.REPORTS_DIR / f"{d}.html", config.SITE_DIR / "reports" / f"{d}.html")
    repo = config.repo_slug()
    edit_url = f"https://github.com/{repo}/edit/main/config/followed_games.txt" if repo else None
    ctx = {"reports": reports, "followed": rows, "updated": now_local.strftime("%d %b %Y %H:%M"), "edit_url": edit_url}
    (config.SITE_DIR / "index.html").write_text(render.dashboard("index", **ctx), encoding="utf-8")
    (config.SITE_DIR / "archive.html").write_text(render.dashboard("archive", **ctx), encoding="utf-8")
    (config.SITE_DIR / ".nojekyll").write_text("", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true", help="run now even if outside the time window")
    parser.add_argument("--rescan", action="store_true", help="forget today's seen posts and process them again")
    args = parser.parse_args()
    ran = run(args.force, args.rescan)
    set_output("ran", "true" if ran else "false")


if __name__ == "__main__":
    main()
