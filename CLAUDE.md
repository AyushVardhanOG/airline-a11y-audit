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
  (the page is the homepage itself; not captured/scanned separately)
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
- [ ] Step 3: choose the final list of ~30 airlines and pages — IN PROGRESS
  - [x] 30 airlines listed in `data/airlines.csv`
  - [x] capture method chosen (SingleFile for all airlines), guide written, scanners + live-vs-copy comparison built
  - [x] which airlines blocked automated access recorded (Step 2: 6 airlines; all 30 after Step 4 part 1)
  - [x] URLs suggested by web search for all 90 pages (84 found, 6 MISSING), all `url_verified = no`;
        source notes in `data/url_search_notes.csv`; `docs/capture_checklist.md` has one box per page
  - [ ] check each airline's URLs by hand and set `url_verified = yes` (20 of 30 done: India, Japan/Asia, Europe complete)
  - [ ] capture home/checkin/assistance pages for all 30 airlines (by hand), ticking `docs/capture_checklist.md`
        (53 pages done on 2026-11-11: India 11 + Japan/Asia 13 + Europe 29; registered with
        `src/register_captures.py`. Of the 90 page slots: 7 MISSING, 2 SAME_AS_HOME (SpiceJet and
        Turkish check-in), so 81 pages to capture in total; still open: North America,
        Middle East/Oceania)
  - [ ] airlines with access "allowed" (11): live scan in the same hour as their captures, then run the live-vs-copy comparison
        (ANA live scan done, run 20261111T124041Z: home + assistance ok, check-in page connection cut;
        live-vs-copy comparison for ANA not run yet;
        SpiceJet, Akasa Air, Air India Express live scan done, run 20261111T130057Z, ~10 min after
        their captures: all 6 pages ok;
        Ryanair, Finnair, TAP live scan done, run 20261111T133826Z, ~15 min after their captures:
        8 of 9 pages ok, Ryanair assistance (help.ryanair.com) blocked 403; Finnair home was the
        country-selection page and is NOT comparable with the new fi-en capture (no fi-en live scan yet);
        7 of 11 allowed airlines now have live scans)
- [ ] Step 4: full audit pipeline (Objective 1)
  - [x] part 1: one headless homepage visit to the 24 untested airlines (`src/access_test.py`);
        all 30 now in `data/results/automated_access.csv`: 11 allowed, 9 blocked, 3 blocked_unconfirmed, 7 error
- [ ] Step 5: LLM repair prototype (Objective 2)
- [ ] Step 6: evaluate fixes + label them works/fails (Objective 3)
- [ ] Step 7: train the ML failure predictor + dashboard (Objective 3)
- [ ] Step 8: paper draft
