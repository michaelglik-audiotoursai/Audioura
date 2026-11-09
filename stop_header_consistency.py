"""stop_header_consistency.py -- LOCAL-876: a stop's Type/Specialty and Specific
Examples HEADER lines must not contradict the stop's own body or its evidence.

Evidence (tour 544, ouVCyG8V, HCMC walking tour): Stop 1 Notre-Dame Cathedral
Basilica of Saigon shipped with

    Specific Examples: Stunning neo-Romanesque architecture, ...

in the header while the narration / the stop's own evidence describe the
cathedral's design as neo-Gothic (Gothic Revival).  Nothing checked it:

  * ``stop_headers.restore_stop_headers`` (LOCAL-866) RESTORES these lines from
    the poi dict -- it never reconciles them with the body or evidence;
  * ``generate_tour_text._check_type_prose_contradiction`` (LOCAL-27) runs only
    for ``tour_category == 'museum'`` AND its period groups put *gothic* and
    *romanesque* BOTH in "medieval", so neo-Romanesque vs neo-Gothic is not a
    contradiction to it;
  * the LOCAL-872 claim gate filters BODY sentences, not the header lines.

This module is the reconciler for the header lines on the walking / landmark
path.  For each ``Stop N:`` block it reconciles the ``Type/Specialty:`` and
``Specific Examples:`` lines:

  1. FACT SHEET first.  When the stop's poi carries a fact sheet that names an
     architectural style, that style is authoritative: a header style that
     disagrees with it is replaced by (or, if the header has no other content,
     dropped in favour of) the fact-sheet style.

  2. Otherwise, run the header through the same idea as the LOCAL-872 claim
     gate: a STYLE word in the header that contradicts a DIFFERENT, mutually
     exclusive style stated in the body or the evidence is UNSOURCED-and-
     contradicted, and is dropped.  A style phrase is removed from the line; if
     removing it leaves the line with no real content, the whole line is
     dropped.

Architectural styles are treated as ONE mutually-exclusive dimension: a building
is described with one primary style, so "neo-Romanesque" in the header and
"neo-Gothic" in the body cannot both be right.  Romanesque Revival (a.k.a.
neo-Romanesque) and Gothic Revival (neo-Gothic) are distinct families.

Pure: no network, no LLM, no DB.  Deterministic and idempotent.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "style_tokens", "contradicting_style", "reconcile_header_line",
    "reconcile_stop_block", "reconcile_stop_headers", "fact_sheet_style",
]

_STOP_LINE = re.compile(r'^Stop\s+(\d+):[^\n]*$', re.M)

# The two header lines this module reconciles.
_HEADER_LABELS = ("Type/Specialty", "Specific Examples")

# ── Architectural style families ─────────────────────────────────────────────
#
# Each entry is (canonical family, regex that matches any spelling of it).  The
# families are mutually exclusive as a building's PRIMARY style: stating two of
# them for one structure is a contradiction.  "neo-X", "neo X", "Gothic Revival"
# (== neo-Gothic) and "Romanesque Revival" (== neo-Romanesque) all normalise to
# the same family so the header's "neo-Romanesque" and the body's "neo-Gothic"
# land in different families and clash.
_STYLE_FAMILIES: Tuple[Tuple[str, "re.Pattern[str]"], ...] = (
    ("gothic",
     re.compile(r"(?i)\b(?:neo[\s\-]?gothic|gothic\s+revival|gothic)\b")),
    ("romanesque",
     re.compile(r"(?i)\b(?:neo[\s\-]?romanesque|romanesque\s+revival|romanesque)\b")),
    ("baroque",
     re.compile(r"(?i)\b(?:neo[\s\-]?baroque|baroque)\b")),
    ("rococo", re.compile(r"(?i)\brococo\b")),
    ("renaissance",
     re.compile(r"(?i)\b(?:neo[\s\-]?renaissance|renaissance\s+revival|renaissance)\b")),
    ("neoclassical",
     re.compile(r"(?i)\b(?:neo[\s\-]?classical|neoclassic(?:al)?|classical\s+revival)\b")),
    ("art_deco", re.compile(r"(?i)\bart[\s\-]?deco\b")),
    ("art_nouveau", re.compile(r"(?i)\bart[\s\-]?nouveau\b")),
    ("brutalist", re.compile(r"(?i)\bbrutalis[tm]\b")),
    ("modernist",
     re.compile(r"(?i)\b(?:modernis[tm]|international\s+style)\b")),
)

# The exact phrase to strip from a header line for each family (so dropping the
# contradicted style removes the human-readable words, not the regex).  Matched
# against the header text itself; a family present in the header is removed with
# its surrounding adjective "architecture"/"style"/"design" word if adjacent.
_STYLE_PHRASE_RE = re.compile(
    r"(?i)\b(?:(?:neo[\s\-]?)?(?:gothic|romanesque|baroque|renaissance|classical)"
    r"(?:\s+revival)?|rococo|neoclassic(?:al)?|art[\s\-]?deco|art[\s\-]?nouveau|"
    r"brutalis[tm]|modernis[tm]|international\s+style)"
    r"(?:\s+(?:revival\s+)?(?:architecture|architectural\s+style|style|design))?\b"
)


def style_tokens(text: str) -> List[str]:
    """The architectural-style families named in ``text`` (canonical names, in
    family order, de-duplicated).  Empty when it names no known style."""
    if not text:
        return []
    out: List[str] = []
    for fam, rx in _STYLE_FAMILIES:
        if rx.search(text) and fam not in out:
            out.append(fam)
    return out


def contradicting_style(header: str, body_or_evidence: str) -> Optional[Tuple[str, str]]:
    """``(header_family, other_family)`` when the header names a style and the
    body/evidence names a DIFFERENT style (mutually-exclusive families), else
    None.  Only the FIRST such clash is reported."""
    h = style_tokens(header)
    b = style_tokens(body_or_evidence)
    if not h or not b:
        return None
    bset = set(b)
    for fam in h:
        if fam not in bset:
            # a style in the header that the body/evidence does NOT share, and
            # the body/evidence states a different style instead → contradiction
            return fam, next(f for f in b if f != fam) if any(f != fam for f in b) else b[0]
    return None


def fact_sheet_style(poi: Optional[Dict]) -> Optional[str]:
    """The architectural style the poi's FACT SHEET names, canonicalised, or
    None when there is no fact sheet or it names no style.  Accepts a fact sheet
    under ``fact_sheet`` / ``_fact_sheet`` as a dict (any string value is
    scanned) or a plain string."""
    if not poi:
        return None
    fs = poi.get("fact_sheet") or poi.get("_fact_sheet")
    if not fs:
        return None
    if isinstance(fs, dict):
        blob = " ".join(str(v) for v in fs.values() if v)
    else:
        blob = str(fs)
    toks = style_tokens(blob)
    return toks[0] if toks else None


def _strip_style_phrase(line_value: str, family: str) -> str:
    """Remove the phrase(s) naming ``family`` from a header line value, tidying
    the leftover punctuation.  Returns the cleaned value (may be empty)."""
    fam_rx = dict(_STYLE_FAMILIES)[family]

    def _repl(m: "re.Match[str]") -> str:
        return "" if fam_rx.search(m.group(0)) else m.group(0)

    out = _STYLE_PHRASE_RE.sub(_repl, line_value)
    # tidy: collapse doubled separators / stray leading adjectives left behind
    out = re.sub(r"(?i)\b(stunning|beautiful|striking|elegant|magnificent|"
                 r"impressive|fine)\s+(?=,|;|\.|and\b|$)", "", out)
    out = re.sub(r"\s*,\s*,\s*", ", ", out)
    out = re.sub(r"\s*,\s*(?:and\s+)?(?=,|\.|$)", "", out)
    out = re.sub(r"^\s*(?:,|and|;)\s*", "", out)
    out = re.sub(r"\s*(?:,|and|;)\s*$", "", out)
    out = re.sub(r"\s{2,}", " ", out).strip()
    out = re.sub(r"\s+([.,;])", r"\1", out)
    # a value that is now only punctuation / an orphan article is empty
    if re.fullmatch(r"(?i)[\s.,;]*(?:a|an|the)?[\s.,;]*", out):
        return ""
    return out


def reconcile_header_line(label: str, value: str, body: str, evidence: str = "",
                          fs_style: Optional[str] = None
                          ) -> Tuple[Optional[str], Optional[str]]:
    """Reconcile one header line value.

    Returns ``(new_value, reason)``:
      * ``new_value`` is the cleaned value, or None to DROP the whole line;
      * ``reason`` is a short note when something changed, else None.

    Rules (LOCAL-876):
      1. Fact sheet wins: if ``fs_style`` is set and the header names a
         DIFFERENT style, the header style is dropped (the fact sheet is the
         authority).  The header style is kept when it agrees with the sheet.
      2. Else a header style contradicted by the body/evidence is dropped.
    A value stripped to nothing drops the line."""
    if not value or not value.strip():
        return value, None
    h_styles = style_tokens(value)
    if not h_styles:
        return value, None  # no style claim in this header line → nothing to do

    drop_family: Optional[str] = None
    reason: Optional[str] = None

    # 1. fact sheet is authoritative
    if fs_style is not None:
        for fam in h_styles:
            if fam != fs_style:
                drop_family = fam
                reason = (f"{label}: style '{fam}' dropped — fact sheet says "
                          f"'{fs_style}'")
                break

    # 2. else: contradicted by body / evidence
    if drop_family is None:
        clash = contradicting_style(value, (body or "") + "\n" + (evidence or ""))
        if clash:
            drop_family = clash[0]
            reason = (f"{label}: style '{clash[0]}' contradicts the "
                      f"body/evidence ('{clash[1]}') — dropped")

    if drop_family is None:
        return value, None

    new_value = _strip_style_phrase(value, drop_family)
    if not new_value:
        return None, (reason or f"{label}: contradicted style line dropped")
    return new_value, reason


def reconcile_stop_block(block: str, poi: Optional[Dict] = None,
                         evidence: str = "") -> Tuple[str, List[str]]:
    """Reconcile the Type/Specialty and Specific Examples header lines in one
    ``Stop N:`` block against that block's BODY (and ``evidence``).  Returns
    ``(new_block, reasons)``.

    The body, for the contradiction test, is every line in the block that is NOT
    one of the structural header lines (Stop/Address/Coordinates/Type/Specific
    Examples)."""
    lines = block.split("\n")
    header_idx: Dict[str, int] = {}
    body_parts: List[str] = []
    label_res = {lab: re.compile(r"^" + re.escape(lab) + r":[ \t]*(.*)$")
                 for lab in _HEADER_LABELS}
    structural = re.compile(r"(?i)^(Stop\s+\d+|Address|Coordinates|Type/Specialty|"
                            r"Specific Examples)\s*:")
    for i, ln in enumerate(lines):
        matched = False
        for lab, rx in label_res.items():
            if rx.match(ln):
                header_idx[lab] = i
                matched = True
                break
        if matched:
            continue
        if not structural.match(ln):
            body_parts.append(ln)
    body = "\n".join(body_parts)

    fs_style = fact_sheet_style(poi)
    reasons: List[str] = []
    drop_lines: List[int] = []
    for lab in _HEADER_LABELS:
        if lab not in header_idx:
            continue
        i = header_idx[lab]
        value = label_res[lab].match(lines[i]).group(1).strip()
        new_value, reason = reconcile_header_line(lab, value, body, evidence, fs_style)
        if reason:
            reasons.append(reason)
        if new_value is None:
            drop_lines.append(i)
        elif new_value != value:
            lines[i] = f"{lab}: {new_value}"

    if drop_lines:
        drop = set(drop_lines)
        kept: List[str] = []
        for i, ln in enumerate(lines):
            if i in drop:
                # also swallow an immediately-following blank line left behind
                continue
            kept.append(ln)
        # collapse the blank-line pair a dropped line can leave
        out_lines: List[str] = []
        for ln in kept:
            if ln == "" and out_lines and out_lines[-1] == "":
                continue
            out_lines.append(ln)
        lines = out_lines

    return "\n".join(lines), reasons


def reconcile_stop_headers(text: str, poi_list: Optional[Sequence[Dict]] = None,
                           stop_evidence: Optional[Dict[int, Sequence[str]]] = None,
                           log=None) -> str:
    """Return ``text`` with every stop block's Type/Specialty & Specific Examples
    header lines reconciled against that stop's body (and its evidence / fact
    sheet).  Idempotent.  Never raises on ordinary input.

    ``poi_list`` supplies the per-stop fact sheet (matched by name, then stop
    number, like ``stop_headers``).  ``stop_evidence`` optionally maps a 1-based
    stop number to extra evidence strings."""
    if not text:
        return text
    heads = list(_STOP_LINE.finditer(text))
    if not heads:
        return text
    pois = list(poi_list or [])
    pieces: List[str] = []
    pos = 0
    all_reasons: List[str] = []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = text[m.start():end]
        num = int(m.group(1))
        poi = _poi_for_block(num, _title(m.group(0)), pois)
        ev_items = (stop_evidence or {}).get(num) or []
        evidence = "\n".join(str(e) for e in ev_items if e)
        try:
            new_block, reasons = reconcile_stop_block(block, poi, evidence)
        except Exception:
            new_block, reasons = block, []
        if reasons:
            all_reasons.extend(f"{num}: {r}" for r in reasons)
        pieces.append(text[pos:m.start()])
        pieces.append(new_block)
        pos = end
    pieces.append(text[pos:])
    if all_reasons and log:
        log(f"  [LOCAL-876] reconciled stop header style(s): {all_reasons}")
    return "".join(pieces)


# ── poi matching (mirrors stop_headers._poi_for_block) ───────────────────────
def _norm(s: Optional[str]) -> str:
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def _title(stop_line: str) -> str:
    return stop_line.split(':', 1)[1].strip() if ':' in stop_line else ''


def _poi_for_block(num: int, title: str, pois: Sequence[Dict]) -> Optional[Dict]:
    nt = _norm(title)
    if nt:
        for p in pois:
            np_ = _norm(p.get('name'))
            if np_ and (np_ == nt or nt.startswith(np_) or np_.startswith(nt)):
                return p
    for p in pois:
        try:
            if int(p.get('stop_number')) == num:
                return p
        except (TypeError, ValueError):
            continue
    return None
