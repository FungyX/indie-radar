"""State kept in the repo (data/) so every run remembers what earlier runs saw."""
import csv
import json
from datetime import date, timedelta

from .config import DATA_DIR

STATE_FILE = DATA_DIR / "state.json"
SNAPSHOTS_FILE = DATA_DIR / "snapshots.csv"
REPORTS_DIR = DATA_DIR / "reports"
# Public file: Steam data only. Gamalytic numbers live in radar/private.py.
SNAPSHOT_FIELDS = ["date", "appid", "name", "followers", "est_wishlists"]


def load_state() -> dict:
    if STATE_FILE.exists():
        state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    else:
        state = {}
    state.setdefault("last_daily_sent", None)
    state.setdefault("seen_posts", {})      # reddit post id -> date first seen
    state.setdefault("reported_games", {})  # steam appid (str) -> date last reported
    return state


def save_state(state: dict, today: date) -> None:
    # Forget old entries so the file stays small.
    cutoff = (today - timedelta(days=30)).isoformat()
    state["seen_posts"] = {k: v for k, v in state["seen_posts"].items() if v >= cutoff}
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")


def load_snapshots() -> list[dict]:
    if not SNAPSHOTS_FILE.exists():
        return []
    with SNAPSHOTS_FILE.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def save_snapshots(rows: list[dict]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    rows = sorted(rows, key=lambda r: (r["date"], int(r["appid"])))
    with SNAPSHOTS_FILE.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=SNAPSHOT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in SNAPSHOT_FIELDS})


def upsert_snapshot(rows: list[dict], day: date, game: dict) -> None:
    key = (day.isoformat(), str(game["appid"]))
    rows[:] = [r for r in rows if (r["date"], r["appid"]) != key]
    rows.append({
        "date": key[0],
        "appid": key[1],
        "name": game.get("name", ""),
        "followers": game.get("followers") or "",
        "est_wishlists": game.get("est_wishlists") or "",
    })


def history_for(rows: list[dict], appid: int) -> list[dict]:
    return sorted((r for r in rows if r["appid"] == str(appid)), key=lambda r: r["date"])


def save_report(day: date, report_data: dict, email_html: str) -> None:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"{day.isoformat()}.json").write_text(
        json.dumps(report_data, indent=1, default=str), encoding="utf-8")
    (REPORTS_DIR / f"{day.isoformat()}.html").write_text(email_html, encoding="utf-8")


def list_reports() -> list[str]:
    if not REPORTS_DIR.exists():
        return []
    return sorted((p.stem for p in REPORTS_DIR.glob("*.html")), reverse=True)
