#!/usr/bin/env python3
"""
Competitor News Tracker for Too Good To Go
Fetches Google News RSS for competitor keywords, deduplicates,
generates HTML archive, and sends weekly email digest.
"""

import html
import os
import json
import hashlib
import smtplib
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

COMPETITORS = {
    "Olio": ["Olio app food sharing", "Olio community sharing platform"],
    "Flashfood": ["Flashfood grocery surplus", "Flashfood app"],
    "Karma": ["Karma food waste app", "Karma surplus food"],
    "Phenix": ["Phenix food waste France", "Phenix food rescue France"],
    "ResQ Club": ["ResQ Club food rescue", "ResQ Club Finland food"],
    "Wasteless": ["Wasteless dynamic pricing grocery", "Wasteless AI dynamic pricing"],
    "Too Good To Go": ["Too Good To Go funding", "Too Good To Go expansion", "TGTG partnership"],
}

DATA_FILE = Path("docs/data.json")
INDEX_FILE = Path("docs/index.html")
ISSUE_DIR = Path("docs/issues")

SEND_EMAIL = os.environ.get("SEND_EMAIL", "false").lower() == "true"
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
SMTP_HOST = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_rss(query: str) -> list[dict]:
    """Fetch Google News RSS for a query string."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
    req = urllib.request.Request(url, headers=headers)

    articles = []
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            tree = ET.parse(resp)
            root = tree.getroot()
            channel = root.find("channel")
            if channel is None:
                return []
            for item in channel.findall("item"):
                title = (item.findtext("title") or "").strip()
                link = (item.findtext("link") or "").strip()
                pub_date = (item.findtext("pubDate") or "").strip()
                source_el = item.find("source")
                source = source_el.text.strip() if source_el is not None else "Unknown"
                articles.append({
                    "title": title,
                    "link": link,
                    "pub_date": pub_date,
                    "source": source,
                })
    except Exception as e:
        print(f"  ⚠ Error fetching '{query}': {e}")
    return articles


def article_id(article: dict) -> str:
    return hashlib.md5(article["link"].encode()).hexdigest()


_TLD_TO_COUNTRY = {
    "uk": "United Kingdom", "co.uk": "United Kingdom", "org.uk": "United Kingdom",
    "fr": "France", "de": "Germany", "dk": "Denmark", "nl": "Netherlands",
    "es": "Spain", "it": "Italy", "be": "Belgium", "pt": "Portugal",
    "ie": "Ireland", "no": "Norway", "se": "Sweden", "fi": "Finland",
    "pl": "Poland", "at": "Austria", "ch": "Switzerland", "ca": "Canada",
    "com.au": "Australia", "au": "Australia", "nz": "New Zealand",
    "in": "India", "sg": "Singapore", "za": "South Africa",
}
_FLAG = {
    "United Kingdom": "🇬🇧", "France": "🇫🇷", "Germany": "🇩🇪", "Denmark": "🇩🇰",
    "Netherlands": "🇳🇱", "Spain": "🇪🇸", "Italy": "🇮🇹", "Belgium": "🇧🇪",
    "Portugal": "🇵🇹", "Ireland": "🇮🇪", "Norway": "🇳🇴", "Sweden": "🇸🇪",
    "Finland": "🇫🇮", "Poland": "🇵🇱", "Austria": "🇦🇹", "Switzerland": "🇨🇭",
    "Canada": "🇨🇦", "Australia": "🇦🇺", "New Zealand": "🇳🇿",
    "India": "🇮🇳", "Singapore": "🇸🇬", "South Africa": "🇿🇦",
    "United States": "🇺🇸",
}


def detect_country(link: str) -> str:
    """Infer country from article URL domain TLD."""
    try:
        host = urllib.parse.urlparse(link).hostname or ""
        host = host.lower().removeprefix("www.")
        # Check two-part TLDs first (e.g. co.uk, com.au)
        parts = host.split(".")
        if len(parts) >= 2:
            two = ".".join(parts[-2:])
            if two in _TLD_TO_COUNTRY:
                return _TLD_TO_COUNTRY[two]
        tld = parts[-1] if parts else ""
        if tld in _TLD_TO_COUNTRY:
            return _TLD_TO_COUNTRY[tld]
    except Exception:
        pass
    return "United States"  # .com / .org / .net default


def country_flag(country: str) -> str:
    return _FLAG.get(country, "🌐")


def pub_date_key(article: dict) -> datetime:
    """Parse RSS pub_date for sorting; falls back to fetched_at, then epoch."""
    for field in ("pub_date", "fetched_at"):
        val = article.get(field, "")
        if not val:
            continue
        try:
            return parsedate_to_datetime(val).astimezone(timezone.utc)
        except Exception:
            pass
        try:
            return datetime.fromisoformat(val).astimezone(timezone.utc)
        except Exception:
            pass
    return datetime.fromtimestamp(0, tz=timezone.utc)


def load_data() -> dict:
    if DATA_FILE.exists():
        return json.loads(DATA_FILE.read_text())
    return {"seen_ids": [], "articles": []}


def save_data(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2))


def fetch_all() -> list[dict]:
    """Fetch all competitors, return deduplicated new articles."""
    data = load_data()
    seen = set(data["seen_ids"])
    new_articles = []

    for competitor, queries in COMPETITORS.items():
        print(f"Fetching: {competitor}")
        for query in queries:
            articles = fetch_rss(query)
            for a in articles:
                aid = article_id(a)
                if aid not in seen:
                    seen.add(aid)
                    a["competitor"] = competitor
                    a["country"] = detect_country(a["link"])
                    a["id"] = aid
                    a["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    new_articles.append(a)
                    print(f"  + {a['title'][:80]}")

    # Persist — sort by pub_date descending, drop >6 months old, then cap
    cutoff_6mo = datetime.now(timezone.utc) - timedelta(days=183)
    all_articles = new_articles + data.get("articles", [])
    all_articles.sort(key=pub_date_key, reverse=True)
    all_articles = [a for a in all_articles if pub_date_key(a) >= cutoff_6mo]
    all_articles = all_articles[:500]
    # Prune seen_ids to match kept articles so the list doesn't grow without bound
    kept_ids = {a["id"] for a in all_articles}
    data["seen_ids"] = list(seen & kept_ids)
    data["articles"] = all_articles
    save_data(data)

    return new_articles


# ── HTML Generation ───────────────────────────────────────────────────────────

CARD_COLORS = {
    "Olio": "#2d7a4f",
    "Flashfood": "#1d5fa8",
    "Karma": "#b45309",
    "Phenix": "#6d28d9",
    "ResQ Club": "#b91c1c",
    "Wasteless": "#0e7490",
    "Too Good To Go": "#00615f",
}

SHARED_CSS = """
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #f9f3f0;
    --surface: #ffffff;
    --border: #dee3e3;
    --text: #222222;
    --muted: #6b7280;
    --accent: #00615f;
    --accent-mid: #03a97b;
    --accent-light: #ddf3e4;
    --topbar-bg: #00615f;
  }
  body {
    background: var(--bg);
    color: var(--text);
    font-family: 'DM Sans', system-ui, -apple-system, sans-serif;
    font-size: 14px;
    line-height: 1.5;
    min-height: 100vh;
  }
  a { color: inherit; }

  /* ── Top bar ── */
  .topbar {
    background: var(--topbar-bg);
    padding: 0 2rem;
    display: flex;
    align-items: center;
    gap: 1rem;
    height: 56px;
  }
  .topbar-wordmark {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    text-decoration: none;
  }
  /* TGTG heart-bag icon, simplified as SVG inline via background */
  .topbar-icon {
    width: 30px; height: 30px;
    background: #ffffff;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    font-size: 14px;
    font-weight: 700;
    color: var(--topbar-bg);
    letter-spacing: -0.03em;
  }
  .topbar-name {
    font-weight: 700;
    font-size: 0.9rem;
    color: #ffffff;
    letter-spacing: -0.01em;
  }
  .topbar-divider {
    width: 1px; height: 20px;
    background: rgba(255,255,255,0.25);
    margin: 0 0.25rem;
  }
  .topbar-section {
    font-size: 0.8rem;
    color: rgba(255,255,255,0.75);
    font-weight: 500;
  }

  /* ── Page header ── */
  .page-header {
    max-width: 1140px;
    margin: 0 auto;
    padding: 2rem 2rem 1.25rem;
    display: flex;
    align-items: flex-end;
    justify-content: space-between;
    flex-wrap: wrap;
    gap: 0.5rem;
    border-bottom: 1px solid var(--border);
  }
  .page-header h1 {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--text);
    letter-spacing: -0.02em;
  }
  .page-header .meta {
    font-size: 0.78rem;
    color: var(--muted);
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 120px;
    padding: 0.3rem 0.85rem;
  }
  .back-link {
    font-size: 0.8rem;
    color: var(--accent);
    text-decoration: none;
    display: inline-flex;
    align-items: center;
    gap: 0.3rem;
    font-weight: 500;
  }
  .back-link:hover { text-decoration: underline; }

  /* ── Layout ── */
  .layout {
    max-width: 1140px;
    margin: 0 auto;
    padding: 1.5rem 2rem 3rem;
    display: grid;
    grid-template-columns: 1fr 260px;
    gap: 1.5rem;
    align-items: start;
  }
  @media (max-width: 720px) { .layout { grid-template-columns: 1fr; } }

  /* ── Section card ── */
  .section-card {
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 12px;
    overflow: hidden;
    box-shadow: 0 1px 3px rgba(0,97,95,0.06);
  }
  .section-header {
    padding: 0.9rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #faf8f6;
  }
  .section-header h2 {
    font-size: 0.72rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    color: var(--accent);
  }
  .section-count {
    font-size: 0.72rem;
    font-weight: 600;
    color: var(--accent);
    background: var(--accent-light);
    border-radius: 120px;
    padding: 0.15rem 0.6rem;
  }

  /* ── Filter bars ── */
  .filter-bar {
    padding: 0.6rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
    background: #faf8f6;
  }
  .filter-bar:last-of-type { border-bottom: 1px solid var(--border); }
  .filter-label {
    font-size: 0.65rem;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.07em;
    color: var(--muted);
    margin-right: 0.25rem;
    white-space: nowrap;
  }
  .filter-btn {
    background: var(--surface);
    border: 1.5px solid var(--border);
    color: var(--text);
    padding: 0.3rem 0.85rem;
    border-radius: 120px;
    font-size: 0.72rem;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    transition: all 0.12s;
  }
  .filter-btn:hover { border-color: var(--accent-mid); color: var(--accent); }
  .filter-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #ffffff;
    font-weight: 600;
  }

  /* ── Article rows ── */
  .article-list { display: flex; flex-direction: column; }
  .article-row {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    gap: 0.875rem;
    align-items: flex-start;
    transition: background 0.1s;
  }
  .article-row:last-child { border-bottom: none; }
  .article-row:hover { background: #faf8f6; }
  .article-accent {
    width: 3px;
    border-radius: 3px;
    flex-shrink: 0;
    align-self: stretch;
    min-height: 40px;
  }
  .article-body { flex: 1; min-width: 0; }
  .article-tag {
    display: inline-block;
    font-size: 0.65rem;
    font-weight: 700;
    padding: 0.18rem 0.55rem;
    border-radius: 120px;
    margin-bottom: 0.4rem;
    color: #fff;
    letter-spacing: 0.02em;
  }
  .article-title {
    font-size: 0.875rem;
    font-weight: 600;
    line-height: 1.45;
    margin-bottom: 0.4rem;
    letter-spacing: -0.01em;
  }
  .article-title a { text-decoration: none; color: var(--text); }
  .article-title a:hover { color: var(--accent); }
  .article-meta { font-size: 0.7rem; color: var(--muted); display: flex; gap: 0.75rem; flex-wrap: wrap; }
  .article-meta-sep { color: var(--border); }

  /* ── Issues sidebar ── */
  .issue-list { display: flex; flex-direction: column; }
  .issue-row {
    padding: 0.8rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    text-decoration: none;
    color: var(--text);
    font-size: 0.8rem;
    font-weight: 600;
    transition: background 0.1s;
  }
  .issue-row:last-child { border-bottom: none; }
  .issue-row:hover { background: var(--accent-light); color: var(--accent); }
  .issue-arrow { color: var(--muted); font-size: 0.75rem; }

  /* ── Legend ── */
  .legend {
    padding: 0.75rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    gap: 0.6rem;
    background: #faf8f6;
  }
  .legend-item { display: flex; align-items: center; gap: 0.35rem; font-size: 0.7rem; color: var(--muted); font-weight: 500; }
  .legend-dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }

  /* ── Empty state ── */
  .empty {
    padding: 2.5rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.8rem;
  }
