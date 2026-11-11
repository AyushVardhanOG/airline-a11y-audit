"""
analyze.py - Step 4: turn the raw axe-core scans of the saved copies into tables, charts
and a plain-language summary.

Input (read only, never changed):
  data/raw/capture_scans/<run_id>/*.json    the LATEST run of scan_captures.py (or --run <id>)
  data/airlines.csv                          airline names, regions, excluded airlines
  data/results/automated_access.csv          which airlines blocked automated access
  data/results/live_vs_capture_pages.csv     (optional) live vs saved-copy comparison

Output (all in data/results/, rewritten every run):
  violations_all.csv          one row per failing HTML element (axe "node")
  pages_summary.csv           one row per scanned page
  summary_per_airline.csv     one row per airline (excluded airlines included, marked)
  charts/*.png + charts/*.csv six charts, each with a CSV of exactly the numbers it shows
  summary.md                  the key numbers in plain words

Words used:
  rule     = one axe-core check, e.g. "color-contrast" (only WCAG 2.0/2.1 A + AA rules were run)
  element  = one HTML element that fails a rule (axe calls it a "node")
  Airlines have 1-3 scanned pages (some pages are MISSING or SAME_AS_HOME), so airlines,
  regions and page types are compared by the AVERAGE number of failing elements PER PAGE.

Run:  .venv\\Scripts\\python.exe src\\analyze.py            (latest capture-scan run)
      .venv\\Scripts\\python.exe src\\analyze.py --run 20261111T142232Z
"""

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")  # draw to files only, no window
import matplotlib.pyplot as plt
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
RAW_CAPTURE_SCANS = PROJECT_ROOT / "data" / "raw" / "capture_scans"
RESULTS = PROJECT_ROOT / "data" / "results"
CHARTS = RESULTS / "charts"

PAGE_TYPES = ["home", "checkin", "assistance"]
IMPACTS = ["critical", "serious", "moderate", "minor"]  # axe-core's impact levels, worst first
HTML_SNIPPET_MAX = 2000  # characters of HTML kept per element in violations_all.csv

# ---------------------------------------------------------------- chart style
# Colors and chrome follow the project's chart guidance (light mode, reference palette).
SURFACE = "#fcfcfb"
INK = "#0b0b0b"           # titles, values
INK_2 = "#52514e"         # subtitles, labels
MUTED = "#898781"         # axis ticks
GRID = "#e1e0d9"          # hairline gridlines
AXIS = "#c3c2b7"          # baseline
SERIES_1 = "#2a78d6"      # single-series bars (one color for every bar)
CATEGORICAL = ["#2a78d6", "#eb6834", "#1baf7a", "#eda100"]  # validated as a set (adjacent pairs)
LABEL_ON_FILL = {"#eda100": INK}  # near-black text on yellow, white on the others

plt.rcParams.update({
    "font.family": ["Segoe UI", "DejaVu Sans"],
    "font.size": 10,
    "axes.edgecolor": AXIS,
    "axes.labelcolor": INK_2,
    "xtick.color": MUTED,
    "ytick.color": INK_2,
    "figure.facecolor": SURFACE,
    "axes.facecolor": SURFACE,
    "savefig.facecolor": SURFACE,
})


# ---------------------------------------------------------------- loading

def latest_run(run_id=None):
    if run_id:
        return RAW_CAPTURE_SCANS / run_id
    runs = sorted(p for p in RAW_CAPTURE_SCANS.iterdir() if p.is_dir())
    if not runs:
        raise SystemExit("No capture scans found. Run src/scan_captures.py first.")
    return runs[-1]


def wcag_criteria(tags):
    """axe tags like 'wcag143' -> '1.4.3' (the WCAG success criterion)."""
    return ";".join(f"{m[1]}.{m[2]}.{m[3]}" for t in tags if (m := re.fullmatch(r"wcag(\d)(\d)(\d+)", t)))


def wcag_level(tags):
    """'A' or 'AA' from the axe level tags (wcag2a, wcag21a -> A; wcag2aa, wcag21aa -> AA)."""
    if any(t in ("wcag2aa", "wcag21aa") for t in tags):
        return "AA"
    if any(t in ("wcag2a", "wcag21a") for t in tags):
        return "A"
    return ""


