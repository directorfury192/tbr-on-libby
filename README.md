# TBR on Libby

Check your [StoryGraph](https://app.thestorygraph.com) to-read list against your local library's Libby/OverDrive catalog — instantly see what you can borrow now, place on hold, or request elsewhere.

**Live app:** [directorfury192.github.io/tbr-on-libby](https://directorfury192.github.io/tbr-on-libby/)

---

## What it does

1. You export your StoryGraph library as a CSV
2. You type your library's name, city, or zip code and select it from the dropdown
3. The app checks every book on your to-read list against your library's digital catalog
4. Results are shown as individual format editions — eBooks and audiobooks appear as separate cards, each with its own availability status and direct Libby link
5. Filter by availability (Borrow now / Hold / Not found / Owned) and by format (eBooks, audiobooks, or both)
6. Click any result to open that specific edition directly in Libby
7. Save your results as a CSV for later reference

Books you already own (marked "Owned" in StoryGraph) are automatically filtered out of the search. Because one book can have both an ebook and an audiobook edition, the result count may exceed your TBR count — a summary above the results explains the breakdown.

---

## How to use it

### Step 1 — Export your StoryGraph library
1. Log into [app.thestorygraph.com](https://app.thestorygraph.com)
2. Click your profile icon (top right) → **Account**
3. Scroll to **Import and Export Data**
4. Click **Export your library** — a `.csv` file downloads

### Step 2 — Upload and search
1. Open the app and drag your CSV onto the upload zone (or click Browse)
2. Type your library's name, city, or zip code and select it from the dropdown
3. Choose eBooks, audiobooks, or both — only selected formats will appear in results
4. Click **Search my library catalog**

### Step 3 — Browse and save results
Filter by availability tab, search by title, and click any result card to open that edition directly in Libby. Use **Save results as CSV** to download the full results for offline reference.

---

## How it works (technical)

This is a single `index.html` file that runs entirely in the browser — no backend, no account, nothing stored.

**Library lookup** uses the `locate.libbyapp.com/autocomplete` endpoint, which is CORS-open and works as a direct browser call. The correct library key for API calls is extracted from the `DigitalLibraryUrl` link in the system object returned by that endpoint (e.g. `mcplmd.overdrive.com` → key `mcplmd`). This key differs from the internal `fulfillmentId` field and works for both the book search API and Libby deep links.

**Book availability** uses the OverDrive Thunder API (`thunder.api.overdrive.com/v2/libraries/{key}/media`), which returns `Access-Control-Allow-Origin: *` and can be called directly from the browser with no proxy needed. Each search returns up to 20 results; all title-matching editions are returned as separate result cards so that ebook and audiobook availability are shown independently.

**Libby deep links** use the format `libbyapp.com/search/{key}/search/query-{title}/page-1/{contentId}`, pointing directly to the specific edition in the user's library catalog.

---

## Files

| File | Purpose |
|---|---|
| `index.html` | The entire app — HTML, CSS, and JS in one file |
| `tbr_libby.py` | Python reference script used during development and debugging |

---

## Research & prior art

[Libby Multi-Library Search](https://libbysearch.com) (libbysearch.com) was a key reference during development. Inspecting its network traffic was instrumental in identifying the correct Thunder API URL format, the `DigitalLibraryUrl` field as the source of library keys, and the Libby deep link structure with content IDs.

---

## License

MIT — free to use, fork, and adapt.
