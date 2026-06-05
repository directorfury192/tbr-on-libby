#!/usr/bin/env python3
"""
StoryGraph → Libby TBR Sync
────────────────────────────
Reads your StoryGraph CSV export, checks each book against your library's
OverDrive/Libby catalog, and generates a beautiful HTML report you can open
in any browser with clickable borrow / hold links.

USAGE:
    python3 storygraph_libby_sync.py

    On first run it will ask for:
      • Path to your StoryGraph CSV export
      • Your Libby library key  (found in your Libby URL:
        libbyapp.com/library/YOUR_KEY_HERE)

    Results are saved to  tbr_libby_results.html  in the same folder.
    Open that file in your browser — every book links straight to Libby.

HOW TO GET YOUR STORYGRAPH CSV:
    StoryGraph → Account (top-right) → Import & Export → Export your library
    Download the CSV and note the file path.

HOW TO FIND YOUR LIBRARY KEY:
    Open Libby, tap your library name at the top, then "Manage your libraries".
    Or look at your browser URL when browsing Libby:
    https://libbyapp.com/library/alamedacountylibrary  →  key = alamedacountylibrary

REQUIRES:  Python 3.8+  •  requests  (pip install requests)
"""

import csv
import json
import os
import sys
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

try:
    import requests
except ImportError:
    print("❌  'requests' is not installed. Run:  pip install requests")
    sys.exit(1)

# ──────────────────────────────────────────────
#  CONFIG  (edit these or let the script prompt you)
# ──────────────────────────────────────────────

CSV_PATH = ""          # e.g. "/Users/you/Downloads/storygraph_export.csv"
LIBRARY_KEY = ""       # e.g. "alamedacountylibrary"
OUTPUT_FILE = "tbr_libby_results.html"
FORMATS = ["ebook-epub-adobe", "ebook-epub-open", "audiobook-mp3", "audiobook-overdrive"]
REQUEST_DELAY = 0.4    # seconds between API calls — be polite to OverDrive servers


# ──────────────────────────────────────────────
#  STORYGRAPH CSV PARSER
# ──────────────────────────────────────────────

def parse_storygraph_csv(path: str) -> list[dict]:
    """Parse a StoryGraph CSV export and return to-read books."""
    books = []
    path = Path(path).expanduser()

    if not path.exists():
        print(f"❌  File not found: {path}")
        sys.exit(1)

    with open(path, newline="", encoding="utf-8-sig") as f:
        # StoryGraph sometimes uses BOM; utf-8-sig handles that
        reader = csv.DictReader(f)
        headers = [h.strip().lower() for h in (reader.fieldnames or [])]

        # Flexible header matching
        def find_col(patterns):
            for pat in patterns:
                for h in (reader.fieldnames or []):
                    if pat in h.lower():
                        return h
            return None

        title_col  = find_col(["title"])
        author_col = find_col(["author"])
        status_col = find_col(["read status", "read-status", "readstatus", "status"])
        pages_col  = find_col(["pages", "num pages", "page count"])
        genres_col = find_col(["genres", "tags"])
        rating_col = find_col(["star rating", "rating"])
        isbn_col   = find_col(["isbn"])

        for row in reader:
            status = row.get(status_col, "").strip().lower() if status_col else ""
            # Include "to-read" and entries with no status (some exports omit it)
            if status not in ("to-read", "to read", "want to read", "tbr", ""):
                continue

            title  = row.get(title_col, "").strip() if title_col else ""
            author = row.get(author_col, "").strip() if author_col else ""

            if not title:
                continue

            books.append({
                "title":  title,
                "author": author,
                "pages":  row.get(pages_col, "").strip() if pages_col else "",
                "genres": row.get(genres_col, "").strip() if genres_col else "",
                "rating": row.get(rating_col, "").strip() if rating_col else "",
                "isbn":   row.get(isbn_col, "").strip() if isbn_col else "",
            })

    return books


# ──────────────────────────────────────────────
#  OVERDRIVE / LIBBY CATALOG SEARCH
# ──────────────────────────────────────────────

