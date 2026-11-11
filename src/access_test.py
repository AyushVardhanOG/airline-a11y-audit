"""
access_test.py - Step 4, part 1: does each airline's website let an automated
(headless) browser in?

Tests the airlines whose result in data/results/automated_access.csv is "not_tested"
(the 24 airlines that were not in the Step 2 feasibility test).

For each airline, ONE AT A TIME, exactly ONE visit to its homepage (from data/airlines.csv):
  1. Open the homepage in a fresh headless Chromium context (default user agent,
     which says "HeadlessChrome" - not disguised).
  2. Record metadata: UTC time, URL, final URL after redirects, page title, HTTP status,
     browser version, user agent, load time.
  3. Decide whether we got the real page or a block page (axe_runner.detect_block).
  4. Save a screenshot (block pages: *_blocked.png, which git ignores because block
     pages can show our IP address) and a raw JSON record.
  5. Wait 10 seconds before the next site.

What we do NOT do: no retries, no clicks, no cookie banners, no typing, no captcha
solving, no changes to the browser to avoid detection. If blocked, we record it and move on.
This script does NOT run axe-core: it only tests access.

Output (new timestamped folder per run):
  data/raw/access_test/<run_id>/<airline_id>.json
  screenshots/access_test/<run_id>/<airline_id>.png   (or <airline_id>_blocked.png)
  data/results/access_test_<run_id>.csv               (same columns as the Step 2 summary)

Afterwards run src/record_access.py to update data/results/automated_access.csv.

Run:  .venv\\Scripts\\python.exe src\\access_test.py
"""

import csv
import json
import time

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

import axe_runner as ax

AIRLINES_PATH = ax.PROJECT_ROOT / "data" / "airlines.csv"
ACCESS_PATH = ax.PROJECT_ROOT / "data" / "results" / "automated_access.csv"
RAW_DIR = ax.PROJECT_ROOT / "data" / "raw" / "access_test"
SHOTS_DIR = ax.PROJECT_ROOT / "screenshots" / "access_test"
RESULTS_DIR = ax.PROJECT_ROOT / "data" / "results"

WAIT_BETWEEN_SITES_S = 10  # politeness rule (at least 10 s)
PAGE_LOAD_TIMEOUT_MS = 60_000
SETTLE_TIME_S = 3


def airlines_to_test():
    """(airline_id, display name, homepage) for every airline still 'not_tested'."""
    with open(ACCESS_PATH, newline="", encoding="utf-8") as f:
        not_tested = {r["airline_id"] for r in csv.DictReader(f) if r["result"] == "not_tested"}
    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        return [(r["airline_id"], r["airline"], r["homepage"].strip())
                for r in csv.DictReader(f) if r["airline_id"] in not_tested]


def visit(browser, airline_id, name, url, out_raw, out_shots):
    """One visit to one homepage. Returns a summary row (dict)."""
    record = {
        "airline_id": airline_id,
        "airline": name,
        "url": url,
        "visit_started_utc": ax.utc_now(),
        "tool_versions": ax.tool_versions(browser),
        "settings": {
            "viewport": ax.VIEWPORT,
            "headless": True,
            "page_load_timeout_ms": PAGE_LOAD_TIMEOUT_MS,
            "settle_time_s": SETTLE_TIME_S,
            "visits_per_site": 1,
        },
        "status": None,  # "ok", "blocked" or "error"
        "block_reason": None,
        "error": None,
    }

    context = browser.new_context(viewport=ax.VIEWPORT, locale="en-US")
    page = context.new_page()
    record["user_agent"] = page.evaluate("navigator.userAgent")

    try:
        t0 = time.time()
        response = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        try:
            page.wait_for_load_state("networkidle", timeout=15_000)
        except PlaywrightError:
            record["note"] = "network never went idle within 15 s"
        time.sleep(SETTLE_TIME_S)
        record["load_time_s"] = round(time.time() - t0, 1)
        record["http_status"] = response.status if response else None
        record["final_url"] = page.url
        record["page_title"] = page.title()

        body_text = page.inner_text("body", timeout=10_000)
        record["visible_text_length"] = len(body_text.strip())
        block_reason = ax.detect_block(record["http_status"], record["page_title"], body_text)

        if block_reason:
            record["status"] = "blocked"
            record["block_reason"] = block_reason
            record["visible_text_start"] = ax.redact_ips(body_text[:500])  # evidence, IPs removed
            record["screenshot"] = ax.take_screenshot(page, out_shots / f"{airline_id}_blocked.png")
        else:
            record["status"] = "ok"
            record["screenshot"] = ax.take_screenshot(page, out_shots / f"{airline_id}.png")
    except PlaywrightError as e:
        record["status"] = "error"
        record["error"] = str(e).splitlines()[0]
    finally:
        record["visit_finished_utc"] = ax.utc_now()
        context.close()

    with open(out_raw / f"{airline_id}.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    # Same columns as the Step 2 summary, so record_access.py can read both.
    return {
        "airline": name,
        "status": record["status"],
        "http": record.get("http_status"),
        "load_s": record.get("load_time_s"),
        "final_url": record.get("final_url"),
        "page_title": record.get("page_title"),
        "note": record["block_reason"] or record["error"] or "",
    }


def main():
    airlines = airlines_to_test()
    if not airlines:
        print("No airlines are 'not_tested' in data/results/automated_access.csv.")
        return

    run_id = ax.make_run_id()
    out_raw = RAW_DIR / run_id
    out_shots = SHOTS_DIR / run_id
    out_raw.mkdir(parents=True)
    out_shots.mkdir(parents=True)
    print(f"Run id: {run_id}  ({len(airlines)} airlines, one homepage visit each)\n")

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, (airline_id, name, url) in enumerate(airlines):
            print(f"[{i + 1}/{len(airlines)}] {name}: {url}", flush=True)
            row = visit(browser, airline_id, name, url, out_raw, out_shots)
            print(f"      -> {row['status']}  http={row['http']}  {row['note']}", flush=True)
            rows.append(row)
            if i < len(airlines) - 1:
                time.sleep(WAIT_BETWEEN_SITES_S)  # politeness pause
        browser.close()

    summary_path = RESULTS_DIR / f"access_test_{run_id}.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nRaw JSON   : {out_raw.relative_to(ax.PROJECT_ROOT)}")
    print(f"Screenshots: {out_shots.relative_to(ax.PROJECT_ROOT)}")
    print(f"Summary CSV: {summary_path.relative_to(ax.PROJECT_ROOT)}")
    print("Next: run src/record_access.py to update data/results/automated_access.csv")


if __name__ == "__main__":
    main()
