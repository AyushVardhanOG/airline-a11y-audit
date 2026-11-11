"""
repair.py - Step 5 (Objective 2) PILOT: can an LLM fix the accessibility failures that
axe-core found?

Three commands, run in this order:

  select  Pick about 40 failing elements: the 10 most common rules (by number of pages, same
          ranking as the analysis), about 4 elements each, spread over as many airlines as
          possible. Experimental rules and elements inside iframes are skipped; so are elements
          whose full HTML is longer than MAX_HTML_CHARS (too big to replace reliably).
          Exact element positions (axe "target" selectors) come from the raw capture-scan JSON
          that violations_all.csv was made from. No LLM, no website: saved copies only.
          -> data/results/repairs_pilot_selection.csv

  run     For each selected element:
            1. open the saved copy OFFLINE (same setup as scan_captures.py), find the element,
               take its full HTML (SingleFile's data-sf-* attributes removed) and run axe-core
               to confirm the failure ("before");
            2. send the HTML, the axe rule id + help text, axe's failure summary and the WCAG
               criterion to the LLM, asking ONLY for the corrected HTML;
            3. replace the element with the LLM's HTML in a COPY of the page and save it in
               data/repaired/ (never touching data/captures/; rule 4);
            4. re-scan the saved COPY with axe-core ("after"): is the rule still failing on that
               element, and did any new failure appear on the element or on the page?
          -> data/results/repairs_pilot.json (everything, incl. exact prompts and model version)

  report  -> data/results/repairs_pilot_report.html (simple before/after table)

LLM settings come from .env (never committed), e.g. for Ollama (recommended, local, free):
    LLM_PROVIDER=ollama
    LLM_MODEL=qwen2.5-coder:7b
    OLLAMA_URL=http://localhost:11434
or any free API with an OpenAI-compatible endpoint:
    LLM_PROVIDER=openai_compatible
    LLM_BASE_URL=https://.../v1
    LLM_MODEL=<model name>
    LLM_API_KEY=<your key>
Provider "echo" returns the HTML unchanged; it is ONLY for testing this pipeline (no LLM).

Run:
    .venv\\Scripts\\python.exe src\\repair.py select
    .venv\\Scripts\\python.exe src\\repair.py run        (only after the LLM is set up)
    .venv\\Scripts\\python.exe src\\repair.py report
"""

import argparse
import csv
import html
import json
import os
import re
import sys
import time
import urllib.request
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright

import axe_runner as ax

PROJECT_ROOT = ax.PROJECT_ROOT
CAPTURES_DIR = PROJECT_ROOT / "data" / "captures"
RAW_CAPTURE_SCANS = PROJECT_ROOT / "data" / "raw" / "capture_scans"
RESULTS = PROJECT_ROOT / "data" / "results"
REPAIRED_DIR = PROJECT_ROOT / "data" / "repaired"
SELECTION_CSV = RESULTS / "repairs_pilot_selection.csv"
PILOT_JSON = RESULTS / "repairs_pilot.json"
REPORT_HTML = RESULTS / "repairs_pilot_report.html"

N_RULES = 10            # the 10 most common rules
PER_RULE = 4            # about 4 elements per rule -> about 40
MAX_HTML_CHARS = 3000   # longer elements are skipped (measured as SENT: data: URIs shortened)
FAKE_BASE_URL = "http://saved-copy.localhost/"

SYSTEM_PROMPT = "You are a web accessibility expert. You fix HTML so that it meets WCAG 2.1 Level AA."
PROMPT_TEMPLATE = """The following HTML element from an airline website fails an automated accessibility check (axe-core).

Rule: {rule_id} - {rule_help}
WCAG success criterion: {wcag_criteria}
Why it fails (axe-core): {failure_summary}

Failing HTML:
{original_html}

Return ONLY the corrected HTML for this element: the same element with the smallest change that fixes the problem. Keep all other attributes and all content unchanged. Do not add any explanation and do not use Markdown code fences."""


# ---------------------------------------------------------------- small helpers

