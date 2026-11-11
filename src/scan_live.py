"""
scan_live.py - scan LIVE airline pages with axe-core, only for airlines that
allowed automated access in Step 2.

Why this still exists: the main method is now scanning saved copies (scan_captures.py).
For airlines that did not block us, we ALSO scan the live page, so that
compare_live_vs_capture.py can check how much a saved copy differs from the live page.
Run this close in time (same hour if possible) to when the same pages were captured.

Which pages: for each airline whose result in data/results/automated_access.csv is
"allowed" AND whose url_verified is "yes" in data/airlines.csv, the URLs in
data/airlines.csv (homepage, checkin_url, assistance_url).
Empty URLs and URLs marked MISSING are skipped.

Rules followed (CLAUDE.md): one page at a time, 10 s pause between pages, only
open the page (no clicks, no typing, no cookie banner handling, no login), a block
page is recorded as "blocked" and never bypassed. The browser identifies itself as
headless Chromium (default user agent, not disguised).

Output (new timestamped folder per run):
  data/raw/live_scans/<run_id>/<airline_id>_<page_type>.json
  screenshots/live_scans/<run_id>/<airline_id>_<page_type>.png   (*_blocked.png for block pages; git-ignored)
  data/results/live_scans_<run_id>.csv

Run from the project folder:
    .venv\\Scripts\\python.exe src\\scan_live.py          (all allowed airlines)
    .venv\\Scripts\\python.exe src\\scan_live.py ana      (only some airlines)
"""

import csv
import json
import sys
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

import axe_runner as ax

# ---------------------------------------------------------------- settings

AIRLINES_PATH = ax.PROJECT_ROOT / "data" / "airlines.csv"
ACCESS_PATH = ax.PROJECT_ROOT / "data" / "results" / "automated_access.csv"
RAW_DIR = ax.PROJECT_ROOT / "data" / "raw" / "live_scans"
SHOTS_DIR = ax.PROJECT_ROOT / "screenshots" / "live_scans"
RESULTS_DIR = ax.PROJECT_ROOT / "data" / "results"

WAIT_BETWEEN_PAGES_S = 10  # politeness rule (at least 10 s)
PAGE_LOAD_TIMEOUT_MS = 60_000
SETTLE_TIME_S = 3

# Which column of airlines.csv holds the URL for each page type.
URL_COLUMNS = {"home": "homepage", "checkin": "checkin_url", "assistance": "assistance_url"}


# ---------------------------------------------------------------- page list

def pages_to_scan(only_airlines):
    """Build the list of (airline_id, page_type, url) for airlines with access 'allowed'."""
    with open(ACCESS_PATH, newline="", encoding="utf-8") as f:
        allowed = {r["airline_id"] for r in csv.DictReader(f) if r["result"] == "allowed"}
    pages = []
    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["airline_id"] not in allowed:
                continue
            if only_airlines and row["airline_id"] not in only_airlines:
                continue
            # The URLs in airlines.csv started as web-search suggestions. Only visit
            # them live after a person has checked them (url_verified = yes).
            if row.get("url_verified", "").strip().lower() != "yes":
                print(f"Skipping {row['airline_id']}: url_verified is not 'yes' in data/airlines.csv")
                continue
            for page_type, column in URL_COLUMNS.items():
                url = (row.get(column) or "").strip()
                if ax.is_real_url(url):  # skips empty, MISSING and SAME_AS_HOME
                    pages.append((row["airline_id"], page_type, url))
    return pages


# ---------------------------------------------------------------- one page

