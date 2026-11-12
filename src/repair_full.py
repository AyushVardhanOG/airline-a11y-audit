"""
repair_full.py - Step 5 FULL RUN (Objective 2): every de-duplicated failing element, repaired by
3 local LLMs, with the same prompt, settings, apply-to-a-copy, re-scan and control run as the
pilot (all of that logic is imported from repair.py, so the pilot and the full run are identical).

Commands (in this order):

  select   ALL failing elements of the latest capture scan, except
             - elements inside iframes or shadow DOM, and elements that are or contain a
               shadow-DOM host (they cannot be replaced faithfully; pilot finding, R17),
             - <html>, <head>, <body> (they cannot be swapped as one element),
             - elements whose HTML (as sent) is too large for the model context (see MAX_SENT_CHARS),
           and de-duplicated: ONE element per (airline, rule, identical HTML). Identical = the full
           outerHTML without SingleFile's data-sf-* attributes (data: URIs NOT shortened for this
           comparison, so two different images never look identical). The kept element records how
           many copies it stands for and on which pages.
           -> data/results/repairs_full_selection.csv, data/results/repairs_full_exclusions.csv

  prepare  Model-independent part, once per element: "before" scan (the failure is really there)
           and the CONTROL run (unchanged HTML put back, saved, re-scanned).
           -> data/results/repairs_full_controls.jsonl   (resumable)

  run --model M [--limit N]
           For every element with a passing control: ask model M, apply the fix to a COPY in
           data/repaired/full/ and re-scan it. One JSON line per (model, element), appended
           immediately -> data/results/repairs_full_log.jsonl. If the run stops, starting it again
           skips everything already in the log (resumable).

  report   -> data/results/repairs_full.json (meta + all records), repairs_full_summary.csv,
              charts in data/results/charts/

Settings: identical to the pilot (repair.py: same system prompt, prompt template, temperature 0,
seed 42) plus an explicit context window NUM_CTX for every model (see the note at NUM_CTX).
"""

import argparse
import csv
import json
import sys
import time
from collections import Counter
from pathlib import Path

from playwright.sync_api import sync_playwright

import axe_runner as ax
import repair as rp

RESULTS = ax.PROJECT_ROOT / "data" / "results"
SELECTION_CSV = RESULTS / "repairs_full_selection.csv"
EXCLUSIONS_CSV = RESULTS / "repairs_full_exclusions.csv"
CONTROLS_LOG = RESULTS / "repairs_full_controls.jsonl"
RUN_LOG = RESULTS / "repairs_full_log.jsonl"
FULL_JSON = RESULTS / "repairs_full.json"
SUMMARY_CSV = RESULTS / "repairs_full_summary.csv"
REPAIRED_DIR = ax.PROJECT_ROOT / "data" / "repaired" / "full"

# Context window given to EVERY model (prompt + answer must fit). The pilot used Ollama's default,
# which was 4096 tokens (checked with /api/ps). The full run includes larger elements, so the window
# is set explicitly to 8192 = the maximum of gemma2 (the smallest of the three), the same for all models.
NUM_CTX = 8192
# Prompt (~250 tokens of instructions + the element) AND an answer about as long as the element must fit
# in NUM_CTX. HTML is about 3 characters per token or more, so elements up to 10,000 characters as sent
# (~3,300 tokens each way) fit with a margin; larger ones are excluded as too_large_for_context.
MAX_SENT_CHARS = 10_000
DOCUMENT_ELEMENTS = {"html", "head", "body"}


# ---------------------------------------------------------------- jsonl helpers

def read_jsonl(path):
    if not path.exists():
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def append_jsonl(path, record):
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")
        f.flush()


# ---------------------------------------------------------------- select

ELEMENT_INFO = """(s) => { const e = document.querySelector(s); if (!e) return null;
    return {tag: e.tagName.toLowerCase(),
            shadow: [e, ...e.querySelectorAll('*')].some(x => x.shadowRoot),
            outer: e.outerHTML}; }"""


