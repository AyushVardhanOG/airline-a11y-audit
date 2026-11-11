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
- [ ] Step 5: LLM repair prototype (Objective 2) - PILOT PREPARED, waiting for the LLM to be set up
  - [x] `src/repair.py select`: 40 failing elements (top 10 rules x 4, 22 airlines; no iframes/shadow DOM,
        HTML <= 3000 chars as sent) -> `data/results/repairs_pilot_selection.csv`
  - [x] `run`/`report` built and tested WITHOUT an LLM (echo provider + hand-written answers): fixed /
        not fixed / invalid output / fixed-but-new-issue are all detected; fixes go only into copies in
        `data/repaired/` (git-ignored); prompts send the element HTML without data-sf-* attributes and with
        long data: URIs replaced by placeholders (restored before applying)
  - [ ] install Ollama + pull the model (or set a free API in `.env`), then run `repair.py run` and `report`
- [ ] Step 6: evaluate fixes + label them works/fails (Objective 3)
- [ ] Step 7: train the ML failure predictor + dashboard (Objective 3)
- [ ] Step 8: paper draft
