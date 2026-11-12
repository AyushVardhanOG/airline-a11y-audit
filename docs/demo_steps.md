# Live demo for the progress presentation

What the demo shows in about 1 minute of running time: one saved airline page is **scanned** for
accessibility problems, the local AI model **fixes** one problem, and the fix is **checked** again
with the same scanner. It uses exactly the same code and settings as the real experiment
(`src/demo.py` imports them from `src/repair.py` and `src/repair_full.py`).

Main demo page: **Qatar Airways, special-assistance page** (`qatar_airways_assistance_20261111.html`):
11 problems of 3 types, and a short, easy-to-read element. Tested on 2026-11-13: about 9 s for the
model's answer, about 30 s in total.

---

## Before the presentation

1. **Plug the laptop in** and close other heavy programs (the model uses the graphics card).
2. **Start Ollama** (the Ollama app; its icon appears in the taskbar tray).
3. Open **PowerShell in the project folder** (`D:\airline-a11y-audit`) and make the text big
   (Ctrl + mouse wheel), so the room can read it.
4. **Rehearse once, 5-10 minutes before you present.** This also loads the model into memory,
   so the live run is fast (the first answer after a long break can take up to a minute):
   ```powershell
   .venv\Scripts\python.exe src\demo.py qatar_airways_assistance_20261111.html
   ```
5. **Take a screenshot of the rehearsal output** as a backup slide, in case anything fails live.
6. Type `cls` to clear the screen.

---

## The demo, step by step (what to type and what to say)

### Step 0 - introduce it (before typing anything)

> "I will now show the whole pipeline on one real page. This is a copy of Qatar Airways'
> special-assistance page that I saved on 11 November. The demo works completely offline:
> it does not contact the airline's website, and the original saved copy is never changed."

Type:
```powershell
.venv\Scripts\python.exe src\demo.py qatar_airways_assistance_20261111.html
```

### STEP 1 on screen - the scan

Expected: *Found 11 failing elements of 3 problem types*: 9 images without alternative text,
1 colour-contrast problem, 1 link without text.

> "First, axe-core - the standard open-source accessibility checker - scans the page against the
> WCAG 2.1 level A and AA rules. It finds 11 elements that fail. Nine are images with no
> alternative text: a blind person using a screen reader gets no information about them. This is
> a 'critical' problem. Across all 78 pages of 29 airlines, 86% of pages failed at least one rule."

### STEP 2 on screen - the chosen problem

Expected: *Images must have alternative text (rule image-alt, WCAG 1.1.1)* and the HTML
`<img src="data:removed-1" class="open-icon">`.

> "The demo picks one of these problems. Here is the failing HTML: an image with no `alt` text.
> The long image data is replaced by a short placeholder, `data:removed-1`, before the model sees it,
> and put back afterwards. Before asking the AI, the program also checks that putting the
> unchanged element back does not change the scan result by itself - so whatever changes next
> is caused by the AI's fix and not by my method."

### STEP 3 on screen - the AI's fix

Expected (rehearsal on 2026-11-13): `alt="Open icon"` was added, nothing else changed.

> "Now I send this element, the rule and the scanner's explanation to a local language model,
> Qwen 2.5 Coder with 7 billion parameters, running on this laptop with Ollama - nothing is sent
> to the internet. It is the same prompt and settings as in the real experiment: temperature 0,
> a fixed seed. The model added `alt="Open icon"`. The 'What changed' line shows exactly that."

### STEP 4 on screen - the check

Expected: *RESULT: ACCEPTED* and *Review flags: none (looks plausible)*.

> "The fix is put into a copy of the page, the copy is saved and scanned again. axe-core no longer
> reports the problem, and no new problem appeared. But - and this is the important point of my
> project - 'the scanner accepts it' is not the same as 'it helps a real user'. 'Open icon' is the
> model's guess; it never saw the image. That is why my program also raises review flags, for
> example when a fix only hides an image with `alt=""`, and why Objective 3 tests the fixes
> further and trains a model that predicts which fixes are risky."

### Results to show next (slide, not live)

> "I repeated this for 578 problems with three local models: Qwen fixed 61%, Llama 3.1 59% and
> Gemma 2 52%, according to axe-core. 12 to 14% of the accepted fixes still need a human check.
> Simple problems like missing link text or image text were fixed almost always; problems that
> need the page structure changed, like nested interactive elements, almost never."

---

## Optional second run - a problem the AI does NOT fix (about 30 s)

Shows honestly that the method has limits:
```powershell
.venv\Scripts\python.exe src\demo.py air_india_home_20261111.html --rule label-content-name-mismatch
```
Expected (rehearsal on 2026-11-13): the model only changed spaces and line breaks, so the result is
*NOT FIXED*.

> "Here the visible text 'View All 24' must match the button's accessible name. The model only
> re-formatted the HTML, so the problem is still there. This rule is one of the hardest: the
> models fixed only 3 to 55% of these."

Notice in STEP 1 of this run: two problems are marked *added while saving the page, not the
airline's*. If asked:

> "While preparing this demo I found that a tiny link icon next to videos was added by the tool
> I used to save the pages. It caused 16 of the 768 failing elements. They are now left out of all
> results (752 counted), and the demo skips them."

---

## If something goes wrong

| What you see | What to do |
|---|---|
| `Ollama is not running` | Start the Ollama app, wait 10 s, run the command again. |
| `(thinking ...)` takes long | Normal for the first run after a break (model loading, up to a minute). Keep talking about Step 2. |
| The answer differs from the rehearsal | Possible: even with temperature 0 and a fixed seed, Ollama is not 100% repeatable (seen in the pilot). Explain that, and show the backup screenshot. |
| Any other error | Show the backup screenshot from the rehearsal. |

Other useful commands:
- list all saved pages with their number of problems: `.venv\Scripts\python.exe src\demo.py`
- choose the problem type: add `--rule color-contrast` (or `link-name`, `image-alt`, ...)

Every run saves the repaired copy and a full record (exact prompt, model version, answer, result)
in `data/repaired/demo/` (not uploaded to GitHub).
