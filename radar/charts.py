from datetime import date, timedelta
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.ticker import FuncFormatter  # noqa: E402

BG = "#16202d"
LINE = "#66c0f4"
AXIS = "#2a475e"
LABEL = "#61686d"
MARK = "#8f98a0"


def _short(n, _pos=None) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1000:
        return f"{n / 1000:.0f}k" if n >= 10_000 else f"{n / 1000:.1f}k"
    return f"{int(n)}"


def wishlist_chart(points: list[tuple[date, int]], path: Path, demo_date: date | None = None) -> bool:
    """Area chart in the report's style. Returns False when there is nothing to draw."""
    points = sorted(p for p in points if p[1] is not None)
    if not points:
        return False
    if len(points) == 1:
        points = [(points[0][0] - timedelta(days=1), points[0][1]), points[0]]
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]

    fig, ax = plt.subplots(figsize=(6.0, 1.35), dpi=200)
    fig.patch.set_facecolor(BG)
    ax.set_facecolor(BG)
    ax.fill_between(xs, ys, 0, color=LINE, alpha=0.18, linewidth=0)
    ax.plot(xs, ys, color=LINE, linewidth=1.8)
    ax.scatter([xs[-1]], [ys[-1]], color="white", s=10, zorder=3)
    ax.set_ylim(0, max(ys) * 1.12 or 1)
    ax.set_xlim(xs[0], xs[-1])

    if demo_date and xs[0] <= demo_date <= xs[-1]:
        ax.axvline(demo_date, color=MARK, linestyle=(0, (3, 3)), linewidth=0.8)
        ax.text(demo_date, max(ys) * 1.05, " Demo", color=MARK, fontsize=6.5, va="top")

    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(AXIS)
    ax.tick_params(colors=LABEL, labelsize=6.5, length=0)
    ax.set_xticks([xs[0], xs[-1]])
    ax.set_xticklabels([xs[0].strftime("%d %b %Y"), "Today"])
    ax.get_xticklabels()[0].set_ha("left")
    ax.get_xticklabels()[-1].set_ha("right")
    ax.yaxis.tick_right()
    ax.yaxis.set_major_formatter(FuncFormatter(_short))
    ax.yaxis.set_major_locator(plt.MaxNLocator(3))

    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, facecolor=BG, bbox_inches="tight", pad_inches=0.06)
    plt.close(fig)
    return True