OVERDRIVE_BASE = "https://thunder.api.overdrive.com/v2"

def search_overdrive(library_key: str, title: str, author: str = "", isbn: str = "") -> dict:
    """
    Search the OverDrive Thunder API for a title at a specific library.
    Returns a dict with availability info or None if not found.
    """
    # Build search query — ISBN is most precise when available
    if isbn:
        query = isbn
    else:
        query = f"{title} {author}".strip()

    params = {
        "query": query,
        "perPage": 5,
        "page": 1,
        "format": ",".join(FORMATS),
        "sort": "relevance",
    }

    url = f"{OVERDRIVE_BASE}/libraries/{library_key}/media"

    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; LibraryTBRSync/1.0)",
        "Accept": "application/json",
    }

    try:
        resp = requests.get(url, params=params, headers=headers, timeout=10)
        if resp.status_code == 404:
            return {"error": "library_not_found"}
        if resp.status_code != 200:
            return {"error": f"http_{resp.status_code}"}
        data = resp.json()
    except requests.exceptions.ConnectionError:
        return {"error": "connection_error"}
    except requests.exceptions.Timeout:
        return {"error": "timeout"}
    except (json.JSONDecodeError, ValueError):
        return {"error": "json_error"}

    items = data.get("items", [])
    if not items:
        return {"status": "not_found"}

    # Find the best match — prefer exact title match
    best = None
    title_lower = title.lower()
    for item in items:
        if title_lower in item.get("title", "").lower():
            best = item
            break
    if not best:
        best = items[0]  # take top result

    return extract_availability(best, library_key)


def extract_availability(item: dict, library_key: str) -> dict:
    """Pull availability info out of an OverDrive item record."""
    title  = item.get("title", "Unknown")
    author = ", ".join(a.get("name","") for a in item.get("creators", []))
    cover  = item.get("covers", {}).get("cover300Wide", {}).get("href", "")
    od_id  = item.get("id", "")
    formats_available = [f.get("id","") for f in item.get("formats", [])]

    # Determine primary format label
    fmt_label = "eBook"
    if any("audiobook" in f for f in formats_available):
        fmt_label = "Audiobook" if not any("epub" in f for f in formats_available) else "eBook + Audiobook"

    avail = item.get("availability", {})
    is_available   = avail.get("isAvailable", False)
    owned_copies   = avail.get("copiesOwned", 0)
    avail_copies   = avail.get("copiesAvailable", 0)
    holds_count    = avail.get("numberOfHolds", 0)
    always_avail   = avail.get("isAlwaysAvailable", False)  # Libby "always available" titles

    if always_avail or (is_available and avail_copies > 0):
        status = "available"
    elif owned_copies > 0:
        status = "hold"
    else:
        status = "hold"  # in catalog but 0 copies = request-only

    libby_url = f"https://libbyapp.com/library/{library_key}/search/query-{urllib.parse.quote(title)}/page-1"

    return {
        "status":        status,
        "od_title":      title,
        "od_author":     author,
        "cover":         cover,
        "format":        fmt_label,
        "copies_owned":  owned_copies,
        "copies_avail":  avail_copies,
        "holds":         holds_count,
        "libby_url":     libby_url,
        "od_id":         od_id,
    }


# ──────────────────────────────────────────────
#  MAIN SEARCH LOOP
# ──────────────────────────────────────────────

def check_all_books(books: list[dict], library_key: str) -> list[dict]:
    """Search OverDrive for each TBR book. Returns enriched book list."""
    results = []
    total = len(books)

    print(f"\n🔍  Searching {total} books in your library catalog…\n")

    for i, book in enumerate(books, 1):
        bar_done = int((i / total) * 30)
        bar = "█" * bar_done + "░" * (30 - bar_done)
        print(f"\r[{bar}] {i}/{total}  {book['title'][:45]:<45}", end="", flush=True)

        result = search_overdrive(library_key, book["title"], book["author"], book.get("isbn",""))

        if result.get("error") == "library_not_found":
            print(f"\n\n❌  Library key '{library_key}' not found in OverDrive.")
            print("   Double-check it at: https://libbyapp.com  (look at the URL after selecting your library)")
            sys.exit(1)

        book["libby"] = result
        results.append(book)
        time.sleep(REQUEST_DELAY)

    print(f"\r{'✓ Done!':40}  {total}/{total} books checked.\n")
    return results


