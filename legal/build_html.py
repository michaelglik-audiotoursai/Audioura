#!/usr/bin/env python3
"""Render the legal/ Markdown drafts into self-contained, mobile-first HTML
pages (LOCAL-691).

DRAFTS. Nothing here is published — these files are for Michael (and a lawyer if
he chooses) to review before anything goes live on audioura.com.

Style: self-contained (inline CSS, no external CSS/JS), phone-readable, matching
the audioura.com brand placeholder palette from WEBSITE_BRIEF_audioura_com.md
(deep indigo + warm amber accent, large rounded sans-serif) and the self-
contained-HTML approach used by the public "how-we-score" page (LOCAL-688).

No third-party Markdown dependency: a tiny, deterministic converter handles the
subset of Markdown the drafts use (headings, bold, inline links, inline code,
bullet lists, tables, horizontal rules, paragraphs). Run:

    python3 legal/build_html.py

It writes legal/html/<name>.html for each legal/<NAME>.md.
"""

import html
import sys
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "html")

# Markdown file -> (output slug, published route it will live at)
DOCS = [
    ("TERMS.md", "terms", "/terms"),
    ("PRIVACY.md", "privacy", "/privacy"),
    ("REFUNDS.md", "refunds", "/refunds"),
    ("GUIDE_TERMS.md", "guide-terms", "/guide-terms"),
    ("ORGANISER_TERMS.md", "organiser-terms", "/organiser-terms"),
    ("CONTENT_POLICY.md", "content-policy", "/content-policy"),
]
# LEAD_NOTES.md is intentionally NOT rendered — it is an internal document.

STYLE = """
:root {
  --indigo: #2a2a6a;
  --indigo-deep: #1d1d4e;
  --amber: #f5a623;
  --ink: #1f2430;
  --muted: #5b6472;
  --rule: #e7e9f0;
  --bg: #ffffff;
  --panel: #f7f8fc;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--ink);
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto,
    "Helvetica Neue", Arial, sans-serif;
  line-height: 1.6;
  font-size: 17px;
}
header.doc {
  background: linear-gradient(135deg, var(--indigo) 0%, var(--indigo-deep) 100%);
  color: #fff;
  padding: 28px 20px 22px;
}
header.doc .wrap { max-width: 760px; margin: 0 auto; }
header.doc .brand { font-weight: 800; letter-spacing: .2px; font-size: 15px;
  opacity: .9; }
header.doc h1 { margin: 6px 0 4px; font-size: 26px; line-height: 1.2;
  font-weight: 800; }
header.doc .accent { height: 4px; width: 64px; background: var(--amber);
  border-radius: 4px; margin-top: 12px; }
.draft {
  max-width: 760px; margin: 16px auto 0; padding: 10px 14px;
  background: #fff6e6; border: 1px solid var(--amber); border-radius: 10px;
  color: #7a5200; font-size: 14px; font-weight: 600;
}
main {
  max-width: 760px; margin: 0 auto; padding: 10px 20px 56px;
}
main h2 { font-size: 20px; margin: 28px 0 8px; color: var(--indigo-deep); }
main h3 { font-size: 17px; margin: 18px 0 6px; color: var(--indigo-deep); }
main p { margin: 10px 0; }
main ul { margin: 10px 0; padding-left: 22px; }
main li { margin: 6px 0; }
main a { color: #3a3ac0; text-decoration: underline; }
main code {
  background: var(--panel); border: 1px solid var(--rule); border-radius: 5px;
  padding: 1px 5px; font-size: 90%;
}
main hr { border: 0; border-top: 1px solid var(--rule); margin: 26px 0; }
table { border-collapse: collapse; width: 100%; margin: 14px 0; font-size: 15px; }
th, td { border: 1px solid var(--rule); padding: 8px 10px; text-align: left;
  vertical-align: top; }
th { background: var(--panel); }
footer.doc {
  max-width: 760px; margin: 0 auto; padding: 20px; color: var(--muted);
  font-size: 13px; border-top: 1px solid var(--rule);
}
footer.doc a { color: var(--muted); }
"""


def _inline(text: str) -> str:
    """Escape, then re-apply the inline Markdown we use: links, bold, code."""
    # Protect inline code first by extracting to placeholders.
    codes = []

    def _grab_code(m):
        codes.append(m.group(1))
        return f"\x00CODE{len(codes) - 1}\x00"

    text = re.sub(r"`([^`]+)`", _grab_code, text)
    text = html.escape(text, quote=False)
    # Links [label](href)
    text = re.sub(
        r"\[([^\]]+)\]\(([^)]+)\)",
        lambda m: f'<a href="{html.escape(m.group(2), quote=True)}">{m.group(1)}</a>',
        text,
    )
    # Bold **x**
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    # Emphasis *x* (avoid matching bold leftovers)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    # Restore code
    for i, c in enumerate(codes):
        text = text.replace(f"\x00CODE{i}\x00", f"<code>{html.escape(c, quote=False)}</code>")
    return text


