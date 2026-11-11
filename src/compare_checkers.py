"""
compare_checkers.py - Objective 1: compare the two checkers, axe-core and Pa11y
(HTML_CodeSniffer, WCAG2AA), on the same 78 saved copies.

Why compare by WCAG success criterion?
  The tools name their checks differently (axe "image-alt" vs HTML_CodeSniffer
  "WCAG2AA.Principle1.Guideline1_1.1_1_1.H37"), and they point at elements with different
  selector styles, so findings cannot be matched one-to-one reliably. Both, however, say
  which WCAG success criterion (SC) a finding belongs to (e.g. 1.1.1 Non-text Content).
  So for every page we compare the SET of success criteria each tool reports as failed.

Inputs (read only):
  data/raw/capture_scans/<run>/*.json   axe-core results (latest run, or --axe-run)
  data/raw/pa11y_scans/<run>/*.json     Pa11y results (latest run, or --pa11y-run)
Outputs (rewritten every run):
  data/results/checker_comparison_pages.csv     one row per page: SCs found by both / only one tool
  data/results/checker_comparison_criteria.csv  one row per SC: on how many pages each tool flagged it
  data/results/charts/checker_agreement_by_criterion.png (+ .csv with the numbers shown)

Counting rules:
  - axe-core: "violations" only. An axe rule can map to several SCs (e.g. link-name -> 2.4.4 and 4.1.2).
  - Pa11y: "errors" only (warnings/notices are "check by hand" items, not failures).
  - Agreement per page = Jaccard overlap of the two SC sets (1 = same criteria, 0 = none in common).

Run:  .venv\\Scripts\\python.exe src\\compare_checkers.py
"""

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import analyze  # shared chart style (colors, fonts) and paths

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AXE_DIR = PROJECT_ROOT / "data" / "raw" / "capture_scans"
PA11Y_DIR = PROJECT_ROOT / "data" / "raw" / "pa11y_scans"
RESULTS = PROJECT_ROOT / "data" / "results"
CHARTS = RESULTS / "charts"

# WCAG 2.1 Level A and AA success criteria (titles for readable tables and charts).
SC_TITLES = {
    "1.1.1": "Non-text Content", "1.2.1": "Audio-only and Video-only", "1.2.2": "Captions (Prerecorded)",
    "1.2.3": "Audio Description or Media Alternative", "1.2.4": "Captions (Live)", "1.2.5": "Audio Description",
    "1.3.1": "Info and Relationships", "1.3.2": "Meaningful Sequence", "1.3.3": "Sensory Characteristics",
    "1.3.4": "Orientation", "1.3.5": "Identify Input Purpose", "1.4.1": "Use of Color", "1.4.2": "Audio Control",
    "1.4.3": "Contrast (Minimum)", "1.4.4": "Resize Text", "1.4.5": "Images of Text", "1.4.10": "Reflow",
    "1.4.11": "Non-text Contrast", "1.4.12": "Text Spacing", "1.4.13": "Content on Hover or Focus",
    "2.1.1": "Keyboard", "2.1.2": "No Keyboard Trap", "2.1.4": "Character Key Shortcuts", "2.2.1": "Timing Adjustable",
    "2.2.2": "Pause, Stop, Hide", "2.3.1": "Three Flashes", "2.4.1": "Bypass Blocks", "2.4.2": "Page Titled",
    "2.4.3": "Focus Order", "2.4.4": "Link Purpose (In Context)", "2.4.5": "Multiple Ways",
    "2.4.6": "Headings and Labels", "2.4.7": "Focus Visible", "2.5.1": "Pointer Gestures",
    "2.5.2": "Pointer Cancellation", "2.5.3": "Label in Name", "2.5.4": "Motion Actuation",
    "3.1.1": "Language of Page", "3.1.2": "Language of Parts", "3.2.1": "On Focus", "3.2.2": "On Input",
    "3.2.3": "Consistent Navigation", "3.2.4": "Consistent Identification", "3.3.1": "Error Identification",
    "3.3.2": "Labels or Instructions", "3.3.3": "Error Suggestion", "3.3.4": "Error Prevention",
    "4.1.1": "Parsing", "4.1.2": "Name, Role, Value", "4.1.3": "Status Messages",
}


def latest(folder, run=None):
    if run:
        return folder / run
    runs = sorted(p for p in folder.iterdir() if p.is_dir())
    if not runs:
        raise SystemExit(f"No runs in {folder}")
    return runs[-1]