def strip_sf_attributes(snippet):
    """Remove SingleFile's own data-sf-* attributes (added while saving, not on the live site)."""
    return re.sub(r'\s+data-sf-[\w-]+(=("[^"]*"|\'[^\']*\'|[^\s>]*))?', "", snippet)


DATA_URI_RE = re.compile(r"data:[\w.+/-]+;base64,[A-Za-z0-9+/=]{100,}")


def shorten_data_uris(snippet):
    """
    SingleFile embeds images as long base64 'data:' URIs. They waste the prompt and an LLM can
    corrupt them when copying, so each is replaced by a short placeholder 'data:removed-N'
    before sending, and put back before the fix is applied. Returns (short snippet, [uris]).
    """
    uris = []

    def placeholder(m):
        uris.append(m.group(0))
        return f"data:removed-{len(uris)}"
    return DATA_URI_RE.sub(placeholder, snippet), uris


def restore_data_uris(snippet, uris):
    for i in range(len(uris), 0, -1):  # from the highest number down, so "removed-1" never matches "removed-12"
        snippet = snippet.replace(f"data:removed-{i}", uris[i - 1])
    return snippet


def prompt_html(full_outer_html):
    """The element's HTML as sent to the LLM: no data-sf-* attributes, data: URIs shortened."""
    return shorten_data_uris(strip_sf_attributes(full_outer_html))


def clean_llm_output(text):
    """Remove Markdown code fences if the model added them anyway. Returns (html, was_cleaned)."""
    t = text.strip()
    m = re.fullmatch(r"```[\w-]*\s*\n?(.*?)\n?```", t, re.S)
    return (m.group(1).strip(), True) if m else (t, False)


def load_env():
    """Tiny .env reader (KEY=value lines), so no extra package is needed."""
    env = {}
    path = PROJECT_ROOT / ".env"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    return {**env, **{k: v for k, v in os.environ.items() if k.startswith(("LLM_", "OLLAMA_"))}}


def latest_capture_run():
    return sorted(p for p in RAW_CAPTURE_SCANS.iterdir() if p.is_dir())[-1]


def open_offline(browser, file_path, html_bytes=None):
    """Open a saved page completely offline: served from disk, page scripts off, all else blocked."""
    body = html_bytes if html_bytes is not None else Path(file_path).read_bytes()
    url = FAKE_BASE_URL + Path(file_path).name

    def handler(route, request):
        if request.url == url:
            route.fulfill(status=200, body=body, headers={
                "Content-Type": "text/html; charset=utf-8", "Content-Security-Policy": "script-src 'none'"})
        else:
            route.abort()

    context = browser.new_context(viewport=ax.VIEWPORT, locale="en-US")
    context.route("**/*", handler)
    page = context.new_page()
    page.goto(url, wait_until="load", timeout=60_000)
    time.sleep(1)
    return context, page


# JavaScript run inside the page: which axe violations sit on (or inside) the marked element?
RULES_ON_MARKED = """([violations, marker]) => {
    const out = [];
    for (const v of violations) {
        for (const n of v.nodes) {
            if (n.target.length !== 1 || typeof n.target[0] !== 'string') continue;  // iframe / shadow DOM
            let el = null;
            try { el = document.querySelector(n.target[0]); } catch (e) { continue; }
            if (el && el.closest('[data-repair-id="' + marker + '"]')) { out.push(v.id); }
        }
    }
    return [...new Set(out)];
}"""


def axe_on_page(page, axe_source, marker):
    """Run axe on the page; return (violations, rules on the marked element, {rule: elements})."""
    results, _ = ax.run_axe(page, axe_source)
    v = results["violations"]
    on_el = page.evaluate(RULES_ON_MARKED, [v, marker])
    return v, on_el, {x["id"]: len(x["nodes"]) for x in v}


# ---------------------------------------------------------------- select

