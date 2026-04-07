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
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

COMPETITORS = {
    "Olio": ["Olio app food sharing", "Olio community sharing platform"],
    "Flashfood": ["Flashfood grocery surplus", "Flashfood app"],
    "Karma": ["Karma food waste app", "Karma surplus food"],
    "Phenix": ["Phenix food waste", "Phenix anti-gaspillage"],
    "ResQ Club": ["ResQ Club food rescue", "ResQclub surplus food"],
    "Wasteless": ["Wasteless dynamic pricing grocery", "Wasteless food waste"],
    "Too Good To Go": ["Too Good To Go funding", "Too Good To Go expansion", "TGTG partnership"],
}

DATA_FILE = Path("docs/data.json")
INDEX_FILE = Path("docs/index.html")
ISSUE_DIR = Path("docs/issues")

SEND_EMAIL = os.environ.get("SEND_EMAIL", "false").lower() == "true"
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
SMTP_HOST = os.environ.get("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.environ.get("SMTP_PORT", "587"))
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
                    a["id"] = aid
                    a["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    new_articles.append(a)
                    print(f"  + {a['title'][:80]}")

    # Persist
    all_articles = new_articles + data.get("articles", [])
    # Keep last 500 articles to avoid unbounded growth
    all_articles = all_articles[:500]
    # Prune seen_ids to match kept articles so the list doesn't grow without bound
    kept_ids = {a["id"] for a in all_articles}
    data["seen_ids"] = list(seen & kept_ids)
    data["articles"] = all_articles
    save_data(data)

    return new_articles


# ── HTML Generation ───────────────────────────────────────────────────────────

CARD_COLORS = {
    "Olio": "#4CAF50",
    "Flashfood": "#2196F3",
    "Karma": "#FF9800",
    "Phenix": "#9C27B0",
    "ResQ Club": "#F44336",
    "Wasteless": "#00BCD4",
    "Too Good To Go": "#1DB954",
}


def competitor_color(name: str) -> str:
    return CARD_COLORS.get(name, "#666")


def render_article_card(a: dict) -> str:
    color = competitor_color(a["competitor"])
    pub = html.escape(a.get("pub_date", "")[:16])
    safe_link = html.escape(a["link"], quote=True)
    return f"""
    <article class="card">
      <span class="tag" style="background:{color}">{html.escape(a['competitor'])}</span>
      <h3><a href="{safe_link}" target="_blank" rel="noopener">{html.escape(a['title'])}</a></h3>
      <footer>
        <span class="source">{html.escape(a['source'])}</span>
        <span class="date">{pub}</span>
      </footer>
    </article>"""


def render_page(articles: list[dict], title: str, back_link: bool = False) -> str:
    cards = "\n".join(render_article_card(a) for a in articles)
    back = '<a class="back" href="../index.html">← Back to archive</a>' if back_link else ""
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
    count = len(articles)
    filter_btns = "".join(
        f'<button class="filter-btn" data-filter="{html.escape(name, quote=True)}">{html.escape(name)}</button>'
        for name in COMPETITORS
    )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}

    :root {{
      --bg: #0a0a0a;
      --surface: #111;
      --border: #222;
      --text: #e8e8e8;
      --muted: #666;
      --accent: #c8f550;
    }}

    body {{
      background: var(--bg);
      color: var(--text);
      font-family: 'Syne', sans-serif;
      min-height: 100vh;
    }}

    header {{
      padding: 3rem 2rem 2rem;
      border-bottom: 1px solid var(--border);
      max-width: 1100px;
      margin: 0 auto;
    }}

    .eyebrow {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.7rem;
      color: var(--accent);
      letter-spacing: 0.15em;
      text-transform: uppercase;
      margin-bottom: 0.75rem;
    }}

    h1 {{
      font-size: clamp(1.8rem, 4vw, 3rem);
      font-weight: 800;
      line-height: 1.1;
      margin-bottom: 0.5rem;
    }}

    .meta {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.75rem;
      color: var(--muted);
      margin-top: 0.5rem;
    }}

    .back {{
      display: inline-block;
      margin-top: 1rem;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.75rem;
      color: var(--accent);
      text-decoration: none;
    }}
    .back:hover {{ text-decoration: underline; }}

    main {{
      max-width: 1100px;
      margin: 0 auto;
      padding: 2rem;
    }}

    .filter-bar {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.5rem;
      margin-bottom: 2rem;
    }}

    .filter-btn {{
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 0.3rem 0.75rem;
      border-radius: 2px;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.7rem;
      cursor: pointer;
      letter-spacing: 0.05em;
      transition: all 0.15s;
    }}
    .filter-btn:hover, .filter-btn.active {{
      background: var(--accent);
      color: #000;
      border-color: var(--accent);
    }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(320px, 1fr));
      gap: 1px;
      background: var(--border);
    }}

    .card {{
      background: var(--surface);
      padding: 1.25rem;
      display: flex;
      flex-direction: column;
      gap: 0.6rem;
      transition: background 0.15s;
    }}
    .card:hover {{ background: #161616; }}

    .tag {{
      display: inline-block;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.62rem;
      letter-spacing: 0.1em;
      text-transform: uppercase;
      color: #000;
      padding: 0.2rem 0.5rem;
      border-radius: 2px;
      width: fit-content;
      font-weight: 600;
    }}

    .card h3 {{
      font-size: 0.9rem;
      font-weight: 700;
      line-height: 1.4;
      flex: 1;
    }}
    .card h3 a {{
      color: var(--text);
      text-decoration: none;
    }}
    .card h3 a:hover {{
      color: var(--accent);
    }}

    footer.card-footer, .card footer {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.65rem;
      color: var(--muted);
      margin-top: auto;
    }}

    .issues-list {{
      display: flex;
      flex-direction: column;
      gap: 1px;
      background: var(--border);
    }}
    .issue-row {{
      background: var(--surface);
      padding: 1rem 1.25rem;
      display: flex;
      justify-content: space-between;
      align-items: center;
      text-decoration: none;
      color: var(--text);
      transition: background 0.15s;
    }}
    .issue-row:hover {{ background: #161616; color: var(--accent); }}
    .issue-row span {{
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.7rem;
      color: var(--muted);
    }}

    .empty {{
      padding: 3rem;
      text-align: center;
      color: var(--muted);
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.8rem;
      background: var(--surface);
    }}

    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 0.75rem;
      margin-bottom: 2rem;
    }}
    .legend-item {{
      display: flex;
      align-items: center;
      gap: 0.4rem;
      font-family: 'IBM Plex Mono', monospace;
      font-size: 0.68rem;
      color: var(--muted);
    }}
    .legend-dot {{
      width: 8px; height: 8px; border-radius: 50%;
    }}
  </style>
</head>
<body>
  <header>
    <p class="eyebrow">Too Good To Go · Competitive Intelligence</p>
    <h1>{title}</h1>
    <p class="meta">{count} articles · Updated {now}</p>
    {back}
  </header>
  <main>
    <div class="legend">
      {''.join(f'<div class="legend-item"><div class="legend-dot" style="background:{v}"></div>{k}</div>' for k,v in CARD_COLORS.items())}
    </div>
    <div class="filter-bar">{filter_btns}</div>
    {"<div class='grid'>" + cards + "</div>" if articles else "<div class='empty'>No articles yet. Run the scraper to populate.</div>"}
  </main>
  <script>
  // Filter by competitor
  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      const target = btn.dataset.filter;
      btn.classList.toggle('active');
      const active = [...document.querySelectorAll('.filter-btn.active')].map(b => b.dataset.filter);
      document.querySelectorAll('.card').forEach(card => {{
        const tag = card.querySelector('.tag')?.textContent.trim();
        card.style.display = (active.length === 0 || active.includes(tag)) ? '' : 'none';
      }});
    }});
  }});
  </script>