def _render_table(rows):
    """rows: list of raw '| a | b |' lines (header, separator, body...)."""
    def cells(line):
        parts = [c.strip() for c in line.strip().strip("|").split("|")]
        return parts

    header = cells(rows[0])
    body = [cells(r) for r in rows[2:]]  # skip the --- separator row
    out = ["<table>", "<thead><tr>"]
    out += [f"<th>{_inline(c)}</th>" for c in header]
    out.append("</tr></thead><tbody>")
    for r in body:
        out.append("<tr>" + "".join(f"<td>{_inline(c)}</td>" for c in r) + "</tr>")
    out.append("</tbody></table>")
    return "".join(out)


def md_to_html(md: str):
    lines = md.split("\n")
    title = None
    out = []
    i = 0
    n = len(lines)
    while i < n:
        line = lines[i]
        stripped = line.strip()
        if not stripped:
            i += 1
            continue
        # Table: a line starting with | whose next line is a --- separator
        if stripped.startswith("|") and i + 1 < n and re.match(r"^\|[\s:|-]+\|?\s*$", lines[i + 1].strip()):
            block = [lines[i], lines[i + 1]]
            i += 2
            while i < n and lines[i].strip().startswith("|"):
                block.append(lines[i])
                i += 1
            out.append(_render_table(block))
            continue
        if stripped == "---":
            out.append("<hr>")
            i += 1
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            level = len(m.group(1))
            content = _inline(m.group(2))
            if level == 1 and title is None:
                title = re.sub("<[^>]+>", "", content)
                # Strip a leading "Audioura — " brand prefix so the <title> and
                # header read e.g. "Terms of Service", not "Audioura — ...".
                title = re.sub(r"^\s*Audioura\s*[—–-]\s*", "", title).strip()
                # H1 becomes the header title, not body content.
                i += 1
                continue
            tag = f"h{min(level, 3)}"
            out.append(f"<{tag}>{content}</{tag}>")
            i += 1
            continue
        if stripped.startswith(("- ", "* ")):
            items = []
            while i < n and lines[i].strip().startswith(("- ", "* ")):
                items.append(_inline(lines[i].strip()[2:]))
                i += 1
            out.append("<ul>" + "".join(f"<li>{it}</li>" for it in items) + "</ul>")
            continue
        # Paragraph: gather until blank line
        para = [stripped]
        i += 1
        while i < n and lines[i].strip() and not re.match(r"^(#|\||- |\* |---)", lines[i].strip()):
            para.append(lines[i].strip())
            i += 1
        out.append(f"<p>{_inline(' '.join(para))}</p>")
    return title or "Audioura", "\n".join(out)


PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
{robots}<title>{title} — Audioura</title>
<style>{style}</style>
</head>
<body>
<header class="doc"><div class="wrap">
  <div class="brand">AUDIOURA</div>
  <h1>{title}</h1>
  <div class="accent"></div>
</div></header>
{draft}<main>
{body}
</main>
<footer class="doc">© Audioura LLC · 44 Sharpe Rd, Newton Centre, MA 02459, USA ·
  <a href="mailto:info@audioura.com">info@audioura.com</a></footer>
</body>
</html>
"""


# --publish (Michael's "publish", 2026-10-21, D697): no DRAFT banner, indexable.
PUBLISH = "--publish" in sys.argv
DRAFT_BANNER = ('<div class="draft">DRAFT for review — not published. This will live at\n'
                '  <code>{route}</code> on audioura.com once approved.</div>\n')


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    written = []
    for md_name, slug, route in DOCS:
        with open(os.path.join(HERE, md_name), encoding="utf-8") as f:
            md = f.read()
        title, body = md_to_html(md)
        page = PAGE.format(
            title=html.escape(title, quote=False),
            style=STYLE,
            route=html.escape(route, quote=False),
            body=body,
            robots='' if PUBLISH else '<meta name="robots" content="noindex">\n',
            draft='' if PUBLISH else DRAFT_BANNER.format(route=html.escape(route, quote=False)),
        )
        out_path = os.path.join(OUT_DIR, f"{slug}.html")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(page)
        written.append(out_path)
        print(f"wrote {out_path}")
    return written


if __name__ == "__main__":
    main()
