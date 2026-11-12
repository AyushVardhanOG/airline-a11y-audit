"""
capture_artifacts.py - shared helper: find failing elements that were INSERTED BY THE SAVING TOOL
(SingleFile), not by the airline. Found 2026-11-13 while testing the demo (see docs/notes.md).

What it is: next to videos, SingleFile inserted a tiny 16 px link (with a 16 px icon image inside)
with this inline style:
    z-index:2147483647!important;position:absolute!important;margin:8px 0px 0px 8px!important;...
The link has no text and the icon has no alt text, so the checkers report them (link-name,
image-alt / Pa11y H30.2), although they are not part of the airline's website.

Rule used (one rule for every script):
  An element is a capture_artifact if the element itself OR one of its ancestors (e.g. the <img>
  inside that link) has an inline style that contains ALL THREE declarations
      z-index:2147483647   position:absolute   margin:8px 0px 0px <N>px
  (spacing and "!important" ignored). Usually N = 8; the LEFT margin is the only part that varies:
  SingleFile places the icon relative to its video, and the second video on IndiGo's homepage got
  "margin:8px 0px 0px -70px" (same 16 px link to an .mp4 file, otherwise identical).
  A z-index of 2147483647 ALONE is not enough: the airlines' own widgets use that number too
  (checked: Akasa Air's sidebar button has it, without position:absolute / the margin). An element
  that only CONTAINS the inserted link (e.g. the video's container) is not marked either.

How it is checked: element by element, inside the saved page (opened offline and read only, the
same way as the scans): every axe-core finding by its target, every Pa11y error by its selector.
Only pages whose file contains "2147483647" at all are opened (others cannot contain the style).

Commands:
  .venv\\Scripts\\python.exe src\\capture_artifacts.py build
      -> data/results/capture_artifacts.csv: one row per finding (axe node or Pa11y error) on those
         pages whose element or ancestors mention 2147483647, with capture_artifact True/False
         (so the rows that are NOT marked, e.g. chat widgets, are visible too).
Used by: analyze.py, compare_checkers.py, repair_full.py (function load()).
"""

import csv
import json
import re
import sys

from playwright.sync_api import sync_playwright

import axe_runner as ax

PROJECT_ROOT = ax.PROJECT_ROOT
CAPTURES_DIR = PROJECT_ROOT / "data" / "captures"
CAPTURE_SCANS = PROJECT_ROOT / "data" / "raw" / "capture_scans"
PA11Y_SCANS = PROJECT_ROOT / "data" / "raw" / "pa11y_scans"
ARTIFACTS_CSV = PROJECT_ROOT / "data" / "results" / "capture_artifacts.csv"

SINGLEFILE_DECLARATIONS = ["z-index:2147483647", "position:absolute"]  # must be present exactly
SINGLEFILE_MARGIN = r"margin:8px 0px 0px -?\d+(\.\d+)?px"              # and one margin like this
FIELDS = ["tool", "file_name", "rule_or_code", "target", "tag", "found_in_page", "capture_artifact", "reason",
          "axe_run", "pa11y_run"]


def style_declarations(style):
    """'Z-Index: 2147483647 !important; position:absolute' -> ['z-index:2147483647', 'position:absolute']"""
    out = []
    for decl in (style or "").lower().replace("!important", "").split(";"):
        decl = re.sub(r"\s+", " ", re.sub(r"\s*:\s*", ":", decl, count=1)).strip()
        if decl:
            out.append(decl)
    return out


def has_singlefile_style(style):
    """True if an inline style contains all three SingleFile declarations."""
    decls = style_declarations(style)
    return all(d in decls for d in SINGLEFILE_DECLARATIONS) and any(re.fullmatch(SINGLEFILE_MARGIN, d) for d in decls)


def html_has_singlefile_style(html):
    """Same test on an HTML text (only the first tag's style attribute), e.g. Pa11y's 'context' snippet."""
    m = re.match(r"\s*<[^>]*?\sstyle\s*=\s*(\"[^\"]*\"?|'[^']*'?)", html or "")
    return bool(m) and has_singlefile_style(m.group(1).strip("\"'"))


# The same test in JavaScript, run inside the saved page for one selector: the element and its
# ancestors are checked; also reports whether 2147483647 appears at all (to show what is NOT marked).
CHECK_JS = """([sel, wanted, marginPattern]) => {
    const margin = new RegExp('^' + marginPattern + '$');
    let e = null;
    try { e = document.querySelector(sel); } catch (x) { return null; }
    if (!e) return null;
    const decls = s => (s || '').toLowerCase().replace(/!important/g, '').split(';')
        .map(d => d.replace(/\\s*:\\s*/, ':').replace(/\\s+/g, ' ').trim()).filter(d => d);
    let artifact = false, ancestorMentions = false;
    for (let x = e; x; x = x.parentElement) {
        const st = x.getAttribute('style') || '';
        if (st.includes('2147483647')) ancestorMentions = true;
        const d = decls(st);
        if (wanted.every(w => d.includes(w)) && d.some(x => margin.test(x))) { artifact = true; break; }
    }
    return {tag: e.tagName.toLowerCase(), artifact: artifact,
            mentions: ancestorMentions || e.outerHTML.includes('2147483647')};
}"""


def latest(folder):
    return sorted(p for p in folder.iterdir() if p.is_dir())[-1]


def open_saved_page(browser, file_path):
    """Open a saved page offline exactly like the scans do (page scripts off, all requests blocked)."""
    import repair as rp  # imported here: repair.py imports a lot; only build() needs it
    return rp.open_offline(browser, file_path)


