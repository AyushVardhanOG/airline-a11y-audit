"""
open_batch.py - open all pages of ONE region from data/airlines.csv as tabs in my normal
Chrome, in my capture profile ("a11y-capture"), so I can save them by hand with SingleFile.

This script only OPENS tabs. It does not click, type, save or scan anything: I do the
capturing myself, following docs/capture_guide.md.

What it does:
  1. Finds the folder of the Chrome profile named "a11y-capture" in Chrome's "Local State"
     file (e.g. "Profile 4"). If that profile does not exist, it stops - it never falls back
     to another profile (my personal profiles are signed in to accounts).
  2. Collects the URLs of the region's airlines (homepage, checkin_url, assistance_url),
     skipping MISSING / empty URLs and airlines already marked url_verified = yes.
  3. Opens them ONE TAB AT A TIME, waiting 10 s between tabs, so the same airline's site
     never gets several page loads at the same moment (CLAUDE.md rule 1).
  4. Prints the file name each saved page should get (airline_pagetype_YYYYMMDD.html).

Usage (region names exactly as in data/airlines.csv; quotes needed for names with spaces):
    python src\\open_batch.py India
    python src\\open_batch.py Japan/Asia
    python src\\open_batch.py Europe
    python src\\open_batch.py "North America"
    python src\\open_batch.py "Middle East/Oceania"
Options:
    --delay 10     seconds between tabs (minimum 10)
    --dry-run      only list the tabs, do not open Chrome
"""

import argparse
import csv
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AIRLINES_PATH = PROJECT_ROOT / "data" / "airlines.csv"

PROFILE_NAME = "a11y-capture"  # the profile name shown in Chrome's profile menu
CHROME_USER_DATA = Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "User Data"
CHROME_EXE_CANDIDATES = [
    Path(os.environ.get("PROGRAMFILES", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("PROGRAMFILES(X86)", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
    Path(os.environ.get("LOCALAPPDATA", "")) / "Google" / "Chrome" / "Application" / "chrome.exe",
]
URL_COLUMNS = {"home": "homepage", "checkin": "checkin_url", "assistance": "assistance_url"}
MIN_DELAY_S = 10  # politeness rule: at least 10 s


def find_chrome():
    for path in CHROME_EXE_CANDIDATES:
        if path.exists():
            return path
    sys.exit("ERROR: chrome.exe not found in the usual places.")


def find_profile_folder(profile_name):
    """
    Chrome keeps a list of profiles in "User Data/Local State" (a JSON file):
      {"profile": {"info_cache": {"Profile 4": {"name": "a11y-capture", ...}, ...}}}
    Return the folder name (e.g. "Profile 4") whose display name is profile_name.
    """
    local_state = CHROME_USER_DATA / "Local State"
    if not local_state.exists():
        sys.exit(f"ERROR: Chrome's Local State file not found at {local_state}")
    profiles = json.loads(local_state.read_text(encoding="utf-8"))["profile"]["info_cache"]
    matches = [folder for folder, info in profiles.items() if info.get("name") == profile_name]
    if len(matches) != 1:
        names = ", ".join(repr(info.get("name")) for info in profiles.values())
        sys.exit(f"ERROR: expected exactly one Chrome profile named {profile_name!r}, "
                 f"found {len(matches)}. Profiles: {names}. Not opening anything.")
    return matches[0]


def pages_for_region(region):
    """[(airline_id, page_type, url)] for one region, skipping MISSING and verified airlines."""
    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    regions = sorted({r["region"] for r in rows})
    chosen = [r for r in rows if r["region"].lower() == region.lower()]
    if not chosen:
        sys.exit(f"ERROR: unknown region {region!r}. Use one of: {', '.join(regions)}")

    pages, skipped = [], []
    for r in chosen:
        if (r.get("excluded_reason") or "").strip():  # e.g. blocked_for_human_visitor
            skipped.append(f"{r['airline_id']} (excluded: {r['excluded_reason'].strip()})")
            continue
        if r["url_verified"].strip().lower() == "yes":
            skipped.append(f"{r['airline_id']} (url_verified = yes)")
            continue
        for page_type, column in URL_COLUMNS.items():
            url = r[column].strip()
            # MISSING = no such page; SAME_AS_HOME = the page is really the homepage.
            # (Same rule as axe_runner.is_real_url; repeated here so this script runs
            # with plain Python, without Playwright installed.)
            if not url or url.upper() in ("MISSING", "SAME_AS_HOME"):
                skipped.append(f"{r['airline_id']} {page_type} ({url or 'empty'})")
                continue
            pages.append((r["airline_id"], page_type, url))
    return pages, skipped


def main():
    parser = argparse.ArgumentParser(description="Open one region's pages as tabs in the capture profile.")
    parser.add_argument("region", help='e.g. India, Japan/Asia, Europe, "North America", "Middle East/Oceania"')
    parser.add_argument("--delay", type=float, default=MIN_DELAY_S, help="seconds between tabs (min 10)")
    parser.add_argument("--dry-run", action="store_true", help="only list the tabs")
    args = parser.parse_args()
    delay = max(args.delay, MIN_DELAY_S)

    pages, skipped = pages_for_region(args.region)
    today = datetime.now().strftime("%Y%m%d")

    print(f"Region {args.region}: {len(pages)} tab(s) to open")
    for airline_id, page_type, url in pages:
        print(f"  {airline_id}_{page_type}_{today}.html  <-  {url}")
    for s in skipped:
        print(f"  skipped: {s}")
    if not pages or args.dry_run:
        return

    chrome = find_chrome()
    profile_folder = find_profile_folder(PROFILE_NAME)
    print(f"\nOpening in Chrome profile {PROFILE_NAME!r} (folder {profile_folder!r}), "
          f"one tab every {delay:.0f} s. Total about {delay * (len(pages) - 1) / 60:.1f} min.")

    for i, (airline_id, page_type, url) in enumerate(pages):
        # --profile-directory picks the profile; if Chrome is already running, it opens the
        # URL as a new tab in that profile's window. Popen = do not wait for Chrome to close.
        subprocess.Popen([str(chrome), f"--profile-directory={profile_folder}", url])
        print(f"  [{i + 1}/{len(pages)}] opened {airline_id} {page_type}", flush=True)
        if i < len(pages) - 1:
            time.sleep(delay)

    print("\nDone. Save each tab with SingleFile, then run src\\register_captures.py.")


if __name__ == "__main__":
    main()
