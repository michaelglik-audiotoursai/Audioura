"""
Structured stop records (LOCAL-643) — carry the tour as records, render ONCE.
=============================================================================

Strategy A (LEAD 2026-10-09). The fresh-generation path in generate_tour_text.py
assembles the whole tour into ONE string and then runs ~40 late passes over that
string. Those passes are the dominant source of the round's low scores: they glue
headers onto addresses, move one stop's orientation into another, split "9.00"
into two sentences, lose stop headers, and duplicate blocks (D641, LOCAL-641,
NG 495 R9/R12, Uffizi 2-of-3 R7/R8).

This module replaces the CAUSE CLASS. It defines a record for each delivered
unit — ``Stop``, plus a tour-level ``Opening`` and ``Closing`` — and a single
``render_tour`` that produces the delivered text ONCE, at the end, in exactly
today's format (title line → Stop N header → fields → Orientation → narration →
Directions; the opening inside Stop 1 per D640; then the conclusion and the
offer). Because the renderer is the ONLY place that emits headers and field
lines, a late text pass can never see or produce them: ``run_pass_per_stop``
runs a narration-only pass on ONE stop's narration paragraphs at a time.

Nothing here calls an LLM. The renderer is deterministic and is proven
byte-identical to the generate_tour_text render loop on the parity fixtures
(see test_local643_*). The module is inert unless the caller chooses to use it;
the ``STRUCTURED_STOPS`` env flag that gates the live wiring lives in the caller
(generate_tour_text), not here, so this module is import-safe everywhere.

The field format mirrors generate_tour_text.py:23426-23739 and the pool
renderer stop_pool_assembly._render_stop_block, so a structured-rendered tour is
indistinguishable from a freshly string-assembled one.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Callable, List, Optional


# ── Env gate ─────────────────────────────────────────────────────────────────
def structured_stops_enabled() -> bool:
    """True when STRUCTURED_STOPS=1 (default OFF).

    The flag is read here so every call-site agrees on the same truth. LEAD
    flips the default only after a benchmark round with the flag ON beats the
    flag OFF; until then the old string path is the default and this returns
    False.
    """
    return str(os.environ.get("STRUCTURED_STOPS", "")).strip() in ("1", "true", "True", "yes")


# ── Records ──────────────────────────────────────────────────────────────────
@dataclass
class Stop:
    """One delivered stop, as a record rather than a slice of a big string.

    ``narration`` is a LIST of paragraphs so a narration-only pass can be run per
    paragraph and the renderer joins them with the house blank-line separator.
    All header/field values are stored as already-resolved strings; the renderer
    never re-parses them out of prose. ``index`` is 1-based and authoritative —
    the renderer always numbers "Stop N" from it, so a header can never be lost.
    """
    index: int
    title: str
    artist: str = ""
    year: str = ""
    address: str = ""
    coordinates: str = ""
    type_specialty: str = ""
    specific_examples: str = ""
    operational_details: str = ""
    # [D7] On a single-venue museum tour, the operational details are rendered as
    # "Museum Information" and only on stop 1. The caller sets this flag.
    operational_label: str = "Operational Details"
    emit_operational: bool = True
    orientation: str = ""
    narration: List[str] = field(default_factory=list)
    # The transition line to the NEXT stop (already composed by the caller, from
    # the records — no "Continue to" inference happens in the renderer). None/""
    # on the last stop.
    directions: str = ""

    def narration_text(self) -> str:
        """The stop's narration as the single block the delivered text carries."""
        paras = [p.strip() for p in (self.narration or []) if p and p.strip()]
        return "\n\n".join(paras)


