# Project: Automated Accessibility Auditing and LLM-Based Repair of Airline Booking Websites

This is my college major project (and a planned research paper). I am still learning to code,
so explain every step in simple words and tell me what each file does after you write it.

## What the project does
We check how accessible airline booking websites are for people with disabilities
(screen-reader users, keyboard-only users, low-vision users), test whether an AI (LLM)
can fix the problems it finds, and check whether those fixes actually work.

## The 3 objectives
1. **Audit pipeline**: scan the main booking pages of ~30 airlines (India, Japan, EU, US and others)
   for WCAG 2.1 Level AA violations using two different checkers (axe-core + Pa11y or IBM Equal Access).
2. **LLM repair module**: generate fixes for the detected violations on SAVED COPIES of the pages.
3. **Evaluation + ML failure predictor**: check every AI fix (re-scan with both checkers,
   keyboard-only test, before/after screenshot comparison) and label it "works" or "fails".
   Then train a machine learning model that predicts, before a fix is applied, whether it will fail,
   so only risky fixes go to a human reviewer. Show results on a dashboard.
   - Features: violation rule, impact level, HTML element type, snippet length, nesting depth,
     ARIA involved or not, page type, which LLM made the fix
   - Models: logistic regression (baseline), random forest, XGBoost; SHAP for feature importance
   - Split train/test BY AIRLINE (no airline in both), so results are not inflated
   - Metrics: precision, recall, F1, ROC-AUC
   - Generate fixes with 2-3 different LLMs to get enough data (aim for 500+ fix attempts)

## Why it matters (for the problem statement)
- US: 14 CFR 382.43 requires airline primary websites to meet WCAG 2.0 Level AA.
- EU: the European Accessibility Act (in effect since 28 June 2025) covers air transport websites,
  apps and e-ticketing, with WCAG 2.1 AA as the technical baseline.
- Automated scanners catch only part of all issues, so this tool supports human audits; it does not replace them.

## Tech stack
- Python 3, Playwright (Chromium) for browser automation
- axe-core (injected into the page) as the main checker; a second checker added later
- An LLM for repairs (free API tier or a local model via Ollama), decided in Objective 2
- scikit-learn, XGBoost, SHAP for the failure predictor (Objective 3)
- FastAPI + a simple React dashboard (Objective 3)
- Git + GitHub; GitHub Actions later

## Method: how pages are collected (decided after Step 2)
In Step 2 most airline sites blocked our headless browser (only ANA allowed it); in the Step 4
access test of all 30 airlines, 11 allowed it and 19 did not (blocked, error page or connection cut). Rule 3 forbids
getting around that, so **every airline is measured the same way**:
1. **Saved copies (main method, ALL airlines)**: I open each page in my normal Chrome and save it
   with the SingleFile extension, following `docs/capture_guide.md`. Files are named
   `airline_pagetype_YYYYMMDD.html` (page types: home, checkin, assistance), stored in
   `data/captures/`, and every capture gets a row in `data/captures/log.csv` (URL, local time + UTC offset,
   browser and SingleFile versions). `src/scan_captures.py` scans them fully offline: page scripts
   off (CSP `script-src 'none'`), all network requests blocked, same axe-core rules and iframe setting
   as live scans (shared code in `src/axe_runner.py`). For saved copies, HTTP status does not exist;
   capture time and URL come from the log.
2. **Live scans (only airlines with result "allowed" in `data/results/automated_access.csv`)**:
   `src/scan_live.py`, run within the same hour as the capture, so that
   `src/compare_live_vs_capture.py` can measure how much a saved copy differs from the live page
   (failed rules and element counts per page). This validates method 1.
3. Which airlines blocked automated access is itself a **result** (`src/record_access.py` ->
   `data/results/automated_access.csv`) and goes in the paper.

## Folder structure
- `src/` all code
- `data/airlines.csv` the 30 airlines (airline_id used in all file names), their page URLs, and
  `url_verified` (yes only after a person checked the URLs; the live scanner skips airlines that are not yes)
