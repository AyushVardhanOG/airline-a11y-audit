"""
scan_captures.py - scan the saved SingleFile copies in data/captures/ with axe-core.

This is now the MAIN way pages are measured (method decided after Step 2, where most
airline sites blocked automated browsers). See docs/capture_guide.md for how the
copies are made.

For every file data/captures/<airline_id>_<page_type>_<YYYYMMDD>.html:
  1. Check the file name and find its row in data/captures/log.csv
     (who/when/where it was captured). Missing log rows are reported as warnings.
  2. Open it in headless Chromium, completely OFFLINE:
       - the file is served from disk by Playwright under a fake local address
         (http://saved-copy.localhost/...), so it has a normal web origin;
       - EVERY other request (images, scripts, trackers on the internet) is blocked,
         so scanning a copy never contacts the airline's website;
       - the page's own JavaScript is switched off with a Content-Security-Policy
         header ("script-src 'none'"). A SingleFile copy is a snapshot of the page
         as the browser drew it; re-running its scripts could change it.
         axe-core still works, because Playwright injects it through the browser's
         debugging channel, which this header does not affect.
         (Tested in Step 3: a test page's own script did not run, axe found all
         planted errors, including one inside an iframe.)
  3. Run axe-core with the same rules and iframe setting as the live scanner
     (shared code in axe_runner.py), then take a screenshot.
  4. Save one raw JSON file per capture and a summary CSV.

Output (new timestamped folder per run, old results are never overwritten):
  data/raw/capture_scans/<run_id>/<file_stem>.json
  screenshots/capture_scans/<run_id>/<file_stem>.png
  data/results/capture_scans_<run_id>.csv

Run from the project folder:
    .venv\\Scripts\\python.exe src\\scan_captures.py              (scan all captures)
    .venv\\Scripts\\python.exe src\\scan_captures.py ana_home_20261112.html   (only some)
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

import axe_runner as ax

# ---------------------------------------------------------------- settings

CAPTURES_DIR = ax.PROJECT_ROOT / "data" / "captures"
LOG_PATH = CAPTURES_DIR / "log.csv"
AIRLINES_PATH = ax.PROJECT_ROOT / "data" / "airlines.csv"
RAW_DIR = ax.PROJECT_ROOT / "data" / "raw" / "capture_scans"
SHOTS_DIR = ax.PROJECT_ROOT / "screenshots" / "capture_scans"
RESULTS_DIR = ax.PROJECT_ROOT / "data" / "results"

# Fake local address the saved file is served under. ".localhost" names never go
# to the internet, and on top of that Playwright answers the request itself.
FAKE_BASE_URL = "http://saved-copy.localhost/"

# File name pattern: airline_pagetype_YYYYMMDD.html, e.g. air_india_checkin_20261112.html
FILE_NAME_RE = re.compile(
    r"^(?P<airline_id>[a-z0-9_]+)_(?P<page_type>" + "|".join(ax.PAGE_TYPES) + r")_(?P<date>\d{8})\.html$"
)


# ---------------------------------------------------------------- helpers

def load_capture_log():
    """Read data/captures/log.csv into a dict: file_name -> row."""
    if not LOG_PATH.exists():
        return {}
    with open(LOG_PATH, newline="", encoding="utf-8-sig") as f:
        return {row["file_name"].strip(): row for row in csv.DictReader(f) if row.get("file_name")}


def load_airline_ids():
    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        return {row["airline_id"] for row in csv.DictReader(f)}


def captured_utc_from_log(row):
    """
    Combine the log's local time + UTC offset into one UTC time.
    Example: "2026-11-12 10:15" + "+05:30" -> "2026-11-12T04:45:00+00:00".
    Returns None if the log row is missing or the time cannot be read.
    """
    try:
        local = datetime.fromisoformat(row["captured_at_local"].strip().replace(" ", "T") + row["utc_offset"].strip())
        if local.tzinfo is None:  # no offset given: do not guess the time zone
            return None
        return local.astimezone(timezone.utc).isoformat(timespec="seconds")
    except (KeyError, ValueError, AttributeError):
        return None


def read_singlefile_header(html_text):
    """
    SingleFile writes a comment at the top of each saved page with the original URL
    and the save date. We store it as a cross-check of the log.
    """
    head = html_text[:3000]
    if "Page saved with SingleFile" not in head:
        return {"found": False}
    url = re.search(r"url:\s*(\S+)", head)
    saved = re.search(r"saved date:\s*([^\n]+)", head)
    return {
        "found": True,
        "url": url.group(1) if url else None,
        "saved_date": saved.group(1).strip() if saved else None,
    }


# ---------------------------------------------------------------- one capture

def scan_capture(browser, html_path, log_row, axe_source, out_raw, out_shots):
    """Scan one saved page completely offline. Returns a summary row (dict)."""
    m = FILE_NAME_RE.match(html_path.name)
    html_bytes = html_path.read_bytes()

    record = {
        "source": "saved_copy",
        "file_name": html_path.name,
        "airline_id": m["airline_id"],
        "page_type": m["page_type"],
        "file_date": m["date"],
        "capture_log": log_row,  # None if the file has no row in log.csv
        "captured_utc": captured_utc_from_log(log_row) if log_row else None,
        "url": (log_row or {}).get("url"),
        "singlefile_header": read_singlefile_header(html_bytes.decode("utf-8", errors="replace")),
        "file_size_bytes": len(html_bytes),
        "scan_started_utc": ax.utc_now(),
        "tool_versions": ax.tool_versions(browser),
        "settings": {
            "wcag_tags": ax.WCAG_TAGS,
            "viewport": ax.VIEWPORT,
            "headless": True,
            "page_scripts": "disabled (CSP script-src 'none')",
            "network": "all requests blocked except the saved file itself",
        },
        "http_status": None,  # not applicable: the page comes from disk
        "status": None,  # "ok" or "error"
        "error": None,
    }

    page_url = FAKE_BASE_URL + html_path.name
    blocked_hosts = {}  # host -> number of blocked requests (no full URLs: they can hold tracking ids)

    def handle_request(route):
        url = route.request.url
        if url == page_url:
            route.fulfill(
                status=200,
                headers={
                    "Content-Type": "text/html; charset=utf-8",
                    "Content-Security-Policy": "script-src 'none'",
                },
                body=html_bytes,
            )
        else:
            host = url.split("/")[2] if "://" in url else url[:30]
            blocked_hosts[host] = blocked_hosts.get(host, 0) + 1
            route.abort()

    context = browser.new_context(viewport=ax.VIEWPORT, locale="en-US")
    context.route("**/*", handle_request)
    page = context.new_page()

    try:
        page.goto(page_url, wait_until="load", timeout=60_000)
        time.sleep(1)  # let the browser finish laying out the page
        record["page_title"] = page.title()

        # Warn if the saved copy itself is a block/error page (would make results useless).
        body_text = page.inner_text("body", timeout=10_000)
        record["looks_like_block_page"] = ax.detect_block(None, record["page_title"], body_text)

        results, info = ax.run_axe(page, axe_source)
        record.update(info)
        record["tool_versions"]["axe_core"] = results["testEngine"]["version"]
        record["axe_results"] = results
        # Screenshot AFTER axe, so resizing for a full-page shot cannot change what axe saw.
        record["screenshot"] = ax.take_screenshot(page, out_shots / f"{html_path.stem}.png")
        record["status"] = "ok"
    except PlaywrightError as e:
        record["status"] = "error"
        record["error"] = str(e).splitlines()[0]
    finally:
        record["blocked_requests_by_host"] = blocked_hosts
        record["scan_finished_utc"] = ax.utc_now()
        context.close()

    with open(out_raw / f"{html_path.stem}.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    row = {
        "file_name": html_path.name,
        "airline_id": record["airline_id"],
        "page_type": record["page_type"],
        "captured_utc": record["captured_utc"],
        "status": record["status"],
        "rules_failed": None, "elements_failed": None,
        "critical": None, "serious": None, "moderate": None, "minor": None,
        "note": record["error"] or record.get("looks_like_block_page") or "",
    }
    if record["status"] == "ok":
        row.update(ax.summarize_violations(results["violations"]))
    return row


# ---------------------------------------------------------------- main

def find_capture_files(only_names):
    """List the capture files to scan, and report files with wrong names."""
    files, bad_names = [], []
    for path in sorted(CAPTURES_DIR.glob("*.html")):
        if only_names and path.name not in only_names:
            continue
        (files if FILE_NAME_RE.match(path.name) else bad_names).append(path)
    return files, bad_names


def main():
    only_names = set(sys.argv[1:])
    axe_source = ax.load_axe_source()
    log = load_capture_log()
    airline_ids = load_airline_ids()

    files, bad_names = find_capture_files(only_names)
    for path in bad_names:
        print(f"SKIPPED (name does not match airline_pagetype_YYYYMMDD.html): {path.name}")
    if not files:
        print(f"No capture files to scan in {CAPTURES_DIR.relative_to(ax.PROJECT_ROOT)}.")
        return

    # Warnings, so problems with the log are visible instead of silently ignored.
    for path in files:
        airline_id = FILE_NAME_RE.match(path.name)["airline_id"]
        if airline_id not in airline_ids:
            print(f"WARNING: '{airline_id}' is not an airline_id in data/airlines.csv ({path.name})")
        if path.name not in log:
            print(f"WARNING: no row in data/captures/log.csv for {path.name} (capture time unknown)")

    run_id = ax.make_run_id()
    out_raw = RAW_DIR / run_id
    out_shots = SHOTS_DIR / run_id
    out_raw.mkdir(parents=True)
    out_shots.mkdir(parents=True)
    print(f"Run id: {run_id}  ({len(files)} files)\n")

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, path in enumerate(files):
            print(f"[{i + 1}/{len(files)}] {path.name}", flush=True)
            row = scan_capture(browser, path, log.get(path.name), axe_source, out_raw, out_shots)
            print(f"      -> {row['status']}  rules={row['rules_failed']}  elements={row['elements_failed']}  {row['note']}", flush=True)
            rows.append(row)
        browser.close()

    summary_path = RESULTS_DIR / f"capture_scans_{run_id}.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nRaw JSON   : {out_raw.relative_to(ax.PROJECT_ROOT)}")
    print(f"Screenshots: {out_shots.relative_to(ax.PROJECT_ROOT)}")
    print(f"Summary CSV: {summary_path.relative_to(ax.PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