def axe_criteria(record):
    """{SC: number of failing elements} from one axe-core scan record."""
    out = {}
    for v in record["axe_results"]["violations"]:
        for t in v.get("tags", []):
            m = re.fullmatch(r"wcag(\d)(\d)(\d+)", t)
            if m:
                sc = f"{m[1]}.{m[2]}.{m[3]}"
                out[sc] = out.get(sc, 0) + len(v["nodes"])
    return out


def pa11y_criteria(record):
    """{SC: number of error issues} from one Pa11y record, e.g. ...Guideline1_4.1_4_3.G18.Fail -> 1.4.3."""
    out = {}
    for issue in record.get("issues", []):
        m = re.search(r"Guideline\d+_\d+\.(\d+)_(\d+)_(\d+)", issue["code"])
        if m:
            sc = f"{m[1]}.{m[2]}.{m[3]}"
            out[sc] = out.get(sc, 0) + 1
    return out


def sc_sort_key(sc):
    return tuple(int(x) for x in sc.split("."))


def stacked_chart(crit, n_pages, path):
    """One stacked horizontal bar per SC: pages flagged by both / only axe-core / only Pa11y."""
    parts = [("pages_both", "Both tools"), ("pages_only_axe", "Only axe-core"), ("pages_only_pa11y", "Only Pa11y")]
    colors = analyze.CATEGORICAL[:3]
    n = len(crit)
    fig, ax = plt.subplots(figsize=(9, 1.6 + 0.32 * n), dpi=150)
    y = list(range(n))
    left = [0] * n
    for (col, label), color in zip(parts, colors):
        vals = list(crit[col])
        ax.barh(y, vals, left=left, height=0.55, color=color, edgecolor=analyze.SURFACE, linewidth=1.0, label=label)
        for yi, l, v in zip(y, left, vals):
            if v >= 2:  # only label a segment that is wide enough for its number
                ax.text(l + v / 2, yi, str(v), ha="center", va="center", color="#ffffff", fontsize=8.5, fontweight="bold")
        left = [a + b for a, b in zip(left, vals)]
    for yi, total in zip(y, left):
        ax.text(total + 0.3, yi, f"{total} page" if total == 1 else f"{total} pages", va="center", ha="left",
                color=analyze.INK_2, fontsize=9)
    ax.set_yticks(y, [f"{sc} {SC_TITLES.get(sc, '')}" for sc in crit.index])
    ax.invert_yaxis()
    ax.set_xlim(0, max(left) * 1.18)
    ax.set_xlabel(f"pages (of {n_pages}) where at least one tool reports a failure of this criterion", color=analyze.INK_2)
    analyze.style_axes(ax, "Do axe-core and Pa11y flag the same WCAG criteria?",
                       "Per success criterion: pages flagged by both tools, only by axe-core, or only by Pa11y (HTML_CodeSniffer)")
    # Legend below the plot (above it, it collided with the subtitle)
    leg = ax.legend(loc="upper center", bbox_to_anchor=(0.5, -0.09), ncol=3, frameon=False, fontsize=9.5,
                    handlelength=1.2, handleheight=1.0)
    for t in leg.get_texts():
        t.set_color(analyze.INK_2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def main():
    parser = argparse.ArgumentParser(description="Compare axe-core and Pa11y results.")
    parser.add_argument("--axe-run")
    parser.add_argument("--pa11y-run")
    args = parser.parse_args()

    pa11y_dir = latest(PA11Y_DIR, args.pa11y_run)
    pa11y = {json.loads(p.read_text(encoding="utf-8"))["file_name"]: json.loads(p.read_text(encoding="utf-8"))
             for p in sorted(pa11y_dir.glob("*.json"))}
    # Use the axe run that Pa11y was run against, so both tools saw exactly the same files.
    axe_run = args.axe_run or next(iter(pa11y.values()))["capture_scan_run"]
    axe_dir = AXE_DIR / axe_run
    axe = {json.loads(p.read_text(encoding="utf-8"))["file_name"]: json.loads(p.read_text(encoding="utf-8"))
           for p in sorted(axe_dir.glob("*.json"))}

    rows, skipped = [], []
    for file_name, a in sorted(axe.items()):
        p = pa11y.get(file_name)
        if a.get("status") != "ok" or p is None or p.get("status") != "ok":
            skipped.append(file_name)
            continue
        ax_sc, pa_sc = axe_criteria(a), pa11y_criteria(p)
        both, only_a, only_p = ax_sc.keys() & pa_sc.keys(), ax_sc.keys() - pa_sc.keys(), pa_sc.keys() - ax_sc.keys()
        either = ax_sc.keys() | pa_sc.keys()
        rows.append({
            "file_name": file_name, "airline_id": a["airline_id"], "page_type": a["page_type"],
            "axe_elements": sum(len(v["nodes"]) for v in a["axe_results"]["violations"]),
            "pa11y_errors": len(p.get("issues", [])),
            "axe_criteria": len(ax_sc), "pa11y_criteria": len(pa_sc),
            "criteria_both": ";".join(sorted(both, key=sc_sort_key)),
            "criteria_only_axe": ";".join(sorted(only_a, key=sc_sort_key)),
            "criteria_only_pa11y": ";".join(sorted(only_p, key=sc_sort_key)),
            "n_both": len(both), "n_only_axe": len(only_a), "n_only_pa11y": len(only_p),
            "criteria_jaccard": round(len(both) / len(either), 3) if either else 1.0,
            "_axe": ax_sc, "_pa11y": pa_sc,
        })
    pages = pd.DataFrame(rows)

    # Per success criterion
    all_sc = sorted(set().union(*[set(r["_axe"]) | set(r["_pa11y"]) for r in rows]), key=sc_sort_key)
    crit_rows = []
    for sc in all_sc:
        in_axe = pages["_axe"].apply(lambda d: sc in d)
        in_pa = pages["_pa11y"].apply(lambda d: sc in d)
        crit_rows.append({
            "criterion": sc, "title": SC_TITLES.get(sc, ""),
            "pages_axe": int(in_axe.sum()), "pages_pa11y": int(in_pa.sum()),
            "pages_both": int((in_axe & in_pa).sum()), "pages_only_axe": int((in_axe & ~in_pa).sum()),
            "pages_only_pa11y": int((~in_axe & in_pa).sum()),
            "axe_elements": int(pages["_axe"].apply(lambda d: d.get(sc, 0)).sum()),
            "pa11y_errors": int(pages["_pa11y"].apply(lambda d: d.get(sc, 0)).sum()),
        })
    crit = pd.DataFrame(crit_rows).set_index("criterion")
    crit["pages_either"] = crit["pages_both"] + crit["pages_only_axe"] + crit["pages_only_pa11y"]
    crit = crit.sort_values(["pages_either", "pages_both"], ascending=False)

    pages.drop(columns=["_axe", "_pa11y"]).to_csv(RESULTS / "checker_comparison_pages.csv", index=False)
    crit.to_csv(RESULTS / "checker_comparison_criteria.csv")
    CHARTS.mkdir(parents=True, exist_ok=True)
    top = crit.head(12)
    top[["title", "pages_both", "pages_only_axe", "pages_only_pa11y", "pages_either"]].to_csv(
        CHARTS / "checker_agreement_by_criterion.csv")
    stacked_chart(top, len(pages), CHARTS / "checker_agreement_by_criterion.png")

    # Console summary
    n = len(pages)
    tot_both, tot_a, tot_p = pages["n_both"].sum(), pages["n_only_axe"].sum(), pages["n_only_pa11y"].sum()
    print(f"axe-core run {axe_run} vs Pa11y run {pa11y_dir.name}: {n} pages compared, {len(skipped)} skipped {skipped or ''}")
    print(f"failing elements: axe-core {pages['axe_elements'].sum()} | Pa11y errors {pages['pa11y_errors'].sum()}")
    print(f"pages with >=1 failure: axe-core {(pages['axe_elements'] > 0).sum()} | Pa11y {(pages['pa11y_errors'] > 0).sum()}")
    print(f"(page, criterion) pairs: both {tot_both} | only axe-core {tot_a} | only Pa11y {tot_p} "
          f"-> {tot_both / (tot_both + tot_a + tot_p):.0%} found by both")
    print(f"per-page criteria overlap (Jaccard): mean {pages['criteria_jaccard'].mean():.2f}, "
          f"median {pages['criteria_jaccard'].median():.2f}; identical sets on {(pages['criteria_jaccard'] == 1).sum()} pages")
    print("\ntop criteria:\n" + crit.head(12)[["title", "pages_both", "pages_only_axe", "pages_only_pa11y"]].to_string())
    print("\nWrote checker_comparison_pages.csv, checker_comparison_criteria.csv, charts/checker_agreement_by_criterion.png")


if __name__ == "__main__":
    main()
