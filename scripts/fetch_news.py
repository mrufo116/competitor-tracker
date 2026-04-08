#!/usr/bin/env python3
"""
Competitor News Tracker for Too Good To Go
Fetches Google News RSS for competitor keywords, deduplicates,
generates HTML archive, and sends weekly email digest.
"""

import concurrent.futures
import html
import os
import json
import hashlib
import smtplib
import threading
import time
import urllib.error
import urllib.request
import urllib.parse
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import parsedate_to_datetime
from pathlib import Path

# ── Config ────────────────────────────────────────────────────────────────────

# Single source of truth: (name, [search queries], category) or (name, [search queries], category, "Primary Country")
# Add a 4th element to override TLD-based country detection for competitors whose .com domain
# doesn't reflect their actual primary market (e.g. a Korean app with a .com domain).
_COMPETITOR_DATA: list[tuple] = [
    # ── Existing ──
    ("Olio",           ["Olio app food sharing", "Olio community sharing platform"],                "B2C Marketplaces"),
    ("Flashfood",      ["Flashfood grocery surplus", "Flashfood app"],                              "B2C Marketplaces"),
    ("Karma",          ["Karma food waste app", "Karma surplus food"],                              "B2C Marketplaces"),
    ("Phenix",         ["Phenix food waste France", "Phenix food rescue France"],                   "B2C Marketplaces"),
    ("ResQ Club",      ["ResQ Club food rescue", "ResQ Club Finland food"],                         "B2C Marketplaces"),
    ("Wasteless",      ["Wasteless dynamic pricing grocery", "Wasteless AI dynamic pricing"],       "Other Surplus Optimisation"),
    ("Too Good To Go", ["Too Good To Go funding", "Too Good To Go expansion", "TGTG partnership"], "B2C Marketplaces"),
    # ── B2C Marketplaces ──
    ("Vers Voor Vandaag", ["Vers Voor Vandaag food surplus", "Vers Voor Vandaag app"],                          "B2C Marketplaces"),
    ("Crumbs",            ["Crumbs food surplus app", "Crumbs food waste marketplace"],                        "B2C Marketplaces"),
    ("Toriniko",          ["Toriniko food app", "Toriniko food waste Japan"],                                   "B2C Marketplaces",  "Japan"),
    ("Still Good",        ["Still Good food surplus app", "Still Good food waste marketplace"],                 "B2C Marketplaces"),
    ("Gone Good",         ["Gone Good food surplus app", "Gone Good food waste"],                               "B2C Marketplaces"),
    ("Platable",          ["Platable food surplus app", "Platable food marketplace"],                           "B2C Marketplaces"),
    ("Foodbag",           ["Foodbag food surplus app", "Foodbag food delivery waste"],                          "B2C Marketplaces"),
    ("Leftovers",         ["Leftovers food surplus app", "Leftovers food waste marketplace"],                   "B2C Marketplaces"),
    ("Hallowa",           ["Hallowa food app Korea", "Hallowa surplus food"],                                   "B2C Marketplaces",  "South Korea"),
    ("Lucky Meal",        ["Lucky Meal food app surplus", "Lucky Meal food waste Korea"],                       "B2C Marketplaces",  "South Korea"),
    ("Cirklua",           ["Cirklua food surplus marketplace", "Cirklua food app"],                             "B2C Marketplaces"),
    ("Second Plate",      ["Second Plate food surplus app", "Second Plate food waste"],                         "B2C Marketplaces"),
    ("Save Me",           ["Save Me food surplus app", "Save Me food waste app"],                               "B2C Marketplaces"),
    ("Forsa",             ["Forsa food surplus marketplace", "Forsa food waste app"],                           "B2C Marketplaces"),
    ("OrderLemon",        ["OrderLemon food surplus app", "OrderLemon food marketplace"],                       "B2C Marketplaces"),
    ("Savefood",          ["Savefood food surplus app", "Savefood food waste platform"],                        "B2C Marketplaces"),
    ("SaveFOOD",          ["SaveFOOD food technology platform", "SaveFOOD food preservation app"],              "B2C Marketplaces"),
    ("1plate1world",      ["1plate1world food surplus", "1plate1world food waste app"],                         "B2C Marketplaces"),
    ("Buen Provecho",     ["Buen Provecho food surplus app", "Buen Provecho food waste"],                       "B2C Marketplaces"),
    ("Reat",              ["Reat food surplus marketplace", "Reat food waste app"],                             "B2C Marketplaces"),
    ("Salveme!",          ["Salveme food surplus app", "Salveme food waste marketplace"],                       "B2C Marketplaces"),
    # ── Other Surplus Optimisation ──
    ("KitchenPal",                    ["KitchenPal app food waste management", "KitchenPal food inventory"],                          "Other Surplus Optimisation"),
    ("Innovafeed",                    ["Innovafeed insect protein food waste", "Innovafeed food by-product feed"],                    "Other Surplus Optimisation"),
    ("Mottainai Food Tech",           ["Mottainai Food Tech food waste", "Mottainai food technology"],                               "Other Surplus Optimisation"),
    ("Rescube",                       ["Rescube food waste technology", "Rescube food surplus"],                                      "Other Surplus Optimisation"),
    ("Fridge Friend",                 ["Fridge Friend food waste app", "Fridge Friend food expiry tracker"],                         "Other Surplus Optimisation"),
    ("Hulec",                         ["Hulec food waste technology", "Hulec food surplus"],                                          "Other Surplus Optimisation"),
    ("ChicP",                         ["ChicP hummus food waste upcycled", "ChicP surplus food product"],                            "Other Surplus Optimisation"),
    ("Good Grub",                     ["Good Grub food waste", "Good Grub surplus food"],                                            "Other Surplus Optimisation"),
    ("Ecosphere Organics",            ["Ecosphere Organics food waste", "Ecosphere Organics composting"],                            "Other Surplus Optimisation"),
    ("Vego",                          ["Vego food waste app", "Vego surplus food technology"],                                        "Other Surplus Optimisation"),
    ("Lomi",                          ["Lomi food waste composter", "Lomi home composting device"],                                  "Other Surplus Optimisation"),
    ("Reencle",                       ["Reencle food waste composter", "Reencle home composting"],                                   "Other Surplus Optimisation"),
    ("Refood",                        ["Refood food waste rescue", "Refood food bank Portugal"],                                     "Other Surplus Optimisation"),
    ("Proseed",                       ["Proseed food waste technology", "Proseed surplus ingredients"],                               "Other Surplus Optimisation"),
    ("Fonte Ingredients",             ["Fonte Ingredients food waste upcycled", "Fonte Ingredients surplus"],                        "Other Surplus Optimisation"),
    ("Wonky Coffee",                  ["Wonky Coffee surplus food waste", "Wonky Coffee imperfect coffee"],                          "Other Surplus Optimisation"),
    ("Ripe Guard",                    ["Ripe Guard food freshness technology", "Ripe Guard food waste preservation"],                "Other Surplus Optimisation"),
    ("Vitesy",                        ["Vitesy food preservation device", "Vitesy food waste technology"],                           "Other Surplus Optimisation"),
    ("Topanga.io",                    ["Topanga food waste technology", "Topanga.io surplus food platform"],                         "Other Surplus Optimisation"),
    ("Liva",                          ["Liva food waste reduction app", "Liva food surplus optimisation"],                           "Other Surplus Optimisation"),
    ("Proteme",                       ["Proteme food waste technology", "Proteme food preservation"],                                "Other Surplus Optimisation"),
    ("Akorn Technology",              ["Akorn Technology food waste", "Akorn food surplus optimisation"],                            "Other Surplus Optimisation"),
    ("Cetogenix",                     ["Cetogenix food waste technology", "Cetogenix food surplus"],                                 "Other Surplus Optimisation"),
    ("Volare",                        ["Volare food waste technology", "Volare food surplus"],                                       "Other Surplus Optimisation"),
    ("YeastUp",                       ["YeastUp food waste yeast", "YeastUp fermentation food by-product"],                         "Other Surplus Optimisation"),
    ("No Waste App",                  ["No Waste App food inventory tracker", "No Waste food waste manager"],                        "Other Surplus Optimisation"),
    ("Mimica Lab",                    ["Mimica Lab food freshness technology", "Mimica expiry label food waste"],                    "Other Surplus Optimisation"),
    ("Cool Innovation",               ["Cool Innovation food waste", "Cool Innovation food freshness technology"],                   "Other Surplus Optimisation"),
    ("Bpacks",                        ["Bpacks sustainable food packaging", "Bpacks food waste packaging"],                          "Other Surplus Optimisation"),
    ("Viridian Renewable Technology", ["Viridian Renewable food waste technology", "Viridian food surplus"],                         "Other Surplus Optimisation"),
    ("Cerve",                         ["Cerve food waste technology", "Cerve surplus food"],                                         "Other Surplus Optimisation"),
    ("Prism",                         ["Prism food waste optimisation", "Prism food surplus technology"],                            "Other Surplus Optimisation"),
    ("Hubcycled",                     ["Hubcycled food waste upcycled", "Hubcycled surplus food technology"],                        "Other Surplus Optimisation"),
    ("Edama Solutions",               ["Edama Solutions food waste", "Edama food technology"],                                       "Other Surplus Optimisation"),
    ("Skonelabs",                     ["Skonelabs food waste technology", "Skonelabs food surplus"],                                 "Other Surplus Optimisation"),
    ("Ipsago",                        ["Ipsago food waste technology", "Ipsago food surplus optimisation"],                          "Other Surplus Optimisation"),
    ("Green Spot Technologies",       ["Green Spot Technologies food waste", "Green Spot food tech"],                                "Other Surplus Optimisation"),
    ("Rscued",                        ["Rscued food surplus app", "Rscued food waste marketplace"],                                  "Other Surplus Optimisation"),
    ("Unverschwendet",                ["Unverschwendet food waste Austria", "Unverschwendet surplus food"],                          "Other Surplus Optimisation"),
    ("BeBananas",                     ["BeBananas food waste app", "BeBananas surplus food"],                                        "Other Surplus Optimisation"),
    ("FollowFood",                    ["FollowFood food waste app", "FollowFood food tracking"],                                     "Other Surplus Optimisation"),
    ("B!POD",                         ["BPOD food waste technology", "BPOD food surplus"],                                           "Other Surplus Optimisation"),
    ("FoodUp",                        ["FoodUp food waste app", "FoodUp surplus food platform"],                                     "Other Surplus Optimisation"),
    ("ProNovo",                       ["ProNovo food waste technology", "ProNovo food surplus"],                                     "Other Surplus Optimisation"),
    ("Cascara Foods",                 ["Cascara Foods food waste upcycled", "Cascara surplus ingredients"],                          "Other Surplus Optimisation"),
    ("Cook Forever",                  ["Cook Forever food preservation", "Cook Forever food waste"],                                 "Other Surplus Optimisation"),
    ("Skip Shapiro",                  ["Skip Shapiro food waste", "Skip Shapiro food surplus"],                                      "Other Surplus Optimisation"),
    # ── Retail Tech: Donation ──
    ("Eatcloud",                       ["Eatcloud food donation technology", "Eatcloud food bank platform"],                         "Retail Tech: Donation"),
    ("4MyCity",                        ["4MyCity food donation app", "4MyCity food sharing platform"],                               "Retail Tech: Donation"),
    ("PDApp",                          ["PDApp food donation app", "PDApp food rescue platform"],                                    "Retail Tech: Donation"),
    ("We Don't Waste",                 ["We Don't Waste food donation", "We Don't Waste food rescue"],                               "Retail Tech: Donation"),
    ("Knead Technologies",             ["Knead Technologies food waste donation", "Knead food rescue tech"],                         "Retail Tech: Donation"),
    ("Eco Looping",                    ["Eco Looping food donation", "Eco Looping food waste rescue"],                               "Retail Tech: Donation"),
    ("Caboodle",                       ["Caboodle food rescue app", "Caboodle food donation platform"],                              "Retail Tech: Donation"),
    ("Second Harvest Food Rescue App", ["Second Harvest food rescue app", "Second Harvest food donation"],                           "Retail Tech: Donation"),
    ("Fome de Tudo",                   ["Fome de Tudo food app Brazil", "Fome de Tudo food rescue"],                                 "Retail Tech: Donation", "Brazil"),
    ("Hungree App",                    ["Hungree App food donation", "Hungree food rescue app"],                                     "Retail Tech: Donation"),
    ("Sharing Excess",                 ["Sharing Excess food rescue", "Sharing Excess food donation"],                               "Retail Tech: Donation"),
    ("BringtheFood",                   ["BringtheFood food donation app", "BringtheFood food rescue"],                               "Retail Tech: Donation"),
    ("Ecibo",                          ["Ecibo food donation app", "Ecibo food rescue technology"],                                  "Retail Tech: Donation"),
    ("BitGood",                        ["BitGood food donation app", "BitGood food rescue"],                                        "Retail Tech: Donation"),
    ("Stasera Offro Io",               ["Stasera Offro Io food app Italy", "Stasera Offro food donation"],                          "Retail Tech: Donation", "Italy"),
    ("OzHarvest Food App",             ["OzHarvest food rescue app", "OzHarvest food donation Australia"],                          "Retail Tech: Donation"),
    ("O Masa Calda",                   ["O Masa Calda food app", "O Masa Calda food rescue"],                                       "Retail Tech: Donation"),
    ("Food Recovery",                  ["Food Recovery app platform", "Food Recovery food rescue tech"],                             "Retail Tech: Donation"),
    # ── Retail Tech ──
    ("Platter",    ["Platter food retail technology", "Platter restaurant food management"],   "Retail Tech"),
    ("Restoke",    ["Restoke restaurant inventory management", "Restoke food waste retail"],   "Retail Tech"),
    ("Fresho",     ["Fresho food ordering platform wholesale", "Fresho fresh food supply tech"], "Retail Tech"),
    ("FoodTracks", ["FoodTracks food retail analytics", "FoodTracks food waste retail"],       "Retail Tech"),
    ("Foodwise",   ["Foodwise food waste retail", "Foodwise food management platform"],        "Retail Tech"),
    ("Martee ai",  ["Martee AI food retail technology", "Martee food waste AI"],               "Retail Tech"),
    ("LinkRetail", ["LinkRetail food waste technology", "LinkRetail retail food platform"],    "Retail Tech"),
    # ── E-commerce ──
    ("Best Before Store",         ["Best Before Store surplus food", "Best Before short dated food shop"],                   "E-commerce"),
    ("Leckerposten",              ["Leckerposten food discount Germany", "Leckerposten surplus food"],                       "E-commerce"),
    ("Lebensmittel-sonderposten", ["Lebensmittel-sonderposten surplus food", "Lebensmittel sonderposten Germany food"],     "E-commerce"),
    ("Optifood",                  ["Optifood food ecommerce surplus", "Optifood online food shop"],                         "E-commerce"),
    ("Misfits Garden",            ["Misfits Garden food imperfect produce", "Misfits Garden food waste"],                   "E-commerce"),
    ("Wonky Box",                 ["Wonky Box imperfect produce food", "Wonky Box food waste delivery"],                    "E-commerce"),
    ("Circlr",                    ["Circlr food waste ecommerce", "Circlr surplus food online shop"],                       "E-commerce"),
    ("Veggiebox",                 ["Veggiebox food delivery surplus", "Veggiebox vegetable box"],                           "E-commerce"),
    ("Bella Dentro",              ["Bella Dentro imperfect produce food", "Bella Dentro food waste"],                       "E-commerce"),
    ("Equal Food",                ["Equal Food surplus imperfect produce", "Equal Food food waste ecommerce"],               "E-commerce"),
    ("Veggie Specials",           ["Veggie Specials surplus food", "Veggie Specials vegetables discount"],                  "E-commerce"),
    ("Ruben Retter",              ["Ruben Retter food surplus", "Ruben Retter food waste"],                                 "E-commerce"),
    ("Foodpass",                  ["Foodpass food subscription surplus", "Foodpass food ecommerce"],                        "E-commerce"),
    ("SuperOpa",                  ["SuperOpa food surplus discount", "SuperOpa food waste ecommerce"],                      "E-commerce"),
    ("Gooxxy",                    ["Gooxxy food surplus ecommerce", "Gooxxy food waste online"],                            "E-commerce"),
    ("Uglyfruits",                ["Uglyfruits imperfect produce delivery", "Uglyfruits food waste ecommerce"],             "E-commerce"),
    ("Querfeld",                  ["Querfeld food surplus Germany", "Querfeld imperfect produce"],                          "E-commerce"),
    ("LEROMA",                    ["LEROMA food surplus ecommerce", "LEROMA food waste"],                                   "E-commerce"),
    ("Wonky Veg Boxes",           ["Wonky Veg Boxes imperfect produce", "Wonky Veg food waste delivery"],                   "E-commerce"),
    ("Coupang",                   ["Coupang fresh food ecommerce", "Coupang food delivery Korea"],                          "E-commerce",        "South Korea"),
]