def load_scans(run_dir, airlines):
    """Read every scan JSON of one run into a page table and an element (violation) table."""
    pages, elements = [], []
    for path in sorted(run_dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        a = airlines.loc[rec["airline_id"]]
        base = {"airline_id": rec["airline_id"], "airline": a["airline"], "region": a["region"],
                "page_type": rec["page_type"], "file_name": rec["file_name"]}
        page = {**base, "status": rec["status"], "url": rec.get("url"),
                "captured_utc": rec.get("captured_utc"), "page_title": rec.get("page_title")}
        if rec["status"] != "ok":
            page["error"] = rec.get("error")
            pages.append(page)
            continue
        violations = rec["axe_results"]["violations"]
        page["rules_failed"] = len(violations)
        page["elements_failed"] = sum(len(v["nodes"]) for v in violations)
        for imp in IMPACTS:
            page[imp] = sum(len(v["nodes"]) for v in violations if (v.get("impact") or "minor") == imp)
        page["rules_passed"] = len(rec["axe_results"].get("passes", []))
        pages.append(page)
        for v in violations:
            for node in v["nodes"]:
                html = node.get("html") or ""
                elements.append({
                    **base,
                    "rule_id": v["id"],
                    "impact": v.get("impact") or "minor",
                    "wcag_level": wcag_level(v.get("tags", [])),
                    "wcag_criteria": wcag_criteria(v.get("tags", [])),
                    "is_experimental": "experimental" in v.get("tags", []),
                    "rule_help": v.get("help"),
                    "target": " >> ".join(" ".join(t) if isinstance(t, list) else str(t) for t in node["target"]),
                    "in_iframe": len(node["target"]) > 1,
                    "html_length": len(html),
                    "html_snippet": html[:HTML_SNIPPET_MAX],
                    "scan_run": run_dir.name,
                })
    return pd.DataFrame(pages), pd.DataFrame(elements)


# ---------------------------------------------------------------- tables

def airline_summary(airlines, access, pages_ok, elements):
    rows = []
    for airline_id, a in airlines.iterrows():
        p = pages_ok[pages_ok["airline_id"] == airline_id]
        e = elements[elements["airline_id"] == airline_id]
        n = len(p)
        rows.append({
            "airline_id": airline_id, "airline": a["airline"], "region": a["region"],
            "access_result": access.get(airline_id, ""),
            "excluded_reason": a.get("excluded_reason", "") or "",
            "pages_scanned": n,
            "page_types_scanned": ";".join(pt for pt in PAGE_TYPES if pt in set(p["page_type"])),
            "rules_failed_distinct": e["rule_id"].nunique() if n else None,
            "elements_failed": int(p["elements_failed"].sum()) if n else None,
            "elements_per_page": round(p["elements_failed"].mean(), 1) if n else None,
            **{imp: int(p[imp].sum()) if n else None for imp in IMPACTS},
        })
    return pd.DataFrame(rows)


def group_per_page(pages_ok, column, order):
    g = pages_ok.groupby(column)["elements_failed"]
    out = pd.DataFrame({"pages": g.size(), "elements_failed": g.sum(),
                        "mean_elements_per_page": g.mean().round(1),
                        "median_elements_per_page": g.median()})
    return out.reindex([o for o in order if o in out.index])


# ---------------------------------------------------------------- charts

def style_axes(ax, title, subtitle):
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_linewidth(0.8)
    ax.xaxis.grid(True, color=GRID, linewidth=0.8)  # solid hairline gridlines
    ax.set_axisbelow(True)
    ax.tick_params(axis="y", length=0)
    ax.tick_params(axis="x", length=0, labelcolor=MUTED)
    ax.set_title(title, loc="left", color=INK, fontsize=13, fontweight="bold", pad=26)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK_2, fontsize=9.5, va="bottom")


