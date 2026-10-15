"""Adds or removes a game in config/followed_games.txt from a GitHub issue title.

    python -m radar.follow "follow 1030300 Hollow Knight: Silksong"
    python -m radar.follow "unfollow https://store.steampowered.com/app/1030300/"
"""
import re
import sys

from .config import CONFIG_DIR, parse_app_id

FILE = CONFIG_DIR / "followed_games.txt"


def apply(title: str) -> str:
    m = re.match(r"\s*(follow|unfollow)\s+(.+)", title, re.IGNORECASE)
    if not m:
        return "Title must start with 'follow' or 'unfollow' followed by a Steam app id or link."
    action, rest = m.group(1).lower(), m.group(2)
    appid = parse_app_id(rest)
    if not appid:
        return "Couldn't find a Steam app id in the title."
    name = re.sub(r"^\S+\s*", "", rest).strip()

    lines = FILE.read_text(encoding="utf-8").splitlines() if FILE.exists() else []
    present = [i for i, line in enumerate(lines)
               if line.split("#", 1)[0].strip() and parse_app_id(line.split("#", 1)[0]) == appid]

    if action == "follow":
        if present:
            return f"{appid} is already followed."
        lines.append(f"{appid}  # {name}" if name else str(appid))
        msg = f"Now following {name or appid}. It will appear in the next Monday report and on the dashboard."
    else:
        if not present:
            return f"{appid} wasn't in the followed list."
        lines = [line for i, line in enumerate(lines) if i not in present]
        msg = f"Stopped following {name or appid}."
    FILE.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return msg


if __name__ == "__main__":
    print(apply(" ".join(sys.argv[1:])))
