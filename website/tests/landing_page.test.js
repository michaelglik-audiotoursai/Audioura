// [LOCAL-709 / D671] Pure-logic tests for the landing page (website/t/index.html).
//
// The page exports its parsing helpers under module.exports when run in Node
// (the DOM-wiring block is guarded by `typeof document`, so requiring the file
// never touches the browser). We re-run the <script> body here by requiring a
// tiny shim that evaluates the page's script section.
//
// Run: node website/tests/landing_page.test.js   (exit 0 = all passed)

const fs = require('fs');
const path = require('path');
const vm = require('vm');

// Extract the <script> block that ends with module.exports from index.html and
// evaluate it in a Node context so we test the EXACT code that ships.
const html = fs.readFileSync(
  path.join(__dirname, '..', 't', 'index.html'),
  'utf8'
);
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
if (!scriptMatch) {
  console.error('FAIL: could not find <script> block in t/index.html');
  process.exit(1);
}
const sandbox = {
  module: { exports: {} },
  navigator: { userAgent: '' },
  // URLSearchParams is a browser global; provide Node's for the harness.
  URLSearchParams: URLSearchParams,
};
// No `document` in the sandbox → the DOM-wiring IIFE is skipped by its guard.
vm.createContext(sandbox);
vm.runInContext(scriptMatch[1], sandbox);
const page = sandbox.module.exports;

let failures = 0;
function eq(actual, expected, msg) {
  const a = JSON.stringify(actual);
  const e = JSON.stringify(expected);
  if (a !== e) {
    failures++;
    console.error(`FAIL: ${msg}\n  expected ${e}\n  got      ${a}`);
  } else {
    console.log(`ok: ${msg}`);
  }
}

// --- codeFromPath: path → code -------------------------------------------
eq(page.codeFromPath('/t/FFush25U'), 'FFush25U', 'codeFromPath: bare /t/CODE');
eq(page.codeFromPath('/t/FFush25U/'), 'FFush25U', 'codeFromPath: trailing slash');
eq(page.codeFromPath('/t/FFush25U?n=Hello'), 'FFush25U', 'codeFromPath: with query');
eq(page.codeFromPath('/'), '', 'codeFromPath: no code on root');
eq(page.codeFromPath('/legal/terms'), '', 'codeFromPath: non-/t/ path → empty');
eq(page.codeFromPath('/t/index.html'), '',
  'codeFromPath: a dotted segment (index.html) is not a code');

// --- androidUrlWithReferrer: carries audioura_code ------------------------
eq(
  page.androidUrlWithReferrer(
    'https://play.google.com/store/apps/details?id=com.audioura.audiotours',
    'FFush25U'
  ),
  'https://play.google.com/store/apps/details?id=com.audioura.audiotours&referrer=audioura_code%3DFFush25U',
  'androidUrlWithReferrer: appends &referrer=audioura_code%3D<CODE>'
);
eq(page.androidUrlWithReferrer('', 'FFush25U'), '',
  'androidUrlWithReferrer: empty base → empty (Coming soon)');

// --- storeButtonState: empty URL → Coming soon + disabled -----------------
eq(page.storeButtonState('android', ''),
  { enabled: false, label: 'Coming soon to Google Play' },
  'storeButtonState: empty Android URL → disabled Coming soon');
eq(page.storeButtonState('ios', ''),
  { enabled: false, label: 'Coming soon to the App Store' },
  'storeButtonState: empty iOS URL → disabled Coming soon');
eq(page.storeButtonState('android', 'https://play.google.com/x'),
  { enabled: true, label: 'Get it on Google Play' },
  'storeButtonState: present Android URL → enabled');
eq(page.storeButtonState('ios', 'https://apps.apple.com/x'),
  { enabled: true, label: 'Download on the App Store' },
  'storeButtonState: present iOS URL → enabled');

// --- platformFromUA -------------------------------------------------------
eq(page.platformFromUA('Mozilla/5.0 (Linux; Android 13)'), 'android',
  'platformFromUA: Android');
eq(page.platformFromUA('Mozilla/5.0 (iPhone; CPU iPhone OS 17_0)'), 'ios',
  'platformFromUA: iPhone');
eq(page.platformFromUA('Mozilla/5.0 (Macintosh; Intel Mac OS X)'), 'desktop',
  'platformFromUA: desktop → both buttons');

// --- [LOCAL-710 / D672] Fixed headline, no tour name in the page ----------
// The headline is ALWAYS "An Audioura tour for you" — the `?n=` name is gone.
eq(/<title>An Audioura tour for you<\/title>/.test(html), true,
  'D672: <title> is the fixed "An Audioura tour for you"');
eq(/id="headline"[^>]*>An Audioura tour for you</.test(html), true,
  'D672: <h1 id="headline"> is the fixed "An Audioura tour for you"');
eq(typeof page.nameFromQuery, 'undefined',
  'D672: nameFromQuery is removed (no tour name parsing)');
eq(/nameFromQuery/.test(html), false,
  'D672: no nameFromQuery anywhere in the page');
eq(/\?n=/.test(html) || /get\(["']n["']\)/.test(html), false,
  'D672: the page no longer reads an n query param');

if (failures > 0) {
  console.error(`\n${failures} test(s) FAILED`);
  process.exit(1);
}
console.log('\nAll landing-page tests passed.');