def ranked_bars(labels, values, value_text, title, subtitle, xlabel, path):
    """Horizontal bars, one series, one color, value printed at each bar's tip."""
    n = len(labels)
    fig, ax = plt.subplots(figsize=(8.5, 1.3 + 0.3 * n), dpi=150)
    y = range(n)
    ax.barh(list(y), values, height=0.5, color=SERIES_1)  # 0.3 in row at 150 dpi -> ~22px bar
    ax.set_yticks(list(y), labels)
    ax.invert_yaxis()  # largest on top
    vmax = max(values) if len(values) else 1
    for yi, v, txt in zip(y, values, value_text):
        ax.text(v + vmax * 0.01, yi, txt, va="center", ha="left", color=INK_2, fontsize=9)
    ax.set_xlim(0, vmax * 1.15 if vmax else 1)
    ax.set_xlabel(xlabel, color=INK_2)
    style_axes(ax, title, subtitle)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def segmented_bar(names, counts, title, subtitle, path):
    """One whole split into parts (<= 4): a tall segmented bar with labels inside + legend."""
    total = sum(counts)
    fig, ax = plt.subplots(figsize=(8.5, 2.6), dpi=150)
    left = 0
    for name, c, color in zip(names, counts, CATEGORICAL):
        if c == 0:
            continue
        # edgecolor = surface -> a thin surface-colored gap between touching segments
        ax.barh(0, c, left=left, height=0.5, color=color, edgecolor=SURFACE, linewidth=1.5, label=name)
        share = c / total
        if share >= 0.08:  # only label a block that is wide enough for its text
            ax.text(left + c / 2, 0, f"{c}  ({share:.0%})", ha="center", va="center",
                    color=LABEL_ON_FILL.get(color, "#ffffff"), fontsize=10, fontweight="bold")
        left += c
    ax.set_xlim(0, total)
    ax.set_ylim(-2.1, 2.1)  # keeps the bar about 28px tall (a 'tall segmented bar' never exceeds 28px)
    ax.axis("off")
    ax.set_title(title, loc="left", color=INK, fontsize=13, fontweight="bold", pad=26)
    ax.text(0, 1.02, subtitle, transform=ax.transAxes, color=INK_2, fontsize=9.5, va="bottom")
    # matplotlib fills legend columns top-to-bottom; re-order so that, read left-to-right,
    # the legend lists the parts in the same order as the blocks of the bar.
    handles, names_ = ax.get_legend_handles_labels()
    ncol = 2
    nrow = -(-len(handles) // ncol)
    order = [r * ncol + c for c in range(ncol) for r in range(nrow) if r * ncol + c < len(handles)]
    leg = ax.legend([handles[i] for i in order], [names_[i] for i in order], loc="upper center",
                    bbox_to_anchor=(0.5, 0.18), ncol=ncol, frameon=False,
                    fontsize=9.5, handlelength=1.2, handleheight=1.0)
    for text in leg.get_texts():
        text.set_color(INK_2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def make_charts(pages_ok, elements, per_airline, access_df):
    CHARTS.mkdir(parents=True, exist_ok=True)
    n_pages = len(pages_ok)
    made = []

    # 1. Top 10 rules by number of pages that fail them
    by_rule = (elements.groupby("rule_id")
               .agg(pages_affected=("file_name", "nunique"), airlines_affected=("airline_id", "nunique"),
                    elements_failed=("file_name", "size"), impact=("impact", "first"),
                    wcag_criteria=("wcag_criteria", "first"), rule_help=("rule_help", "first"))
               .sort_values(["pages_affected", "elements_failed"], ascending=False))
    by_rule.to_csv(CHARTS / "top_violation_types.csv")  # all rules; the chart shows the top 10
    top = by_rule.head(10)
    ranked_bars(list(top.index), list(top["pages_affected"]),
                [f"{p} pages ({p / n_pages:.0%})" for p in top["pages_affected"]],
                "Top 10 accessibility rules failed",
                f"Number of pages (of {n_pages} scanned) with at least one failing element, axe-core WCAG 2.1 A/AA",
                "pages", CHARTS / "top10_violation_types.png")
    made.append("top10_violation_types")

    # 2. Violations per airline (average failing elements per scanned page)
    pa = per_airline[per_airline["pages_scanned"] > 0].sort_values("elements_per_page", ascending=False)
    pa[["airline", "region", "pages_scanned", "elements_failed", "elements_per_page"]].to_csv(
        CHARTS / "violations_per_airline.csv", index=False)
    excluded = per_airline[per_airline["excluded_reason"] != ""]["airline"].tolist()
    ranked_bars([f"{r.airline}  ({r.pages_scanned}p)" for r in pa.itertuples()],
                list(pa["elements_per_page"]),
                [f"{v:g}" for v in pa["elements_per_page"]],
                "Failing elements per page, by airline",
                "Average number of failing HTML elements per scanned page; (Np) = pages scanned"
                + (f"; excluded: {', '.join(excluded)}" if excluded else ""),
                "failing elements per page (average)", CHARTS / "violations_per_airline.png")
    made.append("violations_per_airline")

    # 3. By region, 4. by page type
    regions = list(dict.fromkeys(per_airline["region"]))
    for column, order, name, title in (("region", regions, "violations_by_region", "Failing elements per page, by region"),
                                       ("page_type", PAGE_TYPES, "violations_by_page_type", "Failing elements per page, by page type")):
        g = group_per_page(pages_ok, column, order)
        g.to_csv(CHARTS / f"{name}.csv")
        ranked_bars([f"{i}  ({int(r.pages)} pages)" for i, r in g.iterrows()], list(g["mean_elements_per_page"]),
                    [f"{m:g}  (median {md:g})" for m, md in zip(g["mean_elements_per_page"], g["median_elements_per_page"])],
                    title, "Average number of failing HTML elements per scanned page (median in brackets)",
                    "failing elements per page (average)", CHARTS / f"{name}.png")
        made.append(name)

    # 5. By impact level (kept in axe's severity order, not ranked)
    imp = pd.DataFrame({"elements_failed": [int((elements["impact"] == i).sum()) for i in IMPACTS],
                        "pages_affected": [elements[elements["impact"] == i]["file_name"].nunique() for i in IMPACTS]},
                       index=IMPACTS)
    imp.to_csv(CHARTS / "violations_by_impact.csv")
    total = imp["elements_failed"].sum()
    fig_vals = list(imp["elements_failed"])
    ranked_bars(IMPACTS, fig_vals, [f"{v} ({v / total:.0%})" if total else "0" for v in fig_vals],
                "Failing elements by impact level",
                "axe-core impact level of each failing element, all scanned pages (worst level first)",
                "failing elements", CHARTS / "violations_by_impact.png")
    made.append("violations_by_impact")

    # 6. Share of airlines that block automated (headless) access
    labels = {"allowed": "Allowed (real page loaded)",
              "blocked": "Blocked (HTTP 403 / 'Access Denied')",
              "blocked_unconfirmed": "Error page instead of real page (probably blocked)",
              "error": "Connection cut before loading (cause unknown)"}
    counts = [int((access_df["result"] == k).sum()) for k in labels]
    pd.DataFrame({"result": list(labels), "meaning": list(labels.values()), "airlines": counts}).to_csv(
        CHARTS / "automated_access_share.csv", index=False)
    segmented_bar(list(labels.values()), counts,
                  "Did the airline website let an automated browser in?",
                  f"One headless Chromium visit per homepage, {len(access_df)} airlines, 11 Nov 2026",
                  CHARTS / "automated_access_share.png")
    made.append("automated_access_share")
    return made, by_rule


# ---------------------------------------------------------------- summary.md

def pages_word(n):
    return f"{n} page" if n == 1 else f"{n} pages"


def live_vs_copy_section():
    path = RESULTS / "live_vs_capture_pages.csv"
    if not path.exists():
        return ["## Live page vs saved copy", "", "Not available: run src/compare_live_vs_capture.py first.", ""]
    lv = pd.read_csv(path)
    n = len(lv)
    same_rules = int((lv["rule_jaccard"] == 1.0).sum())
    lines = ["## Live page vs saved copy (method check)", "",
             f"For the {lv['airline_id'].nunique()} airlines that allowed automated access, {n} pages were "
             "scanned both live and as a saved copy, at most about 15 minutes apart.", "",
             f"- **{same_rules} of {n} pages** ({same_rules / n:.0%}) failed exactly the same set of rules in both versions.",
             f"- Average rule overlap (Jaccard, 1 = identical): **{lv['rule_jaccard'].mean():.2f}** "
             f"(median {lv['rule_jaccard'].median():.2f}, lowest {lv['rule_jaccard'].min():.2f}).",
             f"- Failing elements in total: **{int(lv['live_elements'].sum())} live** vs "
             f"**{int(lv['capture_elements'].sum())} in the saved copies**."]
    only_live = pd.Series(";".join(lv["rules_only_live"].fillna("")).split(";")).replace("", pd.NA).dropna().value_counts()
    only_copy = pd.Series(";".join(lv["rules_only_capture"].fillna("")).split(";")).replace("", pd.NA).dropna().value_counts()
    if len(only_live):
        lines.append("- Rules that failed only on the live page: " + ", ".join(f"{r} ({pages_word(c)})" for r, c in only_live.items()) + ".")
    if len(only_copy):
        lines.append("- Rules that failed only in the saved copy: " + ", ".join(f"{r} ({pages_word(c)})" for r, c in only_copy.items()) + ".")
    lines.append("")
    return lines


def experimental_section(elements, pages_ok):
    """
    Checked 2026-11-11: axe-core 4.14.0 has 6 experimental rules; axe leaves them out unless asked
    for, and none appears in our results. If a future scan ever contains one, report the main
    numbers with AND without experimental rules (the column is_experimental is then kept).
    """
    exp = elements[elements["is_experimental"]]
    if exp.empty:
        return ["## Rule check: experimental rules", "",
                "- None of the rules in the results is tagged \"experimental\" by axe-core (checked against the "
                "installed axe-core's own rule list). All numbers are therefore from standard WCAG 2.0/2.1 A/AA rules.", ""]
    non = elements[~elements["is_experimental"]]
    pages_with = lambda e: e.groupby("file_name").size().reindex(pages_ok["file_name"], fill_value=0)
    n = len(pages_ok)
    return ["## Rule check: experimental rules", "",
            f"- Experimental rules found: {', '.join(sorted(exp['rule_id'].unique()))} ({len(exp)} elements).",
            "| | with experimental rules | without |", "|---|---|---|",
            f"| pages failing at least one rule | {(pages_with(elements) > 0).sum()} of {n} | {(pages_with(non) > 0).sum()} of {n} |",
            f"| failing elements | {len(elements)} | {len(non)} |",
            f"| different rules | {elements['rule_id'].nunique()} | {non['rule_id'].nunique()} |", ""]


def second_checker_section():
    pages_csv, crit_csv = RESULTS / "checker_comparison_pages.csv", RESULTS / "checker_comparison_criteria.csv"
    if not pages_csv.exists():
        return ["## Second checker (Pa11y)", "", "Not available: run src/scan_pa11y.js and src/compare_checkers.py.", ""]
    cp, cc = pd.read_csv(pages_csv, keep_default_na=False), pd.read_csv(crit_csv, keep_default_na=False, dtype={"criterion": str})
    n = len(cp)
    both, only_a, only_p = cp["n_both"].sum(), cp["n_only_axe"].sum(), cp["n_only_pa11y"].sum()
    pairs = both + only_a + only_p
    common = cc[(cc["pages_axe"] > 0) & (cc["pages_pa11y"] > 0)].set_index("criterion")
    c_both, c_a, c_p = common["pages_both"].sum(), common["pages_only_axe"].sum(), common["pages_only_pa11y"].sum()
    c_pairs = c_both + c_a + c_p
    L = ["## Second checker: Pa11y (HTML_CodeSniffer, WCAG2AA) vs axe-core", "",
         f"The same {n} saved copies were also scanned with Pa11y, under the same offline conditions. "
         "The tools name their checks differently, so they are compared by WCAG success criterion (SC): "
         "for each page, which criteria each tool reports as failed. Pa11y \"errors\" only (its warnings and "
         "notices are \"check by hand\" items).", "",
         f"- Pages with at least one failure: **axe-core {(cp['axe_elements'] > 0).sum()}**, "
         f"**Pa11y {(cp['pa11y_errors'] > 0).sum()}** (of {n}).",
         f"- Findings: axe-core {cp['axe_elements'].sum()} failing elements; Pa11y {cp['pa11y_errors'].sum()} errors.",
         f"- Of all {pairs} (page, criterion) failures found by either tool, **{both} ({both / pairs:.0%}) were found by "
         f"both**, {only_a} ({only_a / pairs:.0%}) only by axe-core and {only_p} ({only_p / pairs:.0%}) only by Pa11y.",
         f"- Many criteria are only ever reported by ONE of the tools. Counting only the {len(common)} criteria that both "
         f"tools reported at least once ({', '.join(common.index)}): **{c_both} of {c_pairs} ({c_both / c_pairs:.0%}) "
         f"found by both**, {c_a} only by axe-core, {c_p} only by Pa11y.",
         f"- Per page, the overlap of the two sets of failed criteria (Jaccard, 1 = identical) is "
         f"{cp['criteria_jaccard'].mean():.2f} on average (median {cp['criteria_jaccard'].median():.2f}); "
         f"identical on {(cp['criteria_jaccard'] == 1).sum()} pages.", "",
         "Criteria flagged on the most pages (both / only axe-core / only Pa11y):", ""]
    for r in cc.head(8).itertuples():
        L.append(f"- {r.criterion} {r.title}: {r.pages_both} / {r.pages_only_axe} / {r.pages_only_pa11y}")
    L += ["", "Why they differ (checked on this data; details in docs/notes.md):", "",
          "- **Same problem, different criterion**: a missing iframe title is 2.4.1 for Pa11y but 4.1.2 for axe-core; "
          "axe-core's link-name rule counts for both 2.4.4 and 4.1.2.",
          "- **Criteria only one tool tests**: 4.1.1 Parsing (duplicate ids) only Pa11y - axe-core 4.14 switches its "
          "duplicate-id rules off by default and 4.1.1 was removed in WCAG 2.2; 3.2.2 (form without submit button) and "
          "obsolete `<font>` markup (1.3.1) only Pa11y; 2.5.3 Label in Name, 1.4.4 (zoom blocked) and 1.4.1 (links "
          "told apart by colour only) only axe-core.",
          "- **Hidden elements**: Pa11y also reports hidden or zero-size elements (e.g. tracking-pixel images without "
          "alt text), which axe-core skips on purpose.",
          "", "So low agreement does not mean one tool is wrong: they implement different tests. Using both gives wider "
          "coverage; neither replaces manual testing. Chart: `charts/checker_agreement_by_criterion.png`.", ""]
    return L


def write_summary(run_dir, pages, pages_ok, elements, per_airline, by_rule, access_df, made):
    n = len(pages_ok)
    with_viol = int((pages_ok["elements_failed"] > 0).sum())
    total_el = len(elements)
    imp_counts = elements["impact"].value_counts()
    pa = per_airline[per_airline["pages_scanned"] > 0].sort_values("elements_per_page", ascending=False)
    reg = group_per_page(pages_ok, "region", list(dict.fromkeys(per_airline["region"])))
    pt = group_per_page(pages_ok, "page_type", PAGE_TYPES)
    acc = access_df["result"].value_counts()
    not_allowed = len(access_df) - int(acc.get("allowed", 0))
    errors = pages[pages["status"] != "ok"]
    excluded = per_airline[per_airline["excluded_reason"] != ""]

    L = ["# Summary of the accessibility audit", "",
         f"Generated by `src/analyze.py` from capture-scan run `{run_dir.name}` "
         "(saved copies of the pages, captured by hand on 11 Nov 2026). Numbers are from "
         "axe-core, WCAG 2.0/2.1 Level A and AA rules only.", "",
         "## What was scanned", "",
         f"- **{per_airline['pages_scanned'].gt(0).sum()} airlines**, **{n} pages** (homepage, check-in, special assistance). "
         f"Pages scanned per type: " + ", ".join(f"{t} {int(pt.loc[t, 'pages'])}" for t in pt.index) + ".",
         f"- Excluded: {', '.join(f'{r.airline} ({r.excluded_reason})' for r in excluded.itertuples()) or 'none'}. "
         "Pages that do not exist (MISSING) or are the homepage again (SAME_AS_HOME) were not scanned.",
         f"- Scan errors: {len(errors)}." + (" " + "; ".join(f"{r.file_name}: {r.error}" for r in errors.itertuples()) if len(errors) else ""), "",
         "## Main results", "",
         f"- **{with_viol} of {n} pages ({with_viol / n:.0%}) failed at least one rule.** Automated tools find only "
         "part of all accessibility problems, so a page with no failures is not proven accessible.",
         f"- In total **{total_el} failing HTML elements** were found, on average **{pages_ok['elements_failed'].mean():.1f} per page** "
         f"(median {pages_ok['elements_failed'].median():g}; a few pages with many failures pull the average up).",
         f"- **{by_rule.shape[0]} different rules** failed at least once.",
         "- By impact: " + ", ".join(f"{imp} {int(imp_counts.get(imp, 0))} ({imp_counts.get(imp, 0) / total_el:.0%})" for imp in IMPACTS) + " of the failing elements.", "",
         "### Most common problems (by number of pages)", ""]
    for rule, r in by_rule.head(5).iterrows():
        L.append(f"- **{rule}** ({r.impact}; WCAG {r.wcag_criteria or 'n/a'}): {r.pages_affected} pages at "
                 f"{r.airlines_affected} airlines, {r.elements_failed} elements - {r.rule_help}.")
    L += ["", "### Airlines (average failing elements per page)", "",
          "- Most: " + ", ".join(f"{r.airline} {r.elements_per_page:g}" for r in pa.head(3).itertuples()) + ".",
          "- Fewest: " + ", ".join(f"{r.airline} {r.elements_per_page:g}" for r in pa.tail(3).iloc[::-1].itertuples()) + ".",
          "- Full table: `summary_per_airline.csv`. Airlines have 1-3 scanned pages, so compare averages, not totals.", "",
          "### Regions and page types (average failing elements per page)", "",
          "- By region: " + ", ".join(f"{i} {r.mean_elements_per_page:g} ({int(r.pages)} pages)" for i, r in reg.iterrows()) + ".",
          "- By page type: " + ", ".join(f"{i} {r.mean_elements_per_page:g} ({int(r.pages)} pages)" for i, r in pt.iterrows()) + ".",
          "- These groups are small (5-10 airlines per region), so differences between them are descriptive, "
          "not statistically tested.", "",
          "## Automated access (blocking)", "",
          f"- **{not_allowed} of {len(access_df)} airlines ({not_allowed / len(access_df):.0%}) did not show their real homepage "
          f"to a headless browser**: {int(acc.get('blocked', 0))} blocked it outright, {int(acc.get('blocked_unconfirmed', 0))} showed an "
          f"error page, {int(acc.get('error', 0))} cut the connection. Only {int(acc.get('allowed', 0))} allowed it.",
          "- This is why all pages were captured by hand with SingleFile instead of scanned automatically.", ""]
    L += experimental_section(elements, pages_ok)
    L += live_vs_copy_section()
    L += second_checker_section()
    L += ["## Limitations (state these in the paper)", "",
          "- Automated checkers detect only part of all WCAG problems; manual testing is still needed.",
          "- Saved copies are snapshots: menus, focus behaviour and anything after a click are not tested.",
          "- Several homepages were redirected by location to their India version (the capture was made "
          "from India), so results describe what a visitor from India sees.",
          "- One capture per page on one day; websites change often.",
          "- 7 pages could not be found (MISSING) and Alaska could not be loaded at all.", "",
          "## Files", "",
          "- `violations_all.csv` - every failing element (rule, impact, WCAG criterion, selector, HTML snippet)",
          "- `pages_summary.csv`, `summary_per_airline.csv`",
          "- `charts/` - " + ", ".join(f"`{m}.png`" for m in made) + " (each with a `.csv` of the numbers shown)",
          ""]
    (RESULTS / "summary.md").write_text("\n".join(L), encoding="utf-8")


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Analyse the capture scans.")
    parser.add_argument("--run", help="capture-scan run id (default: latest)")
    args = parser.parse_args()

    run_dir = latest_run(args.run)
    airlines = pd.read_csv(PROJECT_ROOT / "data" / "airlines.csv", dtype=str, keep_default_na=False).set_index("airline_id")
    access_df = pd.read_csv(RESULTS / "automated_access.csv", dtype=str, keep_default_na=False)
    access = dict(zip(access_df["airline_id"], access_df["result"]))

    pages, elements = load_scans(run_dir, airlines)
    pages_ok = pages[pages["status"] == "ok"].copy()
    print(f"Run {run_dir.name}: {len(pages)} pages ({len(pages_ok)} ok), {len(elements)} failing elements")

    # is_experimental is only written if any experimental rule appears (checked: none in run 20261111T142233Z)
    to_write = elements if elements["is_experimental"].any() else elements.drop(columns=["is_experimental"])
    to_write.to_csv(RESULTS / "violations_all.csv", index=False)
    pages.to_csv(RESULTS / "pages_summary.csv", index=False)
    per_airline = airline_summary(airlines, access, pages_ok, elements)
    per_airline.to_csv(RESULTS / "summary_per_airline.csv", index=False)

    made, by_rule = make_charts(pages_ok, elements, per_airline, access_df)
    write_summary(run_dir, pages, pages_ok, elements, per_airline, by_rule, access_df, made)
    print("Wrote violations_all.csv, pages_summary.csv, summary_per_airline.csv, summary.md and "
          f"{len(made)} charts in {CHARTS.relative_to(PROJECT_ROOT)}")


if __name__ == "__main__":
    main()
