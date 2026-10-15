import json
import os
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"
OUT_DIR = ROOT / "out"
SITE_DIR = ROOT / "site"

APP_ID_RE = re.compile(r"(?:store\.steampowered\.com/app/)?(\d{2,9})")


def _lines(path: Path) -> list[str]:
    if not path.exists():
        return []
    result = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            result.append(line)
    return result


def settings() -> dict:
    return json.loads((CONFIG_DIR / "settings.json").read_text(encoding="utf-8"))


def subreddits() -> list[str]:
    return [s.removeprefix("r/").strip("/") for s in _lines(CONFIG_DIR / "subreddits.txt")]


def parse_app_id(text: str) -> int | None:
    m = APP_ID_RE.search(text)
    return int(m.group(1)) if m else None


def followed_games() -> list[int]:
    ids = []
    for line in _lines(CONFIG_DIR / "followed_games.txt"):
        appid = parse_app_id(line)
        if appid and appid not in ids:
            ids.append(appid)
    return ids


def repo_slug() -> str:
    """owner/repo, from GitHub Actions or the REPO env var when run locally."""
    return os.environ.get("GITHUB_REPOSITORY") or os.environ.get("REPO", "")


def site_url() -> str:
    url = settings().get("site_url") or ""
    if not url and repo_slug():
        owner, repo = repo_slug().split("/", 1)
        url = f"https://{owner}.github.io/{repo}/"
    return url.rstrip("/") + "/" if url else ""
