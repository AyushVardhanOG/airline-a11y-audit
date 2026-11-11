/*
 * scan_pa11y.js - the SECOND checker (Objective 1): scan the saved SingleFile copies with
 * Pa11y, using its HTML_CodeSniffer runner and the WCAG2AA standard.
 *
 * Same pages and same conditions as scan_captures.py (axe-core), so the two checkers can be
 * compared fairly:
 *   - exactly the same pages: the file list is taken from the LATEST capture-scan run in
 *     data/raw/capture_scans/ (78 files; _duplicates/ and SAME_AS_HOME pages are not in it);
 *   - completely OFFLINE: the saved file is served from disk under the same fake address
 *     http://saved-copy.localhost/<file> and EVERY other request is blocked;
 *   - the page's own JavaScript is switched off with the same header
 *     "Content-Security-Policy: script-src 'none'". Pa11y still works, because it injects
 *     HTML_CodeSniffer with page.evaluate() (browser debugging channel), not a <script> tag;
 *   - the same browser build: Playwright's Chromium (found in the ms-playwright folder),
 *     not a second Chrome downloaded by Puppeteer; same 1366x768 viewport.
 * Only "errors" are kept (includeWarnings / includeNotices = false). HTML_CodeSniffer's
 * warnings and notices are "please check by hand" items, which is closer to axe-core's
 * "incomplete" list than to its "violations", so they are left out of the comparison.
 *
 * Output (new timestamped folder per run, never overwritten):
 *   data/raw/pa11y_scans/<run_id>/<file_stem>.json
 *   data/results/pa11y_scans_<run_id>.csv
 *
 * Run from the project folder:
 *   node src/scan_pa11y.js
 */

'use strict';

const fs = require('fs');
const path = require('path');
const pa11y = require('pa11y');
const puppeteer = require('puppeteer');

const PROJECT_ROOT = path.resolve(__dirname, '..');
const CAPTURES_DIR = path.join(PROJECT_ROOT, 'data', 'captures');
const CAPTURE_SCANS_DIR = path.join(PROJECT_ROOT, 'data', 'raw', 'capture_scans');
const RAW_DIR = path.join(PROJECT_ROOT, 'data', 'raw', 'pa11y_scans');
const RESULTS_DIR = path.join(PROJECT_ROOT, 'data', 'results');
const FAKE_BASE_URL = 'http://saved-copy.localhost/';
const VIEWPORT = { width: 1366, height: 768 };
const STANDARD = 'WCAG2AA';

// ------------------------------------------------------------------ helpers

function utcNow() {
	return new Date().toISOString().replace(/\.\d{3}Z$/, '+00:00');
}

function makeRunId() {
	// Same format as the Python scripts, e.g. 20261111T142233Z
	return new Date().toISOString().replace(/[-:]/g, '').replace(/\.\d{3}Z$/, 'Z');
}

function packageVersion(name) {
	const file = path.join(PROJECT_ROOT, 'node_modules', ...name.split('/'), 'package.json');
	return JSON.parse(fs.readFileSync(file, 'utf8')).version;
}

/** Path of the Chromium that Playwright downloaded (newest chromium-* folder). */
function playwrightChromium() {
	const base = path.join(process.env.LOCALAPPDATA || '', 'ms-playwright');
	const dirs = fs.readdirSync(base).filter(d => /^chromium-\d+$/.test(d)).sort();
	for (const d of dirs.reverse()) {
		const exe = path.join(base, d, 'chrome-win64', 'chrome.exe');
		if (fs.existsSync(exe)) {
			return exe;
		}
	}
	throw new Error(`Playwright Chromium not found in ${base}`);
}

/** The 78 capture files scanned by the latest axe-core capture-scan run. */
function latestCaptureScan() {
	const runs = fs.readdirSync(CAPTURE_SCANS_DIR).filter(d => /^\d{8}T\d{6}Z$/.test(d)).sort();
	if (!runs.length) {
		throw new Error('No capture-scan run found. Run src/scan_captures.py first.');
	}
	const runId = runs[runs.length - 1];
	const records = fs.readdirSync(path.join(CAPTURE_SCANS_DIR, runId))
		.filter(f => f.endsWith('.json'))
		.map(f => JSON.parse(fs.readFileSync(path.join(CAPTURE_SCANS_DIR, runId, f), 'utf8')));
	return { runId, files: records.map(r => ({ fileName: r.file_name, airlineId: r.airline_id, pageType: r.page_type })) };
}

const quietLog = { debug() {}, error() {}, info() {} };

// ------------------------------------------------------------------ one page

/**
 * Scan one saved HTML file with Pa11y (HTML_CodeSniffer, WCAG2AA), fully offline.
 * Returns the raw record (also used by the test in the notes).
 */
