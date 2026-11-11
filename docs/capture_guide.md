# Capture guide: saving airline pages with SingleFile

**Why we capture by hand:** in Step 2, most airline websites blocked our automated
(headless) browser. We do not get around bot protection (CLAUDE.md rule 3). Instead,
a person opens each page in a normal browser and saves it with the SingleFile
extension, and our pipeline scans the saved copy offline. **Every airline is measured
this way**, so all airlines are treated the same.

SingleFile saves the page *as the browser currently shows it* (after its JavaScript
has run) into one `.html` file, with images and styles packed inside.

---

## 1. One-time setup

1. Use **Google Chrome** (or Microsoft Edge). Our scanner uses Chromium, the same
   engine, so the page is drawn the same way.
2. Create a **separate Chrome profile** just for captures
   (profile icon at top right > *Add* > name it `a11y-capture`). In this profile:
   - do **not** sign in to Google or to any airline account;
   - do **not** install ad blockers, privacy or translation extensions.
     They change pages, and that would change our results.
3. Install **SingleFile** (by Gildas Lormeau) from the Chrome Web Store into that profile.
   Pin its icon to the toolbar (puzzle-piece icon > pin).
4. **Keep SingleFile's default settings.** Do not change them halfway through the project.
   Open the options page (right-click the SingleFile icon > *Options*). If there is an
   export button, export the settings to `data/captures/singlefile_settings.json`.
   If not, take screenshots of the options page and save them in `data/captures/`
   as `singlefile_settings_1.png`, `singlefile_settings_2.png`, ...
5. Note your Chrome version (`chrome://version`, first line) and SingleFile version
   (`chrome://extensions`). You need them for the log.
6. Browser window: **maximised** on your laptop screen, zoom **100%** (Ctrl+0).

---

## 2. Which pages to capture

Work through **[capture_checklist.md](capture_checklist.md)**: it lists every page with a
suggested URL (found by web search, not yet checked) and notes on what to check.

For **each airline** in `data/airlines.csv`, three pages:

| page_type    | What it is |
|--------------|-----------|
| `home`       | The airline's homepage, English version. |
| `checkin`    | The **online check-in** start page (the empty form asking for booking reference + name). If the airline has no separate check-in page, use the **manage booking** start page. Write which one in `notes`. |
| `assistance` | The main **special assistance / accessibility / passengers with reduced mobility** information page. |

**Language and region:** use the English version. If the site asks for a country,
choose the airline's **home country** if it has an English version there
(e.g. ANA: Japan / English), otherwise the international / global English site.
Write the country you chose in `notes`.

If a suggested URL is wrong, correct it in `data/airlines.csv`. If an airline has no
such page, or you cannot find it within about 5 minutes, write `MISSING` in that
column and move on. If the page turns out to be the homepage itself (e.g. SpiceJet's
check-in is the homepage with a check-in tab open), write `SAME_AS_HOME`: it is then
not captured or scanned separately. When all three URLs of an airline are checked, set its
`url_verified` column to `yes`.

Capture all three pages of one airline **in one sitting** (same day, close together).

---

## 3. Safety rules while capturing (from CLAUDE.md)

- **Do not log in. Do not type anything into forms.** Not even a booking reference.
- Never click "search", "continue", "submit" or anything that starts a booking.
  Never go anywhere near the payment step.
- **Cookie banner: do not click it.** Leave it as a first-time visitor sees it.
  The live scanner also never touches it, so live and saved copies stay comparable.
  If you visited the site before in this profile, first clear that site's data:
  padlock icon left of the address > *Site settings* > *Delete data*, then reload.
- If a "verify you are human" check appears, do **not** use any tool or trick to
  get past it. If you pass it normally as a human, write `human check shown` in `notes`.
  If the site refuses you, write `blocked for human visitor` in `notes` and skip it.
- Do not scroll through the page or open menus before saving. We want the page as it
  first appears, which is also what the live scanner sees.

---

## 4. Capturing one page, step by step

**Tip: open a whole region at once.** `src\open_batch.py` opens every page of one region
as tabs in your `a11y-capture` Chrome profile, one tab every 10 s (skipping MISSING URLs and
airlines already marked `url_verified = yes`), and prints the file name each page should get:

