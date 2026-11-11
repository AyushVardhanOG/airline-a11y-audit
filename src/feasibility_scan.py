"""
feasibility_scan.py - Step 2: feasibility test on 6 airline homepages.

NOTE: kept as the exact record of how the Step 2 results were produced.
New scans use scan_captures.py (saved copies, main method) and scan_live.py
(live pages), which share their axe-core settings through axe_runner.py.

Question this step answers: "Can we load real airline homepages with Playwright
and scan them with axe-core, or do the sites block automated browsers?"

For each airline, ONE AT A TIME:
  1. Open the homepage in a fresh headless Chromium browser context.
  2. Record metadata: UTC time, URL, final URL after redirects, page title,
     HTTP status, browser version, axe-core version, user agent.
  3. Take a full-page screenshot.
  4. Check whether the site blocked us (HTTP 403/429/..., or "access denied" /
     captcha style pages). If blocked: record it as "blocked" and move on.
     We NEVER try to get around bot protection.
  5. If not blocked: inject axe-core and run only the WCAG 2.0 / 2.1 Level A + AA rules.
  6. Save everything as one raw JSON file.
  7. Wait 10 seconds before the next site (politeness rule).

What we do NOT do: click anything, accept/close cookie banners, log in, type data,
or go beyond the homepage. The scan therefore includes whatever cookie banner
the site shows on first visit - that is what a real first-time visitor sees.

Output (a new timestamped folder per run, so old results are never overwritten):
  data/raw/step2_feasibility/<run_id>/<airline>.json
  screenshots/step2_feasibility/<run_id>/<airline>.png
  data/results/step2_feasibility_<run_id>.csv      (summary table)

Run from the project folder:
    .venv\\Scripts\\python.exe src\\feasibility_scan.py
"""

import csv
import json
import re
import sys
import time
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------- settings

AIRLINES = [
    # (short id used in file names, display name, homepage URL)
    ("air_india", "Air India", "https://www.airindia.com"),
    ("indigo", "IndiGo", "https://www.goindigo.in"),
    ("ana", "ANA", "https://www.ana.co.jp/en/jp/"),
    ("jal", "JAL", "https://www.jal.co.jp/jp/en/"),
    ("lufthansa", "Lufthansa", "https://www.lufthansa.com"),
    ("emirates", "Emirates", "https://www.emirates.com"),
]

# Only check WCAG 2.0 and 2.1, Level A and AA (our research scope).
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]

WAIT_BETWEEN_SITES_S = 10  # politeness rule from CLAUDE.md (at least 10 s)
PAGE_LOAD_TIMEOUT_MS = 60_000  # give up on a page after 60 s
SETTLE_TIME_S = 3  # extra pause so late JavaScript can finish drawing the page
VIEWPORT = {"width": 1366, "height": 768}  # a common laptop screen size

# HTTP status codes that usually mean "you are not allowed in".
BLOCK_STATUS_CODES = {401, 403, 405, 429, 503}

# Phrases that typically appear on bot-protection / block pages.
BLOCK_PHRASES = [
    "access denied",
    "request unsuccessful",
    "are you a robot",
    "verify you are human",
    "verifying you are human",
    "just a moment",
    "attention required",
    "pardon our interruption",
    "captcha",
    "unusual traffic",
    "you have been blocked",
    "request blocked",
]

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AXE_PATH = PROJECT_ROOT / "node_modules" / "axe-core" / "axe.min.js"


# ---------------------------------------------------------------- helpers