</body>
</html>"""


def build_index(all_articles: list[dict], issue_dates: list[str]):
    """Build the main archive index page."""
    recent = all_articles[:30]
    cards = "\n".join(render_article_card(a) for a in recent)
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
    total = len(all_articles)

    issue_rows = ""
    for d in sorted(issue_dates, reverse=True)[:12]:
        display = datetime.strptime(d, "%Y-%m-%d").strftime("%B %d, %Y")
        issue_rows += f'<a class="issue-row" href="issues/{d}.html"><strong>Week of {display}</strong><span>→</span></a>\n'

    filter_btns = "".join(
        f'<button class="filter-btn" data-filter="{name}">{name}</button>'
        for name in COMPETITORS
    )

    page = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>TGTG Competitor Intelligence</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Mono:wght@400;600&family=Syne:wght@400;700;800&display=swap" rel="stylesheet">
  <style>
    *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
    :root {{
      --bg: #0a0a0a; --surface: #111; --border: #222;
      --text: #e8e8e8; --muted: #666; --accent: #c8f550;
    }}
    body {{ background: var(--bg); color: var(--text); font-family: 'Syne', sans-serif; min-height: 100vh; }}
    header {{ padding: 3rem 2rem 2rem; border-bottom: 1px solid var(--border); max-width: 1100px; margin: 0 auto; }}
    .eyebrow {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: var(--accent); letter-spacing: 0.15em; text-transform: uppercase; margin-bottom: 0.75rem; }}
    h1 {{ font-size: clamp(2rem, 5vw, 4rem); font-weight: 800; line-height: 1.05; }}
    .meta {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.75rem; color: var(--muted); margin-top: 0.75rem; }}
    main {{ max-width: 1100px; margin: 0 auto; padding: 2rem; display: grid; grid-template-columns: 1fr 280px; gap: 2rem; }}
    @media (max-width: 760px) {{ main {{ grid-template-columns: 1fr; }} }}
    h2 {{ font-size: 1rem; font-weight: 700; margin-bottom: 1rem; letter-spacing: 0.03em; }}
    .filter-bar {{ display: flex; flex-wrap: wrap; gap: 0.4rem; margin-bottom: 1.25rem; }}
    .filter-btn {{ background: var(--surface); border: 1px solid var(--border); color: var(--text); padding: 0.25rem 0.65rem; border-radius: 2px; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; cursor: pointer; letter-spacing: 0.05em; transition: all 0.15s; }}
    .filter-btn:hover, .filter-btn.active {{ background: var(--accent); color: #000; border-color: var(--accent); }}
    .grid {{ display: grid; gap: 1px; background: var(--border); }}
    .card {{ background: var(--surface); padding: 1.25rem; display: flex; flex-direction: column; gap: 0.6rem; transition: background 0.15s; }}
    .card:hover {{ background: #161616; }}
    .tag {{ display: inline-block; font-family: 'IBM Plex Mono', monospace; font-size: 0.62rem; letter-spacing: 0.1em; text-transform: uppercase; color: #000; padding: 0.2rem 0.5rem; border-radius: 2px; width: fit-content; font-weight: 600; }}
    .card h3 {{ font-size: 0.88rem; font-weight: 700; line-height: 1.4; flex: 1; }}
    .card h3 a {{ color: var(--text); text-decoration: none; }}
    .card h3 a:hover {{ color: var(--accent); }}
    .card footer {{ display: flex; justify-content: space-between; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: var(--muted); }}
    aside h2 {{ margin-bottom: 1rem; }}
    .issues-list {{ display: flex; flex-direction: column; gap: 1px; background: var(--border); }}
    .issue-row {{ background: var(--surface); padding: 0.85rem 1rem; display: flex; justify-content: space-between; align-items: center; text-decoration: none; color: var(--text); transition: background 0.15s; font-size: 0.82rem; font-weight: 700; }}
    .issue-row:hover {{ background: #161616; color: var(--accent); }}
    .issue-row span {{ font-family: 'IBM Plex Mono', monospace; font-size: 0.7rem; color: var(--muted); }}
    .empty {{ padding: 2rem; text-align: center; color: var(--muted); font-family: 'IBM Plex Mono', monospace; font-size: 0.8rem; background: var(--surface); }}
    .legend {{ display: flex; flex-wrap: wrap; gap: 0.6rem; margin-bottom: 1.25rem; }}
    .legend-item {{ display: flex; align-items: center; gap: 0.35rem; font-family: 'IBM Plex Mono', monospace; font-size: 0.65rem; color: var(--muted); }}
    .legend-dot {{ width: 7px; height: 7px; border-radius: 50%; }}
  </style>
</head>
<body>
  <header>
    <p class="eyebrow">Too Good To Go · Competitive Intelligence</p>
    <h1>Competitor<br>News Tracker</h1>
    <p class="meta">{total} articles tracked · {now}</p>
  </header>
  <main>
    <section>
      <h2>Recent Articles</h2>
      <div class="legend">
        {''.join(f'<div class="legend-item"><div class="legend-dot" style="background:{v}"></div>{k}</div>' for k,v in CARD_COLORS.items())}
      </div>
      <div class="filter-bar">{filter_btns}</div>
      {"<div class='grid'>" + cards + "</div>" if recent else "<div class='empty'>No articles yet.</div>"}
    </section>
    <aside>
      <h2>Weekly Issues</h2>
      {"<div class='issues-list'>" + issue_rows + "</div>" if issue_rows else "<div class='empty'>No issues yet.</div>"}
    </aside>
  </main>
  <script>
  document.querySelectorAll('.filter-btn').forEach(btn => {{
    btn.addEventListener('click', () => {{
      btn.classList.toggle('active');
      const active = [...document.querySelectorAll('.filter-btn.active')].map(b => b.dataset.filter);
      document.querySelectorAll('.card').forEach(card => {{
        const tag = card.querySelector('.tag')?.textContent.trim();
        card.style.display = (active.length === 0 || active.includes(tag)) ? '' : 'none';
      }});
    }});
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
    html = render_page(articles, f"Week of {display}", back_link=True)
    (ISSUE_DIR / f"{date_str}.html").write_text(html)
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

    html = build_email_html(articles, week_str)
    msg.attach(MIMEText(html, "html"))

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
        weekly_articles = [a for a in all_articles if a.get("fetched_at", "") >= cutoff]

        build_issue_page(weekly_articles, week_start)
        issue_dates.append(week_start)

        if SEND_EMAIL:
            send_weekly_email(weekly_articles)

    # Always rebuild index
    build_index(all_articles, issue_dates)
    print("\n── Done ──\n")


if __name__ == "__main__":
    main()