```powershell
.venv\Scripts\python.exe src\open_batch.py India
.venv\Scripts\python.exe src\open_batch.py "North America" --dry-run   # only list the tabs
```

It only opens tabs. You still check each page, save it, and follow the steps below.

1. Open the page and **wait about 10 seconds** until it stops changing.
2. Click the **SingleFile icon**. Wait until it finishes. The file appears in your
   Downloads folder.
3. **Rename** the file (or skip steps 3-5 and run `src
egister_captures.py`, which reads the
   URL and save date from the file, renames it and adds the log row for you - the final
   URL must already be in `data/airlines.csv`) to:

   ```
   <airline_id>_<page_type>_<YYYYMMDD>.html
   ```

   - `airline_id`: exactly as in the first column of `data/airlines.csv` (e.g. `air_india`)
   - `page_type`: `home`, `checkin` or `assistance`
   - `YYYYMMDD`: the date you captured it

   Examples: `air_india_checkin_20261112.html`, `ana_home_20261112.html`

4. **Move** it into `data/captures/`.
5. **Immediately add a row** to `data/captures/log.csv` (open it in VS Code or Excel;
   if Excel, save as CSV UTF-8):

   | column               | example                         | meaning |
   |----------------------|---------------------------------|---------|
   | `file_name`          | `ana_home_20261112.html`        | the new file name |
   | `airline_id`         | `ana`                           | from airlines.csv |
   | `page_type`          | `home`                          | home / checkin / assistance |
   | `url`                | `https://www.ana.co.jp/en/jp/`  | copied from the address bar |
   | `captured_at_local`  | `2026-11-12 10:15`              | your clock time when you clicked SingleFile |
   | `utc_offset`         | `+05:30`                        | your time zone (India = `+05:30`) |
   | `browser`            | `Chrome`                        | |
   | `browser_version`    | `142.0.7444.60`                 | from `chrome://version` |
   | `singlefile_version` | `1.22.80`                       | from `chrome://extensions` |
   | `notes`              | `Japan/English; cookie banner shown` | region chosen, anything unusual |

6. If the URL differs from the suggestion in `data/airlines.csv` (`homepage`,
   `checkin_url` or `assistance_url`), correct it there. Tick the box in
   `docs/capture_checklist.md`.

**Duplicates**: a capture that is not needed (e.g. a second copy of the same page) is
moved, unchanged, to `data/captures/_duplicates/` - never deleted. Files in that folder
are not scanned and, like all captures, are not uploaded to GitHub.

**Never edit a saved capture file afterwards.** Captures are raw data, like
`data/raw/`. The LLM fixes in Objective 2 will work on copies stored elsewhere.

---

## 5. Airlines that allow automated access (11 airlines, see the list in automated_access.csv)

See `data/results/automated_access.csv`. For these airlines we **also** scan the live
pages, to measure how much a saved copy differs from the live page. The two must be
made **close together in time**, because websites change:

1. Capture the airline's 3 pages as above, check their URLs in `data/airlines.csv`
   and set `url_verified` to `yes` (the live scanner skips airlines that are not `yes`).
2. **Within the same hour**, run the live scan for that airline (its `airline_id`):
   ```powershell
   .venv\Scripts\python.exe src\scan_live.py ana
   ```

---

## 6. After capturing: run the pipeline

```powershell
.venv\Scripts\python.exe src\scan_captures.py              # scan all saved copies
.venv\Scripts\python.exe src\compare_live_vs_capture.py    # live vs saved copy ("allowed" airlines)
```

`scan_captures.py` prints a WARNING if a file has no row in `log.csv` or uses an unknown
airline id, and SKIPS files whose names do not follow the pattern. Fix those and run again.

---

## 7. What goes on GitHub, and backups

- The captured `.html` files are **not** uploaded to GitHub (`.gitignore`). Two reasons:
  they are full copies of the airlines' own (copyrighted) pages, and they can contain
  details about you, such as your location or IP shown by the site.
- `log.csv`, the settings file, and all scan results **are** uploaded.
- Because the captures exist only on your computer, **back them up**: after each capture
  session, copy `data/captures/` to Google Drive or a USB drive.
