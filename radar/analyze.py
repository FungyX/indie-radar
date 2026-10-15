"""Reads Reddit posts with Claude Code (your Claude subscription, no API key) and pulls out the stats.

GitHub Actions authenticates the `claude` CLI with CLAUDE_CODE_OAUTH_TOKEN, made once with
`claude setup-token`. If the CLI is missing, a simple regex fallback is used so the pipeline
still runs (useful for local testing), but it is much less accurate.
"""
import json
import re
import shutil
import subprocess

PROMPT = """You review Reddit posts from game-dev subreddits for a daily report about indie game marketing.
For EACH post below, decide whether an indie developer is sharing real numbers about their OWN game
(wishlists above all; also followers, sales, demo results, festival results, what marketing worked).

Be strict. "shares_stats" is FALSE when:
- the numbers are about other people's games, the industry, or hypotheticals
  (e.g. "you see others hitting 100K wishlists", "what if I had 10k wishlists?", "is 2k wishlists good?")
- the post is a question, advice, rant or opinion without the author's own concrete results
- the game can't be identified: no game name in the post and no Steam link
- the wishlist number is a goal or a target, not the current count
Only the author's own, current, stated wishlist count goes in "wishlists".

Return ONLY a JSON array, one object per post, no prose, with exactly these keys:
- "id": the post id, copied exactly
- "shares_stats": true only if the author shares concrete current numbers about their own, identifiable game
- "game_name": the game's title as written in the post or its Steam link, or null. Never use the post title as a game name.
- "wishlists": total wishlists the author says THEIR game has right now, as an integer, or null (convert "4.2k" to 4200)
- "period_days": over how many days those wishlists were gathered, counting from when the Steam page went up, as an integer, or null if not stated
- "period_text": short human phrase for that period ("6 weeks", "since March") or null
- "has_steam_page": true/false/null
- "strategies": list of {"name": short label like "Steam Next Fest", "Reddit posts", "TikTok", "Streamers", "Paid ads", "wishlists": integer gained from it or null, "note": max 12 words}
- "demo": short note about a demo and its effect on wishlists, or null
- "interest_score": 0-100, how useful this post is to another indie dev planning marketing. High = concrete numbers, clear cause and effect, time periods. Low = vague, bragging, no numbers, or not their own game.
- "summary": one sentence (max 25 words) with the main takeaway, numbers included

POSTS:
"""

WISHLIST_RE = re.compile(r"(\d[\d,.]*)\s*(k)?\s*(?:\+\s*)?(?:wish\s?lists?|WLs?)\b", re.IGNORECASE)


def _claude_cli() -> str | None:
    return shutil.which("claude")


def _extract_json_array(text: str) -> list:
    start, end = text.find("["), text.rfind("]")
    if start < 0 or end < start:
        raise ValueError("no JSON array in Claude output")
    return json.loads(text[start:end + 1])


def _ask_claude(posts: list[dict], model: str) -> list[dict]:
    payload = [{
        "id": p["id"],
        "subreddit": p["subreddit"],
        "title": p["title"],
        "steam_links_found": p["steam_appids"],
        "text": p["text"][:5000],
    } for p in posts]
    prompt = PROMPT + json.dumps(payload, ensure_ascii=False, indent=1)
    proc = subprocess.run(
        [_claude_cli(), "-p", "--model", model, "--output-format", "json"],
        input=prompt, capture_output=True, text=True, encoding="utf-8", timeout=900,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"claude exited {proc.returncode}: {(proc.stderr or proc.stdout)[-500:].strip()}")
    try:
        envelope = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise RuntimeError(f"unexpected claude output: {proc.stdout[:300]!r}")
    if isinstance(envelope, list):  # some versions print every message; the result is the last one
        envelope = next((m for m in reversed(envelope) if isinstance(m, dict) and m.get("type") == "result"), {})
    if envelope.get("is_error"):
        raise RuntimeError(f"claude error: {envelope.get('result')}")
    return _extract_json_array(envelope.get("result", ""))


FIRST_PERSON_RE = re.compile(r"\b(I|I'm|I've|we|we're|we've|my|our)\b", re.IGNORECASE)


def _fallback(post: dict) -> dict:
    """Crude stand-in when Claude can't run. Only trusts posts that link a Steam page and speak
    in first person, so general discussion about other people's numbers is skipped."""
    if not post["steam_appids"] or not FIRST_PERSON_RE.search(post["title"] + "\n" + post["text"]):
        return {"id": post["id"], "shares_stats": False, "wishlists": None, "interest_score": 0}
    best = None
    for num, k, *_ in WISHLIST_RE.findall(post["title"] + "\n" + post["text"]):
        try:
            value = float(num.replace(",", "")) * (1000 if k else 1)
        except ValueError:
            continue
        best = max(best or 0, int(value))
    return {
        "id": post["id"], "shares_stats": best is not None, "game_name": None, "wishlists": best,
        "period_days": None, "period_text": None, "has_steam_page": bool(post["steam_appids"]) or None,
        "strategies": [], "demo": None, "interest_score": 50 if best else 0,
        "summary": post["title"],
    }


def analyze(posts: list[dict], settings: dict, log=print) -> dict[str, dict]:
    """post id -> extracted info."""
    results: dict[str, dict] = {}
    if not posts:
        return results
    if not _claude_cli():
        log("! claude CLI not found, using the regex fallback (less accurate)")
        return {p["id"]: _fallback(p) for p in posts}
    size = settings.get("claude_batch_size", 12)
    model = settings.get("claude_model", "sonnet")
    for i in range(0, len(posts), size):
        batch = posts[i:i + size]
        try:
            for item in _ask_claude(batch, model):
                if isinstance(item, dict) and item.get("id"):
                    results[item["id"]] = item
        except Exception as exc:
            log(f"! Claude failed on a batch ({exc}); using the regex fallback for it")
            for p in batch:
                results[p["id"]] = _fallback(p)
    return results


def passes_threshold(info: dict, settings: dict) -> bool:
    wl = info.get("wishlists")
    if not isinstance(wl, (int, float)) or not info.get("shares_stats"):
        return False
    if wl >= settings["min_wishlists"]:
        return True
    days = info.get("period_days")
    return isinstance(days, (int, float)) and days <= settings["first_week_days"] and wl >= settings["first_week_wishlists"]
