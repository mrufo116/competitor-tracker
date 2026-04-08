# Reliability & Performance Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Harden `scripts/fetch_news.py` against runtime failures and cut the 240-request fetch time from ~1 hour worst-case to under 5 minutes.

**Architecture:** All changes are contained in `scripts/fetch_news.py`. No new files. Six targeted edits: extract constants, collapse the two competitor dicts into one source, guard JSON load, add per-request retry + throttle, parallelize fetching with ThreadPoolExecutor, and update the email template to match the TGTG dashboard brand.

**Tech Stack:** Python 3.11 stdlib only — `concurrent.futures`, `threading`, `time` (all already available)

---

### Task 1: Extract magic numbers as named constants

**Files:**
- Modify: `scripts/fetch_news.py:307-317` (Config section) and lines 467, 471, 938

- [ ] **Step 1: Add constants to the Config section**

  After the `DATA_FILE / INDEX_FILE / ISSUE_DIR` lines (around line 307), add:

  ```python
  MAX_ARTICLES = 2000
  ARTICLES_ON_INDEX = 60
  ARTICLE_RETENTION_DAYS = 183
  ```

- [ ] **Step 2: Replace magic numbers in `fetch_all()`**

  Change:
  ```python
  cutoff_6mo = datetime.now(timezone.utc) - timedelta(days=183)
  all_articles = new_articles + data.get("articles", [])
  all_articles.sort(key=pub_date_key, reverse=True)
  all_articles = [a for a in all_articles if pub_date_key(a) >= cutoff_6mo]
  all_articles = all_articles[:2000]
  ```
  To:
  ```python
  cutoff = datetime.now(timezone.utc) - timedelta(days=ARTICLE_RETENTION_DAYS)
  all_articles = new_articles + data.get("articles", [])
  all_articles.sort(key=pub_date_key, reverse=True)
  all_articles = [a for a in all_articles if pub_date_key(a) >= cutoff]
  all_articles = all_articles[:MAX_ARTICLES]
  ```

- [ ] **Step 3: Replace magic number in `build_index()`**

  Change:
  ```python
  recent = all_articles[:60]
  ```
  To:
  ```python
  recent = all_articles[:ARTICLES_ON_INDEX]
  ```