COMPETITORS = {name: queries for name, queries, *_ in _COMPETITOR_DATA}
COMPETITOR_CATEGORIES = {name: cat for name, _, cat, *_ in _COMPETITOR_DATA}
COMPETITOR_COUNTRIES = {name: rest[0] for name, _, _, *rest in _COMPETITOR_DATA if rest}

# Category colors — new competitors use these; original 7 keep distinct colors via CARD_COLORS
CATEGORY_COLORS = {
    "B2C Marketplaces":           "#2563eb",
    "E-commerce":                 "#7c3aed",
    "Other Surplus Optimisation": "#059669",
    "Retail Tech":                "#0891b2",
    "Retail Tech: Donation":      "#d97706",
}

# Original 7 keep their distinct brand colors
CARD_COLORS = {
    "Olio":           "#2d7a4f",
    "Flashfood":      "#1d5fa8",
    "Karma":          "#b45309",
    "Phenix":         "#6d28d9",
    "ResQ Club":      "#b91c1c",
    "Wasteless":      "#0e7490",
    "Too Good To Go": "#00615f",
}

DATA_FILE = Path("docs/data.json")
INDEX_FILE = Path("docs/index.html")
ISSUE_DIR = Path("docs/issues")

MAX_ARTICLES = 2000
ARTICLES_ON_INDEX = 60
ARTICLE_RETENTION_DAYS = 183
FETCH_WORKERS = 12