@dataclass
class Opening:
    """The tour's opening SECTION, placed at the top of Stop 1 per D640/D611 order:
    (a) honest shortfall → (b) About the venue / tour overview (the prolog) →
    (c) 'Your first stop is X.' → (d) entrance directive. All four are optional.

    Two house styles exist and the renderer reproduces BOTH, controlled by
    ``fold_into_orientation``:

    * NORMAL path (generate_tour_text.py:23555-23601): the pieces are folded
      INSIDE the Orientation line, right after the literal 'Orientation: ' label
      so the verbalization/translation layer still keys on it (LOCAL-264). Use
      ``prefix()``.
    * POOL / section path (stop_pool_assembly._render_stop_block, D611): the About
      + visiting-information are their own leading paragraphs BEFORE the
      Orientation line (``about_paragraphs``). Use ``section()``.
    """
    shortfall: str = ""        # (a) honest "we found N of M" clause
    about: str = ""            # (b) the prolog / overall tour description (inline)
    first_stop_sentence: str = ""   # (c) "Your first stop is X."
    entrance_directive: str = ""    # (d) where to physically go first
    # Section style: About + practical/visiting paragraphs rendered BEFORE
    # Orientation, one blank line between each (pool/D611 layout).
    about_paragraphs: List[str] = field(default_factory=list)
    fold_into_orientation: bool = True
    # Verbatim inline prefix already composed by the caller (normal path): the
    # exact text that sits between 'Orientation: ' and Stop 1's own orientation.
    # When set, it is used as-is and the piecewise fields above are ignored.
    inline_prefix: str = ""

    def prefix(self) -> str:
        """Inline opening text inserted between 'Orientation: ' and Stop 1's own
        orientation (normal-path layout).
        """
        if self.inline_prefix:
            return self.inline_prefix
        if not self.fold_into_orientation:
            return ""
        out = ""
        if self.shortfall.strip():
            out += self.shortfall.strip() + " "
        if self.about.strip():
            out += self.about.strip() + " "
        if self.first_stop_sentence.strip():
            out += self.first_stop_sentence.strip() + " "
        if self.entrance_directive.strip():
            out += self.entrance_directive.strip() + " "
        return out

    def section(self) -> str:
        """Standalone opening paragraphs rendered BEFORE Orientation (pool layout).

        Returns the paragraphs joined with the house blank-line separator, or ""
        when there are none / inline folding is in effect.
        """
        if self.fold_into_orientation:
            return ""
        paras = [p.strip() for p in self.about_paragraphs if p and p.strip()]
        return "\n\n".join(paras)


@dataclass
class Closing:
    """The tour's conclusion then offer, plus an optional Sources line.

    ``conclusion`` is the recap built from the delivered stops; ``offer`` is the
    restaurant/news offer that is always the last spoken sentence; ``sources`` is
    the trailing "Sources: …" credit line (empty when there are none). The
    renderer emits them in exactly this order onto the last stop's block, like
    generate_tour_text.py:23648-23735.
    """
    conclusion: str = ""
    offer: str = ""
    sources: str = ""
    # Verbatim tail already composed by the caller (normal path): the exact
    # epilog+sources blob appended to the last stop. When set, it is appended
    # as-is and the piecewise fields above are ignored. The leading/trailing
    # whitespace is preserved so re-rendering reproduces the delivered text.
    raw_tail: str = ""

    def render(self) -> str:
        if self.raw_tail:
            return self.raw_tail
        out = ""
        if (self.conclusion or "").strip():
            out += self.conclusion.strip() + " "
        if (self.offer or "").strip():
            out += self.offer.strip()
        out = out.rstrip()
        tail = ""
        if out:
            tail += "\n\n" + out
        if (self.sources or "").strip():
            tail += f"\n\nSources: {self.sources.strip()}"
        return tail