- `data/url_search_notes.csv` where each web-search URL suggestion came from / what to check
- `docs/capture_checklist.md` one checkbox per page to capture (made by `src/make_capture_checklist.py`)
- `data/captures/` saved SingleFile copies (`*.html`, NOT on GitHub, back them up) + `log.csv`;
  `data/captures/_duplicates/` holds unneeded duplicate captures (moved, never deleted, not scanned)
- URL columns of `data/airlines.csv` may also hold `MISSING` (no such page) or `SAME_AS_HOME`
  (the page is the homepage itself; not captured/scanned separately). Column `excluded_reason`
  (e.g. Alaska: `blocked_for_human_visitor`) marks airlines kept in the results but not captured/scanned
- `data/raw/` raw scan results (JSON), never edited by hand
- `data/results/` processed tables and charts
- `screenshots/` page screenshots
- `docs/notes.md` running notes: what I tried, what failed, why I changed things

## Rules (always follow these)
1. **Be polite to websites**: wait at least 10 seconds between sites, scan one page at a time,
   no parallel requests to the same site.
2. **Never go past the payment step.** Never log in, never enter personal data, never submit bookings.
3. **Never try to bypass bot protection or captchas.** If a site blocks us, record it as "blocked" and move on.
4. **AI fixes are applied only to saved local copies** of pages, never to live websites.
5. **Save metadata with every scan**: date/time (UTC), URL, page title, HTTP status,
   axe-core version, browser version. For LLM steps also save the model name/version and the exact prompt.
6. **Never edit or delete files in `data/raw/`**; write processed output to `data/results/` instead.
7. **Report results honestly**: if something fails or a number looks wrong, tell me, don't hide it.
8. **Commit after every working step** with a clear message saying what changed and why,
   then remind me to push to GitHub. Never fake commit dates.
9. After each step, add a short entry to `docs/notes.md`.
10. Keep code simple and well commented, so I can explain it to my professor.

## Current status
- [x] Step 1: project setup
- [x] Step 2: feasibility test on 6 airline homepages (Air India, IndiGo, ANA, JAL, Lufthansa, Emirates)
- [x] Step 3: choose the final list of ~30 airlines and pages (finished 2026-11-11)
  - [x] 30 airlines in `data/airlines.csv`; URLs first suggested by web search (`data/url_search_notes.csv`),
        then checked by hand while capturing: 29 airlines `url_verified = yes`, Alaska excluded
        (`excluded_reason = blocked_for_human_visitor`: no page loaded in a normal browser)
  - [x] capture method: SingleFile by hand for ALL airlines (`docs/capture_guide.md`), opened per region
        with `src/open_batch.py`, registered with `src/register_captures.py`, ticked in `docs/capture_checklist.md`
  - [x] all captures done on 2026-11-11: 90 page slots = **78 captured** + 7 MISSING + 2 SAME_AS_HOME
        (SpiceJet, Turkish check-in) + 3 excluded (Alaska). Unneeded duplicates in `data/captures/_duplicates/`.
        Several homepages were redirected by location to their India versions (noted in `data/captures/log.csv`)
  - [x] live scans of all 11 "allowed" airlines within ~15 min of their captures (runs 20261111T124041Z,
        T130057Z, T133826Z, T140859Z, T141945Z). Not scannable live: ANA check-in (connection cut),
        Ryanair assistance (403). Finnair live home = country-selection page, NOT comparable with
        the fi-en capture. Exclude spicejet/checkin (SAME_AS_HOME) from live analyses.
