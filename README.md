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
- [ ] Step 3: final list of airlines and pages
- [ ] Step 4: full audit pipeline
- [ ] Step 5: LLM repair prototype
- [ ] Step 6: evaluate fixes
- [ ] Step 7: ML failure predictor and dashboard
- [ ] Step 8: paper draft
