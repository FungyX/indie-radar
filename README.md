# Indie Radar

A daily email report about indie games, built from Reddit, Steam, Gamalytic and YouTube.

- **Daily, about 8:00 Prague time:** new posts from the last 24 hours where indie devs share wishlist numbers. Each post is read by Claude, which pulls out wishlists, time period, what marketing worked and demo results. The post must claim **≥ 1,000 wishlists**, or **≥ 500 within the first 7 days**. The game is then looked up on Steam (followers, demo and its date, trailer length), Gamalytic (outstanding wishlists, daily wishlist gain, top wishlist rank, predicted month-1 sales, tags) and YouTube (trailer views). The same game posted to several subreddits shows up as one card, and a game isn't repeated within 14 days.
- **Mondays:** a "Followed games" section with each game's capsule, Steam link, wishlists, change since last week and a history chart.
- **Dashboard:** a small public website (GitHub Pages) with followed games updated daily and every past report. It shows **Steam followers only**: Gamalytic's terms forbid redistributing their data, so Gamalytic numbers appear only in your private email.

Everything runs free on GitHub Actions. Claude uses your **Claude subscription** through Claude Code, not the paid API. Email goes through Resend, which needs an API key, not your email password.

## One-time setup

1. **Create a GitHub repository**, e.g. `indie-radar`. It must be **public** for free GitHub Pages; the report only contains public data. Upload this folder to it.
2. **Turn on Pages:** repo → Settings → Pages → Source: **GitHub Actions**.
3. **Get a Claude token (uses your subscription):**
   - Install Claude Code CLI in PowerShell: `irm https://claude.ai/install.ps1 | iex`
   - Run `claude setup-token`, sign in, and copy the token it prints.
4. **Get a Resend key (for email):** sign up at [resend.com](https://resend.com) using your Gmail address ("Continue with Google" works, no password needed). API Keys → Create → "Sending access". Without your own domain, Resend can only email the address you signed up with, which is all we need.
5. **Make a data key** (encrypts the Gamalytic wishlist history saved in the public repo). In this folder run:
   `.venv\Scripts\python.exe -m radar.private` and copy the line it prints. Keep it safe: if it's lost, the saved wishlist history can't be read and starts over.
6. **Add secrets:** repo → Settings → Secrets and variables → Actions → New repository secret:

   | Name | Value |
   |---|---|
   | `CLAUDE_CODE_OAUTH_TOKEN` | the token from step 3 |
   | `RESEND_API_KEY` | the key from step 4 |
   | `REPORT_TO` | your Gmail address |
   | `DATA_KEY` | the key from step 5 |
   | `GAMALYTIC_API_KEY` | *optional*, only with a paid Gamalytic plan |

7. **Test it:** Actions tab → "Daily report" → Run workflow. When it finishes you get the email, and the dashboard is at `https://<your-user>.github.io/indie-radar/`.

## Everyday use

| To change | Edit |
|---|---|
| Subreddits | `config/subreddits.txt` |
| Followed games | `config/followed_games.txt`, or the **+ Follow** / **Unfollow** links in the email (they open a pre-filled GitHub issue; press Submit) |
| Thresholds, time, timezone, weekly day | `config/settings.json` |

You can edit files right on github.com (pencil icon), or ask Claude to do it.

`settings.json` options:
- `min_wishlists` / `first_week_wishlists` / `first_week_days`: the wishlist filter.
- `min_interest_score`: Claude's 0–100 score for how useful a post is. Lower it to see more posts.
- `max_full_cards`: number of big cards. Up to 6 more posts appear as small cards.
- `repeat_game_cooldown_days`: don't show the same game again within this many days.
- `wishlists_per_follower`: the multiplier used to estimate wishlists from Steam followers.
- `daily_not_before`, `timezone`, `weekly_day`: timing.

## What the numbers mean (limits)

- **Wishlists in the email** are Gamalytic's "outstanding wishlists" estimate, read from the same data their public game page shows (no account needed). That data isn't an official API, so Gamalytic can change or block it; then the report falls back to **Steam followers × 10** (`wishlists_per_follower`). Gamalytic hides numbers for some games (often released ones); those use the fallback too.
- **History charts:** Gamalytic's free data has no past wishlist numbers, so the tool records them itself every day. Charts start the day a game is first seen; games shown in daily reports are tracked for 60 days, so a game you follow later already has data. Until a game has a week of data, "vs last week" is estimated from Gamalytic's daily rate (marked "est."). With a paid `GAMALYTIC_API_KEY`, full history since the page went up is used.
- **Privacy split:** Gamalytic numbers are stored encrypted (`data/private.enc`, key `DATA_KEY`) and weekly charts are attached inside the email. The public dashboard and `data/snapshots.csv` contain Steam data only.
- **"Wishlists claimed" and marketing numbers** come from the dev's own post, read by Claude.
- **YouTube** is read from the public search page, so a game with a generic name can match the wrong video. Check the link.
- **Reddit** is read through its public RSS feeds. If Reddit starts blocking GitHub's servers, the report will say so at the top; the fix is to run the Reddit step from your own PC.

## Running locally

```bash
pip install -r requirements.txt
python -m radar.main --force
```

This writes `out/email_preview.html` (the email as you'd see it) and `site/` (the public dashboard). Set `RADAR_WEEKLY=1` to include the weekly section on any day. It doesn't send email. Without the `claude` CLI logged in, a much simpler keyword parser is used instead of Claude.