- [x] Step 4: full audit pipeline (Objective 1) - done 2026-11-11 with both checkers (axe-core + Pa11y)
  - [x] part 1: one headless homepage visit to the 24 untested airlines (`src/access_test.py`);
        all 30 now in `data/results/automated_access.csv`: 11 allowed, 9 blocked, 3 blocked_unconfirmed, 7 error
  - [x] scanned the 78 saved copies offline (`src/scan_captures.py`, run 20261111T142233Z): 0 errors,
        768 failing elements, 67 of 78 pages (86%) fail at least one rule
  - [x] live-vs-copy comparison (`src/compare_live_vs_capture.py`): 25 page pairs, 16 (64%) with identical
        failed-rule sets, mean rule overlap (Jaccard) 0.77; color-contrast is the least stable rule
  - [x] `src/analyze.py` -> `data/results/`: violations_all.csv, pages_summary.csv, summary_per_airline.csv,
        6 charts in `charts/` (each with its CSV), and `summary.md` (key numbers in plain words)
  - [x] experimental-rule check: axe-core 4.14.0 has 6 experimental rules; none in our results
        (label-content-name-mismatch is a normal WCAG 2.1 A rule, SC 2.5.3), so no is_experimental column needed
  - [x] second checker: Pa11y 10.0.0 / HTML_CodeSniffer 2.6.0, WCAG2AA, errors only (`src/scan_pa11y.js`,
        run 20261111T144723Z), same 78 copies, same offline setup and same Chromium 158; 0 errors
  - [x] `src/compare_checkers.py`: compared per page by WCAG success criterion; 21% of (page, criterion)
        failures found by both tools (44% on the 5 criteria both tools report); differences explained
        (different criterion mapping, criteria only one tool tests, Pa11y also flags hidden elements)
- [x] Step 5: LLM repairs - **Objective 2 DONE 2026-11-12** (pilot 2026-11-11: one LLM, 40 elements;
      full run: 3 LLMs x 587 elements; 3-model comparison in `data/results/summary.md`)
  - [x] LLM: Ollama 0.40.16, qwen2.5-coder:7b (7.6B, Q4_K_M, digest dae161e27b0e...), local, temperature 0, seed 42;
        settings in `.env` (git-ignored), template in `.env.example`
  - [x] `src/repair.py select/run/report`: 40 elements (top 10 rules x 4, 21 airlines, no iframes/shadow DOM);
        fix applied to a COPY (`data/repaired/`, git-ignored) and re-scanned; per element a CONTROL run (unchanged
        HTML put back) must leave the result unchanged, else `pipeline_artifact` (found in the 5-element trial)
  - [x] result: **24 of 40 fixed** per axe-core (all 4 for color-contrast, link-name, image-alt, button-name;
        0 of 4 for label-content-name-mismatch, nested-interactive, aria-required-children), 16 not fixed
        (6 times the model returned the HTML unchanged); no invalid output, no new violations, no artifacts
  - [x] automatic review flags: of the 24 "fixed", **11 need a human check** (placeholder alt text, alt="",
        removed ARIA, added role) and 13 look plausible -> `repairs_pilot_summary.csv`, `repairs_pilot_report.html`
  - [ ] not fully reproducible: same prompt, different answer for 1 of 4 repeated elements (R13) despite temp 0 + seed
  - [x] FULL RUN done 2026-11-12 (`src/repair_full.py`; run-all with 5 s cool-down, commit every 100 elements):
        601 de-duplicated elements selected (28 airlines, 62 pages; excluded: iframe/shadow DOM, duplicates,
        too large, document element -> `repairs_full_exclusions.csv`); 14 IndiGo-home controls failed -> excluded,
        so **587 elements x 3 models = 1,761 attempts**, same prompt as pilot, temp 0, seed 42, num_ctx 8192
  - [x] models (Ollama 0.40.16): qwen2.5-coder:7b (dae161e27b0e), llama3.1:8b (46e0c10c039e, 8.0B Q4_K_M),
        gemma2:9b (ff02c3702f32, 9.2B Q4_0). Fixed per axe-core: **qwen 361 (61%), llama 350 (60%), gemma 310 (53%)**;
        needs a human check among fixed: 55 / 45 / 43; invalid output 1 / 4 / 15; answer unchanged 67 / 20 / 113
  - [x] per element: 223 fixed by all 3 models, 132 by 2, 88 by 1, 144 by none. Hardest: nested-interactive,
        aria-required-parent, aria-required-children; easiest: link-name, image-alt (100% for all 3)
  - [x] outputs: `repairs_full.json`, `repairs_full_summary.csv`, `repairs_full_log.jsonl`, 3 `charts/repair_*` charts
  - [ ] for Objective 3: human works/fails labels (axe-core "fixed" is not proof the fix works)
- [ ] Step 6: evaluate fixes + label them works/fails (Objective 3)
- [ ] Step 7: train the ML failure predictor + dashboard (Objective 3)
- [ ] Step 8: paper draft
