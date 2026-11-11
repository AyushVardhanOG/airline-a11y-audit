"""
record_access.py - record, as a research RESULT, which airlines blocked automated access.

Inputs (summary CSVs of headless homepage visits):
  data/results/step2_feasibility_<run_id>.csv   Step 2: 6 airlines (visit + axe scan)
  data/results/access_test_<run_id>.csv         Step 4 part 1: the other airlines (visit only),
                                                 found automatically, oldest first
  data/airlines.csv                              the full airline list
Output:
  data/results/automated_access.csv

We read the summary CSVs (not the raw JSON) because some raw files are kept off
GitHub for privacy, so the CSVs are the copy everyone has.
If the same airline appears in several runs, the LATEST run wins.

Result categories:
  allowed              real page loaded
  blocked              refused with a "go away" HTTP status (e.g. 403), OR the page
                       contained a clear block phrase (e.g. "access denied", "captcha")
  blocked_unconfirmed  we got an error page instead of the real page (almost no text, or an
                       HTTP error status like 404/406) but no explicit block message;
                       most likely bot protection, but not proven
  error                page did not load at all (e.g. connection cut, timeout); cause unknown
  not_tested           airline has not been visited yet

Run:  .venv\\Scripts\\python.exe src\\record_access.py
"""

import csv
from collections import Counter

import axe_runner as ax

RESULTS_DIR = ax.PROJECT_ROOT / "data" / "results"
STEP2_RUN_ID = "20261111T115319Z"
AIRLINES_PATH = ax.PROJECT_ROOT / "data" / "airlines.csv"
OUT_PATH = RESULTS_DIR / "automated_access.csv"


def source_files():
    """(run_id, label, path) for every summary CSV, oldest first."""
    sources = [(STEP2_RUN_ID, "step2_feasibility", RESULTS_DIR / f"step2_feasibility_{STEP2_RUN_ID}.csv")]
    for path in sorted(RESULTS_DIR.glob("access_test_*.csv")):  # run ids sort by time
        sources.append((path.stem.removeprefix("access_test_"), "step4_access_test", path))
    return sources


def classify(row):
    """Turn a summary row into one of the result categories above."""
    status = row["status"]
    http = int(row["http"]) if row["http"] else None
    if status == "ok" and http is not None and http >= 400:
        # Run 20261111T121946Z was made before detect_block() checked all HTTP error codes:
        # Singapore Airlines (404) and Alaska (406) were marked "ok" but their screenshots
        # show error pages, not homepages. An error status is never counted as "allowed".
        return "blocked_unconfirmed"
    if status == "ok":
        return "allowed"
    if status == "blocked" and http in ax.BLOCK_STATUS_CODES:
        return "blocked"
    if status == "blocked" and row["note"].startswith("block phrase found"):
        return "blocked"
    if status == "blocked":
        return "blocked_unconfirmed"
    return "error"


def main():
    # Latest result per airline (keyed by display name, as in the summary CSVs).
    latest = {}
    for run_id, label, path in source_files():
        with open(path, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                latest[row["airline"]] = (run_id, label, row)

    rows = []
    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        for airline in csv.DictReader(f):
            run_id, label, s = latest.get(airline["airline"], ("", "", None))
            result = classify(s) if s else "not_tested"
            evidence = s["note"] if s else ""
            if s and not evidence and result != "allowed":  # explain re-classified rows
                evidence = f"HTTP {s['http']} error page instead of homepage (title: {s.get('page_title', '')})"
            rows.append({
                "airline_id": airline["airline_id"],
                "airline": airline["airline"],
                "region": airline["region"],
                "result": result,
                "http_status": s["http"] if s else "",
                "evidence": evidence,
                "tested_in": label,
                "tested_in_run": run_id,
                "live_scan_kept": "yes" if result == "allowed" else "no",
            })

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"Wrote {OUT_PATH.relative_to(ax.PROJECT_ROOT)}\n")
    for r in rows:
        print(f"  {r['airline']:<20} {r['result']:<20} {r['http_status']:<4} {r['evidence'][:70]}")
    print("\nTotals:", dict(Counter(r["result"] for r in rows)))


if __name__ == "__main__":
    main()
