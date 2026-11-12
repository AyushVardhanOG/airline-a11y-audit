"""
demo.py - a short live demo for the progress presentation (NOT used for research results).

For ONE saved page (a SingleFile copy in data/captures/) it shows the whole idea of the project:
  1. scan the page with axe-core (offline, page scripts off) and list the problems by type,
  2. pick one failing element and ask the local LLM (Ollama, qwen2.5-coder:7b) to fix it,
  3. put the fix into a COPY of the page, scan the copy again, and say whether axe-core accepts it.

It reuses the exact code of the real pipeline (repair.py / repair_full.py): the same offline scan,
the same prompt, the same settings (temperature 0, seed 42, num_ctx 8192), the same control run and
the same review flags. No website is contacted and the saved page itself is never changed (rule 4).

Usage (from the project folder):
  .venv\\Scripts\\python.exe src\\demo.py                                   list the pages you can choose
  .venv\\Scripts\\python.exe src\\demo.py qantas_home_20261111.html         run the demo on that page
  .venv\\Scripts\\python.exe src\\demo.py qantas_home_20261111.html --rule color-contrast
                                                                       choose which problem type to repair
Saved: the repaired copy and a record of the LLM step (exact prompt, model version, answer, result)
in data/repaired/demo/ (git-ignored, like all repaired copies).
"""

import argparse
import csv
import difflib
import json
import re
import sys
import urllib.error

from playwright.sync_api import sync_playwright

import axe_runner as ax
import repair as rp
import repair_full as rf

DEFAULT_MODEL = "qwen2.5-coder:7b"
DEMO_DIR = ax.PROJECT_ROOT / "data" / "repaired" / "demo"
# Problem types that are easy to explain on a slide. Without --rule, the demo repairs the first of
# these that the page has; if it has none of them, it takes the most common problem type on the page.
EASY_TO_EXPLAIN = ["image-alt", "link-name", "button-name", "color-contrast"]
SHORT_HTML = 400  # prefer an element whose HTML (as sent to the LLM) is at most this long: fits on a slide
IMPACT_WORDS = {"critical": "critical", "serious": "serious", "moderate": "moderate", "minor": "minor", None: "?"}
LINE = "-" * 78

# Found while testing this demo (see docs/notes.md, 2026-11-13): on 7 saved pages a tiny 16 px link
# with this exact style sits next to every video. It was inserted while SAVING the page (identical on
# 4 unrelated airlines; absent from the Ryanair live scan), so it is not the airline's own code.
# The demo labels such elements and never picks one to repair.
SAVE_TOOL_STYLE = "z-index:2147483647!important;position:absolute!important;margin:8px 0px 0px 8px"
ELEMENT_INFO = """([s, key]) => { const e = document.querySelector(s); if (!e) return null;
    const a = e.closest('a');
    return {tag: e.tagName.toLowerCase(),
            shadow: [e, ...e.querySelectorAll('*')].some(x => x.shadowRoot),
            added_by_save_tool: !!(a && (a.getAttribute('style') || '').includes(key)),
            outer: e.outerHTML}; }"""


def element_info(page, node):
    """Tag, shadow DOM, 'added while saving' and HTML of a failing element (None if inside an iframe / shadow DOM)."""
    if len(node["target"]) != 1 or not isinstance(node["target"][0], str):
        return None
    return page.evaluate(ELEMENT_INFO, [node["target"][0], SAVE_TOOL_STYLE])


def list_pages():
    """No page given: print the saved pages with their number of failing elements (from Step 4)."""
    counts = {}
    summary = rp.RESULTS / "pages_summary.csv"
    if summary.exists():
        counts = {r["file_name"]: r["elements_failed"] for r in csv.DictReader(open(summary, encoding="utf-8"))}
    print("Saved pages you can use (failing elements found in Step 4):\n")
    for path in sorted(rp.CAPTURES_DIR.glob("*.html")):
        print(f"  {counts.get(path.name, '?'):>4}  {path.name}")
    print("\nRun:  .venv\\Scripts\\python.exe src\\demo.py <file name>")


def wcag_criteria(tags):
    """axe tags like 'wcag143' -> '1.4.3' (same format as the real pipeline)."""
    return ";".join(f"{m[1]}.{m[2]}.{m[3]}" for t in tags if (m := re.fullmatch(r"wcag(\d)(\d)(\d+)", t)))


