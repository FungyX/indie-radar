"""Sends the report through Resend (https://resend.com). Needs only an API key, no email password.

Env: RESEND_API_KEY, REPORT_TO (your address, must be the one you signed up to Resend with
while you use the default onboarding@resend.dev sender), optional REPORT_FROM.
"""
import base64
import json
import os
import sys
from pathlib import Path

import requests

from .config import OUT_DIR


def inline_images() -> list[dict]:
    """Weekly charts go inside the email (cid:) so private numbers never touch the public site."""
    spec = OUT_DIR / "inline.json"
    if not spec.exists():
        return []
    return [{
        "filename": Path(item["file"]).name,
        "content": base64.b64encode(Path(item["file"]).read_bytes()).decode(),
        "content_type": "image/png",
        "content_id": item["cid"],
    } for item in json.loads(spec.read_text(encoding="utf-8"))]


def send(html: str, subject: str) -> None:
    key = os.environ.get("RESEND_API_KEY")
    to = os.environ.get("REPORT_TO")
    if not key or not to:
        raise SystemExit("RESEND_API_KEY and REPORT_TO must be set to send email")
    r = requests.post(
        "https://api.resend.com/emails",
        headers={"Authorization": f"Bearer {key}"},
        json={
            "from": os.environ.get("REPORT_FROM") or "Indie Radar <onboarding@resend.dev>",
            "to": [to],
            "subject": subject,
            "html": html,
            **({"attachments": images} if (images := inline_images()) else {}),
        },
        timeout=30,
    )
    if r.status_code >= 300:
        raise SystemExit(f"Resend refused the email: {r.status_code} {r.text}")
    print(f"Email sent to {to}: {subject}")


if __name__ == "__main__":
    html = (OUT_DIR / "email.html").read_text(encoding="utf-8")
    subject = (OUT_DIR / "subject.txt").read_text(encoding="utf-8").strip()
    send(html, subject)
    sys.exit(0)
