"""Daily Gamalytic wishlist numbers, kept out of the public repo.

With DATA_KEY set (a GitHub secret), the store is committed encrypted as data/private.enc.
Without it (local runs), it is a plain data/private.local.json that .gitignore keeps out of git.
"""
import json
import os

from cryptography.fernet import Fernet, InvalidToken

from .config import DATA_DIR

ENC_FILE = DATA_DIR / "private.enc"
PLAIN_FILE = DATA_DIR / "private.local.json"


def _key() -> bytes | None:
    key = os.environ.get("DATA_KEY", "").strip()
    return key.encode() if key else None


def load() -> dict:
    key = _key()
    if key and ENC_FILE.exists():
        try:
            return json.loads(Fernet(key).decrypt(ENC_FILE.read_bytes()))
        except InvalidToken:
            raise SystemExit("DATA_KEY can't decrypt data/private.enc: the key changed. "
                             "Restore the old key, or delete data/private.enc to start over.")
    if PLAIN_FILE.exists():
        return json.loads(PLAIN_FILE.read_text(encoding="utf-8"))
    return {}


def save(store: dict) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    raw = json.dumps(store, sort_keys=True).encode()
    key = _key()
    if key:
        ENC_FILE.write_bytes(Fernet(key).encrypt(raw))
    else:
        PLAIN_FILE.write_bytes(raw)


def record(store: dict, appid: int, day: str, wishlists: int) -> None:
    store.setdefault(str(appid), {})[day] = int(wishlists)


def series(store: dict, appid: int) -> list[tuple[str, int]]:
    return sorted(store.get(str(appid), {}).items())


def missing_key_in_ci() -> bool:
    return bool(os.environ.get("GITHUB_ACTIONS")) and not _key()


if __name__ == "__main__":
    # python -m radar.private  -> prints a new key for the DATA_KEY secret
    print(Fernet.generate_key().decode())