def utc_now():
    """Current time in UTC as an ISO string, e.g. 2026-11-11T15:04:05+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def redact_ips(text):
    """
    Replace IP addresses with [IP REDACTED]. Some block pages print the visitor's
    own IP address (Lufthansa did in Step 2), and this repo is public.
    """
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[IP REDACTED]", text)  # IPv4
    text = re.sub(r"\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b", "[IP REDACTED]", text)  # IPv6
    return text


def detect_block(http_status, title, body_text):
    """
    Decide whether the page we got is a block page instead of the real homepage.
    Returns a reason string if blocked, or None if the page looks normal.
    """
    if http_status in BLOCK_STATUS_CODES:
        return f"HTTP status {http_status}"

    # Only look at the title and the start of the visible text. Block pages are short,
    # and this avoids false alarms from words deep inside a normal page.
    text_to_check = (title + " " + body_text[:2000]).lower()
    for phrase in BLOCK_PHRASES:
        if phrase in text_to_check:
            return f"block phrase found: '{phrase}'"

    if len(body_text.strip()) < 100:
        return "page has almost no visible text (possible block or failed load)"

    return None


def inject_axe(page, axe_source):
    """
    Load axe-core into the page and into every iframe, so content inside
    iframes is checked too. page.evaluate() runs through the browser's debugging
    channel, so the site's Content-Security-Policy does not stop the injection.

    By default axe-core only talks to iframes from the SAME origin (domain) as the page,
    and silently skips others. Booking widgets and chat boxes are often loaded from
    other domains, and users still have to use them, so we allow all origins.
    (Tested in Step 2: without this setting cross-origin iframes were not scanned.)
    In the results, an element inside an iframe has a "target" list with more than
    one entry: [iframe selector, element selector].

    Frames that cannot be injected are skipped and counted.
    """
    allow_all = "axe.configure({ allowedOrigins: ['<unsafe_all_origins>'] })"
    page.evaluate(axe_source)
    page.evaluate(allow_all)
    skipped_frames = 0
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame.evaluate(axe_source)
            frame.evaluate(allow_all)
        except PlaywrightError:
            skipped_frames += 1
    return skipped_frames


def count_by_impact(violations):
    """Count affected elements (nodes) per impact level: critical/serious/moderate/minor."""
    counts = {"critical": 0, "serious": 0, "moderate": 0, "minor": 0}
    for v in violations:
        impact = v.get("impact") or "minor"
        counts[impact] = counts.get(impact, 0) + len(v["nodes"])
    return counts


# ---------------------------------------------------------------- one site

def scan_site(browser, airline_id, name, url, axe_source, out_raw, out_shots):
    """Scan one homepage and return a summary row (dict) for the table."""
    record = {
        "airline_id": airline_id,
        "airline": name,
        "url": url,
        "scan_started_utc": utc_now(),
        "tool_versions": {
            "python": sys.version.split()[0],
            "playwright": version("playwright"),
            "browser": f"chromium {browser.version}",
        },
        "settings": {
            "wcag_tags": WCAG_TAGS,
            "viewport": VIEWPORT,
            "headless": True,
            "page_load_timeout_ms": PAGE_LOAD_TIMEOUT_MS,
            "settle_time_s": SETTLE_TIME_S,
        },
        "status": None,  # "ok", "blocked" or "error"
        "block_reason": None,
        "error": None,
    }

    # A fresh context = like a brand-new browser profile (no cookies from other sites).
    context = browser.new_context(viewport=VIEWPORT, locale="en-US")
    page = context.new_page()
    record["user_agent"] = page.evaluate("navigator.userAgent")

    try:
        t0 = time.time()
        response = page.goto(url, wait_until="domcontentloaded", timeout=PAGE_LOAD_TIMEOUT_MS)
        # Many airline sites keep loading things forever, so "network idle" may never
        # happen. We wait up to 15 s for it and then continue anyway.
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
        block_reason = detect_block(record["http_status"], record["page_title"], body_text)

        # Full-page screenshot. Screenshots of BLOCK pages get a "_blocked" suffix;
        # .gitignore keeps those off GitHub because they can show our own IP address.
        suffix = "_blocked" if block_reason else ""
        shot_path = out_shots / f"{airline_id}{suffix}.png"
        try:
            page.screenshot(path=str(shot_path), full_page=True, timeout=30_000)
        except PlaywrightError:
            page.screenshot(path=str(shot_path), timeout=30_000)  # fall back to visible area
        record["screenshot"] = shot_path.relative_to(PROJECT_ROOT).as_posix()

        if block_reason:
            record["status"] = "blocked"
            record["block_reason"] = block_reason
            record["visible_text_start"] = redact_ips(body_text[:500])  # evidence for the notes
        else:
            record["frames_total"] = len(page.frames)
            record["frames_not_injected"] = inject_axe(page, axe_source)
            results = page.evaluate(
                """async (tags) => await axe.run(document, {
                       runOnly: { type: 'tag', values: tags },
                       resultTypes: ['violations']
                   })""",
                WCAG_TAGS,
            )
            record["tool_versions"]["axe_core"] = results["testEngine"]["version"]
            record["status"] = "ok"
            record["axe_results"] = results

    except PlaywrightError as e:
        record["status"] = "error"
        record["error"] = str(e).splitlines()[0]  # first line is enough
    finally:
        record["scan_finished_utc"] = utc_now()
        context.close()

    # Save the raw record. Each run has its own folder, so nothing is overwritten.
    with open(out_raw / f"{airline_id}.json", "w", encoding="utf-8") as f:
        json.dump(record, f, indent=2, ensure_ascii=False)

    # Build the summary row.
    row = {
        "airline": name,
        "status": record["status"],
        "http": record.get("http_status"),
        "load_s": record.get("load_time_s"),
        "rules_failed": None,
        "elements_failed": None,
        "critical": None, "serious": None, "moderate": None, "minor": None,
        "note": record["block_reason"] or record["error"] or "",
    }
    if record["status"] == "ok":
        violations = record["axe_results"]["violations"]
        row["rules_failed"] = len(violations)
        row["elements_failed"] = sum(len(v["nodes"]) for v in violations)
        row.update(count_by_impact(violations))
    return row


# ---------------------------------------------------------------- main

def print_table(rows):
    cols = ["airline", "status", "http", "load_s", "rules_failed", "elements_failed",
            "critical", "serious", "moderate", "minor", "note"]
    show = lambda v: "-" if v is None else str(v)
    widths = {c: max(len(c), *(len(show(r[c])) for r in rows)) for c in cols}
    print("  ".join(c.ljust(widths[c]) for c in cols))
    print("  ".join("-" * widths[c] for c in cols))
    for r in rows:
        print("  ".join(show(r[c]).ljust(widths[c]) for c in cols))


def main():
    if not AXE_PATH.exists():
        print(f"ERROR: axe-core not found at {AXE_PATH}. Run `npm install` first.")
        sys.exit(1)
    axe_source = AXE_PATH.read_text(encoding="utf-8")

    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out_raw = PROJECT_ROOT / "data" / "raw" / "step2_feasibility" / run_id
    out_shots = PROJECT_ROOT / "screenshots" / "step2_feasibility" / run_id
    out_raw.mkdir(parents=True)
    out_shots.mkdir(parents=True)
    print(f"Run id: {run_id}\n")

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for i, (airline_id, name, url) in enumerate(AIRLINES):
            print(f"[{i + 1}/{len(AIRLINES)}] Scanning {name}: {url}", flush=True)
            row = scan_site(browser, airline_id, name, url, axe_source, out_raw, out_shots)
            print(f"      -> {row['status']} {row['note']}", flush=True)
            rows.append(row)
            if i < len(AIRLINES) - 1:
                time.sleep(WAIT_BETWEEN_SITES_S)  # politeness pause
        browser.close()

    # Save the summary table (processed output goes to data/results/).
    summary_path = PROJECT_ROOT / "data" / "results" / f"step2_feasibility_{run_id}.csv"
    with open(summary_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print()
    print_table(rows)
    print(f"\nRaw JSON   : {out_raw.relative_to(PROJECT_ROOT)}")
    print(f"Screenshots: {out_shots.relative_to(PROJECT_ROOT)}")
    print(f"Summary CSV: {summary_path.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
