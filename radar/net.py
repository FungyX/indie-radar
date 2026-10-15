import time

import requests

BROWSER_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/130.0 Safari/537.36"
)

_session = requests.Session()
_session.headers.update({"User-Agent": BROWSER_UA, "Accept-Language": "en-US,en;q=0.9"})


def get(url: str, *, params=None, headers=None, retries: int = 3, timeout: int = 30) -> requests.Response:
    """GET with a few retries on network errors, 429 and 5xx."""
    last_exc = None
    for attempt in range(retries):
        try:
            r = _session.get(url, params=params, headers=headers, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                raise requests.HTTPError(f"{r.status_code} for {url}", response=r)
            r.raise_for_status()
            return r
        except requests.RequestException as exc:
            last_exc = exc
            status = getattr(getattr(exc, "response", None), "status_code", None)
            if status and 400 <= status < 500 and status != 429:
                raise
            if attempt == retries - 1:
                break
            if status == 429:
                retry_after = exc.response.headers.get("Retry-After", "")
                time.sleep(min(int(retry_after), 120) if retry_after.isdigit() else 30 * (attempt + 1))
            else:
                time.sleep(2 * (attempt + 1))
    raise last_exc
