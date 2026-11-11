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

---

## 2026-11-11 - Step 2: feasibility test on 6 airline homepages

Changed from 4 to 6 airlines: added JAL and Emirates.

**Done**
- Wrote `src/feasibility_scan.py`. For each homepage, one at a time with 10 s between sites:
  load the page (headless Chromium, 1366x768, default Playwright user agent, which says
  "HeadlessChrome"), save metadata + full-page screenshot, check for block pages, and if not
  blocked run axe-core with tags wcag2a, wcag2aa, wcag21a, wcag21aa. No clicks, no cookie
  banner handling, no logins, nothing beyond the homepage.
- Run `20261111T115319Z` (UTC). Raw JSON in `data/raw/step2_feasibility/20261111T115319Z/`,
  summary in `data/results/step2_feasibility_20261111T115319Z.csv`.

**Result: only 1 of 6 homepages could be scanned.**

| Airline   | Result  | Evidence |
|-----------|---------|----------|
| Air India | error   | `net::ERR_HTTP2_PROTOCOL_ERROR`, page never loaded. Possibly bot protection cutting the connection, but not confirmed. |
| IndiGo    | blocked? | HTTP 200 but page only says "Something went wrong. Please contact our customer support team." Could be a block or a failed app load; **unconfirmed**. |
| ANA       | ok      | Real homepage loaded (checked screenshot). 7 rules failed, 29 elements: 19 critical, 10 serious. |
| JAL       | blocked | HTTP 403 "Access Denied" (Akamai error page). |
| Lufthansa | blocked | HTTP 403 "Security check ... unusual behaviour from your browser, which resembles that of a bot". |
| Emirates  | blocked | HTTP 403, redirected to `/error/accessrestricted.html`. |

ANA violations (all in the main page, none inside iframes): aria-required-parent (10),
aria-allowed-attr (7), list (4), color-contrast (3), aria-required-children (2),
aria-toggle-field-name (2), link-name (1). axe also listed color-contrast as "incomplete"
(needs human check) for some elements.

**Problems found and fixed**
- axe-core by default skips iframes from a different domain. Tested on local pages:
  same-origin iframe scanned, cross-origin iframe skipped. Fixed with
  `axe.configure({allowedOrigins: ['<unsafe_all_origins>']})` in every frame.
  (ANA had no iframes, so this did not affect this run.)
- PRIVACY: Lufthansa's block page shows the visitor's public IP address, so it ended up in
  `lufthansa.json` and `lufthansa.png`. The repo is public, so these two files are listed
  in `.gitignore` and stay on my computer only (not edited, rule 6). The script was then
  changed for future runs: IP addresses are removed from saved text, and block-page
  screenshots are saved as `*_blocked.png`, which git ignores. This change does not affect
  how pages are scanned.

**What this means for the project**
Headless automated scanning is blocked by most big airline sites (4-5 of 6 here).
Per rule 3 we do not try to get around this: no fake user agent, no "stealth" plugins,
no captcha solving. Running a visible (headed) browser *in order to* get past the block
would also count as bypassing. A decision is needed before Step 3 on how to get pages.
Options that stay within the rules:
1. Manual capture: I open each page myself in my normal browser and save it
   (e.g. "Save page as" / SingleFile), then the pipeline scans the saved copy locally.
   Fits Objective 2 well, which works on saved copies anyway. Downside: manual work,
   and saved copies can lose some dynamic behaviour.
2. Run axe in my own browser by hand (axe DevTools extension) and export the JSON.
3. Ask airlines for permission / allow-listing for research scanning (slow, uncertain).
4. Only include airlines that allow automated access. Simple, but this is selection bias
   and must be reported in the paper.
5. Scan archived copies (Internet Archive) - quality varies, and not the live site.

**Next**: decide on the page-collection method, then Step 3 (final airline list).