def candidates(page, violations, rule_choice):
    """
    The elements the demo may repair, best first: one problem type (rule_choice, or an easy one,
    or the most common one), elements the real pipeline would also accept (not in an iframe or
    shadow DOM, not <html>/<head>/<body>), not added by the saving tool, shortest HTML first so
    it is readable on screen.
    """
    by_id = {v["id"]: v for v in violations}
    if rule_choice:
        if rule_choice not in by_id:
            sys.exit(f"This page has no '{rule_choice}' problems. Problem types on this page: {', '.join(by_id)}")
        order = [rule_choice]
    else:
        easy = [r for r in EASY_TO_EXPLAIN if r in by_id]
        common = sorted(by_id, key=lambda r: -len(by_id[r]["nodes"]))
        order = easy + [r for r in common if r not in easy]
    for rule_id in order:
        v, found = by_id[rule_id], []
        for node in v["nodes"]:
            info = element_info(page, node)  # None = inside an iframe or shadow DOM (excluded in the real run too)
            if info is None or info["tag"] in rf.DOCUMENT_ELEMENTS or info["shadow"] or info["added_by_save_tool"]:
                continue
            sent, _ = rp.prompt_html(info["outer"])
            found.append({"rule_id": rule_id, "impact": v.get("impact"), "rule_help": v.get("help"),
                          "wcag_criteria": wcag_criteria(v.get("tags", [])), "target": node["target"][0],
                          # same text as in the real run's prompt (newlines -> spaces)
                          "failure_summary": (node.get("failureSummary") or "").replace("\n", " "),
                          "sent_chars": len(sent)})
        if found:  # this rule has usable elements: shortest first
            return sorted(found, key=lambda c: c["sent_chars"])
    return []


def what_changed(before, after):
    """Words removed from / added to the HTML, so the audience sees the change at a glance."""
    a, b = re.findall(r"[^\s<>]+|[<>]", before), re.findall(r"[^\s<>]+|[<>]", after)
    removed, added = [], []
    for op, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a, b, autojunk=False).get_opcodes():
        if op in ("delete", "replace"):
            removed.append(" ".join(a[i1:i2]))
        if op in ("insert", "replace"):
            added.append(" ".join(b[j1:j2]))
    if not removed and not added and before != after:
        return "(no words)", "(no words - only spaces / line breaks changed)"
    short = lambda parts: "; ".join(p if len(p) <= 120 else p[:117] + "..." for p in parts) or "(nothing)"
    return short(removed), short(added)