"""


def competitor_color(name: str) -> str:
    return CARD_COLORS.get(name, "#666")


def render_article_row(a: dict) -> str:
    color = competitor_color(a["competitor"])
    pub = html.escape(a.get("pub_date", "")[:16])
    safe_link = html.escape(a["link"], quote=True)
    c = a.get("country", "United States")
    flag = country_flag(c)
    safe_competitor = html.escape(a["competitor"], quote=True)
    safe_country = html.escape(c, quote=True)
    return f"""
    <div class="article-row" data-competitor="{safe_competitor}" data-country="{safe_country}">
      <div class="article-accent" style="background:{color}"></div>
      <div class="article-body">
        <span class="article-tag" style="background:{color}">{html.escape(a['competitor'])}</span>
        <div class="article-title">
          <a href="{safe_link}" target="_blank" rel="noopener">{html.escape(a['title'])}</a>
        </div>
        <div class="article-meta">
          <span>{html.escape(a['source'])}</span>
          <span class="article-meta-sep">·</span>
          <span>{flag} {html.escape(c)}</span>
          <span class="article-meta-sep">·</span>
          <span>{pub}</span>
        </div>
      </div>
    </div>"""


def render_page(articles: list[dict], title: str, back_link: bool = False) -> str:
    rows = "\n".join(render_article_row(a) for a in articles)
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
    count = len(articles)
    competitor_btns = "".join(
        f'<button class="filter-btn" data-type="competitor" data-filter="{html.escape(name, quote=True)}">{html.escape(name)}</button>'
        for name in COMPETITORS
    )
    present_countries = sorted({a.get("country", "United States") for a in articles})
    country_btns = "".join(
        f'<button class="filter-btn" data-type="country" data-filter="{html.escape(c, quote=True)}">{country_flag(c)} {html.escape(c)}</button>'
        for c in present_countries
    )
    back = '<a class="back-link" href="../index.html">← Back to archive</a>' if back_link else ""

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{html.escape(title)} — TGTG Intel</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>{SHARED_CSS}
    .layout {{ display: block; max-width: 820px; margin: 0 auto; padding: 0 2rem 3rem; }}
  </style>
</head>
<body>
  <nav class="topbar">
    <div class="topbar-wordmark">
      <div class="topbar-icon">TG</div>
      <span class="topbar-name">Too Good To Go</span>
    </div>
    <div class="topbar-divider"></div>
    <span class="topbar-section">Competitive Intelligence</span>
  </nav>
  <div class="page-header" style="max-width:820px">
    <div>
      {back}
      <h1 style="margin-top:0.4rem">{html.escape(title)}</h1>
    </div>
    <span class="meta">{count} articles · {now}</span>
  </div>
  <div class="layout">
    <div class="section-card">
      <div class="section-header">
        <h2>Articles</h2>
        <span class="section-count">{count}</span>
      </div>
      <div class="legend">
        {''.join(f'<div class="legend-item"><div class="legend-dot" style="background:{v}"></div>{k}</div>' for k,v in CARD_COLORS.items())}
      </div>
      <div class="filter-bar"><span class="filter-label">Competitor</span>{competitor_btns}</div>
      <div class="filter-bar"><span class="filter-label">Country</span>{country_btns}</div>
      {"<div class='article-list'>" + rows + "</div>" if articles else "<div class='empty'>No articles for this period.</div>"}
    </div>
  </div>
  <script>
  function applyFilters() {{
    const ac = [...document.querySelectorAll('.filter-btn[data-type="competitor"].active')].map(b => b.dataset.filter);
    const ak = [...document.querySelectorAll('.filter-btn[data-type="country"].active')].map(b => b.dataset.filter);
    document.querySelectorAll('.article-row').forEach(row => {{
      const mc = ac.length === 0 || ac.includes(row.dataset.competitor);
      const mk = ak.length === 0 || ak.includes(row.dataset.country);
      row.style.display = (mc && mk) ? '' : 'none';
    }});
  }}
  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{ btn.classList.toggle('active'); applyFilters(); }});
  }});
  </script>
</body>
</html>"""


