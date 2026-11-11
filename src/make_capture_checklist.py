"""
make_capture_checklist.py - create docs/capture_checklist.md from data/airlines.csv.

The checklist has one checkbox per page (30 airlines x 3 pages = 90 boxes), grouped
by region, with the suggested URL and any note from data/url_search_notes.csv
(where the URL came from, and what to check).

The checklist is a WORKING document: you tick boxes in it while capturing.
So this script will NOT overwrite an existing checklist (that would erase your ticks)
unless you run it with --force.

Run:  .venv\\Scripts\\python.exe src\\make_capture_checklist.py
"""

import csv
import sys
from urllib.parse import urlparse

import axe_runner as ax

AIRLINES_PATH = ax.PROJECT_ROOT / "data" / "airlines.csv"
NOTES_PATH = ax.PROJECT_ROOT / "data" / "url_search_notes.csv"
OUT_PATH = ax.PROJECT_ROOT / "docs" / "capture_checklist.md"

URL_COLUMNS = {"home": "homepage", "checkin": "checkin_url", "assistance": "assistance_url"}

HEADER = """# Capture checklist

One box per page: **{n_pages} pages** ({n_airlines} airlines x 3 page types).
How to capture each page: see [capture_guide.md](capture_guide.md).

The URLs were **suggested by web search** on {search_date} and are **not checked yet**
(`url_verified = no` in `data/airlines.csv`). For every page:

1. Open the suggested URL in your capture browser profile.
2. Check it is the right page, in English, for the right country (see the note).
   - Wrong or outdated? Find the right page by clicking through the site
     (no logins, no typing into forms) and **correct the URL in `data/airlines.csv`**.
   - `MISSING` = web search did not find it. Look for it on the site for up to
     about 5 minutes. If the airline really has no such page, leave `MISSING`.
3. Capture it with SingleFile, rename it, add the row to `data/captures/log.csv`.
4. Tick the box.

When all three pages of an airline are checked, set **`url_verified` to `yes`** for that
airline in `data/airlines.csv`. (The live scanner only scans airlines marked `yes`.)

**{n_missing} pages are MISSING** and **{n_noted} have a note** to check.
"""


def load_notes():
    with open(NOTES_PATH, newline="", encoding="utf-8") as f:
        return {(r["airline_id"], r["page_type"]): r["note"] for r in csv.DictReader(f)}


def auto_note(page_type, url):
    """A standard note for homepages given only as the bare domain (e.g. https://www.klm.com)."""
    if page_type == "home" and urlparse(url).path in ("", "/"):
        return "bare domain: the site redirects by location - choose English and the airline's home country"
    return ""


def main():
    if OUT_PATH.exists() and "--force" not in sys.argv:
        sys.exit(f"{OUT_PATH.relative_to(ax.PROJECT_ROOT)} already exists (it may contain your ticks). "
                 "Use --force to overwrite it.")

    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        airlines = list(csv.DictReader(f))
    notes = load_notes()

    body, n_missing, n_noted = [], 0, 0
    current_region = None
    for a in airlines:
        if a["region"] != current_region:  # new region heading (CSV is ordered by region)
            current_region = a["region"]
            body.append(f"\n## {current_region}\n")
        body.append(f"\n### {a['airline']} (`{a['airline_id']}`)\n")
        for page_type, column in URL_COLUMNS.items():
            url = a[column].strip()
            if url.upper() == "MISSING":
                n_missing += 1
                line = f"- [ ] **{page_type}**: MISSING"
            else:
                line = f"- [ ] **{page_type}**: <{url}>"
            note = notes.get((a["airline_id"], page_type)) or auto_note(page_type, url)
            if note:
                n_noted += 1
                line += f"  \n  _Note: {note}_"
            body.append(line)

    header = HEADER.format(
        n_pages=len(airlines) * 3, n_airlines=len(airlines), search_date="2026-11-11",
        n_missing=n_missing, n_noted=n_noted,
    )
    OUT_PATH.write_text(header + "\n".join(body) + "\n", encoding="utf-8")
    print(f"Wrote {OUT_PATH.relative_to(ax.PROJECT_ROOT)}: {len(airlines) * 3} pages, "
          f"{n_missing} MISSING, {n_noted} with notes")


if __name__ == "__main__":
    main()