- [ ] **Step 4: Verify the script still runs**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  python scripts/fetch_news.py --help 2>&1 || python -c "import scripts.fetch_news" 2>&1 || python -c "
  import sys; sys.path.insert(0,'scripts')
  import importlib.util, pathlib
  spec = importlib.util.spec_from_file_location('fn', 'scripts/fetch_news.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  assert mod.MAX_ARTICLES == 2000
  assert mod.ARTICLES_ON_INDEX == 60
  assert mod.ARTICLE_RETENTION_DAYS == 183
  print('constants OK')
  "
  ```
  Expected: `constants OK`

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/fetch_news.py
  git commit -m "refactor: extract MAX_ARTICLES, ARTICLES_ON_INDEX, ARTICLE_RETENTION_DAYS constants"
  ```

---

### Task 2: Single source of truth for competitor data

**Files:**
- Modify: `scripts/fetch_news.py:24-285` (replace `COMPETITORS` + `COMPETITOR_CATEGORIES` dicts)

The two dicts currently list the same 120 competitor names twice. Adding a competitor requires editing both. This task replaces them with a single `_COMPETITOR_DATA` list of `(name, queries, category)` tuples, then derives both dicts from it.

- [ ] **Step 1: Replace the two dicts with a single tuple list**

  Delete the entire `COMPETITORS = { ... }` block (lines 24–156) and `COMPETITOR_CATEGORIES = { ... }` block (lines 158–285) and replace with:

  ```python
  # Single source of truth: (name, [search queries], category)
  _COMPETITOR_DATA: list[tuple[str, list[str], str]] = [
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
      ("Toriniko",          ["Toriniko food app", "Toriniko food waste Japan"],                                   "B2C Marketplaces"),
      ("Still Good",        ["Still Good food surplus app", "Still Good food waste marketplace"],                 "B2C Marketplaces"),
      ("Gone Good",         ["Gone Good food surplus app", "Gone Good food waste"],                               "B2C Marketplaces"),
      ("Platable",          ["Platable food surplus app", "Platable food marketplace"],                           "B2C Marketplaces"),
      ("Foodbag",           ["Foodbag food surplus app", "Foodbag food delivery waste"],                          "B2C Marketplaces"),
      ("Leftovers",         ["Leftovers food surplus app", "Leftovers food waste marketplace"],                   "B2C Marketplaces"),
      ("Hallowa",           ["Hallowa food app Korea", "Hallowa surplus food"],                                   "B2C Marketplaces"),
      ("Lucky Meal",        ["Lucky Meal food app surplus", "Lucky Meal food waste Korea"],                       "B2C Marketplaces"),
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
      ("Fome de Tudo",                   ["Fome de Tudo food app Brazil", "Fome de Tudo food rescue"],                                 "Retail Tech: Donation"),
      ("Hungree App",                    ["Hungree App food donation", "Hungree food rescue app"],                                     "Retail Tech: Donation"),
      ("Sharing Excess",                 ["Sharing Excess food rescue", "Sharing Excess food donation"],                               "Retail Tech: Donation"),
      ("BringtheFood",                   ["BringtheFood food donation app", "BringtheFood food rescue"],                               "Retail Tech: Donation"),
      ("Ecibo",                          ["Ecibo food donation app", "Ecibo food rescue technology"],                                  "Retail Tech: Donation"),
      ("BitGood",                        ["BitGood food donation app", "BitGood food rescue"],                                        "Retail Tech: Donation"),
      ("Stasera Offro Io",               ["Stasera Offro Io food app Italy", "Stasera Offro food donation"],                          "Retail Tech: Donation"),
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
      ("Coupang",                   ["Coupang fresh food ecommerce", "Coupang food delivery Korea"],                          "E-commerce"),
  ]

  COMPETITORS = {name: queries for name, queries, _ in _COMPETITOR_DATA}
  COMPETITOR_CATEGORIES = {name: cat for name, _, cat in _COMPETITOR_DATA}
  ```

- [ ] **Step 2: Verify counts match original**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  python -c "
  import importlib.util
  spec = importlib.util.spec_from_file_location('fn', 'scripts/fetch_news.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  assert len(mod.COMPETITORS) == 120, f'Expected 120, got {len(mod.COMPETITORS)}'
  assert len(mod.COMPETITOR_CATEGORIES) == 120, f'Expected 120, got {len(mod.COMPETITOR_CATEGORIES)}'
  assert set(mod.COMPETITORS.keys()) == set(mod.COMPETITOR_CATEGORIES.keys()), 'Keys out of sync'
  print(f'OK — {len(mod.COMPETITORS)} competitors, all categorised')
  "
  ```
  Expected: `OK — 120 competitors, all categorised`

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/fetch_news.py
  git commit -m "refactor: consolidate COMPETITORS and COMPETITOR_CATEGORIES into single _COMPETITOR_DATA list"
  ```

---

### Task 3: Guard against corrupted data.json

**Files:**
- Modify: `scripts/fetch_news.py` — `load_data()` function (~line 427)

- [ ] **Step 1: Add try/except around JSON parse in `load_data()`**

  Change:
  ```python
  def load_data() -> dict:
      if DATA_FILE.exists():
          return json.loads(DATA_FILE.read_text())
      return {"seen_ids": [], "articles": []}
  ```
  To:
  ```python
  def load_data() -> dict:
      if DATA_FILE.exists():
          try:
              return json.loads(DATA_FILE.read_text())
          except (json.JSONDecodeError, ValueError) as e:
              print(f"⚠ data.json corrupted ({e}), starting fresh")
      return {"seen_ids": [], "articles": []}
  ```

- [ ] **Step 2: Verify corrupted JSON is handled gracefully**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  python -c "
  import importlib.util, pathlib, json

  spec = importlib.util.spec_from_file_location('fn', 'scripts/fetch_news.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)

  # Temporarily write bad JSON
  backup = mod.DATA_FILE.read_text()
  mod.DATA_FILE.write_text('{bad json')
  result = mod.load_data()
  mod.DATA_FILE.write_text(backup)  # restore

  assert result == {'seen_ids': [], 'articles': []}, f'Got: {result}'
  print('OK — corrupted JSON returns empty structure')
  "
  ```
  Expected: `OK — corrupted JSON returns empty structure` (with a warning line before it)

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/fetch_news.py
  git commit -m "fix: guard load_data() against corrupted data.json"
  ```

---

### Task 4: Add retry + throttle to fetch_rss()

**Files:**
- Modify: `scripts/fetch_news.py` — imports and `fetch_rss()` function (~line 321)

- [ ] **Step 1: Add `import time` to imports**

  Find the imports block at the top of the file and add `import time` after `import urllib.parse`:

  ```python
  import time
  ```

- [ ] **Step 2: Replace `fetch_rss()` with retry + throttle version**

  Replace the entire `fetch_rss()` function with:

  ```python
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
      return []
  ```

  Note: `urllib.error` is already available via `urllib.request` — no extra import needed.

- [ ] **Step 3: Verify the function is importable (syntax check)**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  python -c "
  import importlib.util
  spec = importlib.util.spec_from_file_location('fn', 'scripts/fetch_news.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  import inspect
  src = inspect.getsource(mod.fetch_rss)
  assert 'for attempt in range(3)' in src
  assert 'URLError' in src
  print('OK — fetch_rss has retry logic')
  "
  ```
  Expected: `OK — fetch_rss has retry logic`

- [ ] **Step 4: Commit**

  ```bash
  git add scripts/fetch_news.py
  git commit -m "fix: add 3-attempt retry with exponential backoff to fetch_rss()"
  ```

---

### Task 5: Parallelize RSS fetching with ThreadPoolExecutor

**Files:**
- Modify: `scripts/fetch_news.py` — imports and `fetch_all()` function (~line 438)

- [ ] **Step 1: Add `concurrent.futures` and `threading` to imports**

  Add to the imports block:
  ```python
  import concurrent.futures
  import threading
  ```

- [ ] **Step 2: Replace the sequential fetch loop in `fetch_all()` with ThreadPoolExecutor**

  Replace the entire `fetch_all()` function body with:

  ```python
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
                      a["country"] = detect_country(a["link"])
                      a["id"] = aid
                      a["fetched_at"] = datetime.now(timezone.utc).isoformat()
                      new_articles.append(a)
                      print(f"  + [{comp}] {a['title'][:70]}")

      print(f"Fetching {len(work)} queries across {len(COMPETITORS)} competitors (parallel, max 12 workers)…")
      with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
          futures = [executor.submit(fetch_one, comp, query) for comp, query in work]
          concurrent.futures.wait(futures)

      # Re-raise any unexpected exceptions from workers
      for f in futures:
          if f.exception():
              print(f"  ⚠ Worker exception: {f.exception()}")

      # Persist — sort by pub_date desc, drop >6 months old, cap at MAX_ARTICLES
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
  ```

- [ ] **Step 3: Verify the function is importable and uses ThreadPoolExecutor**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  python -c "
  import importlib.util, inspect
  spec = importlib.util.spec_from_file_location('fn', 'scripts/fetch_news.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  src = inspect.getsource(mod.fetch_all)
  assert 'ThreadPoolExecutor' in src, 'Missing ThreadPoolExecutor'
  assert 'threading.Lock' in src, 'Missing lock'
  print('OK — fetch_all uses ThreadPoolExecutor with lock')
  "
  ```
  Expected: `OK — fetch_all uses ThreadPoolExecutor with lock`

- [ ] **Step 4: Commit**

  ```bash
  git add scripts/fetch_news.py
  git commit -m "perf: parallelize RSS fetching with ThreadPoolExecutor (12 workers)"
  ```

---

### Task 6: Update email template to TGTG brand

**Files:**
- Modify: `scripts/fetch_news.py` — `build_email_html()` function (~line 1014)

The current email uses a dark/neon theme (`#0a0a0a` background, `#c8f550` links). This task replaces it with the cream/teal TGTG brand used on the dashboard.

- [ ] **Step 1: Replace `build_email_html()` with branded version**

  Replace the entire `build_email_html()` function with:

  ```python
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
  <html><head><meta charset="UTF-8"></head>
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
  ```

- [ ] **Step 2: Verify no dark-theme colors remain in the function**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  python -c "
  import importlib.util, inspect
  spec = importlib.util.spec_from_file_location('fn', 'scripts/fetch_news.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)
  src = inspect.getsource(mod.build_email_html)
  dark_colors = ['#0a0a0a', '#c8f550', '#1e1e1e', 'background:#000']
  found = [c for c in dark_colors if c in src]
  assert not found, f'Dark colors still present: {found}'
  assert '#00615f' in src, 'TGTG teal missing'
  assert '#f9f3f0' in src, 'TGTG cream background missing'
  print('OK — email uses TGTG brand colors')
  "
  ```
  Expected: `OK — email uses TGTG brand colors`

- [ ] **Step 3: Commit**

  ```bash
  git add scripts/fetch_news.py
  git commit -m "fix: update email template to match TGTG cream/teal brand"
  ```

---

### Task 7: Final smoke test + push

- [ ] **Step 1: Run a full import and sanity check**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  python -c "
  import importlib.util
  spec = importlib.util.spec_from_file_location('fn', 'scripts/fetch_news.py')
  mod = importlib.util.module_from_spec(spec)
  spec.loader.exec_module(mod)

  # Counts
  assert len(mod.COMPETITORS) == 120
  assert len(mod.COMPETITOR_CATEGORIES) == 120
  assert set(mod.COMPETITORS.keys()) == set(mod.COMPETITOR_CATEGORIES.keys())

  # Constants
  assert mod.MAX_ARTICLES == 2000
  assert mod.ARTICLES_ON_INDEX == 60
  assert mod.ARTICLE_RETENTION_DAYS == 183

  # detect_country
  assert mod.detect_country('https://www.bbc.co.uk/article') == 'United Kingdom'
  assert mod.detect_country('https://www.lemonde.fr/article') == 'France'
  assert mod.detect_country('https://techcrunch.com/article') == 'United States'

  # competitor_color
  assert mod.competitor_color('Too Good To Go') == '#00615f'
  assert mod.competitor_color('Coupang') == '#7c3aed'  # E-commerce category color

  # load_data with corrupted file
  backup = mod.DATA_FILE.read_text()
  mod.DATA_FILE.write_text('{bad}')
  result = mod.load_data()
  mod.DATA_FILE.write_text(backup)
  assert result == {'seen_ids': [], 'articles': []}

  print('All checks passed.')
  "
  ```
  Expected: `All checks passed.`

- [ ] **Step 2: Push to GitHub**

  ```bash
  cd /Users/mrufo/claude-projects/competitor-tracker
  git push origin main
  ```

- [ ] **Step 3: Trigger a manual workflow run to verify live**

  ```bash
  gh workflow run tracker.yml --field mode=daily --repo mrufo116/competitor-tracker
  ```
  Then watch: `gh run list --repo mrufo116/competitor-tracker --limit 3`
