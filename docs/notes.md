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

---

## 2026-11-11 - Step 3 (part 1): capture method for all airlines

**Decision**: option 1 from Step 2 for ALL airlines. Every page is saved by hand with the
SingleFile extension and scanned offline, so every airline is measured the same way.
Live scans are kept only for airlines that allowed automated access (only ANA so far),
to check how much a saved copy differs from the live page.

(An earlier plan for this step, crawling each homepage with Playwright to find the check-in and
assistance links, was dropped: it would hit the same bot blocks.)

**Done**
- `data/airlines.csv`: the 30 airlines with a fixed `airline_id` used in all file names.
  URL columns are filled in by hand during capture (or `MISSING`).
- `docs/capture_guide.md`: how to save pages with SingleFile (separate Chrome profile, no
  extensions that change pages, default SingleFile settings, don't touch cookie banners,
  don't log in or type), file naming `airline_pagetype_YYYYMMDD.html`, and `data/captures/log.csv`.
- `src/axe_runner.py`: shared code so live and saved-copy scans use the same axe-core
  version, WCAG tags and iframe setting.
- `src/scan_captures.py`: scans saved copies fully offline.
- `src/scan_live.py`: replaces the Step 2 script for live scans. Reads the page list from
  airlines.csv + automated_access.csv. Now runs axe BEFORE the full-page screenshot, so the
  screenshot's viewport resize cannot change what axe sees (Step 2 did it the other way round).
- `src/compare_live_vs_capture.py`: pairs each saved-copy scan with the live scan of the same
  page closest in time; reports failed rules on both / only live / only copy, element
  counts, rule overlap (Jaccard), and warns if the two are more than 24 h apart.
- `src/record_access.py` -> `data/results/automated_access.csv`: Step 2 access result per
  airline (allowed 1, blocked 3, blocked_unconfirmed 1, error 1, not_tested 24).

**Problems and how they were solved**
- First idea for scanning saved copies offline: switch JavaScript off completely in Playwright.
  Result: axe-core hung (no result after more than 60 s), presumably because switching off
  JavaScript also stops the timers axe needs. Solution: serve the saved file
  from disk under a fake local address (`http://saved-copy.localhost/`) with the header
  `Content-Security-Policy: script-src 'none'`. The page's own scripts are blocked, but axe-core
  still runs because Playwright injects it through the browser's debugging channel.
  All other network requests are blocked, so scanning a copy never contacts the airline.
- Tested on local test pages (no real sites): the page script did not run, the internet
  image was blocked, axe found errors inside a srcdoc iframe, the SingleFile header
  (URL + save date) was read, and 10:15 +05:30 was converted to 04:45 UTC. A planted
  difference between a "live" and a "saved" test page was reported correctly
  (link-name only live, button-name only in copy, image-alt in both, Jaccard 0.333).

**Limitations to mention in the paper**
- A saved copy is a snapshot: interactive behaviour (menus, focus handling, things that
  appear after clicks) is not in it. Keyboard testing in Objective 3 must keep this in mind.
- SingleFile may change the page slightly while saving (for example, removing hidden
  elements, depending on its settings). The live-vs-copy comparison measures this, but only for
  airlines that allow automated access (currently only ANA: one airline is a small sample).
- Saved `.html` captures are not on GitHub (copyright + they can contain personal
  details). They must be backed up separately.

**Next**: capture the pages for all 30 airlines; for ANA, run `scan_live.py ana` in the same
hour; then `scan_captures.py` and `compare_live_vs_capture.py`.

---

## 2026-11-11 - Step 3 (part 2): URL suggestions for all 30 airlines

**Done**
- `data/airlines.csv` rewritten with columns: airline_id, airline, region, homepage,
  checkin_url, assistance_url, url_verified. Requested columns plus `airline_id`, which
  is kept because capture file names and all scanners depend on it.
- URLs were suggested by **web search** (search engine results only; no airline page was opened
  by Playwright or any script). About 70 searches: one for check-in and one for special assistance per
  airline, restricted to the airline's own domain, plus follow-up searches for gaps.
  All rows have `url_verified = no`.
- Result: 84 of 90 pages have a suggestion, **6 MISSING**: Akasa Air assistance (only a
  section in its Conditions of Carriage), Air India Express assistance, Peach check-in
  (check-in is app-only), Cathay Pacific check-in (only FAQ pages found), United assistance
  (only on a preview server, gtmpreview.united.com, which was not used), Air Canada assistance
  (only the formal Accessibility Plan found).
- `data/url_search_notes.csv`: one note per suggestion that needs attention (38 notes).
  Main issues: many URLs are another country's version of the site (e.g. Lufthansa /ge/en/,
  United /en/NG/), some are help/FAQ pages rather than the check-in form, and some are on
  separate sites (help.ryanair.com, support.southwest.com, mobilecheckin.jetblue.com,
  ANA's booking engine aswbe-i.ana.co.jp).
- Homepages are mostly the bare domain (e.g. https://www.klm.com); those sites redirect by
  location, so the English / home-country version must be chosen while capturing.
- `src/make_capture_checklist.py` -> `docs/capture_checklist.md`: 90 checkboxes grouped by region,
  with URL and notes. The script refuses to overwrite an existing checklist (so ticks are
  not lost) unless run with `--force`.
- `src/scan_live.py` now only scans airlines with `url_verified = yes`, so unchecked
  suggestions are never visited by the live scanner. (ANA is currently skipped for this reason.)

**Why web search instead of Playwright**: the Step 2 result showed most airline sites block
the headless browser, so crawling homepages for links would mostly fail; search results also
do not touch the airline sites at all.

**Limitation**: search-engine results can be outdated or point to old page versions (several
results were marked as years old). That is why every URL must be checked by hand before use.

**Next**: check URLs and capture pages, airline by airline, using the checklist.

---

## 2026-11-11 - Step 4 (part 1): automated-access test of the remaining 24 airlines

**Done**
- `src/access_test.py`: ONE headless visit to the homepage of each airline still `not_tested`
  (24 airlines), one at a time, 10 s apart, default "HeadlessChrome" user agent, no retries,
  no clicks, nothing to avoid detection. No axe-core scan (access only).
  IP addresses removed from saved text; block-page screenshots are git-ignored.
- Run `20261111T121946Z`. Raw JSON in `data/raw/access_test/20261111T121946Z/`,
  summary in `data/results/access_test_20261111T121946Z.csv`.
- `src/record_access.py` now merges Step 2 and Step 4 runs into `automated_access.csv`
  (latest run wins per airline; new column `tested_in`).

**Result for all 30 airlines** (Step 2 + Step 4 part 1):

| Result | n | Airlines |
|---|---|---|
| allowed | 11 | SpiceJet, Akasa Air, Air India Express, ANA, Ryanair, Finnair, TAP Air Portugal, Southwest, JetBlue, Air Canada, Qantas |
| blocked | 9 | JAL, Lufthansa, Emirates (Step 2); easyJet, Iberia, SAS, American, Qatar Airways (HTTP 403), Delta (HTTP 444 + "Access Denied") |
| blocked_unconfirmed | 3 | IndiGo (Step 2); Singapore Airlines (HTTP 404 error page), Alaska (HTTP 406 error page) |
| error | 7 | Air India (Step 2); Peach, Cathay Pacific, Air France, KLM, Turkish Airlines, United - all `net::ERR_HTTP2_PROTOCOL_ERROR` (connection cut before any page loaded) |

So 19 of 30 (63%) did not give our headless browser the real homepage.

**Problem found and fixed**
- The script first marked Singapore Airlines (HTTP 404, title "SIA-Maintenance Page") and
  Alaska (HTTP 406, title "Looks like we hit some turbulence") as `ok`, because
  `detect_block()` only treated 401/403/405/429/503 as refusals and these error pages had enough
  text. Checked the screenshots: both are error pages, not homepages (Alaska's page suggests
  pausing VPNs / privacy extensions; Singapore's shows an Akamai-style reference code like
  Delta's block page). Fixes:
  - `record_access.py`: a page with HTTP status >= 400 is never counted as "allowed";
    these two are `blocked_unconfirmed`, with the status and title in the evidence column.
    (Raw files not edited, rule 6.)
  - `axe_runner.detect_block()`: any HTTP status >= 400 is now flagged, for future runs.
- Small change to the categories: a clear block phrase (e.g. "access denied") now counts as
  `blocked` even without a 4xx status. Checked: this does not change any Step 2 result.

**How to read the categories (for the paper)**
- `error` with ERR_HTTP2_PROTOCOL_ERROR: the server closed the connection. This pattern is
  often bot protection, but we cannot prove it, so it is not counted as "blocked".
- All results are from ONE visit from ONE location (India) on ONE day. Sites can behave
  differently from other countries or at other times.
- Some allowed sites redirected by location: Air Canada and Qantas to their India versions
  (/in/en, en-in), Ryanair to Ireland (/ie/en), and TAP opened in Portuguese (pt-pt). This only
  affects the access test, not the captures.

**Next**: Step 4 part 2. With 11 "allowed" airlines, the live-vs-copy comparison can now be
done on more than one airline.

---

## 2026-11-11 - First captures (ANA) and first live scan

**Captures (by hand, SingleFile)**: ANA home, check-in and assistance, saved 2026-11-11
21:37-21:38 local time, which is 12:37-12:38 UTC.
- The SingleFile header says GMT+0900 (Japan Standard Time): this computer's clock is set to
  Japan time, while websites see the connection as coming from India. The log uses the
  offset written in the file (+09:00), so the UTC time is correct.
- Homepage: typed https://www.ana.co.jp/en/jp/ but ANA redirected by location to /en/in/
  (India version). So the "home" capture is the India/English homepage, not Japan/English.
- Check-in: the web-search suggestion redirected to
  https://aswbe.ana.co.jp/webapps/checkin/checkin-search?LANG=en&CONNECTION_KIND=CHE
- `data/airlines.csv`: ANA now has these final URLs and `url_verified = yes`.
- Chrome and SingleFile versions were not filled in by hand, so they were read from the installed
  files at 12:40 UTC: Chrome 157.0.8103.40 and SingleFile 1.37.0 (only installed in Chrome
  "Profile 4"). Recorded as such in the log notes.

**New script**: `src/register_captures.py` reads the SingleFile header (URL + save date),
matches the URL to `data/airlines.csv`, renames the file to `airline_pagetype_YYYYMMDD.html`
and appends the log row. Files whose URL is not in airlines.csv are left untouched.
First run crashed (harmlessly, before renaming) because the Windows console could not print the
"｜" character in SingleFile names; fixed by printing UTF-8.

**Live scan of ANA** (`scan_live.py ana`, run 20261111T124041Z, started 12:40 UTC, about 3 min
after the captures):

| Page | Result |
|---|---|
| home (/en/in/) | ok: 10 rules failed, 38 elements |
| checkin (aswbe.ana.co.jp) | **error**: `net::ERR_HTTP2_PROTOCOL_ERROR`, the same pattern as the 7 "error" airlines. Not retried (rule 3). |
| assistance | ok: 3 rules failed, 6 elements (aria-hidden-focus, listitem, nested-interactive) |

So ANA allows automated access to www.ana.co.jp but its check-in site (aswbe.ana.co.jp) cut
the connection. For the paper: access can differ between parts of one airline's site, so the
homepage access test does not guarantee access to the booking pages. Only 2 of ANA's 3 pages can
be compared live vs saved copy.

Note: the ANA homepage now fails 10 rules (38 elements), compared with 7 rules (29 elements)
on /en/jp/ in Step 2. These are different page versions on different days, so the numbers
are not directly comparable.

**Next**: scan the 3 ANA captures (`scan_captures.py`) and run `compare_live_vs_capture.py`.

---

## 2026-11-11 - Helper to open one region's pages for capturing

- `src/open_batch.py <region>` opens all pages of one region from `data/airlines.csv` as tabs in
  my normal Chrome, in the "a11y-capture" profile. It finds the profile folder by reading
  Chrome's "Local State" file (currently "Profile 4"). If the profile is not found it stops instead of
  using another profile, because my other profiles are signed in to personal accounts.
- Skips MISSING URLs and airlines with `url_verified = yes`. It opens one tab every 10 s
  (minimum), so the same airline's site never gets several page loads at once (rule 1).
- It only opens tabs: a person still checks, saves and registers each page. This is normal
  browsing, not automation, and the browser is not disguised.
- Tested with `--dry-run` only: India 13 tabs, Japan/Asia 10, Europe 30, North America 19,
  Middle East/Oceania 9. That is 81 tabs = 90 pages - 3 ANA (verified) - 6 MISSING.