async function scanFile(browser, htmlPath, meta = {}) {
	const fileName = path.basename(htmlPath);
	const pageUrl = FAKE_BASE_URL + encodeURIComponent(fileName);
	const body = fs.readFileSync(htmlPath);
	const blockedHosts = {};
	const record = {
		source: 'saved_copy',
		tool: 'pa11y',
		file_name: fileName,
		airline_id: meta.airlineId || null,
		page_type: meta.pageType || null,
		scan_started_utc: utcNow(),
		settings: {
			runner: 'htmlcs',
			standard: STANDARD,
			include_warnings: false,
			include_notices: false,
			viewport: VIEWPORT,
			page_scripts: "disabled (CSP script-src 'none')",
			network: 'all requests blocked except the saved file itself',
		},
		status: null,
		error: null,
	};

	const page = await browser.newPage();
	await page.setViewport(VIEWPORT);
	await page.setRequestInterception(true);
	page.on('request', request => {
		const url = request.url();
		if (url === pageUrl) {
			request.respond({
				status: 200,
				headers: {
					'Content-Type': 'text/html; charset=utf-8',
					'Content-Security-Policy': "script-src 'none'",
				},
				body,
			});
		} else if (url.startsWith('data:') || url.startsWith('blob:')) {
			request.continue(); // inline data inside the saved file, no network
		} else {
			const host = url.includes('://') ? url.split('/')[2] : url.slice(0, 30);
			blockedHosts[host] = (blockedHosts[host] || 0) + 1;
			request.abort();
		}
	});

	try {
		const results = await pa11y(pageUrl, {
			browser,
			page,
			runners: ['htmlcs'],
			standard: STANDARD,
			includeNotices: false,
			includeWarnings: false,
			timeout: 120000,
			wait: 1000,
			log: quietLog,
		});
		record.status = 'ok';
		record.page_title = results.documentTitle;
		record.issues = results.issues.map(i => ({
			code: i.code,
			type: i.type,
			message: i.message,
			selector: i.selector,
			context: i.context,
			runner: i.runner,
		}));
	} catch (err) {
		record.status = 'error';
		record.error = String(err && err.message ? err.message : err).split('\n')[0];
	} finally {
		record.blocked_requests_by_host = blockedHosts;
		record.scan_finished_utc = utcNow();
		await page.close();
	}
	return record;
}

// ------------------------------------------------------------------ main

async function main() {
	const { runId: captureRun, files } = latestCaptureScan();
	const runId = makeRunId();
	const outRaw = path.join(RAW_DIR, runId);
	fs.mkdirSync(outRaw, { recursive: true });

	const executablePath = playwrightChromium();
	const browser = await puppeteer.launch({ executablePath, headless: true });
	const versions = {
		node: process.version,
		pa11y: packageVersion('pa11y'),
		html_codesniffer: packageVersion('@pa11y/html_codesniffer'),
		puppeteer: packageVersion('puppeteer'),
		browser: await browser.version(),
		browser_executable: 'Playwright Chromium (ms-playwright)',
	};
	console.log(`Run id: ${runId}  (${files.length} files from capture-scan run ${captureRun})`);
	console.log(`Pa11y ${versions.pa11y}, HTML_CodeSniffer ${versions.html_codesniffer}, ${versions.browser}\n`);

	const rows = [];
	for (const [i, f] of files.entries()) {
		const htmlPath = path.join(CAPTURES_DIR, f.fileName);
		let record = await scanFile(browser, htmlPath, f);
		// The very first test run hung once ("Navigation timeout") and never again. The pages
		// are local files (no website is contacted), so one retry on a timeout is harmless.
		if (record.status === 'error' && /timeout/i.test(record.error || '')) {
			const firstError = record.error;
			record = await scanFile(browser, htmlPath, f);
			record.retried_after_error = firstError;
		}
		record.tool_versions = versions;
		record.capture_scan_run = captureRun;
		const stem = f.fileName.replace(/\.html$/, '');
		fs.writeFileSync(path.join(outRaw, `${stem}.json`), JSON.stringify(record, null, 2));
		const n = record.issues ? record.issues.length : null;
		console.log(`[${i + 1}/${files.length}] ${f.fileName} -> ${record.status}  errors=${n}  ${record.error || ''}`);
		rows.push([f.fileName, f.airlineId, f.pageType, record.status, n === null ? '' : n,
			record.issues ? new Set(record.issues.map(x => x.code)).size : '', record.error || '']);
	}
	await browser.close();

	const csvCell = v => (/[",\n]/.test(String(v)) ? `"${String(v).replace(/"/g, '""')}"` : String(v));
	const header = ['file_name', 'airline_id', 'page_type', 'status', 'errors', 'distinct_codes', 'error_message'];
	const csv = [header, ...rows].map(r => r.map(csvCell).join(',')).join('\n') + '\n';
	const summaryPath = path.join(RESULTS_DIR, `pa11y_scans_${runId}.csv`);
	fs.writeFileSync(summaryPath, csv);
	console.log(`\nRaw JSON   : ${path.relative(PROJECT_ROOT, outRaw)}`);
	console.log(`Summary CSV: ${path.relative(PROJECT_ROOT, summaryPath)}`);
}

module.exports = { scanFile, playwrightChromium };

if (require.main === module) {
	main().catch(err => {
		console.error(err);
		process.exit(1);
	});
}