def build_index(all_articles: list[dict], issue_dates: list[str]):
    """Build the main archive index page."""
    recent = all_articles[:30]
    rows = "\n".join(render_article_row(a) for a in recent)
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
    total = len(all_articles)

    issue_rows = ""
    for d in sorted(issue_dates, reverse=True)[:12]:
        display = datetime.strptime(d, "%Y-%m-%d").strftime("%B %d, %Y")
        issue_rows += f'<a class="issue-row" href="issues/{d}.html">Week of {display}<span class="issue-arrow">→</span></a>\n'

    competitor_btns = "".join(
        f'<button class="filter-btn" data-type="competitor" data-filter="{html.escape(name, quote=True)}">{html.escape(name)}</button>'
        for name in COMPETITORS
    )
    present_countries = sorted({a.get("country", "United States") for a in recent})
    country_btns = "".join(
        f'<button class="filter-btn" data-type="country" data-filter="{html.escape(c, quote=True)}">{country_flag(c)} {html.escape(c)}</button>'
        for c in present_countries
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Competitor Intel · Too Good To Go</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=DM+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>{SHARED_CSS}</style>
</head>
<body>
  <nav class="topbar">
    <div class="topbar-wordmark">
      <div class="topbar-icon">TG</div>
      <span class="topbar-name">Too Good To Go</span>
    </div>
    <div class="topbar-divider"></div>
    <span class="topbar-section">Competitive Intelligence</span>
  </nav>
  <div class="page-header">
    <h1>Competitor News Tracker</h1>
    <span class="meta">{total} articles tracked · Updated {now}</span>
  </div>
  <div class="layout">
    <section>
      <div class="section-card">
        <div class="section-header">
          <h2>Recent Articles</h2>
          <span class="section-count">{len(recent)} of {total}</span>
        </div>
        <div class="legend">
          {''.join(f'<div class="legend-item"><div class="legend-dot" style="background:{v}"></div>{k}</div>' for k,v in CARD_COLORS.items())}
        </div>
        <div class="filter-bar"><span class="filter-label">Competitor</span>{competitor_btns}</div>
        <div class="filter-bar"><span class="filter-label">Country</span>{country_btns}</div>
        {"<div class='article-list'>" + rows + "</div>" if recent else "<div class='empty'>No articles yet. Run the scraper to populate.</div>"}
      </div>
    </section>
    <aside>
      <div class="section-card">
        <div class="section-header">
          <h2>Weekly Issues</h2>
        </div>
        {"<div class='issue-list'>" + issue_rows + "</div>" if issue_rows else "<div class='empty'>No issues yet.</div>"}
      </div>
    </aside>
  </div>
  <script>
  function applyFilters() {{
    const ac = [...document.querySelectorAll('.filter-btn[data-type="competitor"].active')].map(b => b.dataset.filter);
    const ak = [...document.querySelectorAll('.filter-btn[data-type="country"].active')].map(b => b.dataset.filter);
    document.querySelectorAll('.article-row').forEach(row => {{
      const mc = ac.length === 0 || ac.includes(row.dataset.competitor);
      const mk = ak.length === 0 || ak.includes(row.dataset.country);
      row.style.display = (mc && mk) ? '' : 'none';
    }});
  }}
  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{ btn.classList.toggle('active'); applyFilters(); }});
  }});
  </script>
