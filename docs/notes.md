# Project notes

Running log: what I tried, what failed, and why I changed things. Newest entry at the bottom.

---

## 2026-11-11 - Step 1: project setup

**Done**
- Created the folder structure: `src/`, `data/raw/`, `data/results/`, `screenshots/`, `docs/`.
  Empty folders contain a `.gitkeep` file only so that Git keeps them.
- Python virtual environment in `.venv/` (not committed). Python 3.14.6.
- Installed Playwright 1.65.0 and its Chromium build (Chrome for Testing 158.0.8127.18).
- Installed axe-core 4.14.0 through npm, pinned to an exact version in `package.json`.
  Python injects `node_modules/axe-core/axe.min.js` into each page.
- Wrote `src/check_setup.py`: runs axe-core on a small in-memory test page that has one
  planted error (image without alt text). Result: axe-core found `image-alt`, test PASSED.
  No real website was visited.

**Decisions**
- axe-core comes from npm instead of a Python wrapper package, because then we control
  the exact axe-core version and can report it in the paper.
- Versions are pinned in `requirements.txt` and `package.json` so scans can be repeated.

**Problems**
- The GitHub CLI (`gh`) was installed but not on the PATH of the open terminal.
  Ran it by its full path (`C:\Program Files\GitHub CLI\gh.exe`). Restarting VS Code should fix the PATH.

**Next**: Step 2, feasibility test on the Air India, IndiGo, ANA and Lufthansa homepages.