# ──────────────────────────────────────────────
#  HTML REPORT GENERATOR
# ──────────────────────────────────────────────

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>My TBR on Libby</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Lora:ital,wght@0,400;0,600;1,400&family=DM+Sans:wght@300;400;500&display=swap" rel="stylesheet">
<style>
  :root {
    --bg: #faf8f4;
    --surface: #ffffff;
    --border: #e8e4dc;
    --text: #1a1814;
    --muted: #706a5e;
    --hint: #a09890;
    --green-bg: #e8f5ec; --green: #2d6b3f;
    --amber-bg: #fef3e2; --amber: #8a5a00;
    --gray-bg: #f0ede8;  --gray: #6b6560;
    --blue-bg: #e8f0fa;  --blue: #2455a0;
    --accent: #c0392b;
  }
  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: 'DM Sans', sans-serif; background: var(--bg); color: var(--text); min-height: 100vh; }

  header {
    background: var(--text);
    color: var(--bg);
    padding: 2.5rem 2rem 2rem;
    position: sticky; top: 0; z-index: 100;
  }
  .header-inner { max-width: 1100px; margin: 0 auto; display: flex; align-items: flex-end; justify-content: space-between; flex-wrap: wrap; gap: 1rem; }
  h1 { font-family: 'Lora', Georgia, serif; font-size: 1.9rem; font-weight: 600; letter-spacing: -0.02em; }
  h1 span { color: #c9b49a; font-style: italic; }
  .header-meta { font-size: 0.8rem; color: #9a9080; text-align: right; line-height: 1.6; }

  .controls {
    background: var(--surface);
    border-bottom: 1px solid var(--border);
    padding: 0.9rem 2rem;
    position: sticky; top: 92px; z-index: 99;
  }
  .controls-inner { max-width: 1100px; margin: 0 auto; display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
  .filter-btn {
    padding: 5px 16px; border-radius: 20px; border: 1px solid var(--border);
    background: var(--bg); cursor: pointer; font-family: inherit;
    font-size: 0.8rem; color: var(--muted); transition: all 0.15s;
  }
  .filter-btn:hover { border-color: var(--text); color: var(--text); }
  .filter-btn.active { background: var(--text); color: var(--bg); border-color: var(--text); }
  .filter-btn .count { opacity: 0.6; margin-left: 4px; }
  #search-box {
    margin-left: auto; padding: 5px 14px; border-radius: 20px;
    border: 1px solid var(--border); background: var(--bg);
    font-family: inherit; font-size: 0.85rem; width: 220px; outline: none;
  }
  #search-box:focus { border-color: var(--text); }

  .stats-bar { max-width: 1100px; margin: 0 auto; padding: 1.5rem 2rem 0; display: flex; gap: 16px; flex-wrap: wrap; }
  .stat-pill {
    display: flex; align-items: center; gap: 8px; padding: 8px 16px;
    border-radius: 8px; font-size: 0.85rem;
  }
  .stat-pill .num { font-size: 1.4rem; font-weight: 500; }
  .stat-pill.avail { background: var(--green-bg); color: var(--green); }
  .stat-pill.hold  { background: var(--amber-bg); color: var(--amber); }
  .stat-pill.none  { background: var(--gray-bg);  color: var(--gray);  }

  main { max-width: 1100px; margin: 0 auto; padding: 1.5rem 2rem 4rem; }

  .book-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(300px, 1fr)); gap: 14px; }

  .book-card {
    background: var(--surface); border: 1px solid var(--border);
    border-radius: 10px; padding: 14px 16px;
    display: flex; gap: 12px; align-items: flex-start;
    transition: box-shadow 0.15s, transform 0.15s;
    animation: fadeIn 0.3s ease both;
  }
  .book-card:hover { box-shadow: 0 4px 16px rgba(0,0,0,0.08); transform: translateY(-1px); }
  .book-card.hidden { display: none; }

  @keyframes fadeIn { from { opacity:0; transform: translateY(6px); } to { opacity:1; transform: translateY(0); } }

  .book-spine {
    width: 42px; height: 58px; border-radius: 4px; flex-shrink: 0;
    display: flex; align-items: center; justify-content: center;
    font-family: 'Lora', serif; font-size: 11px; font-weight: 600;
    letter-spacing: 0.02em; text-align: center; line-height: 1.2;
    overflow: hidden;
  }
  .book-spine img { width: 100%; height: 100%; object-fit: cover; border-radius: 4px; }
  .book-info { flex: 1; min-width: 0; }
  .book-title { font-family: 'Lora', serif; font-size: 0.95rem; font-weight: 600; line-height: 1.3; margin-bottom: 2px; }
  .book-author { font-size: 0.78rem; color: var(--muted); margin-bottom: 8px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
  .book-meta { display: flex; flex-wrap: wrap; gap: 5px; align-items: center; }

  .tag {
    font-size: 0.72rem; padding: 2px 9px; border-radius: 12px; white-space: nowrap;
    display: inline-flex; align-items: center; gap: 3px;
  }
  .tag-available { background: var(--green-bg); color: var(--green); font-weight: 500; }
  .tag-hold      { background: var(--amber-bg); color: var(--amber); }
  .tag-notfound  { background: var(--gray-bg);  color: var(--gray); }
  .tag-format    { background: var(--blue-bg);  color: var(--blue); }

  .btn-borrow, .btn-hold, .btn-worldcat {
    margin-top: 8px; display: inline-block;
    padding: 5px 13px; border-radius: 6px; text-decoration: none;
    font-size: 0.78rem; font-weight: 500; transition: opacity 0.15s;
  }
  .btn-borrow   { background: var(--green); color: #fff; }
  .btn-hold     { background: var(--amber); color: #fff; }
  .btn-worldcat { background: var(--gray-bg); color: var(--gray); border: 1px solid var(--border); }
  .btn-borrow:hover, .btn-hold:hover { opacity: 0.85; }

  .hold-detail { font-size: 0.72rem; color: var(--muted); margin-top: 3px; }

  .section-label { font-size: 0.7rem; font-weight: 500; color: var(--hint); letter-spacing: 0.08em; text-transform: uppercase; padding: 1rem 0 0.5rem; }

  .empty-state { text-align: center; padding: 4rem 2rem; color: var(--hint); font-size: 0.9rem; }

  footer { text-align: center; padding: 2rem; font-size: 0.75rem; color: var(--hint); border-top: 1px solid var(--border); }
</style>
</head>
<body>

<header>
  <div class="header-inner">
    <h1>My TBR <span>on Libby</span></h1>
    <div class="header-meta">
      Library: <strong>LIBRARY_KEY_PLACEHOLDER</strong><br>
      Generated: GENERATED_DATE_PLACEHOLDER
    </div>
  </div>
</header>

<div class="controls">
  <div class="controls-inner">
    <button class="filter-btn active" data-filter="all">All <span class="count">TOTAL_COUNT</span></button>
    <button class="filter-btn" data-filter="available">✓ Available now <span class="count">AVAIL_COUNT</span></button>
    <button class="filter-btn" data-filter="hold">⏳ Place hold <span class="count">HOLD_COUNT</span></button>
    <button class="filter-btn" data-filter="not_found">Not in catalog <span class="count">NOTFOUND_COUNT</span></button>
    <input type="text" id="search-box" placeholder="Search titles or authors…">
  </div>
</div>

<div class="stats-bar">
  <div class="stat-pill avail"><div class="num">AVAIL_COUNT</div><div>ready to borrow</div></div>
  <div class="stat-pill hold"><div class="num">HOLD_COUNT</div><div>available to hold</div></div>
  <div class="stat-pill none"><div class="num">NOTFOUND_COUNT</div><div>not in catalog</div></div>
</div>

<main>
  <div class="book-grid" id="book-grid">
BOOK_CARDS_PLACEHOLDER
  </div>
  <div class="empty-state" id="empty-state" style="display:none;">No books match that filter.</div>
</main>

<footer>
  Built with StoryGraph → Libby Sync &nbsp;·&nbsp; Availability data from OverDrive &nbsp;·&nbsp; Rerun the script to refresh
</footer>

<script>
  const grid = document.getElementById('book-grid');
  const cards = Array.from(grid.querySelectorAll('.book-card'));
  const emptyState = document.getElementById('empty-state');

  let activeFilter = 'all';
  let searchQuery = '';

  function applyFilters() {
    let visible = 0;
    cards.forEach(card => {
      const matchFilter = activeFilter === 'all' || card.dataset.status === activeFilter;
      const matchSearch = !searchQuery ||
        card.dataset.title.toLowerCase().includes(searchQuery) ||
        card.dataset.author.toLowerCase().includes(searchQuery);
      const show = matchFilter && matchSearch;
      card.classList.toggle('hidden', !show);
      if (show) visible++;
    });
    emptyState.style.display = visible === 0 ? 'block' : 'none';
  }

  document.querySelectorAll('.filter-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      activeFilter = btn.dataset.filter;
      applyFilters();
    });
  });

  document.getElementById('search-box').addEventListener('input', e => {
    searchQuery = e.target.value.trim().toLowerCase();
    applyFilters();
  });