</body>
</html>"""

    INDEX_FILE.parent.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(page)
    print(f"✓ index.html written ({total} total articles)")


def build_issue_page(articles: list[dict], date_str: str):
    """Build a weekly digest archive page."""
    ISSUE_DIR.mkdir(parents=True, exist_ok=True)
    display = datetime.strptime(date_str, "%Y-%m-%d").strftime("%B %d, %Y")
    page_html = render_page(articles, f"Week of {display}", back_link=True)
    (ISSUE_DIR / f"{date_str}.html").write_text(page_html)
    print(f"✓ Issue page written: issues/{date_str}.html")


# ── Email ─────────────────────────────────────────────────────────────────────

def build_email_html(articles: list[dict], week_str: str) -> str:
    rows = ""
    for a in articles:
        color = competitor_color(a["competitor"])
        safe_link = html.escape(a["link"], quote=True)
        rows += f"""
        <tr>
          <td style="padding:12px 0; border-bottom:1px solid #1e1e1e; vertical-align:top;">
            <span style="display:inline-block;background:{color};color:#000;font-size:10px;font-weight:700;
              padding:2px 6px;border-radius:2px;letter-spacing:0.08em;text-transform:uppercase;
              margin-bottom:6px;">{html.escape(a['competitor'])}</span><br>
            <a href="{safe_link}" style="color:#c8f550;font-size:14px;font-weight:700;
              text-decoration:none;line-height:1.4;">{html.escape(a['title'])}</a><br>
            <span style="color:#555;font-size:11px;font-family:monospace;">
              {html.escape(a['source'])} · {html.escape(a.get('pub_date','')[:16])}
            </span>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head><meta charset="UTF-8"></head>
