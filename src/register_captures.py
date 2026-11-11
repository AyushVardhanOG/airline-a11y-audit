"""
register_captures.py - rename new SingleFile captures and add them to data/captures/log.csv.

SingleFile saves pages with long names like
    "Online Check-in｜ ANA (11_11_2026 9：37：56 PM).html"
and writes a comment at the top of each file:
    Page saved with SingleFile
    url: https://aswbe.ana.co.jp/webapps/checkin/checkin-search?LANG=en&CONNECTION_KIND=CHE
    saved date: Wed Nov 11 2026 21:37:56 GMT+0900 (Japan Standard Time)

For every .html file in data/captures/ that does NOT yet follow the naming rule
(airline_pagetype_YYYYMMDD.html), this script:
  1. reads the URL and saved date from that header;
  2. finds which airline + page type it is, by comparing the URL with the URLs in
     data/airlines.csv (so put the FINAL URL - after any redirect - into airlines.csv first);
  3. renames the file to <airline_id>_<page_type>_<YYYYMMDD>.html (date = local save date);
  4. adds a row to data/captures/log.csv (local time + UTC offset from the header,
     browser and SingleFile versions from the command line, empty notes).

Files whose URL matches nothing in airlines.csv are NOT touched; the script prints
their URL so you can fix airlines.csv and run it again. Existing files are never overwritten.
The file CONTENTS are never changed (only the name).

Run (versions from chrome://version and chrome://extensions):
    .venv\\Scripts\\python.exe src\\register_captures.py --chrome 157.0.8103.40 --singlefile 1.37.0
    add --dry-run to only show what would happen.
"""

import argparse
import csv
import re
import sys
from datetime import datetime

import axe_runner as ax
from scan_captures import CAPTURES_DIR, FILE_NAME_RE, LOG_PATH, read_singlefile_header

AIRLINES_PATH = ax.PROJECT_ROOT / "data" / "airlines.csv"
URL_COLUMNS = {"home": "homepage", "checkin": "checkin_url", "assistance": "assistance_url"}
LOG_COLUMNS = ["file_name", "airline_id", "page_type", "url", "captured_at_local", "utc_offset",
               "browser", "browser_version", "singlefile_version", "notes"]

# "Wed Nov 11 2026 21:37:56 GMT+0900 (Japan Standard Time)"
SAVED_DATE_RE = re.compile(r"(\w{3} \d{1,2} \d{4} \d{2}:\d{2}:\d{2}) GMT([+-])(\d{2})(\d{2})")


def normalize(url):
    """Make URLs comparable: lower-case scheme/host, no trailing slash (query string kept)."""
    url = url.strip()
    if "://" not in url:
        return url
    scheme, rest = url.split("://", 1)
    host, _, path = rest.partition("/")
    return f"{scheme.lower()}://{host.lower()}/{path}".rstrip("/")


def url_lookup():
    """{normalized URL: (airline_id, page_type)} from data/airlines.csv."""
    lookup = {}
    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            for page_type, column in URL_COLUMNS.items():
                url = row[column].strip()
                if ax.is_real_url(url):  # skips empty, MISSING and SAME_AS_HOME
                    lookup[normalize(url)] = (row["airline_id"], page_type)
    return lookup


def parse_saved_date(text):
    """Return (local datetime without zone, '+09:00'-style offset) or (None, None)."""
    m = SAVED_DATE_RE.search(text or "")
    if not m:
        return None, None
    local = datetime.strptime(m.group(1), "%b %d %Y %H:%M:%S")
    return local, f"{m.group(2)}{m.group(3)}:{m.group(4)}"


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    parser.add_argument("--chrome", required=True, help="Chrome version (chrome://version)")
    parser.add_argument("--singlefile", required=True, help="SingleFile version (chrome://extensions)")
    parser.add_argument("--dry-run", action="store_true", help="only show what would happen")
    args = parser.parse_args()

    # SingleFile names contain characters like "｜" that the Windows console's default
    # encoding cannot print; print them as UTF-8 instead of crashing.
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    lookup = url_lookup()
    new_rows = []
    planned_names = set()  # names given in this run (so the dry run is accurate too)
    for path in sorted(CAPTURES_DIR.glob("*.html")):
        if FILE_NAME_RE.match(path.name):
            continue  # already registered
        header = read_singlefile_header(path.read_text(encoding="utf-8", errors="replace"))
        if not header["found"] or not header.get("url"):
            print(f"SKIP (no SingleFile header with a URL): {path.name}")
            continue
        match = lookup.get(normalize(header["url"]))
        if match is None:
            print(f"SKIP (URL not in data/airlines.csv - put the final URL there and rerun):\n"
                  f"     {path.name}\n     url: {header['url']}")
            continue
        local, offset = parse_saved_date(header.get("saved_date"))
        if local is None:
            print(f"SKIP (could not read the saved date '{header.get('saved_date')}'): {path.name}")
            continue

        airline_id, page_type = match
        new_name = f"{airline_id}_{page_type}_{local:%Y%m%d}.html"
        target = CAPTURES_DIR / new_name
        if target.exists() or new_name in planned_names:
            # Two captures of the same page on the same day (e.g. a URL that redirected to
            # the homepage). Keep the first, leave this one untouched for a person to decide.
            print(f"SKIP (another capture already has the name {new_name}; left untouched):\n"
                  f"     {path.name}")
            continue
        planned_names.add(new_name)

        print(f"{'WOULD RENAME' if args.dry_run else 'RENAMED'}: {path.name}\n     -> {new_name}")
        if not args.dry_run:
            path.rename(target)
        new_rows.append({
            "file_name": new_name,
            "airline_id": airline_id,
            "page_type": page_type,
            "url": header["url"],
            "captured_at_local": f"{local:%Y-%m-%d %H:%M:%S}",
            "utc_offset": offset,
            "browser": "Chrome",
            "browser_version": args.chrome,
            "singlefile_version": args.singlefile,
            "notes": "",
        })

    if new_rows and not args.dry_run:
        with open(LOG_PATH, "a", newline="", encoding="utf-8") as f:
            csv.DictWriter(f, fieldnames=LOG_COLUMNS).writerows(new_rows)
        print(f"\nAdded {len(new_rows)} row(s) to {LOG_PATH.relative_to(ax.PROJECT_ROOT)}. "
              "Add your notes in its 'notes' column.")
    elif not new_rows:
        print("Nothing to register.")


if __name__ == "__main__":
    main()