def main():
    parser = argparse.ArgumentParser(description="Demo: scan one saved page, let the LLM fix one problem, re-check it.")
    parser.add_argument("page", nargs="?", help="file name of a saved page in data/captures/")
    parser.add_argument("--rule", help="which problem type to repair (an axe rule id, e.g. color-contrast)")
    parser.add_argument("--model", default=DEFAULT_MODEL, help=f"Ollama model (default {DEFAULT_MODEL})")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")
    if not args.page:
        list_pages()
        return
    capture = rp.CAPTURES_DIR / args.page.replace("\\", "/").split("/")[-1]  # accept a name or a path
    if not capture.exists():
        sys.exit(f"Not found: {capture}. Run demo.py without a page name to see the list.")

    env = {**rp.load_env(), "LLM_MODEL": args.model}
    try:
        model = rp.model_info("ollama", env)  # exits with a clear message if the model is not pulled
    except urllib.error.URLError:
        sys.exit("Ollama is not running. Start the Ollama app, then run the demo again.")

    axe_source = ax.load_axe_source()
    with sync_playwright() as p:
        browser = p.chromium.launch()

        # ---------- STEP 1: scan the saved page
        print(LINE + "\nSTEP 1  Scan the saved page with axe-core (offline: no website contacted, page scripts off)")
        print(LINE + f"\nPage: {capture.name}")
        context, page = rp.open_offline(browser, capture)
        try:
            results, _ = ax.run_axe(page, axe_source)
            violations = sorted(results["violations"], key=lambda v: -len(v["nodes"]))
            total = sum(len(v["nodes"]) for v in violations)
            print(f"Found {total} failing element{'s' * (total != 1)} of {len(violations)} problem "
                  f"type{'s' * (len(violations) != 1)} (WCAG 2.1 A + AA rules):\n")
            for v in violations:
                saved_extra = sum(bool((info := element_info(page, n)) and info["added_by_save_tool"]) for n in v["nodes"])
                note = f"  ({saved_extra} added while saving the page, not the airline's)" if saved_extra else ""
                print(f"  {len(v['nodes']):>4} x  {v['help']}")
                print(f"          rule {v['id']}, impact {IMPACT_WORDS.get(v.get('impact'), v.get('impact'))}{note}")
            if not violations:
                print("No problems found by axe-core on this page - choose another page for the repair demo.")
                return
            cands = candidates(page, violations, args.rule)
        finally:
            context.close()
        if not cands:
            sys.exit("\nNo element on this page can be repaired by the pipeline (all are inside iframes / shadow DOM). "
                     "Choose another page.")

        # ---------- STEP 2: choose one problem and check the method is neutral for it
        print("\n" + LINE + "\nSTEP 2  Choose one problem to repair")
        print(LINE)
        chosen = None
        short_first = [c for c in cands if c["sent_chars"] <= SHORT_HTML] + [c for c in cands if c["sent_chars"] > SHORT_HTML]
        for c in short_first[:5]:  # try at most 5 elements
            context, page = rp.open_offline(browser, capture)
            try:
                original_full = page.evaluate("(s) => document.querySelector(s).outerHTML", c["target"])
                page.evaluate("([s, m]) => document.querySelector(s).setAttribute('data-repair-id', m)", [c["target"], "DEMO"])
                _, before_on_el, before_page = rp.axe_on_page(page, axe_source, "DEMO")
            finally:
                context.close()
            original, uris = rp.prompt_html(original_full)
            # CONTROL (same as the real run): put the UNCHANGED element back, save, re-scan.
            # If that alone changes the result, this element cannot be tested fairly -> try the next one.
            control = rp.apply_and_rescan(browser, axe_source, capture, c, rp.restore_data_uris(original, uris),
                                          "DEMO", DEMO_DIR / f"control_{capture.name}")
            if (c["rule_id"] in before_on_el and control.get("apply_status") == "applied"
                    and sorted(control["rules_on_element"]) == sorted(before_on_el)
                    and control["page_violations_by_rule"] == before_page):
                chosen = c
                break
        if chosen is None:
            sys.exit("The control check failed for the tried elements (the method would change the result by itself). "
                     "Choose another page or --rule.")
        print(f"Problem: {chosen['rule_help']}  (rule {chosen['rule_id']}, WCAG {chosen['wcag_criteria'].replace(';', ', ')})")
        why = re.sub(r"\s+", " ", chosen["failure_summary"]).strip()  # tidy spacing for the screen only
        print(f"Why axe-core says it fails: {why if len(why) <= 160 else why[:157] + '...'}")
        print(f"\nBEFORE (the failing HTML, as sent to the model):\n  {original}")

        # ---------- STEP 3: ask the local LLM for a fix
        print("\n" + LINE + f"\nSTEP 3  Ask the local LLM ({args.model}, Ollama) to fix it")
        print(LINE)
        prompt = rp.PROMPT_TEMPLATE.format(original_html=original, **{k: chosen[k] for k in
                                           ("rule_id", "rule_help", "wcag_criteria", "failure_summary")})
        print("(thinking ... the first answer can take up to a minute while the model loads)")
        raw, served, secs, usage = rf.ask("ollama", env, prompt)
        fixed, _ = rp.clean_llm_output(raw)
        print(f"Answer received in {secs} s.\n\nAFTER (the model's fix):\n  {fixed}")
        removed, added = what_changed(original, fixed)
        print(f"\nWhat changed:  removed: {removed}\n               added:   {added}")

        # ---------- STEP 4: apply the fix to a COPY and scan it again
        print("\n" + LINE + "\nSTEP 4  Put the fix into a COPY of the page and scan the copy again")
        print(LINE)
        repaired_file = DEMO_DIR / f"repaired_{capture.name}"
        after = rp.apply_and_rescan(browser, axe_source, capture, chosen, rp.restore_data_uris(fixed, uris),
                                    "DEMO", repaired_file)
        flags = rp.quality_flags(original, fixed)
        if fixed.strip() == original.strip():
            verdict = "not_fixed"
            print("RESULT: NOT FIXED - the model returned the HTML unchanged.")
        elif after["apply_status"] != "applied":
            verdict = "invalid_output"
            print(f"RESULT: INVALID - the answer could not be used ({after['apply_status']}).")
        else:
            still = chosen["rule_id"] in after["rules_on_element"]
            new = sorted(set(after["rules_on_element"]) - set(before_on_el)) + \
                sorted(r for r in after["page_violations_by_rule"] if r not in before_page)
            if still:
                verdict = "not_fixed"
                print("RESULT: NOT FIXED - axe-core still reports the same problem on this element.")
            elif new:
                verdict = "fixed_but_new_issue"
                print(f"RESULT: FIXED, BUT NEW PROBLEM - the original problem is gone, but now: {', '.join(new)}")
            else:
                verdict = "fixed"
                print("RESULT: ACCEPTED - axe-core no longer reports the problem, and no new problem appeared.")
        if verdict in ("fixed", "fixed_but_new_issue"):
            reasons = [text for key, text in [("placeholder_text", "uses generic placeholder text"),
                                              ("hides_content", "hides content from screen readers"),
                                              ("removes_aria", "removes ARIA information"),
                                              ("changes_role", "adds or changes a role")] if flags[key]]
            print("Review flags: " + ("a person should check it - the fix " + "; ".join(reasons)
                                      if reasons else "none (looks plausible)"))
        print("Note: passing axe-core is not proof that the fix helps real users - Objective 3 checks that.")

        # Save what this demo did (rule 5: model version and exact prompt for every LLM step).
        record = {"created_utc": ax.utc_now(), "page": capture.name, "tools": ax.tool_versions(browser),
                  "model": model, "settings": {"temperature": 0, "seed": 42, "num_ctx": rf.NUM_CTX},
                  "element": chosen, "system_prompt": rp.SYSTEM_PROMPT, "prompt": prompt, "llm_raw_output": raw,
                  "llm_served_model": served, "llm_seconds": secs, **usage, "fixed_html": fixed,
                  "after": after, "verdict": verdict, "quality_flags": flags}
        record_path = DEMO_DIR / f"demo_{ax.make_run_id()}.json"
        record_path.write_text(json.dumps(record, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"\n(Repaired copy and full record saved in {ax.project_relative(DEMO_DIR)}/ - the saved page itself is unchanged.)")
        browser.close()


if __name__ == "__main__":
    main()
