"""
compare_live_vs_capture.py - does scanning a SAVED COPY give the same result as
scanning the LIVE page?

This matters for the paper: our main method scans saved SingleFile copies, so we
must show how close those results are to scanning the real live page. We can only
check this for airlines that allowed automated access (see automated_access.csv).

How pages are matched:
  Each saved-copy scan (data/raw/capture_scans/) is paired with the live scan
  (data/raw/live_scans/) of the same airline + page type + URL (the live page's final URL
  must equal the captured URL) that is CLOSEST IN TIME to the capture. Websites change, so a big time gap makes the comparison weak;
  pairs more than 24 hours apart get a warning.

Outputs (rewritten every time; they are calculated from the raw files):
  data/results/live_vs_capture_pages.csv  one row per page: counts + which rules differ
  data/results/live_vs_capture_rules.csv  one row per page per rule: elements live vs copy

Key numbers per page:
  rules_in_both / rules_only_live / rules_only_capture
      which axe rules failed on both versions, or on only one of them
  rule_jaccard
      overlap of the two sets of failed rules: |both| / |either|.
      1.0 = exactly the same rules failed, 0.0 = no rule in common.

Run:  .venv\\Scripts\\python.exe src\\compare_live_vs_capture.py
"""

import csv
import json
from datetime import datetime

import axe_runner as ax
from register_captures import normalize  # same URL normalisation as when registering captures

LIVE_DIR = ax.PROJECT_ROOT / "data" / "raw" / "live_scans"
CAPTURE_DIR = ax.PROJECT_ROOT / "data" / "raw" / "capture_scans"
RESULTS_DIR = ax.PROJECT_ROOT / "data" / "results"
MAX_GAP_HOURS = 24  # pairs further apart than this get a warning


def load_ok_scans(folder):
    """Load every successful scan JSON in folder/<run_id>/*.json."""
    scans = []
    for path in sorted(folder.glob("*/*.json")):
        with open(path, encoding="utf-8") as f:
            record = json.load(f)
        if record.get("status") == "ok":
            record["_path"] = ax.project_relative(path)
            scans.append(record)
    return scans


def rule_counts(record):
    """{rule id: (impact, number of failing elements)} for one scan."""
    return {v["id"]: (v.get("impact"), len(v["nodes"])) for v in record["axe_results"]["violations"]}


def to_time(iso_text):
    return datetime.fromisoformat(iso_text) if iso_text else None


def same_url(live, capture):
    """
    True if the live scan ended on the same URL that was captured. Added after Finnair's
    homepage was re-captured: the old live scan showed the country-selection page
    (https://www.finnair.com/), the new capture is https://www.finnair.com/fi-en -
    different pages that must not be compared.
    """
    live_url = live.get("final_url") or live.get("url") or ""
    return normalize(live_url) == normalize(capture.get("url") or "")


def pick_live_scan(capture, live_scans):
    """
    The live scan of the same page (same airline, page type AND URL) closest in time to
    the capture (or the latest one). Returns (live scan or None, number of live scans of the
    same airline/page type that were skipped because their URL differs).
    """
    candidates = [s for s in live_scans
                  if s["airline_id"] == capture["airline_id"] and s["page_type"] == capture["page_type"]]
    same_page = [s for s in candidates if same_url(s, capture)]
    skipped = len(candidates) - len(same_page)
    if not same_page:
        return None, skipped
    captured = to_time(capture.get("captured_utc"))
    if captured is None:  # capture time unknown: use the most recent live scan
        return max(same_page, key=lambda s: s["scan_started_utc"]), skipped
    return min(same_page, key=lambda s: abs(to_time(s["scan_started_utc"]) - captured)), skipped