</script>
</body>
</html>"""


SPINE_COLORS = [
    ("#9FE1CB","#085041"), ("#AFA9EC","#26215C"), ("#F5C4B3","#4A1B0C"),
    ("#B5D4F4","#042C53"), ("#C0DD97","#173404"), ("#FAC775","#412402"),
    ("#F4C0D1","#4B1528"), ("#D3D1C7","#2C2C2A"), ("#85B7EB","#042C53"),
]

def initials(title: str) -> str:
    words = title.split()[:2]
    return "".join(w[0].upper() for w in words if w)

def build_html(books: list[dict], library_key: str) -> str:
    cards_html = []
    counts = {"available": 0, "hold": 0, "not_found": 0}

    for i, book in enumerate(books):
        lb = book.get("libby", {})
        status = lb.get("status", "not_found")

        if lb.get("error") or lb.get("status") == "not_found":
            status = "not_found"

        counts[status] = counts.get(status, 0) + 1

        bg, fg = SPINE_COLORS[i % len(SPINE_COLORS)]
        cover = lb.get("cover", "")

        if cover:
            spine_html = f'<div class="book-spine"><img src="{cover}" alt="" loading="lazy"></div>'
        else:
            spine_html = (f'<div class="book-spine" style="background:{bg};color:{fg}">'
                          f'{initials(book["title"])}</div>')

        display_title  = lb.get("od_title", book["title"])
        display_author = lb.get("od_author", book["author"]) or book["author"]
        fmt_label      = lb.get("format", "")
        libby_url      = lb.get("libby_url", f"https://libbyapp.com/library/{library_key}")
        holds          = lb.get("holds", 0)
        copies_avail   = lb.get("copies_avail", 0)
        copies_owned   = lb.get("copies_owned", 0)

        if status == "available":
            status_tag = '<span class="tag tag-available">✓ Available</span>'
            if fmt_label:
                status_tag += f'<span class="tag tag-format">{fmt_label}</span>'
            action = f'<a class="btn-borrow" href="{libby_url}" target="_blank">Borrow on Libby →</a>'
            hold_detail = (f'<div class="hold-detail">{copies_avail} of {copies_owned} cop{"y" if copies_owned==1 else "ies"} available</div>'
                           if copies_owned else "")
        elif status == "hold":
            status_tag = '<span class="tag tag-hold">⏳ Hold queue</span>'
            if fmt_label:
                status_tag += f'<span class="tag tag-format">{fmt_label}</span>'
            action = f'<a class="btn-hold" href="{libby_url}" target="_blank">Place hold →</a>'
            wait = f" · {holds} hold{'s' if holds != 1 else ''}" if holds else ""
            hold_detail = f'<div class="hold-detail">{copies_owned} cop{"y" if copies_owned==1 else "ies"} owned{wait}</div>' if copies_owned else ""
        else:
            status_tag = '<span class="tag tag-notfound">Not in catalog</span>'
            q = urllib.parse.quote(book["title"] + " " + book["author"])
            action = f'<a class="btn-worldcat" href="https://www.worldcat.org/search?q={q}" target="_blank">Search WorldCat</a>'
            hold_detail = ""

        pages_info = f' · {book["pages"]}p' if book.get("pages") else ""

        card = f"""    <div class="book-card" data-status="{status}" data-title="{display_title.lower()}" data-author="{display_author.lower()}">
      {spine_html}
      <div class="book-info">
        <div class="book-title">{display_title}</div>
        <div class="book-author">{display_author}{pages_info}</div>
        <div class="book-meta">{status_tag}</div>
        {action}
        {hold_detail}
      </div>
    </div>"""
        cards_html.append(card)

    total = len(books)
    html = HTML_TEMPLATE
    html = html.replace("LIBRARY_KEY_PLACEHOLDER", library_key)
    html = html.replace("GENERATED_DATE_PLACEHOLDER", datetime.now().strftime("%B %d, %Y %I:%M %p"))
    html = html.replace("TOTAL_COUNT", str(total))
    html = html.replace("AVAIL_COUNT", str(counts.get("available", 0)))
    html = html.replace("HOLD_COUNT", str(counts.get("hold", 0)))
    html = html.replace("NOTFOUND_COUNT", str(counts.get("not_found", 0)))
    html = html.replace("BOOK_CARDS_PLACEHOLDER", "\n".join(cards_html))
    return html


# ──────────────────────────────────────────────
#  ENTRY POINT
# ──────────────────────────────────────────────

def prompt(label: str, default: str = "") -> str:
    if default:
        val = input(f"{label} [{default}]: ").strip()
        return val if val else default
    while True:
        val = input(f"{label}: ").strip()
        if val:
            return val
        print("  (required — please enter a value)")


def main():
    print("\n" + "═"*55)
    print("  📚  StoryGraph → Libby TBR Sync")
    print("═"*55)

    csv_path    = CSV_PATH    or prompt("\nPath to your StoryGraph CSV export")
    library_key = LIBRARY_KEY or prompt("Your Libby library key (e.g. alamedacountylibrary)")

    print(f"\n📖  Parsing StoryGraph CSV…")
    books = parse_storygraph_csv(csv_path)

    if not books:
        print("⚠️  No to-read books found. Make sure the CSV has a 'Read Status' column with 'to-read' entries.")
        sys.exit(0)

    print(f"   Found {len(books)} books on your TBR list.")

    books = check_all_books(books, library_key)

    print("🎨  Building HTML report…")
    html = build_html(books, library_key)

    out_path = Path(OUTPUT_FILE)
    out_path.write_text(html, encoding="utf-8")

    avail   = sum(1 for b in books if b.get("libby", {}).get("status") == "available")
    on_hold = sum(1 for b in books if b.get("libby", {}).get("status") == "hold")
    missing = len(books) - avail - on_hold

    print(f"\n{'─'*55}")
    print(f"  ✅  {avail:>3} books available to borrow RIGHT NOW")
    print(f"  ⏳  {on_hold:>3} books available to place on hold")
    print(f"  ✗   {missing:>3} books not found in your catalog")
    print(f"{'─'*55}")
    print(f"\n  Results saved to: {out_path.resolve()}")
    print("  Open that file in your browser to start borrowing!\n")


if __name__ == "__main__":
    main()