def cmd_select(args):
    run_dir = latest_capture_run()
    ranking = pd_rule_ranking()
    top_rules = ranking[:N_RULES]
    print(f"Capture-scan run {run_dir.name}; top {N_RULES} rules: {', '.join(top_rules)}")

    # Candidates from the raw scan JSON (exact selectors), one per failing element.
    candidates = {r: [] for r in top_rules}
    for path in sorted(run_dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        for v in rec["axe_results"]["violations"]:
            if v["id"] not in candidates or "experimental" in v.get("tags", []):
                continue
            for node in v["nodes"]:
                if len(node["target"]) != 1 or not isinstance(node["target"][0], str):
                    continue  # inside an iframe or shadow DOM: cannot be replaced reliably
                candidates[v["id"]].append({
                    "airline_id": rec["airline_id"], "page_type": rec["page_type"], "file_name": rec["file_name"],
                    "rule_id": v["id"], "impact": v.get("impact"), "rule_help": v.get("help"),
                    "wcag_criteria": ";".join(f"{m[1]}.{m[2]}.{m[3]}" for t in v.get("tags", [])
                                              if (m := re.fullmatch(r"wcag(\d)(\d)(\d+)", t))),
                    "target": node["target"][0], "failure_summary": (node.get("failureSummary") or "").replace("\n", " "),
                })

    airline_use = Counter()
    chosen, checked = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        pages = {}  # file -> (context, page), opened only when needed

        def html_length(c):
            """Length of the element's full HTML in the saved copy (None if not found)."""
            key = (c["file_name"], c["target"])
            if key not in checked:
                if c["file_name"] not in pages:
                    pages[c["file_name"]] = open_offline(browser, CAPTURES_DIR / c["file_name"])
                page = pages[c["file_name"]][1]
                # Web components keep content in a shadow DOM, which is LOST when an element is
                # re-created from its HTML text (trial: R17), so such elements are skipped.
                outer = page.evaluate("""(s) => { const e = document.querySelector(s); if (!e) return null;
                    if ([e, ...e.querySelectorAll('*')].some(x => x.shadowRoot)) return 'SHADOW';
                    return e.outerHTML; }""", c["target"])
                checked[key] = len(prompt_html(outer)[0]) if outer not in (None, "SHADOW") else None
            return checked[key]

        for rule in top_rules:
            pool = list(candidates[rule])
            picked = []
            while len(picked) < PER_RULE and pool:
                # prefer airlines used least so far, then pages not yet used for this rule
                used_pages = {x["file_name"] for x in picked}
                pool.sort(key=lambda c: (airline_use[c["airline_id"]], c["file_name"] in used_pages,
                                         c["airline_id"], c["file_name"], c["target"]))
                c = pool.pop(0)
                n = html_length(c)
                if n is None or n > MAX_HTML_CHARS:
                    continue  # not found or too large; try the next candidate
                c["html_length"] = n
                picked.append(c)
                airline_use[c["airline_id"]] += 1
            print(f"  {rule:<28} {len(picked)} picked from {len(candidates[rule])} candidates")
            chosen += picked
        for context, _ in pages.values():
            context.close()
        browser.close()

    for i, c in enumerate(chosen, 1):
        c["repair_id"] = f"R{i:02d}"
    fields = ["repair_id", "rule_id", "impact", "wcag_criteria", "airline_id", "page_type", "file_name",
              "target", "html_length", "rule_help", "failure_summary"]
    with open(SELECTION_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(chosen)
    print(f"\n{len(chosen)} elements from {len(set(c['airline_id'] for c in chosen))} airlines "
          f"-> {SELECTION_CSV.relative_to(PROJECT_ROOT)}")


def pd_rule_ranking():
    """Rules ranked like the analysis chart: by pages affected, then by elements."""
    rows = list(csv.DictReader(open(RESULTS / "violations_all.csv", encoding="utf-8")))
    pages, elems = {}, Counter()
    for r in rows:
        if r.get("is_experimental", "False") == "True":
            continue
        pages.setdefault(r["rule_id"], set()).add(r["file_name"])
        elems[r["rule_id"]] += 1
    return sorted(pages, key=lambda k: (-len(pages[k]), -elems[k], k))


# ---------------------------------------------------------------- LLM

def llm_settings():
    env = load_env()
    provider = env.get("LLM_PROVIDER", "")
    if provider not in ("ollama", "openai_compatible", "echo"):
        sys.exit("Set LLM_PROVIDER in .env to ollama, openai_compatible (or echo for a pipeline test).")
    return provider, env


def http_json(url, payload=None, headers=None, timeout=600):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def model_info(provider, env):
    """Model name + exact version, saved with every result (CLAUDE.md rule 5)."""
    if provider == "ollama":
        base = env.get("OLLAMA_URL", "http://localhost:11434")
        name = env["LLM_MODEL"]
        tags = http_json(f"{base}/api/tags")["models"]
        entry = next((m for m in tags if m["name"] == name or m["model"] == name), None)
        if entry is None:
            sys.exit(f"Model {name} is not pulled in Ollama. Run: ollama pull {name}")
        return {"provider": "ollama", "model": name, "digest": entry.get("digest"),
                "details": entry.get("details"), "ollama_version": http_json(f"{base}/api/version").get("version")}
    if provider == "openai_compatible":
        return {"provider": "openai_compatible", "model": env["LLM_MODEL"], "base_url": env["LLM_BASE_URL"]}
    return {"provider": "echo", "model": "echo (pipeline test: returns the HTML unchanged)"}


def ask_llm(provider, env, prompt):
    """Send one prompt. Returns (raw text, model id reported by the server, seconds)."""
    t0 = time.time()
    if provider == "ollama":
        base = env.get("OLLAMA_URL", "http://localhost:11434")
        r = http_json(f"{base}/api/chat", {
            "model": env["LLM_MODEL"], "stream": False,
            "options": {"temperature": 0, "seed": 42},
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]})
        return r["message"]["content"], r.get("model"), round(time.time() - t0, 1)
    if provider == "openai_compatible":
        r = http_json(f"{env['LLM_BASE_URL'].rstrip('/')}/chat/completions", {
            "model": env["LLM_MODEL"], "temperature": 0,
            "messages": [{"role": "system", "content": SYSTEM_PROMPT}, {"role": "user", "content": prompt}]},
            headers={"Authorization": f"Bearer {env['LLM_API_KEY']}"})
        return r["choices"][0]["message"]["content"], r.get("model"), round(time.time() - t0, 1)
    # echo: return the original HTML from the prompt unchanged (pipeline test only)
    original = prompt.split("Failing HTML:\n", 1)[1].split("\n\nReturn ONLY", 1)[0]
    return original, "echo", 0.0


# ---------------------------------------------------------------- run

APPLY_FIX = """([target, fixed, marker]) => {
    const el = document.querySelector(target);
    if (!el) return 'element not found';
    const tpl = document.createElement('template');
    tpl.innerHTML = fixed.trim();
    const roots = [...tpl.content.childNodes].filter(n => !(n.nodeType === 3 && !n.textContent.trim()));
    if (roots.length !== 1 || roots[0].nodeType !== 1) return 'output is not exactly one HTML element (' + roots.length + ' parts)';
    roots[0].setAttribute('data-repair-id', marker);
    el.replaceWith(roots[0]);
    return 'applied';
}"""


def apply_and_rescan(browser, axe_source, capture, sel, new_html, marker, out_path):
    """Replace the element in a COPY of the page, save the copy, re-scan the saved copy from disk."""
    context, page = open_offline(browser, capture)
    try:
        status = page.evaluate(APPLY_FIX, [sel["target"], new_html, marker])
        if status != "applied":
            return {"apply_status": status}
        copy_html = "<!DOCTYPE html>\n" + page.evaluate("() => document.documentElement.outerHTML")
    finally:
        context.close()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(copy_html, encoding="utf-8")
    context, page = open_offline(browser, out_path)
    try:
        _, on_el, by_rule = axe_on_page(page, axe_source, marker)
    finally:
        context.close()
    return {"apply_status": "applied", "repaired_file": ax.project_relative(out_path),
            "rules_on_element": on_el, "page_violations_by_rule": by_rule}


HIDING_PATTERNS = [r'alt\s*=\s*""', r"alt\s*=\s*''", r'aria-hidden\s*=\s*"true"', r'role\s*=\s*"(presentation|none)"']


def hides_content(before, after):
    """
    True if the fix ADDS alt="", aria-hidden="true" or role="presentation"/"none". Such fixes pass
    automated checks by hiding content from assistive technology. That is only right for truly
    decorative content, so a human must judge them (trial: R13 got alt="").
    """
    return any(len(re.findall(p, after, re.I)) > len(re.findall(p, before, re.I)) for p in HIDING_PATTERNS)


GENERIC_TEXTS = {"image", "image description", "description", "icon", "link", "button", "graphic", "picture",
                 "photo", "placeholder", "alt text", "alternative text", "text", "label"}


def attr_pairs(snippet, prefix_re):
    """Set of (attribute, value) pairs whose name matches prefix_re, e.g. aria-* or role."""
    return set(re.findall(rf'\s({prefix_re})\s*=\s*"([^"]*)"', snippet, re.I))


def visible_text(snippet):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", snippet)).strip()


def quality_flags(before, after):
    """
    Automatic review flags for a fix (added after the pilot: passing axe-core is not the same as a
    correct fix). Any of the first four -> needs_human_check.
      placeholder_text  new alt / aria-label text is generic ("Image description", "icon", ...)
      hides_content     adds alt="", aria-hidden="true" or role="presentation"/"none"
      removes_aria      an aria-* attribute or role present before is gone (information removed)
      changes_role      a role was added or changed (behaviour, e.g. keyboard support, may be missing)
      text_changed      the element's text content changed (informational)
    """
    new_labels = {v.strip().lower() for _, v in attr_pairs(after, r"alt|aria-label") - attr_pairs(before, r"alt|aria-label")}
    aria_b, aria_a = attr_pairs(before, r"aria-[\w-]+"), attr_pairs(after, r"aria-[\w-]+")
    role_b, role_a = attr_pairs(before, r"role"), attr_pairs(after, r"role")
    flags = {
        "placeholder_text": any(v in GENERIC_TEXTS for v in new_labels if v),
        "hides_content": hides_content(before, after),
        "removes_aria": bool({n.lower() for n, _ in aria_b} - {n.lower() for n, _ in aria_a}) or bool(role_b - role_a),
        "changes_role": bool(role_a - role_b),
        "text_changed": visible_text(before) != visible_text(after),
    }
    flags["needs_human_check"] = any(flags[k] for k in ("placeholder_text", "hides_content", "removes_aria", "changes_role"))
    return flags


def repair_one(browser, axe_source, provider, env, sel):
    rid, marker = sel["repair_id"], sel["repair_id"]
    rec = {k: sel[k] for k in ("repair_id", "rule_id", "impact", "wcag_criteria", "airline_id", "page_type",
                               "file_name", "target", "rule_help", "failure_summary")}
    capture = CAPTURES_DIR / sel["file_name"]

    # 1. BEFORE: open the saved copy, mark the element (in memory only), confirm the failure.
    context, page = open_offline(browser, capture)
    try:
        original_full = page.evaluate("(s) => { const e = document.querySelector(s); return e ? e.outerHTML : null; }",
                                      sel["target"])
        if original_full is None:
            rec["verdict"] = "element_not_found"
            return rec
        page.evaluate("([s, m]) => document.querySelector(s).setAttribute('data-repair-id', m)", [sel["target"], marker])
        _, before_on_el, before_page = axe_on_page(page, axe_source, marker)
    finally:
        context.close()
    rec["original_html"], uris = prompt_html(original_full)  # exactly what the LLM sees
    rec["data_uris_shortened"] = len(uris)
    rec["before"] = {"rules_on_element": before_on_el, "page_violations_by_rule": before_page,
                     "rule_fails_on_element": sel["rule_id"] in before_on_el}

    # 1b. CONTROL: put the UNCHANGED element back with the same replace + save + re-scan steps as a
    #     real fix. If that alone changes the result, the pipeline is not neutral for this element
    #     (trial: R17, a web component), so a verdict would say nothing about the LLM -> skip it.
    control = apply_and_rescan(browser, axe_source, capture, sel, restore_data_uris(rec["original_html"], uris),
                               marker, REPAIRED_DIR / f"{rid}_control.html")
    rec["control"] = control
    rec["control_ok"] = (control.get("apply_status") == "applied"
                         and sel["rule_id"] in control.get("rules_on_element", [])
                         and sorted(control["rules_on_element"]) == sorted(before_on_el)
                         and control["page_violations_by_rule"] == before_page)
    if not rec["control_ok"]:
        rec["verdict"] = "pipeline_artifact"
        return rec

    # 2. Ask the LLM.
    prompt = PROMPT_TEMPLATE.format(original_html=rec["original_html"], **{k: sel[k] for k in
                                    ("rule_id", "rule_help", "wcag_criteria", "failure_summary")})
    rec["prompt"] = prompt
    try:
        raw, served_model, secs = ask_llm(provider, env, prompt)
    except Exception as e:  # network / server problems are recorded, not hidden
        rec["verdict"] = "llm_error"
        rec["llm_error"] = str(e)
        return rec
    rec["llm_raw_output"], rec["llm_served_model"], rec["llm_seconds"] = raw, served_model, secs
    rec["fixed_html"], rec["output_cleaned"] = clean_llm_output(raw)
    rec["output_unchanged"] = rec["fixed_html"].strip() == rec["original_html"].strip()

    rec["hides_content"] = hides_content(rec["original_html"], rec["fixed_html"])
    rec["quality_flags"] = quality_flags(rec["original_html"], rec["fixed_html"])

    # 3 + 4. Apply the fix to a COPY in data/repaired/ (never the capture) and re-scan that saved copy.
    after = apply_and_rescan(browser, axe_source, capture, sel, restore_data_uris(rec["fixed_html"], uris),
                             marker, REPAIRED_DIR / f"{rid}_{sel['file_name']}")
    rec["apply_status"] = after["apply_status"]
    if after["apply_status"] != "applied":
        rec["verdict"] = "invalid_output"
        return rec
    rec["repaired_file"] = after["repaired_file"]
    after_on_el, after_page = after["rules_on_element"], after["page_violations_by_rule"]
    still = sel["rule_id"] in after_on_el
    new_on_el = sorted(set(after_on_el) - set(before_on_el))
    new_on_page = sorted(r for r in after_page if r not in before_page)
    rec["after"] = {"rules_on_element": after_on_el, "page_violations_by_rule": after_page,
                    "rule_still_fails_on_element": still, "new_rules_on_element": new_on_el,
                    "new_rules_on_page": new_on_page}
    if still:
        rec["verdict"] = "not_fixed"
    elif new_on_el or new_on_page:
        rec["verdict"] = "fixed_but_new_issue"
    else:
        rec["verdict"] = "fixed"
    return rec


def cmd_run(args):
    provider, env = llm_settings()
    if provider == "echo" and not args.test:
        sys.exit("Provider 'echo' is only for pipeline tests (use --test).")
    selection = list(csv.DictReader(open(SELECTION_CSV, encoding="utf-8")))
    if args.ids:
        wanted = [i.strip() for i in args.ids.split(",")]
        selection = [s for s in selection if s["repair_id"] in wanted]
    if args.limit:
        selection = selection[:args.limit]
    info = model_info(provider, env)
    axe_source = ax.load_axe_source()
    out_path = Path(args.out) if args.out else PILOT_JSON
    print(f"{len(selection)} repairs with {info['model']} ({provider}) -> {ax.project_relative(out_path)}")

    records = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        meta = {
            "created_utc": ax.utc_now(), "llm": info, "temperature": 0, "seed": 42 if provider == "ollama" else None,
            "system_prompt": SYSTEM_PROMPT, "prompt_template": PROMPT_TEMPLATE,
            "tool_versions": {**ax.tool_versions(browser), "axe_core": "4.14.0"},
            "capture_scan_run": latest_capture_run().name, "selection_file": ax.project_relative(SELECTION_CSV),
            "settings": {"wcag_tags": ax.WCAG_TAGS, "viewport": ax.VIEWPORT, "max_html_chars": MAX_HTML_CHARS,
                         "page_scripts": "disabled (CSP script-src 'none')", "network": "blocked (offline)"},
        }
        for i, sel in enumerate(selection, 1):
            rec = repair_one(browser, axe_source, provider, env, sel)
            records.append(rec)
            print(f"[{i}/{len(selection)}] {rec['repair_id']} {rec['rule_id']:<28} {rec['airline_id']:<18} -> {rec['verdict']}", flush=True)
            out_path.write_text(json.dumps({"meta": meta, "repairs": records}, indent=2, ensure_ascii=False),
                                encoding="utf-8")  # saved after every repair, so nothing is lost
        browser.close()
    print("\nVerdicts:", dict(Counter(r["verdict"] for r in records)))


# ---------------------------------------------------------------- report

def cmd_report(args):
    src = Path(args.inp) if args.inp else PILOT_JSON
    data = json.loads(src.read_text(encoding="utf-8"))
    reps, meta = data["repairs"], data["meta"]
    counts = Counter(r["verdict"] for r in reps)
    label = {"fixed": "Fixed", "fixed_but_new_issue": "Fixed, but new issue", "not_fixed": "Not fixed",
             "invalid_output": "Invalid output", "llm_error": "LLM error", "element_not_found": "Element not found",
             "pipeline_artifact": "Not evaluated (control failed)"}
    esc = lambda s: html.escape(s or "")
    # Review flags are computed here from the saved before/after HTML (they were added after the pilot
    # run), so the report and the summary CSV are always based on the same rules.
    for r in reps:
        if r.get("fixed_html") is not None:
            r["quality_flags"] = quality_flags(r["original_html"], r["fixed_html"])
            r["hides_content"] = r["quality_flags"]["hides_content"]
    summary_rows = [{
        "repair_id": r["repair_id"], "rule_id": r["rule_id"], "impact": r["impact"], "wcag_criteria": r["wcag_criteria"],
        "airline_id": r["airline_id"], "page_type": r["page_type"], "verdict": r["verdict"],
        "output_unchanged": r.get("output_unchanged"), "llm_seconds": r.get("llm_seconds"),
        **{k: r.get("quality_flags", {}).get(k) for k in ("needs_human_check", "placeholder_text", "hides_content",
                                                           "removes_aria", "changes_role", "text_changed")},
    } for r in reps]
    summary_csv = (Path(args.out).with_suffix(".csv") if args.out else RESULTS / "repairs_pilot_summary.csv")
    with open(summary_csv, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=list(summary_rows[0].keys()))
        w.writeheader()
        w.writerows(summary_rows)
    n_fixed = sum(r["verdict"] == "fixed" for r in reps)
    n_check = sum(r["verdict"] == "fixed" and r.get("quality_flags", {}).get("needs_human_check") for r in reps)
    rows = []
    for r in reps:
        after = r.get("after", {})
        extra = ""
        if after.get("new_rules_on_element") or after.get("new_rules_on_page"):
            extra = f"<div class=note>New: {esc(', '.join(sorted(set(after.get('new_rules_on_element', []) + after.get('new_rules_on_page', [])))))}</div>"
        if r.get("apply_status") and r["apply_status"] != "applied":
            extra += f"<div class=note>{esc(r['apply_status'])}</div>"
        qf = r.get("quality_flags", {})
        if r["verdict"].startswith("fixed") and qf.get("needs_human_check"):
            why = {"placeholder_text": "generic placeholder text", "hides_content": "hides content (alt=\"\", aria-hidden or role=presentation/none)",
                   "removes_aria": "removes ARIA information", "changes_role": "adds or changes a role (behaviour such as keyboard support not checked)"}
            extra += ("<div class='note check'><b>Check by hand:</b> "
                      + esc("; ".join(v for k, v in why.items() if qf.get(k))) + "</div>")
        if r.get("output_unchanged"):
            extra += "<div class=note>Model returned the HTML unchanged</div>"
        if r["verdict"] == "pipeline_artifact":
            extra += "<div class=note>Putting the unchanged element back already changed the result, so the fix cannot be judged</div>"
        rows.append(f"""<tr><td>{esc(r['repair_id'])}</td><td><b>{esc(r['rule_id'])}</b><br><span class=muted>WCAG {esc(r['wcag_criteria'])}</span></td>
<td>{esc(r['airline_id'])}<br><span class=muted>{esc(r['page_type'])}</span></td>
<td><pre>{esc(r.get('original_html'))}</pre></td><td><pre>{esc(r.get('fixed_html'))}</pre></td>
<td><span class="v {esc(r['verdict'])}">{esc(label.get(r['verdict'], r['verdict']))}</span>{extra}</td></tr>""")
    summary = " &middot; ".join(f"{label.get(k, k)}: <b>{v}</b>" for k, v in counts.most_common())
    page = f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8"><title>LLM repair pilot</title>
<meta name="viewport" content="width=device-width, initial-scale=1">
<style>
:root{{--bg:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--line:#e1e0d9;--ok:#006300;--warn:#8a5a00;--bad:#b42323}}
body{{font-family:system-ui,"Segoe UI",sans-serif;background:var(--bg);color:var(--ink);margin:24px 16px;max-width:1400px}}
h1{{font-size:22px;margin:0 0 4px}} .muted{{color:var(--ink2);font-size:13px}}
table{{border-collapse:collapse;width:100%;margin-top:16px}} th,td{{border-top:1px solid var(--line);padding:8px;vertical-align:top;text-align:left}}
th{{font-size:13px;color:var(--ink2)}} pre{{white-space:pre-wrap;word-break:break-all;font-size:12px;margin:0;max-height:260px;overflow:auto}}
td:nth-child(4),td:nth-child(5){{width:34%}} .v{{font-weight:600}} .fixed{{color:var(--ok)}} .fixed_but_new_issue{{color:var(--warn)}}
.not_fixed,.invalid_output,.llm_error,.element_not_found{{color:var(--bad)}} .pipeline_artifact{{color:var(--ink2)}} .check{{color:var(--warn)}} .note{{font-size:12px;color:var(--ink2);margin-top:4px}}
</style></head><body>
<h1>LLM repair pilot: before and after</h1>
<p class=muted>Model: {esc(meta['llm'].get('model'))} ({esc(meta['llm'].get('provider'))}{', digest ' + esc((meta['llm'].get('digest') or '')[:12]) if meta['llm'].get('digest') else ''}) &middot;
created {esc(meta['created_utc'])} &middot; fixes applied to copies of the saved pages and re-scanned with axe-core {esc(meta['tool_versions'].get('axe_core'))}.
"Fixed" = the rule no longer fails on the repaired element and no new failure appeared on the element or page.
"Fixed" means axe-core is satisfied, not that the fix is correct for users: fixes marked "check by hand" use placeholder text,
hide content, remove ARIA information or add a role, and must be judged by a person.</p>
<p>{summary} (of {len(reps)}). Of the {n_fixed} "fixed": <b>{n_check}</b> need a human check (automatic review flags), {n_fixed - n_check} look plausible.</p>
<table><thead><tr><th>ID</th><th>Rule</th><th>Airline / page</th><th>Before (original HTML)</th><th>After (LLM HTML)</th><th>Result</th></tr></thead>
<tbody>{''.join(rows)}</tbody></table></body></html>"""
    out = Path(args.out) if args.out else REPORT_HTML
    out.write_text(page, encoding="utf-8")
    print(f"Wrote {ax.project_relative(out)}")


def main():
    parser = argparse.ArgumentParser(description="LLM repair pilot (Step 5).")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    r = sub.add_parser("run")
    r.add_argument("--limit", type=int, help="only the first N selected elements")
    r.add_argument("--ids", help="only these repair ids, e.g. R01,R05,R09")
    r.add_argument("--out", help="write results here instead of data/results/repairs_pilot.json")
    r.add_argument("--test", action="store_true", help="allow the 'echo' test provider")
    rep = sub.add_parser("report")
    rep.add_argument("--inp", help="results JSON (default data/results/repairs_pilot.json)")
    rep.add_argument("--out", help="report HTML (default data/results/repairs_pilot_report.html)")
    args = parser.parse_args()
    {"select": cmd_select, "run": cmd_run, "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
