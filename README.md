# TGTG Competitor News Tracker

Automated competitive intelligence tool that monitors Google News for competitor activity, publishes a GitHub Pages archive site, and sends a weekly email digest.

## Competitors Tracked

| Competitor | Keywords |
|---|---|
| Olio | App launches, community sharing |
| Flashfood | Grocery surplus, store partnerships |
| Karma | Food waste app, expansions |
| Phenix | Anti-waste campaigns |
| ResQ Club | Food rescue news |
| Wasteless | Dynamic pricing, grocery tech |
| Too Good To Go | Brand monitoring, funding, expansions |

## Schedule

- **Daily (7 AM UTC):** Fetches new articles, updates the GitHub Pages site
- **Weekly (Monday 8 AM UTC):** Builds a weekly issue archive page + sends email digest

## Setup

### 1. Create the repo

```bash
# Create a new GitHub repo called "competitor-tracker"
# Upload these files, then enable GitHub Pages:
# Settings → Pages → Source: Deploy from branch → Branch: main → Folder: /docs
```

### 2. Add email secrets

Go to **Settings → Secrets and variables → Actions** and add:

| Secret | Value |
|---|---|
| `EMAIL_FROM` | Your sending address (e.g. `you@gmail.com`) |
| `EMAIL_TO` | Where to deliver the digest |
| `SMTP_HOST` | `smtp.gmail.com` (or your provider) |
| `SMTP_PORT` | `587` |
| `SMTP_USER` | Your Gmail address |
| `SMTP_PASS` | Gmail App Password (not your login password) |

> **Gmail App Password:** Google Account → Security → 2-Step Verification → App Passwords → Generate one for "Mail"

### 3. Trigger the first run

Go to **Actions → Competitor News Tracker → Run workflow** and select mode `daily`.

The site will be live at: `https://YOUR_USERNAME.github.io/competitor-tracker/`

## Customizing Competitors

Edit `scripts/fetch_news.py` — find the `COMPETITORS` dict near the top:

```python
COMPETITORS = {
    "Olio": ["Olio app food sharing", "Olio community sharing platform"],
    # Add or remove entries here
    "Your Competitor": ["search query 1", "search query 2"],
}
```

## Local Testing

```bash
# Install nothing — only stdlib used
python scripts/fetch_news.py daily    # test daily mode
python scripts/fetch_news.py weekly   # test weekly (builds issue page)
```

Output goes to `docs/` — open `docs/index.html` in a browser to preview.

## File Structure

```
competitor-tracker/
├── .github/workflows/
│   └── tracker.yml        # GitHub Actions cron
├── scripts/
│   └── fetch_news.py      # Main scraper + HTML generator + email
└── docs/                  # GitHub Pages root
    ├── index.html          # Archive homepage (auto-generated)
    ├── data.json           # Seen article IDs + article store
    └── issues/
        └── YYYY-MM-DD.html # Weekly issue pages
```