SEND_EMAIL = os.environ.get("SEND_EMAIL", "false").lower() == "true"
EMAIL_FROM = os.environ.get("EMAIL_FROM", "")
EMAIL_TO = os.environ.get("EMAIL_TO", "")
SMTP_HOST = os.environ.get("SMTP_HOST") or "smtp.gmail.com"
SMTP_PORT = int(os.environ.get("SMTP_PORT") or "587")
SMTP_USER = os.environ.get("SMTP_USER", "")
SMTP_PASS = os.environ.get("SMTP_PASS", "")

# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_rss(query: str) -> list[dict]:
    """Fetch Google News RSS for a query string, with retry and backoff."""
    encoded = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded}&hl=en-US&gl=US&ceid=US:en"
    headers = {"User-Agent": "Mozilla/5.0 (compatible; NewsBot/1.0)"}
    req = urllib.request.Request(url, headers=headers)

    for attempt in range(3):
        if attempt > 0:
            wait = 2 ** attempt  # 2s, then 4s
            print(f"  ↺ Retry {attempt}/2 for '{query}' (waiting {wait}s)")
            time.sleep(wait)
        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                tree = ET.parse(resp)
                root = tree.getroot()
                channel = root.find("channel")
                if channel is None:
                    return []
                articles = []
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
                return articles
        except (urllib.error.URLError, ET.ParseError) as e:
            print(f"  ⚠ Attempt {attempt + 1}/3 failed for '{query}': {e}")
        except Exception as e:
            print(f"  ⚠ Unexpected error for '{query}': {e}")
    return []


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
    return "United States"


