"""
axe_runner.py - shared code used by BOTH scanners:
  - scan_live.py      (scans live websites)
  - scan_captures.py  (scans saved SingleFile copies)

Keeping this in one place guarantees that live pages and saved copies are scanned
with exactly the same axe-core version, the same WCAG rules and the same iframe
setting, so their results can be compared fairly.
"""

import re
import sys
from datetime import datetime, timezone
from importlib.metadata import version
from pathlib import Path

from playwright.sync_api import Error as PlaywrightError

# ---------------------------------------------------------------- settings

PROJECT_ROOT = Path(__file__).resolve().parent.parent
AXE_PATH = PROJECT_ROOT / "node_modules" / "axe-core" / "axe.min.js"

# Only check WCAG 2.0 and 2.1, Level A and AA (our research scope).
WCAG_TAGS = ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"]

VIEWPORT = {"width": 1366, "height": 768}  # a common laptop screen size

# The three page types we collect for every airline (also used in file names).
PAGE_TYPES = ["home", "checkin", "assistance"]

# HTTP status codes that usually mean "you are not allowed in".
BLOCK_STATUS_CODES = {401, 403, 405, 429, 503}

# Phrases that typically appear on bot-protection / block pages.
BLOCK_PHRASES = [
    "access denied",
    "request unsuccessful",
    "are you a robot",
    "verify you are human",
    "verifying you are human",
    "just a moment",
    "attention required",
    "pardon our interruption",
    "captcha",
    "unusual traffic",
    "you have been blocked",
    "request blocked",
]


# ---------------------------------------------------------------- small helpers

def utc_now():
    """Current time in UTC as an ISO string, e.g. 2026-11-11T15:04:05+00:00."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def make_run_id():
    """A folder name for one run of a scanner, e.g. 20261111T115319Z (UTC)."""
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def load_axe_source():
    """Read the axe-core JavaScript file that `npm install` downloaded."""
    if not AXE_PATH.exists():
        sys.exit(f"ERROR: axe-core not found at {AXE_PATH}. Run `npm install` first.")
    return AXE_PATH.read_text(encoding="utf-8")


def tool_versions(browser):
    """Versions saved with every scan (rule 5). axe-core's version is added after a scan."""
    return {
        "python": sys.version.split()[0],
        "playwright": version("playwright"),
        "browser": f"chromium {browser.version}",
    }


def redact_ips(text):
    """
    Replace IP addresses with [IP REDACTED]. Some block pages print the visitor's
    own IP address (Lufthansa did in Step 2), and this repo is public.
    """
    text = re.sub(r"\b\d{1,3}(?:\.\d{1,3}){3}\b", "[IP REDACTED]", text)  # IPv4
    text = re.sub(r"\b(?:[0-9a-fA-F]{1,4}:){3,7}[0-9a-fA-F]{1,4}\b", "[IP REDACTED]", text)  # IPv6
    return text


def detect_block(http_status, title, body_text):
    """
    Decide whether a page is a block page instead of the real page.
    Returns a reason string if blocked, or None if the page looks normal.
    """
    if http_status in BLOCK_STATUS_CODES:
        return f"HTTP status {http_status}"
    # Any other error status (e.g. 404, 406, 444) also means we did not get the real
    # page. Added in Step 4: Singapore Airlines (404) and Alaska (406) showed error pages
    # with enough text to pass the checks below.
    if http_status is not None and http_status >= 400:
        return f"HTTP error status {http_status} (error page, not the real page)"

    # Only look at the title and the start of the visible text. Block pages are short,
    # and this avoids false alarms from words deep inside a normal page.
    text_to_check = (title + " " + body_text[:2000]).lower()
    for phrase in BLOCK_PHRASES:
        if phrase in text_to_check:
            return f"block phrase found: '{phrase}'"

    if len(body_text.strip()) < 100:
        return "page has almost no visible text (possible block or failed load)"

    return None


# ---------------------------------------------------------------- axe-core

def inject_axe(page, axe_source):
    """
    Load axe-core into the page and into every iframe, so content inside
    iframes is checked too. page.evaluate() runs through the browser's debugging
    channel, so the page's Content-Security-Policy does not stop the injection.

    By default axe-core only talks to iframes from the SAME origin (domain) as the page,
    and silently skips others. Booking widgets and chat boxes are often loaded from
    other domains, and users still have to use them, so we allow all origins.
    (Tested in Step 2: without this setting cross-origin iframes were not scanned.)
    In the results, an element inside an iframe has a "target" list with more than
    one entry: [iframe selector, element selector].

    Returns the number of frames that could not be injected.
    """
    allow_all = "axe.configure({ allowedOrigins: ['<unsafe_all_origins>'] })"
    page.evaluate(axe_source)
    page.evaluate(allow_all)
    skipped_frames = 0
    for frame in page.frames:
        if frame == page.main_frame:
            continue
        try:
            frame.evaluate(axe_source)
            frame.evaluate(allow_all)
        except PlaywrightError:
            skipped_frames += 1
    return skipped_frames


def run_axe(page, axe_source):
    """
    Inject axe-core and run the WCAG 2.0/2.1 A + AA rules on the current page.
    Returns (axe results dict, extra info dict).
    """
    frames_not_injected = inject_axe(page, axe_source)
    results = page.evaluate(
        """async (tags) => await axe.run(document, {
               runOnly: { type: 'tag', values: tags },
               resultTypes: ['violations']
           })""",
        WCAG_TAGS,
    )
    info = {"frames_total": len(page.frames), "frames_not_injected": frames_not_injected}
    return results, info


def summarize_violations(violations):
    """
    Turn axe's violation list into simple numbers for summary tables:
    how many rules failed, how many elements failed, and elements per impact level.
    """
    summary = {
        "rules_failed": len(violations),
        "elements_failed": sum(len(v["nodes"]) for v in violations),
        "critical": 0, "serious": 0, "moderate": 0, "minor": 0,
    }
    for v in violations:
        impact = v.get("impact") or "minor"
        summary[impact] += len(v["nodes"])
    return summary


def take_screenshot(page, path):
    """Full-page screenshot; falls back to the visible area if the page is too big."""
    try:
        page.screenshot(path=str(path), full_page=True, timeout=30_000)
    except PlaywrightError:
        page.screenshot(path=str(path), timeout=30_000)
    return project_relative(path)


def project_relative(path):
    """Path as text, relative to the project folder when possible (shorter, portable)."""
    return path.relative_to(PROJECT_ROOT).as_posix() if path.is_relative_to(PROJECT_ROOT) else str(path)