def cmd_select(args):
    run_dir = rp.latest_capture_run()
    nodes, excluded = [], []
    for path in sorted(run_dir.glob("*.json")):
        rec = json.loads(path.read_text(encoding="utf-8"))
        for v in rec["axe_results"]["violations"]:
            if "experimental" in v.get("tags", []):
                excluded.append({"reason": "experimental_rule", "rule_id": v["id"], "file_name": rec["file_name"]})
                continue
            for node in v["nodes"]:
                base = {"airline_id": rec["airline_id"], "page_type": rec["page_type"], "file_name": rec["file_name"],
                        "rule_id": v["id"], "impact": v.get("impact"), "rule_help": v.get("help"),
                        "wcag_criteria": ";".join(f"{m[1]}.{m[2]}.{m[3]}" for t in v.get("tags", [])
                                                  if (m := rp.re.fullmatch(r"wcag(\d)(\d)(\d+)", t))),
                        "failure_summary": (node.get("failureSummary") or "").replace("\n", " ")}
                if len(node["target"]) != 1 or not isinstance(node["target"][0], str):
                    excluded.append({**base, "reason": "inside_iframe_or_shadow_dom"})
                    continue
                nodes.append({**base, "target": node["target"][0]})
    print(f"capture-scan run {run_dir.name}: {len(nodes) + sum(e['reason'] == 'inside_iframe_or_shadow_dom' for e in excluded)} "
          f"failing elements; {len(nodes)} not inside an iframe / shadow DOM")

    kept, seen = [], {}
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for file_name in sorted({n["file_name"] for n in nodes}):
            context, page = rp.open_offline(browser, rp.CAPTURES_DIR / file_name)
            for n in (x for x in nodes if x["file_name"] == file_name):
                info = page.evaluate(ELEMENT_INFO, n["target"])
                if info is None:
                    excluded.append({**n, "reason": "element_not_found"})
                elif info["tag"] in DOCUMENT_ELEMENTS:
                    excluded.append({**n, "reason": "document_element"})
                elif info["shadow"]:
                    excluded.append({**n, "reason": "contains_shadow_dom"})
                else:
                    stripped = rp.strip_sf_attributes(info["outer"])
                    key = (n["airline_id"], n["rule_id"], stripped)
                    if key in seen:  # duplicate: count it on the element we keep
                        k = seen[key]
                        k["copies"] += 1
                        k["copy_files"].add(file_name)
                        excluded.append({**n, "reason": "duplicate", "duplicate_of_target": k["target"],
                                         "duplicate_of_file": k["file_name"]})
                        continue
                    sent_len = len(rp.prompt_html(info["outer"])[0])
                    if sent_len > MAX_SENT_CHARS:
                        excluded.append({**n, "reason": "too_large_for_context", "sent_chars": sent_len})
                        seen[key] = {**n, "copies": 1, "copy_files": {file_name}}  # its duplicates are too large too
                        continue
                    item = {**n, "sent_chars": sent_len, "copies": 1, "copy_files": {file_name}}
                    seen[key] = item
                    kept.append(item)
            context.close()
        browser.close()

    for i, k in enumerate(kept, 1):
        k["element_id"] = f"F{i:04d}"
        k["copy_files"] = ";".join(sorted(k["copy_files"]))
    fields = ["element_id", "rule_id", "impact", "wcag_criteria", "airline_id", "page_type", "file_name", "target",
              "sent_chars", "copies", "copy_files", "rule_help", "failure_summary"]
    with open(SELECTION_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(kept)
    with open(EXCLUSIONS_CSV, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["reason", "rule_id", "airline_id", "page_type", "file_name", "target",
                                          "sent_chars", "duplicate_of_file", "duplicate_of_target"], extrasaction="ignore")
        w.writeheader()
        w.writerows(excluded)

    reasons = Counter(e["reason"] for e in excluded)
    print("excluded:", dict(reasons))
    print(f"SELECTED: {len(kept)} unique elements (they stand for {sum(k['copies'] for k in kept)} failing elements), "
          f"{len({k['airline_id'] for k in kept})} airlines, {len({k['rule_id'] for k in kept})} rules")
    sizes = sorted(k["sent_chars"] for k in kept)
    print(f"size as sent: median {sizes[len(sizes) // 2]}, 90% <= {sizes[int(len(sizes) * 0.9)]}, max {sizes[-1]} characters")
    print("per rule:", dict(Counter(k["rule_id"] for k in kept).most_common()))


# ---------------------------------------------------------------- prepare (before + control, once per element)

def cmd_prepare(args):
    selection = list(csv.DictReader(open(SELECTION_CSV, encoding="utf-8")))
    done = {r["element_id"] for r in read_jsonl(CONTROLS_LOG)}
    todo = [s for s in selection if s["element_id"] not in done][: args.limit or None]
    print(f"{len(done)} already prepared, {len(todo)} to do")
    axe_source = ax.load_axe_source()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for i, sel in enumerate(todo, 1):
            t0 = time.time()
            rec = prepare_one(browser, axe_source, sel)
            rec["seconds"] = round(time.time() - t0, 1)
            append_jsonl(CONTROLS_LOG, rec)
            print(f"[{i}/{len(todo)}] {sel['element_id']} {sel['rule_id']:<28} control_ok={rec['control_ok']} ({rec['seconds']} s)", flush=True)
        browser.close()


def prepare_one(browser, axe_source, sel):
    """Before-scan + control, exactly as in repair.repair_one (model-independent)."""
    eid = sel["element_id"]
    capture = rp.CAPTURES_DIR / sel["file_name"]
    rec = {"element_id": eid, "prepared_utc": ax.utc_now()}
    context, page = rp.open_offline(browser, capture)
    try:
        original_full = page.evaluate("(s) => { const e = document.querySelector(s); return e ? e.outerHTML : null; }", sel["target"])
        if original_full is None:
            return {**rec, "control_ok": False, "problem": "element_not_found"}
        page.evaluate("([s, m]) => document.querySelector(s).setAttribute('data-repair-id', m)", [sel["target"], eid])
        _, before_on_el, before_page = rp.axe_on_page(page, axe_source, eid)
    finally:
        context.close()
    sent, uris = rp.prompt_html(original_full)
    control = rp.apply_and_rescan(browser, axe_source, capture, sel, rp.restore_data_uris(sent, uris), eid,
                                  REPAIRED_DIR / "controls" / f"{eid}_control.html")
    control_ok = (control.get("apply_status") == "applied" and sel["rule_id"] in control.get("rules_on_element", [])
                  and sorted(control["rules_on_element"]) == sorted(before_on_el)
                  and control["page_violations_by_rule"] == before_page)
    return {**rec, "original_html": sent, "data_uris_shortened": len(uris),
            "before": {"rules_on_element": before_on_el, "page_violations_by_rule": before_page,
                       "rule_fails_on_element": sel["rule_id"] in before_on_el},
            "control": control, "control_ok": control_ok}


# ---------------------------------------------------------------- run (one model)

def run_one(browser, axe_source, provider, env, sel, prep, model):
    """LLM + apply-to-copy + re-scan for one element and one model (same logic as repair.repair_one)."""
    eid = sel["element_id"]
    rec = {"element_id": eid, "model": model,
           **{k: sel[k] for k in ("rule_id", "impact", "wcag_criteria", "airline_id", "page_type", "file_name",
                                  "target", "copies")},
           "started_utc": ax.utc_now()}
    original = prep["original_html"]
    prompt = rp.PROMPT_TEMPLATE.format(original_html=original, **{k: sel[k] for k in
                                       ("rule_id", "rule_help", "wcag_criteria", "failure_summary")})
    rec["prompt"] = prompt
    try:
        raw, served, secs, usage = ask(provider, env, prompt)
    except Exception as e:
        return {**rec, "verdict": "llm_error", "llm_error": str(e)}
    rec.update({"llm_raw_output": raw, "llm_served_model": served, "llm_seconds": secs, **usage})
    rec["fixed_html"], rec["output_cleaned"] = rp.clean_llm_output(raw)
    rec["output_unchanged"] = rec["fixed_html"].strip() == original.strip()
    rec["quality_flags"] = rp.quality_flags(original, rec["fixed_html"])
    # The data: URIs of the ORIGINAL element are needed to restore placeholders in the answer.
    capture = rp.CAPTURES_DIR / sel["file_name"]
    context, page = rp.open_offline(browser, capture)
    try:
        original_full = page.evaluate("(s) => document.querySelector(s).outerHTML", sel["target"])
    finally:
        context.close()
    _, uris = rp.prompt_html(original_full)
    safe_model = model.replace(":", "_").replace("/", "_")
    after = rp.apply_and_rescan(browser, axe_source, capture, sel, rp.restore_data_uris(rec["fixed_html"], uris), eid,
                                REPAIRED_DIR / safe_model / f"{eid}_{sel['file_name']}")
    rec["apply_status"] = after["apply_status"]
    if after["apply_status"] != "applied":
        return {**rec, "verdict": "invalid_output"}
    before_on_el, before_page = prep["before"]["rules_on_element"], prep["before"]["page_violations_by_rule"]
    after_on_el, after_page = after["rules_on_element"], after["page_violations_by_rule"]
    still = sel["rule_id"] in after_on_el
    rec["after"] = {"rules_on_element": after_on_el, "page_violations_by_rule": after_page,
                    "rule_still_fails_on_element": still,
                    "new_rules_on_element": sorted(set(after_on_el) - set(before_on_el)),
                    "new_rules_on_page": sorted(r for r in after_page if r not in before_page),
                    "repaired_file": after["repaired_file"]}
    if still:
        rec["verdict"] = "not_fixed"
    elif rec["after"]["new_rules_on_element"] or rec["after"]["new_rules_on_page"]:
        rec["verdict"] = "fixed_but_new_issue"
    else:
        rec["verdict"] = "fixed"
    return rec


def ask(provider, env, prompt):
    """Same request as repair.ask_llm (system prompt, temperature 0, seed 42) + explicit num_ctx; also returns token counts."""
    if provider != "ollama":
        raw, served, secs = rp.ask_llm(provider, env, prompt)
        return raw, served, secs, {}
    base = env.get("OLLAMA_URL", "http://localhost:11434")
    t0 = time.time()
    r = rp.http_json(f"{base}/api/chat", {
        "model": env["LLM_MODEL"], "stream": False,
        "options": {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX},
        "messages": [{"role": "system", "content": rp.SYSTEM_PROMPT}, {"role": "user", "content": prompt}]})
    usage = {"prompt_tokens": r.get("prompt_eval_count"), "answer_tokens": r.get("eval_count"),
             "done_reason": r.get("done_reason")}
    return r["message"]["content"], r.get("model"), round(time.time() - t0, 1), usage


def cmd_run(args):
    provider, env = rp.llm_settings()
    env = {**env, "LLM_MODEL": args.model}
    info = rp.model_info(provider, env)
    selection = {s["element_id"]: s for s in csv.DictReader(open(SELECTION_CSV, encoding="utf-8"))}
    preps = {r["element_id"]: r for r in read_jsonl(CONTROLS_LOG)}
    done = {r["element_id"] for r in read_jsonl(RUN_LOG) if r["model"] == args.model}
    eligible = [e for e in selection if e in preps and preps[e]["control_ok"]]
    todo = [e for e in eligible if e not in done][: args.limit or None]
    print(f"{args.model}: {len(eligible)} elements with a passing control; {len(done)} already done; {len(todo)} to do now")
    axe_source = ax.load_axe_source()
    t_start = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for i, eid in enumerate(todo, 1):
            t0 = time.time()
            rec = run_one(browser, axe_source, provider, env, selection[eid], preps[eid], args.model)
            rec["model_info"] = info
            rec["settings"] = {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX}
            rec["total_seconds"] = round(time.time() - t0, 1)
            append_jsonl(RUN_LOG, rec)  # saved immediately: a restart continues from here
            avg = (time.time() - t_start) / i
            print(f"[{i}/{len(todo)}] {eid} {rec['rule_id']:<28} -> {rec['verdict']:<20} "
                  f"llm {rec.get('llm_seconds', '-')} s, total {rec['total_seconds']} s | "
                  f"ETA {avg * (len(todo) - i) / 60:.0f} min", flush=True)
        browser.close()
    print(f"done in {(time.time() - t_start) / 60:.1f} min")


# ---------------------------------------------------------------- main

def main():
    parser = argparse.ArgumentParser(description="Step 5 full run: 3 LLMs, all de-duplicated failing elements.")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("select")
    pr = sub.add_parser("prepare")
    pr.add_argument("--limit", type=int)
    r = sub.add_parser("run")
    r.add_argument("--model", required=True)
    r.add_argument("--limit", type=int, help="only the next N elements (e.g. 10 for timing)")
    args = parser.parse_args()
    {"select": cmd_select, "prepare": cmd_prepare, "run": cmd_run}[args.cmd](args)


if __name__ == "__main__":
    main()