def country_flag(country: str) -> str:
    return _FLAG.get(country, "🌐")


def competitor_color(name: str) -> str:
    if name in CARD_COLORS:
        return CARD_COLORS[name]
    cat = COMPETITOR_CATEGORIES.get(name, "")
    return CATEGORY_COLORS.get(cat, "#666")


def competitor_category(name: str) -> str:
    return COMPETITOR_CATEGORIES.get(name, "")


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
        try:
            return json.loads(DATA_FILE.read_text())
        except (UnicodeDecodeError, json.JSONDecodeError) as e:
            print(f"⚠ data.json corrupted ({e}), starting fresh")
    return {"seen_ids": [], "articles": []}


def save_data(data: dict):
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    DATA_FILE.write_text(json.dumps(data, indent=2))


def fetch_all() -> list[dict]:
    """Fetch all competitors in parallel, return deduplicated new articles."""
    data = load_data()
    seen = set(data["seen_ids"])

    # Backfill category for existing articles that predate this field
    for a in data.get("articles", []):
        if not a.get("category"):
            a["category"] = competitor_category(a.get("competitor", ""))

    # Build flat list of (competitor_name, query) work items
    work = [(comp, query) for comp, queries in COMPETITORS.items() for query in queries]

    new_articles: list[dict] = []
    lock = threading.Lock()

    def fetch_one(comp: str, query: str) -> None:
        articles = fetch_rss(query)
        with lock:
            for a in articles:
                aid = article_id(a)
                if aid not in seen:
                    seen.add(aid)
                    a["competitor"] = comp
                    a["category"] = competitor_category(comp)
                    a["country"] = COMPETITOR_COUNTRIES.get(comp) or detect_country(a["link"])
                    a["id"] = aid
                    a["fetched_at"] = datetime.now(timezone.utc).isoformat()
                    new_articles.append(a)
                    print(f"  + [{comp}] {a['title'][:70]}")

    print(f"Fetching {len(work)} queries across {len(COMPETITORS)} competitors (parallel, max {FETCH_WORKERS} workers)…")
    with concurrent.futures.ThreadPoolExecutor(max_workers=FETCH_WORKERS) as executor:
        futures = [executor.submit(fetch_one, comp, query) for comp, query in work]

    # Log any unexpected exceptions from workers (fetch_rss handles most internally)
    for f in futures:
        if f.exception():
            print(f"  ⚠ Worker exception: {f.exception()}")

    # Persist — sort by pub_date desc, drop >retention days old, cap at MAX_ARTICLES
    cutoff = datetime.now(timezone.utc) - timedelta(days=ARTICLE_RETENTION_DAYS)
    all_articles = new_articles + data.get("articles", [])
    all_articles.sort(key=pub_date_key, reverse=True)
    all_articles = [a for a in all_articles if pub_date_key(a) >= cutoff]
    all_articles = all_articles[:MAX_ARTICLES]
    kept_ids = {a["id"] for a in all_articles}
    data["seen_ids"] = list(seen & kept_ids)
    data["articles"] = all_articles
    save_data(data)

    return new_articles


