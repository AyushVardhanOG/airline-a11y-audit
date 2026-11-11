# Airline Accessibility Audit

Automated accessibility auditing and LLM-based repair of airline booking websites.
College major project and planned research paper.

## What it does

1. **Audit**: scan the main booking pages of about 30 airlines for WCAG 2.1 Level AA
   violations using two automated checkers (axe-core, plus Pa11y or IBM Equal Access).
2. **Repair**: ask large language models (LLMs) to fix the violations, on **saved local copies**
   of the pages only, never on live websites.
3. **Evaluate and predict**: re-test every fix (both checkers, keyboard-only test, screenshot
   comparison), label it "works" or "fails", and train a model that predicts which fixes
   are likely to fail so a human can review them.

Automated checkers find only part of all accessibility problems. This tool supports
human audits; it does not replace them.

## How pages are collected

Most airline sites block automated browsers (found in Step 2), and we do not get around
bot protection. So every page is **saved by hand** with the SingleFile browser extension
(see [docs/capture_guide.md](docs/capture_guide.md)) and scanned **offline**. For airlines
that do allow automated access, the live page is scanned too, to check how close the
saved copy is to the live page.

| Script | What it does |
|--------|--------------|
| `src/scan_captures.py` | scans saved copies in `data/captures/` offline (main method) |
| `src/scan_live.py` | scans live pages, only for airlines that allow automated access |
| `src/compare_live_vs_capture.py` | compares live vs saved-copy results per page |
| `src/record_access.py` | records which airlines blocked automated access |
| `src/open_batch.py` | opens one region's pages as tabs in the capture Chrome profile (for saving by hand) |
| `src/register_captures.py` | renames new SingleFile captures and adds them to `data/captures/log.csv` |
| `src/axe_runner.py` | shared axe-core settings used by both scanners |

## Ethics and scanning rules

- At least 10 seconds between sites, one page at a time, no parallel requests to the same site.
- Never past the payment step. No logins, no personal data, no submitted bookings.
- No bypassing of bot protection or captchas. Blocked sites are recorded as "blocked".

## Setup (Windows)

Needs Python 3.12+ and Node.js 18+.

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe -m playwright install chromium
npm install
.\.venv\Scripts\python.exe src\check_setup.py   # should print PASS
```

## Folders

| Folder          | Contents                                              |
|-----------------|-------------------------------------------------------|
| `src/`          | all code                                              |
| `data/raw/`     | raw scan results (JSON), never edited by hand         |
| `data/results/` | processed tables and charts                           |
| `screenshots/`  | page screenshots                                      |
| `docs/notes.md` | running log of what was tried and why                 |

## Status

- [x] Step 1: project setup
- [x] Step 2: feasibility test on 6 airline homepages
- [x] Step 3: final list of airlines and pages (78 pages captured by hand on 2026-11-11)
- [ ] Step 4: full audit pipeline (part 1 done: automated-access test of all 30 airlines)
- [ ] Step 5: LLM repair prototype
- [ ] Step 6: evaluate fixes
- [ ] Step 7: ML failure predictor and dashboard
- [ ] Step 8: paper draft
