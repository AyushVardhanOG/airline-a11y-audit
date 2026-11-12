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
import os
import subprocess
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
        os.fsync(f.fileno())  # make sure the line is on disk before the next element (sudden shutdowns)


def repair_log_tail(path):
    """
    After a sudden shutdown the LAST line of a log can be half-written. Such a line is moved
    (not deleted) to <log>_broken.txt and removed from the log, so that element is simply redone
    and new records never get glued onto a broken line.
    """
    if not path.exists():
        return
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    if not lines:
        return
    try:
        json.loads(lines[-1])
        if not text.endswith("\n"):
            path.write_text(text + "\n", encoding="utf-8")
        return
    except json.JSONDecodeError:
        broken = path.with_name(path.stem + "_broken.txt")
        with open(broken, "a", encoding="utf-8") as f:
            f.write(f"# moved from {path.name} at {ax.utc_now()}\n{lines[-1]}\n")
        path.write_text("\n".join(lines[:-1]) + ("\n" if len(lines) > 1 else ""), encoding="utf-8")
        print(f"WARNING: half-written last line moved from {path.name} to {broken.name}; that element will be redone")


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


def model_progress(model):
    """(elements done for this model, elements eligible) - eligible = passing control."""
    preps = read_jsonl(CONTROLS_LOG)
    eligible = {r["element_id"] for r in preps if r["control_ok"]}
    done = {r["element_id"] for r in read_jsonl(RUN_LOG) if r["model"] == model} & eligible
    return len(done), len(eligible)


def run_model(model, limit=None, pause=0.0):
    """Run the next `limit` not-yet-done elements for one model. Returns how many were run."""
    repair_log_tail(RUN_LOG)
    provider, env = rp.llm_settings()
    env = {**env, "LLM_MODEL": model}
    info = rp.model_info(provider, env)
    selection = {s["element_id"]: s for s in csv.DictReader(open(SELECTION_CSV, encoding="utf-8"))}
    preps = {r["element_id"]: r for r in read_jsonl(CONTROLS_LOG)}
    done = {r["element_id"] for r in read_jsonl(RUN_LOG) if r["model"] == model}
    eligible = [e for e in selection if e in preps and preps[e]["control_ok"]]
    todo = [e for e in eligible if e not in done][: limit or None]
    print(f"{model}: {len(eligible)} elements with a passing control; {len(done)} already done; {len(todo)} to do now"
          + (f"; {pause:g} s cool-down pause between elements" if pause else ""), flush=True)
    if not todo:
        return 0
    axe_source = ax.load_axe_source()
    t_start = time.time()
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for i, eid in enumerate(todo, 1):
            t0 = time.time()
            rec = run_one(browser, axe_source, provider, env, selection[eid], preps[eid], model)
            rec["model_info"] = info
            rec["settings"] = {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX}
            rec["total_seconds"] = round(time.time() - t0, 1)
            append_jsonl(RUN_LOG, rec)  # saved immediately: a restart continues from here
            avg = (time.time() - t_start) / i + pause
            print(f"[{len(done) + i}/{len(eligible)}] {eid} {rec['rule_id']:<28} -> {rec['verdict']:<20} "
                  f"llm {rec.get('llm_seconds', '-')} s, total {rec['total_seconds']} s | "
                  f"ETA this batch {avg * (len(todo) - i) / 60:.0f} min", flush=True)
            if pause and i < len(todo):
                time.sleep(pause)  # cool-down: lets the laptop's CPU/GPU cool a little between elements
        browser.close()
    print(f"batch done in {(time.time() - t_start) / 60:.1f} min", flush=True)
    return len(todo)


def cmd_run(args):
    run_model(args.model, args.limit, args.pause)


# ---------------------------------------------------------------- run-all (models in order, commits)

def git(*args):
    """Run a git command in the project folder; return (ok, output)."""
    r = subprocess.run(["git", *args], cwd=ax.PROJECT_ROOT, capture_output=True, text=True)
    return r.returncode == 0, (r.stdout + r.stderr).strip()