# ── HTML Generation ───────────────────────────────────────────────────────────

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

  /* ── Focus ── */
  :focus-visible {
    outline: 2px solid var(--accent);
    outline-offset: 2px;
    border-radius: 4px;
  }

  /* ── Reduced motion ── */
  @media (prefers-reduced-motion: reduce) {
    *, *::before, *::after { transition-duration: 0.01ms !important; }
  }

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
  .topbar-icon {
    width: 30px; height: 30px;
    background: #ffffff;
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
    font-size: 16px;
    line-height: 1;
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
    font-size: 1.625rem;
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
  @media (max-width: 1024px) { .layout { grid-template-columns: 1fr 220px; } }
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
    padding: 0.875rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    align-items: center;
    justify-content: space-between;
    background: #faf8f6;
  }
  .section-header h2 {
    font-size: 0.75rem;
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
    padding: 0.625rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: 0.4rem;
    background: #faf8f6;
  }
  .filter-label {
    font-size: 0.7rem;
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
    transition: background-color 0.18s ease, border-color 0.18s ease, color 0.18s ease;
  }
  .filter-btn:hover {
    border-color: var(--accent-mid);
    color: var(--accent);
    background: var(--accent-light);
  }
  .filter-btn.active {
    background: var(--accent);
    border-color: var(--accent);
    color: #ffffff;
    font-weight: 600;
  }

  /* ── Competitor dropdown ── */
  .competitor-select {
    background: var(--surface);
    border: 1.5px solid var(--border);
    color: var(--text);
    padding: 0.3rem 2.25rem 0.3rem 0.85rem;
    border-radius: 120px;
    font-size: 0.72rem;
    font-weight: 500;
    cursor: pointer;
    font-family: inherit;
    appearance: none;
    -webkit-appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 20 20' fill='%236b7280'%3E%3Cpath fill-rule='evenodd' d='M5.293 7.293a1 1 0 011.414 0L10 10.586l3.293-3.293a1 1 0 111.414 1.414l-4 4a1 1 0 01-1.414 0l-4-4a1 1 0 010-1.414z' clip-rule='evenodd'/%3E%3C/svg%3E");
    background-repeat: no-repeat;
    background-position: right 0.65rem center;
    background-size: 0.75rem;
    transition: border-color 0.18s ease;
    max-width: 260px;
  }
  .competitor-select:hover { border-color: var(--accent-mid); }
  .competitor-select:focus { outline: 2px solid var(--accent); outline-offset: 2px; }

  /* ── Article rows ── */
  .article-list { display: flex; flex-direction: column; }
  .article-row {
    padding: 1rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    gap: 0.875rem;
    align-items: flex-start;
    transition: background-color 0.15s ease;
  }
  .article-row:last-child { border-bottom: none; }
  .article-row:hover { background: var(--accent-light); }
  .article-accent {
    width: 4px;
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
    font-size: 0.9375rem;
    font-weight: 700;
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
    padding: 0.875rem 1.25rem;
    border-bottom: 1px solid var(--border);
    display: flex;
    justify-content: space-between;
    align-items: center;
    text-decoration: none;
    color: var(--text);
    font-size: 0.8rem;
    font-weight: 600;
    transition: background-color 0.15s ease, color 0.15s ease;
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
    padding: 2.5rem 1.25rem;
    text-align: center;
    color: var(--muted);
    font-size: 0.8rem;
    line-height: 1.6;
  }
  .empty-icon { font-size: 1.5rem; margin-bottom: 0.5rem; }