def scan_page(browser, airline_id, page_type, url, axe_source, out_raw, out_shots):
    """Scan one live page. Returns a summary row (dict)."""
    name = f"{airline_id}_{page_type}"
    record = {
        "source": "live",
        "airline_id": airline_id,
        "page_type": page_type,
        "url": url,
        "scan_started_utc": ax.utc_now(),
        "tool_versions": ax.tool_versions(browser),
        "settings": {
            "wcag_tags": ax.WCAG_TAGS,
            "viewport": ax.VIEWPORT,
            "headless": True,
            "page_scripts": "enabled (live site)",
            "page_load_timeout_ms": PAGE_LOAD_TIMEOUT_MS,
            "settle_time_s": SETTLE_TIME_S,
        },
        "status": None,  # "ok", "blocked" or "error"
        "block_reason": None,
        "error": None,
    }

    # Fresh context = brand-new browser profile, like a first-time visitor.
    context = browser.new_context(viewport=ax.VIEWPORT, locale="en-US")
    page = context.new_page()
    record["user_agent"] = page.evaluate("navigator.userAgent")

    try:
        t0 = time.time()
        response = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightError:
            record["note"] = "network never went idle within 15 s; scanned anyway"
        time.sleep(SETTLE_TIME_S)
        record["load_time_s"] = round(time.time() - t0, 1)
        record["http_status"] = response.status if response else None
        record["final_url"] = page.url
        record["page_title"] = page.title()

        body_text = page.inner_text("body", timeout=10_000)
        block_reason = ax.detect_block(record["http_status"], record["page_title"], body_text)

        if block_reason:
            record["status"] = "blocked"
            record["block_reason"] = block_reason
            record["visible_text_start"] = ax.redact_ips(body_text[:500])
            # "_blocked" screenshots are git-ignored: block pages can show our IP address.
            record["screenshot"] = ax.take_screenshot(page, out_shots / f"{name}_blocked.png")
        else:
            results, info = ax.run_axe(page, axe_source)
            record.update(info)
            record["tool_versions"]["axe_core"] = results["testEngine"]["version"]
            record["axe_results"] = results
            # Screenshot AFTER axe, so resizing for a full-page shot cannot change what axe saw.
            record["screenshot"] = ax.take_screenshot(page, out_shots / f"{name}.png")
            record["status"] = "ok"
    except PlaywrightError as e:
        record["status"] = "error"
        record["error"] = str(e).splitlines()[0]
    finally:
        record["scan_finished_utc"] = ax.utc_now()
        context.close()

    with open(out_raw / f"{name}.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    row = {
        "airline_id": airline_id,
        "page_type": page_type,
        "scanned_utc": record["scan_started_utc"],
        "status": record["status"],
        "http": record.get("http_status"),
        "rules_failed": None, "elements_failed": None,
        "critical": None, "serious": None, "moderate": None, "minor": None,
        "note": record["block_reason"] or record["error"] or "",
    }
    if record["status"] == "ok":
        row.update(ax.summarize_violations(results["violations"]))
    return row


# ---------------------------------------------------------------- main

def main():
    only_airlines = set(sys.argv[1:])
    axe_source = ax.load_axe_source()
    pages = pages_to_scan(only_airlines)
    if not pages:
        print("No pages to scan (no 'allowed' airlines with URLs in data/airlines.csv).")
        return

    run_id = ax.make_run_id()
    out_raw = RAW_DIR / run_id
    out_shots = SHOTS_DIR / run_id
    out_raw.mkdir(parents=True)
    out_shots.mkdir(parents=True)
    print(f"Run id: {run_id}  ({len(pages)} pages)\n")

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, (airline_id, page_type, url) in enumerate(pages):
            print(f"[{i + 1}/{len(pages)}] {airline_id} {page_type}: {url}", flush=True)
            row = scan_page(browser, airline_id, page_type, url, axe_source, out_raw, out_shots)
            print(f"      -> {row['status']}  rules={row['rules_failed']}  elements={row['elements_failed']}  {row['note']}", flush=True)
            rows.append(row)
            if i < len(pages) - 1:
                time.sleep(WAIT_BETWEEN_PAGES_S)  # politeness pause
        browser.close()

    summary_path = RESULTS_DIR / f"live_scans_{run_id}.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nRaw JSON   : {out_raw.relative_to(ax.PROJECT_ROOT)}")
    print(f"Screenshots: {out_shots.relative_to(ax.PROJECT_ROOT)}")
    print(f"Summary CSV: {summary_path.relative_to(ax.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
