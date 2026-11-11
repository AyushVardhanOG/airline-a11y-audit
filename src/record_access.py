"""
record_access.py - record, as a research RESULT, which airlines blocked automated access.

Input : data/results/step2_feasibility_<run_id>.csv  (summary of the Step 2 live test)
        data/airlines.csv                            (the full airline list)
Output: data/results/automated_access.csv

We read the Step 2 summary CSV (not the raw JSON) because one raw file
(Lufthansa) is kept off GitHub for privacy, so the CSV is the copy everyone has.

Result categories:
  allowed              real page loaded and was scanned
  blocked              server refused with a "go away" HTTP status (e.g. 403)
  blocked_unconfirmed  page loaded but looked like a block/error page; cannot be sure
  error                page did not load at all (e.g. connection cut); cause unknown
  not_tested           airline was not part of the Step 2 test

Run:  .venv\\Scripts\\python.exe src\\record_access.py
"""

import csv

import axe_runner as ax

STEP2_RUN_ID = "20261111T115319Z"
STEP2_SUMMARY = ax.PROJECT_ROOT / "data" / "results" / f"step2_feasibility_{STEP2_RUN_ID}.csv"
AIRLINES_PATH = ax.PROJECT_ROOT / "data" / "airlines.csv"
OUT_PATH = ax.PROJECT_ROOT / "data" / "results" / "automated_access.csv"


def classify(step2_row):
    """Turn a Step 2 summary row into one of the result categories above."""
    status = step2_row["status"]
    http = int(step2_row["http"]) if step2_row["http"] else None
    if status == "ok":
        return "allowed"
    if status == "blocked" and http in ax.BLOCK_STATUS_CODES:
        return "blocked"
    if status == "blocked":
        return "blocked_unconfirmed"
    return "error"


def main():
    with open(STEP2_SUMMARY, newline="", encoding="utf-8") as f:
        step2 = {r["airline"]: r for r in csv.DictReader(f)}  # keyed by display name

    rows = []
    with open(AIRLINES_PATH, newline="", encoding="utf-8") as f:
        for airline in csv.DictReader(f):
            s2 = step2.get(airline["airline"])
            result = classify(s2) if s2 else "not_tested"
            rows.append({
                "airline_id": airline["airline_id"],
                "airline": airline["airline"],
                "region": airline["region"],
                "result": result,
                "http_status": s2["http"] if s2 else "",
                "evidence": s2["note"] if s2 else "",
                "tested_in_run": STEP2_RUN_ID if s2 else "",
                "live_scan_kept": "yes" if result == "allowed" else "no",
            })

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    tested = [r for r in rows if r["result"] != "not_tested"]
    print(f"Wrote {OUT_PATH.relative_to(ax.PROJECT_ROOT)}")
    for r in tested:
        print(f"  {r['airline']:<12} {r['result']:<20} {r['evidence']}")
    print(f"  ({len(rows) - len(tested)} airlines not tested)")


if __name__ == "__main__":
    main()
