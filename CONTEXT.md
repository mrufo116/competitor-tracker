# TGTG Competitor News Tracker — Context

## What We're Building

An automated competitive intelligence tool for **Too Good To Go** that monitors Google News for activity across key food-waste competitors. It runs entirely on GitHub Actions (zero infrastructure cost) and publishes a branded internal dashboard to GitHub Pages.

**Live site:** https://mrufo116.github.io/competitor-tracker/
**Repo:** https://github.com/mrufo116/competitor-tracker

### Competitors Tracked

| Competitor | Focus |
|---|---|
| Olio | Community food sharing app |
| Flashfood | Grocery surplus partnerships |
| Karma | Food waste app, Nordics/EU |
| Phenix | Anti-waste campaigns, France |
| ResQ Club | Food rescue, Northern Europe |
| Wasteless | Dynamic pricing, grocery tech |
| Too Good To Go | Brand monitoring (own coverage) |

### How It Works

1. **Fetch** — `scripts/fetch_news.py` queries the Google News RSS API for each competitor's keywords, deduplicates by URL hash, detects article country from domain TLD, and stores up to 500 articles in `docs/data.json`.
2. **Render** — Generates `docs/index.html` (main dashboard) and `docs/issues/YYYY-MM-DD.html` (weekly archive pages) as static HTML — no build step, no framework.
3. **Email** — On weekly runs, sends an HTML digest via SMTP (Gmail App Password).
4. **Deploy** — GitHub Actions commits the generated files back to `main`; GitHub Pages serves the `docs/` folder automatically.

### Schedule

| Trigger | Action |
|---|---|
| Daily 7 AM UTC | Fetch new articles, rebuild index |
| Monday 8 AM UTC | Fetch + build weekly issue page + send email digest |
| Manual dispatch | `gh workflow run tracker.yml --field mode=daily` |

### Tech Stack

- **Language:** Python 3.11 (stdlib only — no pip installs)
- **CI:** GitHub Actions
- **Hosting:** GitHub Pages (`docs/` branch deploy)
- **Font:** DM Sans via Google Fonts
- **Email:** SMTP via Gmail App Password (secrets stored in Actions)

### Email Setup (if not yet configured)

```bash
gh secret set EMAIL_FROM   # sending address
gh secret set EMAIL_TO     # recipient
gh secret set SMTP_HOST    # smtp.gmail.com
gh secret set SMTP_PORT    # 587
gh secret set SMTP_USER    # gmail address
gh secret set SMTP_PASS    # Gmail App Password (not login password)
```

---

## Updates

### 2026-04-07 — Country Filters
Added country detection from article URL domain TLDs (`.co.uk` → 🇬🇧 UK, `.fr` → 🇫🇷 France, etc.). A second filter row now appears below the competitor filters. Both rows use AND logic — selecting UK + Olio shows only UK Olio articles. Countries shown are dynamic — only countries present in the current article set appear as buttons.

### 2026-04-07 — Sort by Published Date
Articles now sort by RSS `pub_date` descending (most recent first). Fallback to `fetched_at` if pub_date can't be parsed. Applied to both the main index and weekly issue pages.

### 2026-04-07 — TGTG Brand Design
Replaced generic dark "vibe-codey" design with Too Good To Go's actual brand system: deep teal topbar (`#00615f`), warm cream background (`#f9f3f0`), pill-shaped buttons (120px border-radius), DM Sans font, teal-tinted shadows, and muted green filter states. Colors sourced from toogoodtogo.com CSS.

### 2026-04-07 — Professional UI Redesign
Moved from dark neon aesthetic to a clean light internal-tool layout: white cards with subtle borders, competitor color as left-border accent on each article row, filter pills, two-column layout with weekly issues sidebar, proper section headers.

### 2026-04-07 — Bug Fixes (initial deployment)
- **SMTP_PORT crash** — `int("")` when GitHub Actions blanks unset secrets; fixed with `or "587"` fallback.
- **XSS** — Article title, link, and source were injected into HTML unescaped; added `html.escape()` throughout.
- **Filter buttons missing** on weekly issue pages — CSS existed but buttons were never rendered.
- **`seen_ids` unbounded growth** — IDs now pruned to match the 500-article cap.
- **`inline` param** on `render_article_card` was unused; removed.

### 2026-04-07 — Initial Deploy
Deployed from `/Users/mrufo/Downloads/files/`. Created GitHub repo, enabled Pages from `docs/`, triggered first run. Scraper fetches 7 competitors via Google News RSS, generates static HTML archive, sends weekly email digest.
