# TBR on Libby

Check your [StoryGraph](https://app.thestorygraph.com) to-read list against your local library's Libby/OverDrive catalog — instantly see what you can borrow now, place on hold, or request elsewhere.

**Live app:** [directorfury192.github.io/tbr-on-libby](https://directorfury192.github.io/tbr-on-libby/)

---

## What it does

1. You export your StoryGraph library as a CSV
2. You type your library's name or zip code
3. The app checks every book on your to-read list against your library's digital catalog
4. Results sort into: **Borrow now**, **Place hold**, **Not in catalog**, and **Already owned**
5. Each available book links directly into Libby so you can borrow or hold with one click

Books you already own (marked "Owned" in StoryGraph) are automatically filtered out of the search.

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
3. Choose eBooks, audiobooks, or both
4. Click **Search my library catalog**

### Step 3 — Browse results
Filter by availability tab, search by title, and click any result to open it in Libby.

---

## How it works (technical)

This is a single `index.html` file that runs entirely in the browser — no backend, no account, nothing stored.

**Library lookup** uses the `locate.libbyapp.com/autocomplete` endpoint, which is publicly CORS-open and works as a direct browser call.

**Book availability** uses the OverDrive Thunder API (`thunder.api.overdrive.com/v2/libraries/{key}/media`). This is the same API the Libby web app uses internally. Because it only allows browser requests from Libby's own origin, a small Cloudflare Worker (`worker.js`) is used as a CORS proxy — it forwards the request server-side and adds the missing `Access-Control-Allow-Origin` header.

### CORS proxy setup (required for forking)

If you fork this project you'll need to deploy your own proxy:

1. Create a free [Cloudflare](https://cloudflare.com) account
2. Go to **Workers & Pages** → **Create Worker** → paste `worker.js` → **Deploy**
3. Copy your `*.workers.dev` URL
4. In `index.html`, set `const PROXY_BASE = 'YOUR_URL'` near the top of the `<script>` block

### Current known issue

Book availability search is returning no results even with the CORS proxy in place. The proxy is deployed and the Thunder API call is being routed through it, but results come back empty. The root cause is under investigation — most likely either an authentication requirement, an unexpected response shape, or a library key format mismatch. A working Python reference implementation (`tbr_libby.py`) is included in the repo for comparison.

---

## Files

| File | Purpose |
|---|---|
| `index.html` | The entire app — HTML, CSS, and JS in one file |
| `worker.js` | Cloudflare Worker CORS proxy for the Thunder API |
| `tbr_libby.py` | Python reference script — works correctly, used for debugging |
| `README-PROXY.md` | Step-by-step proxy deployment guide |

---

## Stack

- Vanilla HTML / CSS / JS — no frameworks or build step
- Hosted on GitHub Pages
- CORS proxy via Cloudflare Workers (free tier)
- Data sources: StoryGraph CSV export + OverDrive Thunder API