"""


def render_article_row(a: dict) -> str:
    color = competitor_color(a["competitor"])
    pub = html.escape(a.get("pub_date", "")[:16])
    safe_link = html.escape(a["link"], quote=True)
    c = a.get("country", "United States")
    flag = country_flag(c)
    safe_competitor = html.escape(a["competitor"], quote=True)
    safe_country = html.escape(c, quote=True)
    cat = a.get("category") or competitor_category(a["competitor"])
    safe_category = html.escape(cat, quote=True)
    return f"""
    <div class="article-row" data-competitor="{safe_competitor}" data-country="{safe_country}" data-category="{safe_category}">
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


def _category_btns() -> str:
    return "".join(
        f'<button class="filter-btn" data-type="category" data-filter="{html.escape(cat, quote=True)}">{html.escape(cat)}</button>'
        for cat in CATEGORY_COLORS
    )


def _country_select(articles: list[dict]) -> str:
    present = sorted({a.get("country", "United States") for a in articles})
    options = ['<option value="">All countries</option>']
    for c in present:
        options.append(f'<option value="{html.escape(c, quote=True)}">{country_flag(c)} {html.escape(c)}</option>')
    return f'<select id="country-select" class="competitor-select">{"".join(options)}</select>'


def _competitor_select() -> str:
    from collections import defaultdict
    by_cat: dict[str, list[str]] = defaultdict(list)
    for name in COMPETITORS:
        cat = COMPETITOR_CATEGORIES.get(name, "Other")
        by_cat[cat].append(name)

    parts = ['<select id="competitor-select" class="competitor-select">',
             '<option value="">All competitors</option>']
    for cat in CATEGORY_COLORS:
        names = sorted(by_cat.get(cat, []))
        if names:
            parts.append(f'<optgroup label="{html.escape(cat)}">')
            for name in names:
                parts.append(f'<option value="{html.escape(name, quote=True)}">{html.escape(name)}</option>')
            parts.append('</optgroup>')
    parts.append('</select>')
    return "".join(parts)