def commit_results(message):
    """Rebuild the results (report + summary.md) and commit + push them. Push failures do not stop the run."""
    cmd_report(None)
    subprocess.run([sys.executable, str(ax.PROJECT_ROOT / "src" / "analyze.py")], cwd=ax.PROJECT_ROOT,
                   capture_output=True, text=True)
    files = [RUN_LOG, FULL_JSON, SUMMARY_CSV, RESULTS / "summary.md"]
    files += sorted((RESULTS / "charts").glob("repair_*"))
    broken = RUN_LOG.with_name(RUN_LOG.stem + "_broken.txt")
    if broken.exists():
        files.append(broken)
    git("add", *[str(f.relative_to(ax.PROJECT_ROOT)) for f in files])
    ok, out = git("commit", "-m", message, "-m", "Co-Authored-By: Claude Opus 5.5 <noreply@anthropic.com>")
    if not ok:
        print(f"git commit: {out.splitlines()[-1] if out else 'nothing to commit'}", flush=True)
        return
    ok, out = git("push")
    print(f"committed: {message} | push {'ok' if ok else 'FAILED (will be pushed with a later commit): ' + out[-200:]}",
          flush=True)


def cmd_run_all(args):
    """
    All models in order, resumable. After every `commit_every` elements: rebuild results, commit, push.
    When a model is complete: a final commit for that model.
    """
    for model in args.models:
        while True:
            n_before, total = model_progress(model)
            if n_before >= total:
                print(f"{model}: complete ({n_before}/{total})", flush=True)
                break
            ran = run_model(model, args.commit_every, args.pause)
            n_after, total = model_progress(model)
            if n_after >= total:
                commit_results(f"Step 5 full run: {model} finished ({n_after}/{total} elements)")
                break
            commit_results(f"Step 5 full run: {model} progress {n_after}/{total} elements")
            if ran == 0:
                break


# ---------------------------------------------------------------- report (JSON, summary CSV, charts)

FLAG_KEYS = ["needs_human_check", "placeholder_text", "hides_content", "removes_aria", "changes_role", "text_changed"]


