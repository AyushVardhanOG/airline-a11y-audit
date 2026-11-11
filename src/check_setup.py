"""
check_setup.py - Step 1 self-test.

Purpose: prove that every tool the audit needs is installed and talks to each other,
WITHOUT visiting any real website.

What it does:
  1. Starts a headless Chromium browser with Playwright.
  2. Loads a tiny test page that we write ourselves (it lives only in memory).
     The page has ONE deliberate accessibility mistake: an image with no alt text.
  3. Injects axe-core into the page and runs it.
  4. Checks that axe-core found the "image-alt" violation we planted.
  5. Prints the versions of Python, Playwright, Chromium and axe-core
     (the same metadata we must save with every real scan - see rule 5 in CLAUDE.md).

Run it from the project folder:
    .venv\\Scripts\\python.exe src\\check_setup.py
"""

import json
import sys
from importlib.metadata import version
from pathlib import Path

from playwright.sync_api import sync_playwright

# Path to the axe-core script that `npm install` downloaded.
PROJECT_ROOT = Path(__file__).resolve().parent.parent
AXE_PATH = PROJECT_ROOT / "node_modules" / "axe-core" / "axe.min.js"

# A tiny page with one known problem: <img> without an alt attribute.
TEST_PAGE = """
<!doctype html>
<html lang="en">
  <head><title>Setup test page</title></head>
  <body>
    <main>
      <h1>Setup test</h1>
      <img src="data:image/gif;base64,R0lGODlhAQABAAAAACw=" width="10" height="10">
    </main>
  </body>
</html>
"""


def main():
    # Stop early with a clear message if axe-core was not downloaded.
    if not AXE_PATH.exists():
        print(f"ERROR: axe-core not found at {AXE_PATH}. Run `npm install` first.")
        sys.exit(1)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Load our own test HTML (no network request is made).
        page.set_content(TEST_PAGE)

        # Inject axe-core, then run it. axe.run() returns a JS Promise;
        # Playwright waits for it and converts the result to a Python dict.
        page.add_script_tag(path=str(AXE_PATH))
        results = page.evaluate("async () => await axe.run()")

        browser_version = browser.version
        browser.close()

    found_rules = [v["id"] for v in results["violations"]]

    print("Versions")
    print(f"  Python      : {sys.version.split()[0]}")
    print(f"  Playwright  : {version('playwright')}")
    print(f"  Chromium    : {browser_version}")
    print(f"  axe-core    : {results['testEngine']['version']}")
    print()
    print(f"Violations found on test page: {json.dumps(found_rules)}")

    # The planted mistake must be detected, otherwise something is wrong.
    if "image-alt" in found_rules:
        print("PASS: axe-core detected the missing alt text. Setup works.")
    else:
        print("FAIL: expected an 'image-alt' violation but did not get one.")
        sys.exit(1)


if __name__ == "__main__":
    main()