def _legend() -> str:
    return "".join(
        f'<div class="legend-item"><div class="legend-dot" style="background:{color}"></div>{html.escape(cat)}</div>'
        for cat, color in CATEGORY_COLORS.items()
    )


_FILTER_JS = """
  function applyFilters() {
    const ac = [...document.querySelectorAll('.filter-btn[data-type="category"].active')].map(b => b.dataset.filter);
    const countrySel = document.getElementById('country-select');
    const country = countrySel ? countrySel.value : '';
    const compSel = document.getElementById('competitor-select');
    const comp = compSel ? compSel.value : '';
    document.querySelectorAll('.article-row').forEach(row => {
      const mc = ac.length === 0 || ac.includes(row.dataset.category);
      const mk = country === '' || row.dataset.country === country;
      const mcomp = comp === '' || row.dataset.competitor === comp;
      row.style.display = (mc && mk && mcomp) ? '' : 'none';
    });
  }
  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => { btn.classList.toggle('active'); applyFilters(); });
  });
  document.querySelectorAll('#competitor-select, #country-select').forEach(s => {
    s.addEventListener('change', applyFilters);
  });
"""


def render_page(articles: list[dict], title: str, back_link: bool = False) -> str:
    rows = "\n".join(render_article_row(a) for a in articles)
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
    count = len(articles)
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
      <div class="topbar-icon">♻</div>
      <span class="topbar-name">Too Good To Go</span>
    </div>
    <div class="topbar-divider"></div>
    <span class="topbar-section">Competitive Intelligence</span>
  </nav>
  <header class="page-header" style="max-width:820px">
    <div>
      {back}
      <h1 style="margin-top:0.4rem">{html.escape(title)}</h1>
    </div>
    <span class="meta">{count} articles · {now}</span>
  </header>
  <main class="layout" style="display:block;max-width:820px;margin:0 auto;padding:0 2rem 3rem">
    <div class="section-card">
      <div class="section-header">
        <h2>Articles</h2>
        <span class="section-count">{count}</span>
      </div>
      <div class="legend">{_legend()}</div>
      <div class="filter-bar"><span class="filter-label">Category</span>{_category_btns()}</div>
      <div class="filter-bar"><span class="filter-label">Competitor</span>{_competitor_select()}</div>
      <div class="filter-bar"><span class="filter-label">Country</span>{_country_select(articles)}</div>
      {"<div class='article-list'>" + rows + "</div>" if articles else "<div class='empty'>No articles for this period.</div>"}
    </div>
  </main>
  <script>{_FILTER_JS}</script>