def cmd_report(args):
    """
    Build the results from whatever is in the run log (works for partial runs too):
      repairs_full.json         meta + every record
      repairs_full_summary.csv  one row per (model, element): verdict + review flags
      charts/repair_fix_rate_per_model.png, repair_fix_rate_per_rule_model.png,
      charts/repair_human_check_share.png  (each with a CSV of the numbers shown)
    "Fixed" = the rule no longer fails on the element AND no new violation on element/page
    (same definition as the pilot). "fixed_but_new_issue" is NOT counted as fixed.
    """
    import pandas as pd
    import analyze  # shared chart style
    import capture_artifacts  # shared rule: elements inserted by the saving tool

    artifacts = capture_artifacts.load(axe_run=rp.latest_capture_run().name)["axe"]
    # every record keeps its data; capture_artifact=True marks the ones left out of all counts and charts
    log = [{**r, "capture_artifact": (r["file_name"], r["target"]) in artifacts} for r in read_jsonl(RUN_LOG)]
    controls = read_jsonl(CONTROLS_LOG)
    selection = list(csv.DictReader(open(SELECTION_CSV, encoding="utf-8")))
    models = list(dict.fromkeys(r["model"] for r in log))
    meta = {
        "created_utc": ax.utc_now(),
        "selection": {"elements": len(selection), "control_ok": sum(c["control_ok"] for c in controls),
                      "control_failed": [c["element_id"] for c in controls if not c["control_ok"]]},
        "models": {m: next(r["model_info"] for r in log if r["model"] == m) for m in models},
        "settings": {"temperature": 0, "seed": 42, "num_ctx": NUM_CTX, "system_prompt": rp.SYSTEM_PROMPT,
                     "prompt_template": rp.PROMPT_TEMPLATE},
        "capture_scan_run": rp.latest_capture_run().name,
        "capture_artifacts_left_out": sorted({r["element_id"] for r in log if r["capture_artifact"]}),
    }
    FULL_JSON.write_text(json.dumps({"meta": meta, "repairs": log}, ensure_ascii=False), encoding="utf-8")

    rows = [{"model": r["model"], "element_id": r["element_id"], "rule_id": r["rule_id"], "impact": r["impact"],
             "airline_id": r["airline_id"], "page_type": r["page_type"], "copies": r.get("copies"),
             "verdict": r["verdict"], "output_unchanged": r.get("output_unchanged"), "llm_seconds": r.get("llm_seconds"),
             "prompt_tokens": r.get("prompt_tokens"), "answer_tokens": r.get("answer_tokens"),
             **{k: (r.get("quality_flags") or {}).get(k) for k in FLAG_KEYS},
             "capture_artifact": r["capture_artifact"]} for r in log]
    df = pd.DataFrame(rows)
    df.to_csv(SUMMARY_CSV, index=False)  # ALL rows, incl. capture_artifact=True
    n_art = int(df["capture_artifact"].sum())
    df = df[~df["capture_artifact"]].copy()  # from here on: counts and charts without capture artifacts
    df["fixed"] = df["verdict"] == "fixed"
    charts = RESULTS / "charts"
    charts.mkdir(parents=True, exist_ok=True)

    # 1. Fix rate per model
    per_model = df.groupby("model", sort=False).agg(attempts=("element_id", "size"), fixed=("fixed", "sum"),
                                                    fixed_new_issue=("verdict", lambda v: (v == "fixed_but_new_issue").sum()),
                                                    not_fixed=("verdict", lambda v: (v == "not_fixed").sum()),
                                                    invalid=("verdict", lambda v: (v == "invalid_output").sum()),
                                                    llm_error=("verdict", lambda v: (v == "llm_error").sum()),
                                                    unchanged=("output_unchanged", lambda v: (v == True).sum()))
    per_model["fix_rate"] = (per_model["fixed"] / per_model["attempts"]).round(3)
    per_model.to_csv(charts / "repair_fix_rate_per_model.csv")
    analyze.ranked_bars(list(per_model.index), list(per_model["fix_rate"] * 100),
                        # label from the exact counts (not the rounded fix_rate), so it matches summary.md
                        [f"{r.fixed / r.attempts:.0%}  ({int(r.fixed)} of {int(r.attempts)})" for r in per_model.itertuples()],
                        "LLM repairs that axe-core accepts, per model",
                        "Fixed = rule no longer fails on the element and no new violation; same prompt, temperature 0, seed 42",
                        "% of repair attempts fixed", charts / "repair_fix_rate_per_model.png")

    # 2. Fix rate per rule per model (heatmap, rows = rules ordered by number of elements)
    order = df[df["model"] == models[0]]["rule_id"].value_counts().index.tolist()
    order += [r for r in df["rule_id"].unique() if r not in order]
    pivot_rate = df.pivot_table(index="rule_id", columns="model", values="fixed", aggfunc="mean").reindex(order)[models]
    pivot_n = df.pivot_table(index="rule_id", columns="model", values="fixed", aggfunc="size").reindex(order)[models]
    out = pivot_rate.round(3).add_suffix(" fix_rate").join(pivot_n.add_suffix(" n"))
    out.to_csv(charts / "repair_fix_rate_per_rule_model.csv")
    heatmap(pivot_rate, pivot_n, charts / "repair_fix_rate_per_rule_model.png", analyze)

    # 3. Among fixed repairs: how many need a human check (review flags)?
    fx = df[df["fixed"]]
    share = fx.groupby("model", sort=False)["needs_human_check"].agg(
        fixed="size", needs_check=lambda v: (v == True).sum()).reindex(models)
    share["plausible"] = share["fixed"] - share["needs_check"]
    share.to_csv(charts / "repair_human_check_share.csv")
    two_part_bars(share, charts / "repair_human_check_share.png", analyze)

    print(f"{len(log)} records; {n_art} on capture artifacts left out "
          f"({len(meta['capture_artifacts_left_out'])} elements: {', '.join(meta['capture_artifacts_left_out'])})")
    print(f"counted attempts per model: {', '.join(f'{m} ({int(per_model.loc[m, 'attempts'])})' for m in models)}")
    print(per_model[["attempts", "fixed", "fix_rate", "fixed_new_issue", "not_fixed", "invalid", "llm_error", "unchanged"]].to_string())
    print("\nneeds human check among fixed:\n" + share.to_string())
    print(f"\nWrote {FULL_JSON.name}, {SUMMARY_CSV.name}, 3 charts")


