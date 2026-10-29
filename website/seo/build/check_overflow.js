// LOCAL-812B: phone-width overflow check + screenshots.
// Loads each page at 360/390/430 CSS px, asserts
// document.documentElement.scrollWidth <= innerWidth (no horizontal overflow),
// reports the widest offending element if any, and writes a phone screenshot.
//
// Run (needs puppeteer-core + a local Chrome; nothing is installed into the repo):
//   npm i -g puppeteer-core   # or in a scratch dir
//   node check_overflow.js /abs/path/to/website/seo /abs/path/to/out-dir
// Exits 0 only if every page passes at every width. Writes <name>-phone.png
// (390 px) and overflow-check.json into the out dir.
const puppeteer = require('puppeteer-core');
const http = require('http');
const path = require('path');
const fs = require('fs');

const SITE = process.argv[2];                 // website/seo absolute path
const OUTDIR = process.argv[3];               // where to write screenshots
const CHROME = '/Applications/Google Chrome.app/Contents/MacOS/Google Chrome';

const PAGES = [
  { url: '/tours/paris/louvre-museum-audio-tour/', name: 'louvre' },
  { url: '/tours/paris/', name: 'paris-hub' },
  { url: '/pricing/', name: 'pricing' },
];
const WIDTHS = [360, 390, 430];

const MIME = {
  '.html': 'text/html', '.css': 'text/css', '.js': 'application/javascript',
  '.png': 'image/png', '.mp3': 'audio/mpeg', '.xml': 'application/xml',
  '.txt': 'text/plain', '.json': 'application/json',
};

function serve(root) {
  return new Promise((resolve) => {
    const srv = http.createServer((req, res) => {
      let p = decodeURIComponent(req.url.split('?')[0]);
      if (p.endsWith('/')) p += 'index.html';
      const fp = path.join(root, p);
      if (!fp.startsWith(root) || !fs.existsSync(fp) || fs.statSync(fp).isDirectory()) {
        res.writeHead(404); res.end('nf'); return;
      }
      res.writeHead(200, { 'content-type': MIME[path.extname(fp)] || 'application/octet-stream' });
      fs.createReadStream(fp).pipe(res);
    });
    srv.listen(0, '127.0.0.1', () => resolve(srv));
  });
}

(async () => {
  const srv = await serve(SITE);
  const port = srv.address().port;
  const base = `http://127.0.0.1:${port}`;
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: 'new',
    args: ['--no-sandbox', '--hide-scrollbars'],
  });
  let failures = 0;
  const results = [];
  for (const pg of PAGES) {
    for (const w of WIDTHS) {
      const page = await browser.newPage();
      await page.setViewport({ width: w, height: 900, deviceScaleFactor: 2, isMobile: true });
      await page.goto(base + pg.url, { waitUntil: 'networkidle2', timeout: 30000 });
      // Give the lazy map a moment; it may fail offline — that's fine, the
      // container is width:100% and must not overflow regardless.
      await new Promise(r => setTimeout(r, 600));
      const m = await page.evaluate(() => {
        const de = document.documentElement;
        const iw = window.innerWidth;
        const sw = de.scrollWidth;
        let worst = null, worstW = 0;
        for (const el of document.querySelectorAll('body *')) {
          const r = el.getBoundingClientRect();
          if (r.right > iw + 0.5 && r.width > worstW) {
            worstW = r.width;
            worst = (el.tagName.toLowerCase() +
              (el.id ? '#' + el.id : '') +
              (el.className && typeof el.className === 'string'
                ? '.' + el.className.trim().split(/\s+/).join('.') : '')) +
              ' right=' + Math.round(r.right);
          }
        }
        return { iw, sw, worst };
      });
      const ok = m.sw <= m.iw;
      if (!ok) failures++;
      results.push({ page: pg.name, w, iw: m.iw, sw: m.sw, ok, worst: m.worst });
      console.log(`${ok ? 'PASS' : 'FAIL'}  ${pg.name} @${w}px  scrollWidth=${m.sw} innerWidth=${m.iw}` +
        (m.worst ? `  worst=${m.worst}` : ''));
      // Screenshot only at 390 (the review width), full page.
      if (w === 390) {
        const out = path.join(OUTDIR, `${pg.name}-phone.png`);
        await page.screenshot({ path: out, fullPage: true });
      }
      await page.close();
    }
  }
  await browser.close();
  srv.close();
  fs.writeFileSync(path.join(OUTDIR, 'overflow-check.json'),
    JSON.stringify({ widths: WIDTHS, results, failures }, null, 2));
  console.log(`\n${failures === 0 ? 'ALL PASS' : failures + ' FAILURES'}`);
  process.exit(failures === 0 ? 0 : 1);
})().catch(e => { console.error(e); process.exit(2); });