</body>
</html>"""


def build_index(all_articles: list[dict], issue_dates: list[str]):
    """Build the main archive index page."""
    recent = all_articles[:ARTICLES_ON_INDEX]
    rows = "\n".join(render_article_row(a) for a in recent)
    now = datetime.now(timezone.utc).strftime("%B %d, %Y")
    total = len(all_articles)

    issue_rows = ""
    for d in sorted(issue_dates, reverse=True)[:12]:
        display = datetime.strptime(d, "%Y-%m-%d").strftime("%B %d, %Y")
        issue_rows += f'<a class="issue-row" href="issues/{d}.html">Week of {display}<span class="issue-arrow">→</span></a>\n'

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
      <div class="topbar-icon">♻</div>
      <span class="topbar-name">Too Good To Go</span>
    </div>
    <div class="topbar-divider"></div>
    <span class="topbar-section">Competitive Intelligence</span>
  </nav>
  <header class="page-header">
    <h1>Competitor News Tracker</h1>
    <span class="meta">{total} articles tracked · Updated {now}</span>
  </header>
  <main class="layout">
    <section>
      <div class="section-card">
        <div class="section-header">
          <h2>Recent Articles</h2>
          <span class="section-count">{len(recent)} most recent · {total} total</span>
        </div>
        <div class="legend">{_legend()}</div>
        <div class="filter-bar"><span class="filter-label">Category</span>{_category_btns()}</div>
        <div class="filter-bar"><span class="filter-label">Competitor</span>{_competitor_select()}</div>
        <div class="filter-bar"><span class="filter-label">Country</span>{_country_select(recent)}</div>
        {"<div class='article-list'>" + rows + "</div>" if recent else "<div class='empty'>No articles yet. Run the scraper to populate.</div>"}
      </div>
    </section>
    <aside>
      <div class="section-card">
        <div class="section-header">
          <h2>Weekly Issues</h2>
        </div>
        {"<div class='issue-list'>" + issue_rows + "</div>" if issue_rows else "<div class='empty'><div class='empty-icon'>📋</div>Weekly digests appear here every Monday.</div>"}
      </div>
    </aside>
  </main>
  <script>{_FILTER_JS}</script>
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
          <td style="padding:12px 20px 12px 17px;border-bottom:1px solid #dee3e3;
                     vertical-align:top;border-left:3px solid {color};">
            <span style="display:inline-block;background:{color};color:#ffffff;font-size:10px;
              font-weight:700;padding:2px 8px;border-radius:120px;letter-spacing:0.04em;
              text-transform:uppercase;margin-bottom:6px;">{html.escape(a['competitor'])}</span><br>
            <a href="{safe_link}" style="color:#00615f;font-size:14px;font-weight:700;
              text-decoration:none;line-height:1.4;">{html.escape(a['title'])}</a><br>
            <span style="color:#6b7280;font-size:11px;">
              {html.escape(a['source'])} · {html.escape(a.get('pub_date', '')[:16])}
            </span>
          </td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html><head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
</head>
<body style="margin:0;padding:0;background:#f9f3f0;font-family:'Helvetica Neue',Arial,sans-serif;color:#222222;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#f9f3f0;padding:40px 20px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0"
             style="max-width:600px;width:100%;background:#ffffff;border-radius:12px;
                    overflow:hidden;border:1px solid #dee3e3;">
        <tr><td style="background:#00615f;padding:20px 24px;">
          <p style="margin:0 0 4px;font-size:10px;color:rgba(255,255,255,0.7);
                    letter-spacing:0.12em;text-transform:uppercase;">
            Too Good To Go · Competitive Intelligence
          </p>
          <h1 style="margin:0;font-size:22px;font-weight:700;color:#ffffff;line-height:1.2;">
            Weekly Roundup · <span style="opacity:0.75;font-weight:400;">{week_str}</span>
          </h1>
          <p style="margin:8px 0 0;font-size:12px;color:rgba(255,255,255,0.7);">
            {len(articles)} new articles this week
          </p>
        </td></tr>
        <tr><td style="padding:0 0 8px;">
          <table width="100%" cellpadding="0" cellspacing="0">
            {rows if rows else '<tr><td style="padding:24px;color:#6b7280;font-size:13px;">No new articles this week.</td></tr>'}
          </table>
        </td></tr>
        <tr><td style="padding:14px 24px;border-top:1px solid #dee3e3;background:#faf8f6;">
          <p style="margin:0;font-size:11px;color:#6b7280;">
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
    print(f"Tracking {len(COMPETITORS)} competitors across {len(CATEGORY_COLORS)} categories\n")

    new_articles = fetch_all()
    print(f"\n✓ {len(new_articles)} new articles fetched")

    data = load_data()
    all_articles = data["articles"]

    ISSUE_DIR.mkdir(parents=True, exist_ok=True)
    issue_dates = [f.stem for f in ISSUE_DIR.glob("*.html")]

    if mode == "weekly":
        today = datetime.now(timezone.utc)
        week_start = (today - timedelta(days=today.weekday())).strftime("%Y-%m-%d")

        cutoff = (today - timedelta(days=7)).isoformat()
        weekly_articles = sorted(
            [a for a in all_articles if a.get("fetched_at", "") >= cutoff],
            key=pub_date_key, reverse=True,
        )

        build_issue_page(weekly_articles, week_start)
        issue_dates.append(week_start)

        if SEND_EMAIL:
            send_weekly_email(weekly_articles)

    build_index(all_articles, issue_dates)
    print("\n── Done ──\n")


if __name__ == "__main__":
    main()