def compare(capture, live):
    """Build the page row and the rule rows for one live/capture pair."""
    live_rules, cap_rules = rule_counts(live), rule_counts(capture)
    both = sorted(live_rules.keys() & cap_rules.keys())
    only_live = sorted(live_rules.keys() - cap_rules.keys())
    only_cap = sorted(cap_rules.keys() - live_rules.keys())
    either = live_rules.keys() | cap_rules.keys()

    captured = to_time(capture.get("captured_utc"))
    gap_hours = None
    warnings = []
    if captured is None:
        warnings.append("capture time unknown (check log.csv)")
    else:
        gap_hours = round(abs((to_time(live["scan_started_utc"]) - captured).total_seconds()) / 3600, 2)
        if gap_hours > MAX_GAP_HOURS:
            warnings.append(f"live scan and capture are {gap_hours} h apart")

    page_row = {
        "airline_id": capture["airline_id"],
        "page_type": capture["page_type"],
        "capture_file": capture["file_name"],
        "captured_utc": capture.get("captured_utc"),
        "live_scanned_utc": live["scan_started_utc"],
        "gap_hours": gap_hours,
        "live_rules": len(live_rules),
        "capture_rules": len(cap_rules),
        "live_elements": sum(n for _, n in live_rules.values()),
        "capture_elements": sum(n for _, n in cap_rules.values()),
        "rules_in_both": len(both),
        "rules_only_live": ";".join(only_live),
        "rules_only_capture": ";".join(only_cap),
        "rule_jaccard": round(len(both) / len(either), 3) if either else 1.0,
        "live_scan_file": live["_path"],
        "capture_scan_file": capture["_path"],
        "warning": "; ".join(warnings),
    }

    rule_rows = []
    for rule in sorted(either):
        impact = (live_rules.get(rule) or cap_rules.get(rule))[0]
        live_n = live_rules.get(rule, (None, 0))[1]
        cap_n = cap_rules.get(rule, (None, 0))[1]
        rule_rows.append({
            "airline_id": capture["airline_id"],
            "page_type": capture["page_type"],
            "capture_file": capture["file_name"],
            "rule": rule,
            "impact": impact,
            "live_elements": live_n,
            "capture_elements": cap_n,
            "difference": cap_n - live_n,
        })
    return page_row, rule_rows


def write_csv(path, rows):
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def main():
    live_scans = load_ok_scans(LIVE_DIR)
    capture_scans = load_ok_scans(CAPTURE_DIR)
    print(f"Found {len(live_scans)} live scans and {len(capture_scans)} saved-copy scans (status ok).")

    page_rows, rule_rows = [], []
    for capture in capture_scans:
        live, skipped = pick_live_scan(capture, live_scans)
        if skipped:
            print(f"NOTE: {capture['file_name']}: {skipped} live scan(s) of {capture['airline_id']} "
                  f"{capture['page_type']} skipped because their URL differs from the captured URL")
        if live is None:
            continue  # no live scan for this page (normal for airlines that block us)
        page_row, rows = compare(capture, live)
        page_rows.append(page_row)
        rule_rows.extend(rows)

    if not page_rows:
        print("No page has both a live scan and a saved-copy scan yet. Nothing to compare.")
        return

    write_csv(RESULTS_DIR / "live_vs_capture_pages.csv", page_rows)
    write_csv(RESULTS_DIR / "live_vs_capture_rules.csv", rule_rows)

    print()
    for r in page_rows:
        print(f"{r['airline_id']} {r['page_type']} ({r['capture_file']}), gap {r['gap_hours']} h")
        print(f"   rules failed   live {r['live_rules']:>3} | copy {r['capture_rules']:>3} | in both {r['rules_in_both']} | overlap (Jaccard) {r['rule_jaccard']}")
        print(f"   elements       live {r['live_elements']:>3} | copy {r['capture_elements']:>3}")
        if r["rules_only_live"]:
            print(f"   only live   : {r['rules_only_live']}")
        if r["rules_only_capture"]:
            print(f"   only copy   : {r['rules_only_capture']}")
        if r["warning"]:
            print(f"   WARNING     : {r['warning']}")
    print(f"\nWrote data/results/live_vs_capture_pages.csv and live_vs_capture_rules.csv")


if __name__ == "__main__":
    main()