# ── Per-stop pass wrapper ─────────────────────────────────────────────────────
def run_pass_per_stop(stops: List[Stop], pass_fn: Callable[[str], str],
                      *, join_sep: str = "\n\n", verbose: bool = False) -> int:
    """Run a narration-only text pass on ONE stop's narration at a time.

    This is the whole point of the ticket: a pass that today edits the assembled
    tour string is wrapped so it only ever sees a single stop's narration
    paragraphs — never a header, a field line, an Orientation label, a Directions
    line, the title line, or the conclusion. For each stop we join its narration
    paragraphs into the block the pass expects, call the pass, and split the
    result back into paragraphs.

    ``pass_fn`` takes the narration block (str) and returns the cleaned block
    (str). Passes in this codebase often return a tuple ``(text, notes)``; wrap
    those with ``as_text_pass`` before calling here. Returns the number of stops
    whose narration changed (for the cost/quality ledger).
    """
    changed = 0
    for stop in stops:
        before = stop.narration_text()
        if not before:
            continue
        after = pass_fn(before)
        if after is None:
            continue
        after = str(after)
        if after != before:
            changed += 1
            if verbose:
                print(f"  [structured-stops] pass changed Stop {stop.index}")
        # Re-split into paragraphs on the house blank-line boundary.
        stop.narration = [p.strip() for p in re.split(r'\n\s*\n', after) if p.strip()]
    return changed


def as_text_pass(fn: Callable, *args, **kwargs) -> Callable[[str], str]:
    """Adapt a pass that returns ``(text, notes)`` (or just ``text``) into a
    ``str -> str`` callable suitable for ``run_pass_per_stop``.

    Many guards in this repo have the shape ``f(text, ...) -> (text, notes)``
    (clean_spoken_text, grammar_splice_lint, dedupe_paragraphs, strip_repeated_facts).
    This wrapper calls ``fn(block, *args, **kwargs)`` and returns element 0 when
    the result is a tuple/list, else the result itself.
    """
    def _run(block: str) -> str:
        res = fn(block, *args, **kwargs)
        if isinstance(res, (tuple, list)):
            return res[0] if res else block
        return res
    return _run


# ── Renderer ───────────────────────────────────────────────────────────────-─
def _header_value(stop: Stop) -> str:
    """The part of the header after 'Stop N: ' — name [+ ' by artist'] [+ ', year'].

    Mirrors generate_tour_text.py:23449-23455 and stop_pool_assembly._header_line.
    """
    header = stop.title
    artist = (stop.artist or "").strip()
    year = (stop.year or "").strip()
    if artist and artist.lower() != "unknown artist":
        header += f" by {artist}"
    if year:
        header += f", {year}"
    return header


def render_stop_block(stop: Stop, *, opening: Optional[Opening] = None,
                      closing: Optional[Closing] = None) -> str:
    """Render ONE stop into its delivered-text block, in house format.

    Field order mirrors the generate_tour_text render loop exactly:
      Stop N: {header}
      Address: ...
      Coordinates: ...
      Type/Specialty: ...        (non-museum)
      Specific Examples: ...     (non-museum)
      Museum Information: ...     | Operational Details: ...
      Orientation: {opening-prefix on stop 1}{stop orientation}
      {narration}
      Directions: ...            (omitted on the last stop)
      {conclusion}{offer}{sources}  (last stop only)

    Each field line is followed by a blank line, exactly as the string path emits
    ``\\n\\n`` after every field.
    """
    poi_content = f"Stop {stop.index}: {_header_value(stop)}" + "\n\n"

    if (stop.address or "").strip():
        poi_content += f"Address: {stop.address.strip()}\n\n"
    if (stop.coordinates or "").strip():
        poi_content += f"Coordinates: {stop.coordinates.strip()}\n\n"
    if (stop.type_specialty or "").strip():
        poi_content += f"Type/Specialty: {stop.type_specialty.strip()}\n\n"
    if (stop.specific_examples or "").strip():
        poi_content += f"Specific Examples: {stop.specific_examples.strip()}\n\n"
    if stop.emit_operational and (stop.operational_details or "").strip():
        poi_content += f"{stop.operational_label}: {stop.operational_details.strip()}\n\n"

    # Opening SECTION (pool/D611 layout): About + visiting-information paragraphs
    # BEFORE the Orientation line. Stop 1 only.
    if opening is not None and stop.index == 1:
        section = opening.section()
        if section:
            poi_content += section + "\n\n"

    # Orientation: the literal label first (LOCAL-264), then — on Stop 1 only —
    # the inline opening prefix (D640 order), then the stop's own orientation.
    # The label is emitted ONLY when there is something to say (an inline opening
    # prefix or the stop's own orientation text), so an empty "Orientation:" label
    # never reaches the listener — matching both the pool renderer and the fresh
    # path, which carry no orientation line when there is no orientation.
    prefix = opening.prefix() if (opening is not None and stop.index == 1) else ""
    orientation = (stop.orientation or "").strip()
    if prefix or orientation:
        poi_content += f"Orientation: {prefix}{orientation}".rstrip() + "\n\n"

    # Narration body.
    poi_content += stop.narration_text() + "\n\n"

    # Directions to the next stop (never on the last stop). The transition line is
    # supplied by the caller FROM the records — no inference here. One blank line
    # separates narration from Directions (the canonical pool-renderer layout,
    # stop_pool_assembly._render_stop_block; the fresh path's extra leading
    # newline was whitespace noise the TTS ignores).
    if (stop.directions or "").strip():
        poi_content += f"Directions: {stop.directions.strip()}\n\n"

    # Conclusion + offer + sources ride on the LAST stop's block.
    if closing is not None:
        if closing.raw_tail:
            # Verbatim passthrough (normal path): append the exact epilog blob.
            poi_content = poi_content.rstrip() + "\n\n" + closing.raw_tail.lstrip("\n")
            poi_content += "\n\n"
        else:
            epilog = ""
            if (closing.conclusion or "").strip():
                epilog += closing.conclusion.strip() + " "
            if (closing.offer or "").strip():
                epilog += closing.offer.strip()
            epilog = epilog.rstrip()
            if epilog:
                poi_content += "\n\n" + epilog
            if (closing.sources or "").strip():
                poi_content += f"\n\nSources: {closing.sources.strip()}"

    return poi_content