<body style="margin:0;padding:0;background:#0a0a0a;font-family:'Helvetica Neue',sans-serif;color:#e8e8e8;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#0a0a0a;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">
        <tr><td style="padding-bottom:24px;border-bottom:1px solid #222;">
          <p style="margin:0 0 8px;font-size:10px;color:#c8f550;letter-spacing:0.15em;
            text-transform:uppercase;font-family:monospace;">
            Too Good To Go · Competitive Intelligence
          </p>
          <h1 style="margin:0;font-size:28px;font-weight:800;line-height:1.1;">
            Weekly Roundup<br><span style="color:#555;">Week of {week_str}</span>
          </h1>
          <p style="margin:12px 0 0;font-size:12px;color:#555;font-family:monospace;">
            {len(articles)} new articles this week
          </p>
        </td></tr>
        <tr><td>
          <table width="100%" cellpadding="0" cellspacing="0">
            {rows if rows else '<tr><td style="padding:24px 0;color:#555;font-size:13px;">No new articles this week.</td></tr>'}
          </table>
        </td></tr>
        <tr><td style="padding-top:24px;border-top:1px solid #222;">
          <p style="margin:0;font-size:11px;color:#333;font-family:monospace;">
            TGTG Competitor Tracker · Auto-generated
          </p>
        </td></tr>
      </table>
    </td></tr>
  </table>
