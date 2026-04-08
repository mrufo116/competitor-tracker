# TGTG Competitor News Tracker — Context

## What We're Building

An automated competitive intelligence tool for **Too Good To Go** that monitors Google News for activity across key food-waste competitors. It runs entirely on GitHub Actions (zero infrastructure cost) and publishes a branded internal dashboard to GitHub Pages.

**Live site:** https://mrufo116.github.io/competitor-tracker/
**Repo:** https://github.com/mrufo116/competitor-tracker

### Competitors Tracked

120 competitors across 5 categories (see `scripts/fetch_news.py` for full list):

| Category | Count | Color |
|---|---|---|
| B2C Marketplaces | 27 | #2563eb |
| E-commerce | 20 | #7c3aed |
| Other Surplus Optimisation | 48 | #059669 |
| Retail Tech | 7 | #0891b2 |
| Retail Tech: Donation | 18 | #d97706 |

The original 7 competitors (Olio, Flashfood, Karma, Phenix, ResQ Club, Wasteless, Too Good To Go) keep their individual brand colors; all others use their category color.

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

### Local Copy

Working files live at `/Users/mrufo/claude-projects/competitor-tracker/`.
The `/tmp/competitor-tracker/` clone is stale — always work from `claude-projects`.
Push to GitHub manually when ready (`git push origin main` from the local copy).

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

### 2026-04-08 — Reliability & Performance Hardening (planned)
Six targeted changes to `scripts/fetch_news.py` — plan at `docs/superpowers/plans/2026-04-08-reliability-and-performance.md`:
- **Single source of truth** — `COMPETITORS` and `COMPETITOR_CATEGORIES` now derived from one `_COMPETITOR_DATA` list of `(name, queries, category)` tuples; adding a competitor requires editing one place only
- **JSON guard** — `load_data()` wraps JSON parse in try/except; corrupted `data.json` now returns an empty structure instead of crashing the entire run
- **Retry + backoff** — `fetch_rss()` retries up to 3 times with 2s/4s exponential backoff; catches `URLError` and `ET.ParseError` specifically
- **Parallel fetching** — `fetch_all()` uses `ThreadPoolExecutor(max_workers=12)` with a threading lock; 240 sequential requests replaced by concurrent fetch, cutting worst-case runtime from ~1 hr to ~2 min
- **Email branding** — `build_email_html()` updated from dark/neon theme to TGTG cream (`#f9f3f0`) / teal (`#00615f`) brand, matching the dashboard
- **Named constants** — `MAX_ARTICLES = 2000`, `ARTICLES_ON_INDEX = 60`, `ARTICLE_RETENTION_DAYS = 183` extracted from inline magic numbers

### 2026-04-08 — Competitor Dropdown Filter
Added a styled `<select>` dropdown in the filter bar listing all 120 competitors grouped by category. Selecting a competitor narrows results using AND logic with the category and country filters.

### 2026-04-08 — Country Dropdown Filter
Converted the country filter from pill buttons to a `<select>` dropdown matching the competitor dropdown. Shows only countries present in the current article set.

### 2026-04-08 — Expanded to 120 Competitors (5 Categories)
Added 113 new competitors organised into 5 categories: B2C Marketplaces, E-commerce, Other Surplus Optimisation, Retail Tech, and Retail Tech: Donation. Key structural changes:
- Added `COMPETITOR_CATEGORIES` and `CATEGORY_COLORS` dicts in `fetch_news.py`
- Replaced individual competitor filter buttons with a 5-button category filter bar
- `competitor_color()` falls back to category color for new competitors; original 7 keep distinct colors
- Article cap raised 500 → 2000; index shows 60 most recent (was 30)
- `category` field backfilled on existing articles at fetch time

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