def title_block(location: str, tour_type: str, header_category: str,
                display_category: str) -> str:
    """The title line + Tour-Category header, mirroring the string path
    (generate_tour_text complete_tour init :21944 and stop_pool_assembly._title_line).
    """
    if (tour_type or "").lower() in (location or "").lower():
        tour_title = f"Step-by-Step Audio Guided Tour: {location}"
    else:
        tour_title = f"Step-by-Step Audio Guided Tour: {location} - {display_category} Tour"
    return tour_title + "\n" + f"Tour-Category: {header_category}" + "\n\n"


def render_tour(stops: List[Stop], *, title: str = "",
                opening: Optional[Opening] = None,
                closing: Optional[Closing] = None) -> str:
    """Produce the delivered text ONCE from the records.

    ``title`` is the already-built title block (use ``title_block`` to build it).
    The opening is folded into Stop 1; the closing rides on the last stop. The
    only text processing allowed after this is spoken-text hygiene (the caller's
    responsibility) — no regex re-parses the headers or field lines produced here.
    """
    parts: List[str] = []
    if title:
        parts.append(title if title.endswith("\n\n") else title.rstrip("\n") + "\n\n")
    n = len(stops)
    for i, stop in enumerate(stops):
        is_last = (i == n - 1)
        block = render_stop_block(
            stop,
            opening=opening if i == 0 else None,
            closing=closing if is_last else None,
        )
        parts.append(block.rstrip() + "\n\n")
    return "".join(parts).rstrip() + "\n"


# ── Parsing a delivered tour back into records (parity + stored-record render) ─
_STOP_HEADER_RE = re.compile(r'^Stop\s+(\d+):\s*(.+?)\s*$')
_FIELD_RE = re.compile(
    r'^(Address|Coordinates|Type/Specialty|Specific Examples|'
    r'Operational Details|Museum Information|Orientation|Directions):\s*(.*)$')


def _split_header_value(value: str):
    """Inverse of _header_value: pull (title, artist, year) out of a header value.

    Best-effort and lossless for round-trips of our own output: ', YEAR' at the
    end is the year when it is a bare year or year range; ' by ARTIST' before that
    is the artist. Anything we cannot confidently split stays in the title.
    """
    title, artist, year = value, "", ""
    m = re.search(r',\s*([0-9][0-9\u2013\u2014\-\s]*[0-9s]|[0-9]{3,4}s?)\s*$', title)
    if m:
        year = m.group(1).strip()
        title = title[:m.start()].rstrip()
    m = re.search(r'\s+by\s+(.+)$', title)
    if m:
        artist = m.group(1).strip()
        title = title[:m.start()].rstrip()
    return title, artist, year