def heatmap(rate, n, path, analyze):
    """Rules x models; one blue hue light->dark (sequential), each cell labelled 'xx% (n)'."""
    import matplotlib.pyplot as plt
    from matplotlib.colors import LinearSegmentedColormap
    import numpy as np
    ramp = LinearSegmentedColormap.from_list("blue", ["#cde2fb", "#86b6ef", "#3987e5", "#256abf", "#104281"])
    ramp.set_bad(analyze.SURFACE)  # no attempts = blank cell, never confused with 0%
    rows, cols = rate.shape
    fig, ax_ = plt.subplots(figsize=(2.3 + 1.9 * cols, 1.4 + 0.34 * rows), dpi=150)
    ax_.imshow(np.ma.masked_invalid(rate.values.astype(float)), cmap=ramp, vmin=0, vmax=1, aspect="auto")
    for i in range(rows):
        for j in range(cols):
            v, k = rate.iat[i, j], n.iat[i, j]
            if pd_isna(k):
                ax_.text(j, i, "–", ha="center", va="center", fontsize=9, color=analyze.MUTED)
                continue
            ax_.text(j, i, f"{v:.0%} ({int(k)})", ha="center", va="center", fontsize=8.5,
                     color="#ffffff" if v >= 0.5 else analyze.INK)
    ax_.set_xticks(range(cols), list(rate.columns))
    ax_.set_yticks(range(rows), list(rate.index))
    ax_.tick_params(length=0, labelcolor=analyze.INK_2)
    for s in ax_.spines.values():
        s.set_visible(False)
    ax_.set_title("Fix rate per rule and model", loc="left", color=analyze.INK, fontsize=13, fontweight="bold", pad=24)
    ax_.text(0, 1.01, "Share of repair attempts that axe-core accepts; (n) = attempts; – = no attempts. Darker = more fixed.",
             transform=ax_.transAxes, color=analyze.INK_2, fontsize=9, va="bottom")
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


def pd_isna(x):
    return x != x or x is None  # NaN check without importing pandas here


def two_part_bars(share, path, analyze):
    """Per model: fixed repairs split into 'looks plausible' and 'needs a human check' (stacked)."""
    import matplotlib.pyplot as plt
    fig, ax_ = plt.subplots(figsize=(8.5, 1.6 + 0.45 * len(share)), dpi=150)
    y = list(range(len(share)))
    parts = [("plausible", "Looks plausible", analyze.CATEGORICAL[0]), ("needs_check", "Needs a human check", analyze.CATEGORICAL[1])]
    left = [0] * len(share)
    for col, label, color in parts:
        vals = list(share[col])
        ax_.barh(y, vals, left=left, height=0.5, color=color, edgecolor=analyze.SURFACE, linewidth=1.0, label=label)
        for yi, l, v, tot in zip(y, left, vals, share["fixed"]):
            if tot and v / tot >= 0.12:
                ax_.text(l + v / 2, yi, f"{v} ({v / tot:.0%})", ha="center", va="center", color="#ffffff",
                         fontsize=9, fontweight="bold")
        left = [a + b for a, b in zip(left, vals)]
    ax_.set_yticks(y, list(share.index))
    ax_.invert_yaxis()
    ax_.set_xlim(0, max(left) * 1.05 if max(left) else 1)
    ax_.set_xlabel("repairs that axe-core accepts (fixed)", color=analyze.INK_2)
    analyze.style_axes(ax_, "How many 'fixed' repairs need a human check?",
                       "Review flags: placeholder text, hides content, removes ARIA, adds/changes a role")
    leg = ax_.legend(loc="upper center", bbox_to_anchor=(0.5, -0.28), ncol=2, frameon=False, fontsize=9.5,
                     handlelength=1.2, handleheight=1.0)
    for t in leg.get_texts():
        t.set_color(analyze.INK_2)
    fig.tight_layout()
    fig.savefig(path)
    plt.close(fig)


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
    r.add_argument("--pause", type=float, default=0.0, help="cool-down seconds between elements")
    ra = sub.add_parser("run-all", help="all models in order, resumable, with progress commits")
    ra.add_argument("--models", nargs="+", default=["qwen2.5-coder:7b", "llama3.1:8b", "gemma2:9b"])
    ra.add_argument("--pause", type=float, default=5.0, help="cool-down seconds between elements (default 5)")
    ra.add_argument("--commit-every", type=int, default=100, help="commit + push after this many elements")
    sub.add_parser("report")
    args = parser.parse_args()
    {"select": cmd_select, "prepare": cmd_prepare, "run": cmd_run, "run-all": cmd_run_all,
     "report": cmd_report}[args.cmd](args)


if __name__ == "__main__":
    main()