</body></html>"""


def send_weekly_email(articles: list[dict]):
    if not all([EMAIL_FROM, EMAIL_TO, SMTP_USER, SMTP_PASS]):
        print("⚠ Email env vars not set, skipping send.")
        return

    week_str = datetime.now(timezone.utc).strftime("%B %d, %Y")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = f"TGTG Competitor Roundup — Week of {week_str} ({len(articles)} articles)"
    msg["From"] = EMAIL_FROM
    msg["To"] = EMAIL_TO

    email_html = build_email_html(articles, week_str)
    msg.attach(MIMEText(email_html, "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
        server.starttls()
        server.login(SMTP_USER, SMTP_PASS)
        server.sendmail(EMAIL_FROM, EMAIL_TO, msg.as_string())

    print(f"✓ Weekly email sent to {EMAIL_TO}")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "daily"

    print(f"\n── Running in '{mode}' mode ──\n")

    new_articles = fetch_all()
    print(f"\n✓ {len(new_articles)} new articles fetched")

    # Load all articles for index
    data = load_data()
    all_articles = data["articles"]

    # Discover existing issue pages
    ISSUE_DIR.mkdir(parents=True, exist_ok=True)
    issue_dates = [f.stem for f in ISSUE_DIR.glob("*.html")]

    if mode == "weekly":
        # Build a weekly issue page
        today = datetime.now(timezone.utc)
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

        # Filter articles from last 7 days
        cutoff = (today - timedelta(days=7)).isoformat()
        weekly_articles = sorted(
            [a for a in all_articles if a.get("fetched_at", "") >= cutoff],
            key=pub_date_key, reverse=True,
        )

        build_issue_page(weekly_articles, week_start)
        issue_dates.append(week_start)

        if SEND_EMAIL:
            send_weekly_email(weekly_articles)

    # Always rebuild index
    build_index(all_articles, issue_dates)
    print("\n── Done ──\n")


if __name__ == "__main__":
    main()