def build():
    axe_run = latest(CAPTURE_SCANS)
    pa11y_run = latest(PA11Y_SCANS)
    axe = {r["file_name"]: r for r in (json.loads(p.read_text(encoding="utf-8")) for p in sorted(axe_run.glob("*.json")))}
    pa11y = {r["file_name"]: r for r in (json.loads(p.read_text(encoding="utf-8")) for p in sorted(pa11y_run.glob("*.json")))}

    # Only pages whose saved file mentions 2147483647 at all can contain the SingleFile style.
    candidates = sorted(f for f in axe if "2147483647" in (CAPTURES_DIR / f).read_text(encoding="utf-8", errors="ignore"))
    print(f"axe run {axe_run.name}, Pa11y run {pa11y_run.name}: {len(candidates)} of {len(axe)} saved pages mention 2147483647")

    rows = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for file_name in candidates:
            context, page = open_saved_page(browser, CAPTURES_DIR / file_name)
            try:
                findings = []  # (tool, rule/code, selector or None if inside iframe / shadow DOM)
                for v in (axe[file_name].get("axe_results") or {}).get("violations", []):
                    for node in v["nodes"]:
                        single = len(node["target"]) == 1 and isinstance(node["target"][0], str)
                        findings.append(("axe", v["id"], node["target"][0] if single else None,
                                         " >> ".join(" ".join(t) if isinstance(t, list) else str(t) for t in node["target"])))
                for issue in (pa11y.get(file_name) or {}).get("issues", []):
                    findings.append(("pa11y", issue["code"], issue.get("selector") or None, issue.get("selector") or "",
                                     issue.get("context") or ""))
                for tool, rule, selector, target, *snippet in findings:
                    res = page.evaluate(CHECK_JS, [selector, SINGLEFILE_DECLARATIONS, SINGLEFILE_MARGIN]) if selector else None
                    if res is None:
                        # Not checkable in the page (inside iframe / shadow DOM, or the selector is not valid CSS,
                        # e.g. Pa11y's duplicate-id selectors like "#Rectangle 29"). Fallback for Pa11y: test the
                        # HTML snippet Pa11y saved ("context") with the same rule.
                        artifact = bool(snippet) and html_has_singlefile_style(snippet[0])
                        reason = ("inside iframe or shadow DOM" if selector is None else "selector not usable in saved page"
                                  ) + ("; SingleFile style in Pa11y context" if artifact else "")
                        rows.append({"tool": tool, "file_name": file_name, "rule_or_code": rule, "target": target,
                                     "tag": "", "found_in_page": False, "capture_artifact": artifact, "reason": reason})
                    elif res["mentions"]:
                        rows.append({"tool": tool, "file_name": file_name, "rule_or_code": rule, "target": target,
                                     "tag": res["tag"], "found_in_page": True, "capture_artifact": res["artifact"],
                                     "reason": "SingleFile style on element or ancestor" if res["artifact"]
                                     else "mentions 2147483647 but not the SingleFile style"})
            finally:
                context.close()
        browser.close()

    for r in rows:
        r.update(axe_run=axe_run.name, pa11y_run=pa11y_run.name)
    ARTIFACTS_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(ARTIFACTS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(rows)

    marked = [r for r in rows if r["capture_artifact"]]
    print(f"marked as capture_artifact: axe {sum(r['tool'] == 'axe' for r in marked)}, "
          f"Pa11y {sum(r['tool'] == 'pa11y' for r in marked)} "
          f"(on {len({r['file_name'] for r in marked})} pages)")
    print(f"mention 2147483647 but NOT marked: {sum(r['reason'].startswith('mentions') for r in rows)}; "
          f"not checkable: {sum(not r['found_in_page'] for r in rows)} (listed in the CSV, never marked)")
    print(f"Wrote {ax.project_relative(ARTIFACTS_CSV)}")


def load(axe_run=None):
    """
    The marked findings, as sets of keys for the other scripts:
      {"axe": {(file_name, target)}, "pa11y": {(file_name, selector)}}
    target = the axe target as written in violations_all.csv (a single CSS selector here).
    axe_run: the capture-scan run the caller analyses; it must be the run the list was built from.
    """
    if not ARTIFACTS_CSV.exists():
        sys.exit("data/results/capture_artifacts.csv is missing. Run: .venv\\Scripts\\python.exe src\\capture_artifacts.py build")
    rows = list(csv.DictReader(open(ARTIFACTS_CSV, encoding="utf-8")))
    built_from = {r["axe_run"] for r in rows}
    if axe_run and rows and built_from != {axe_run}:
        sys.exit(f"capture_artifacts.csv was built from run {', '.join(built_from)}, not {axe_run}. "
                 "Run: .venv\\Scripts\\python.exe src\\capture_artifacts.py build")
    keys = {"axe": set(), "pa11y": set()}
    for r in rows:
        if r["capture_artifact"] == "True":
            keys[r["tool"]].add((r["file_name"], r["target"]))
    return keys


def axe_target_key(node_target):
    """The same string as 'target' above, from an axe node's target list."""
    return " >> ".join(" ".join(t) if isinstance(t, list) else str(t) for t in node_target)


if __name__ == "__main__":
    if sys.argv[1:] != ["build"]:
        sys.exit("Usage: .venv\\Scripts\\python.exe src\\capture_artifacts.py build")
    sys.stdout.reconfigure(encoding="utf-8")
    build()
