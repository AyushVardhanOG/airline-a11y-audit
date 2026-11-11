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

## Folder structure
- `src/` all code
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
- [ ] Step 3: choose the final list of ~30 airlines and pages
- [ ] Step 4: full audit pipeline (Objective 1)
- [ ] Step 5: LLM repair prototype (Objective 2)
- [ ] Step 6: evaluate fixes + label them works/fails (Objective 3)
- [ ] Step 7: train the ML failure predictor + dashboard (Objective 3)
- [ ] Step 8: paper draft