def parse_tour_to_records(tour_text: str):
    """Parse a delivered tour string into ``(title, [Stop], Opening, Closing)``.

    Used by the parity harness and to render stored tours (audio_tours.tour_content)
    from records. This is a reader of ALREADY-rendered text — it is NOT part of the
    delivery path (the delivery path builds records at generation time, before any
    string exists). It recovers field values by their labels and treats everything
    between the Orientation line and the next field/header as narration.
    """
    lines = tour_text.split("\n")
    # Title block: everything before the first "Stop 1:" header.
    title_lines: List[str] = []
    idx = 0
    while idx < len(lines) and not _STOP_HEADER_RE.match(lines[idx].strip()):
        title_lines.append(lines[idx])
        idx += 1
    title = "\n".join(title_lines).rstrip("\n")
    if title:
        title += "\n\n"

    stops: List[Stop] = []
    opening = Opening(fold_into_orientation=False)
    closing = Closing()

    cur: Optional[Stop] = None
    section = None            # "orientation" | "narration" | "opening" | None
    narration_buf: List[str] = []
    opening_buf: List[str] = []

    def _flush_narration():
        """Append the buffered prose to the current stop's narration (never
        replaces — a stop may have prose before AND after its Orientation)."""
        nonlocal narration_buf
        if cur is not None and narration_buf:
            block = "\n".join(narration_buf).strip()
            if block:
                cur.narration.extend(
                    p.strip() for p in re.split(r'\n\s*\n', block) if p.strip())
        narration_buf = []

    def _flush_opening():
        nonlocal opening_buf
        if opening_buf:
            block = "\n".join(opening_buf).strip()
            if block:
                opening.about_paragraphs.extend(
                    p.strip() for p in re.split(r'\n\s*\n', block) if p.strip())
        opening_buf = []

    i = idx
    while i < len(lines):
        raw = lines[i]
        line = raw.strip()
        hm = _STOP_HEADER_RE.match(line)
        if hm:
            _flush_opening()
            _flush_narration()
            n = int(hm.group(1))
            t, a, y = _split_header_value(hm.group(2))
            cur = Stop(index=n, title=t, artist=a, year=y)
            stops.append(cur)
            # On Stop 1, prose before the Orientation line is the opening section;
            # on every other stop it is narration.
            section = "opening" if n == 1 else "narration"
            i += 1
            continue
        fm = _FIELD_RE.match(line)
        if fm and cur is not None:
            label, val = fm.group(1), fm.group(2).strip()
            if label == "Orientation":
                _flush_opening()
                _flush_narration()
                cur.orientation = val
                section = "orientation"
            elif label == "Directions":
                _flush_narration()
                cur.directions = val
                section = None
            else:
                if label == "Address":
                    cur.address = val
                elif label == "Coordinates":
                    cur.coordinates = val
                elif label == "Type/Specialty":
                    cur.type_specialty = val
                elif label == "Specific Examples":
                    cur.specific_examples = val
                elif label == "Operational Details":
                    cur.operational_details = val
                    cur.operational_label = "Operational Details"
                elif label == "Museum Information":
                    cur.operational_details = val
                    cur.operational_label = "Museum Information"
                    cur.emit_operational = True
            i += 1
            continue
        # Non-field, non-header line: prose for the current section.
        if cur is not None:
            if section == "orientation":
                if not line:
                    # blank line after Orientation closes it; narration follows
                    section = "narration"
                else:
                    cur.orientation = (cur.orientation + " " + line).strip()
            elif section == "opening":
                opening_buf.append(raw)
            else:
                section = "narration"
                narration_buf.append(raw)
        i += 1

    _flush_opening()
    _flush_narration()
    return title, stops, opening, closing
