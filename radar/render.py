from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import ROOT
from .enrich import best_wishlists


def _num(value) -> str:
    if value is None or value == "":
        return "—"
    try:
        return f"{int(value):,}"
    except (TypeError, ValueError):
        return str(value)


def _signed(value) -> str:
    return f"+{value:,}" if value >= 0 else f"−{abs(value):,}"


env = Environment(
    loader=FileSystemLoader(ROOT / "radar" / "templates"),
    autoescape=select_autoescape(["html"]),
    trim_blocks=True,
    lstrip_blocks=True,
)
env.filters["num"] = _num
env.filters["signed"] = _signed
env.filters["best_wishlists"] = best_wishlists


def email(report: dict, base: str = "", nav: str | None = None, public: bool = False, cid: bool = False) -> str:
    """cid=True: chart images are inline email attachments. public=True: no Gamalytic numbers."""
    return env.get_template("email.html").render(r=report, base=base, nav=nav, public=public, cid=cid)


def dashboard(page: str, **ctx) -> str:
    return env.get_template("dashboard.html").render(page=page, public=True, cid=False, base="", **ctx)
