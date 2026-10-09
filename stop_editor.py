"""[LOCAL-628 / LEAD D637] The final per-stop EDITOR pass.

Four rounds of point fixes (LOCAL-623…627) each cleared their own defects, but
every new venue showed new variants of the SAME class of damage — all of it
introduced by the many deterministic splice/removal passes that run AFTER
narration (story beats, G4 corrective, gloss gate, degrade, guards). The
symptoms converge:

  * sentences in the wrong order (effect before cause; a 1676 widow detail at the
    very end; the Nazi-era episode before what caused it);
  * broken clauses and dangling openers ("As a result …", "This move …",
    "This detail …") whose referent was removed upstream;
  * dropped words ("holdings art", "The effect, heightened the layering");
  * orphan one-word fragments ("Visscher.");
  * evasive filler ("its precise content … must be appreciated in person");
  * a gloss jammed into a name ("Pieter Bruegel, the 16th-century Flemish painter
    known for landscapes, the Elder around 1567");
  * unintroduced references ("Ernest", "as part of this series").

Point fixes will not converge. This module runs ONE LLM copy-edit per stop,
LAST — after every deterministic pass and before the conclusion and the TTS —
to repair the prose a human editor would fix in one read. It adds NO fact: the
model is told to use only what the stop already says, and the edit is then
VALIDATED by the same claim/G4 machinery LOCAL-619B used for the conclusion
(``claim_check.check_paragraph``), with the ORIGINAL stop text plus its passages
as the evidence corpus. Any new UNSUPPORTED/CONTRADICTED claim, a length move
past ±25 %, or any proper noun not already in the original → the edit is
REJECTED and the ORIGINAL stop is kept. The fallback is always the original.

Design properties:
  * PURE and injectable — ``edit_stop`` / ``edit_tour_text`` take an ``llm_fn``
    so tests never hit the network; the default ``_default_editor_llm`` is the
    one place that calls OpenAI, metered through the house ``cost_accumulator``
    exactly like ``tour_conclusion._default_thematic_llm``.
  * ONLY the body narration is rewritten. The ``Stop N:`` header, ``Address:``,
    ``Coordinates:``, the ``Orientation:`` block (listener-addressing — kept
    verbatim) and the ``Directions:`` hand-off line are preserved byte-for-byte.
  * IDEMPOTENT and no re-spend — an edited tour carries a hidden marker; a second
    pass (a cache/pool hit, a re-run) is a no-op that never calls the LLM.
  * Gated behind ``STOP_EDITOR`` (default ON locally); set ``STOP_EDITOR=0`` to
    disable entirely.
"""

from __future__ import annotations

import os
import re
from typing import Callable, Dict, List, Optional, Tuple

# ── LOCAL-651: FAST_PIPELINE overlap of the independent per-stop editor passes
# (safe no-op import; the flag defaults OFF so the serial path is unchanged).
try:
    import fast_pipeline as _fast_pipeline
except Exception:  # pragma: no cover
    _fast_pipeline = None

try:  # logging is best-effort; never let a logger import fail the pass
    import logging
    _log = logging.getLogger("stop_editor")
except Exception:  # pragma: no cover
    _log = None


# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

# The hidden idempotence marker. Appended as an HTML-style comment on its own
# line at the very end of an edited tour. It is invisible to the TTS text
# extractor (which strips/ignores such lines) and to the reader, but lets any
# later pass (cache hit, pool hit, re-run) detect "already edited" and skip,
# so the LLM is never called twice on the same tour. The marker is also stored
# with the cached/pooled text, so a tour that was edited on the fresh path is
# recognised as edited when it comes back from the cache.
EDITED_MARKER = "<!-- LOCAL-628:stop-editor:v1 -->"

# Length guard: an edit whose body moves more than this fraction away from the
# original (in characters) is rejected. The prompt asks for ±20 %; we reject
# only past ±25 % so a legitimate reorder/repair that trims filler is kept.
MAX_LENGTH_DELTA = 0.25

# ``Stop N: <title>`` header — the same shape the cache/pool layers use.
_STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)

# Lines that are STRUCTURAL metadata, preserved verbatim (never sent to the
# editor as rewritable body). A line is structural if it starts with one of
# these labels.
#
# [LOCAL-646 reg1] ``Type/Specialty:``, ``Specific Examples:``,
# ``Operational Details:`` and ``Museum Information:`` were ADDED here. The
# museum work (LOCAL-642/643) made non-museum stops carry these fields too, but
# this split-set still only knew Address/Coordinates/Orientation/Directions. A
# stop that carried a ``Type/Specialty:`` line therefore had that line — and
# EVERYTHING after it, including ``Specific Examples:``, the ``Orientation:``
# block and the narration — mis-classified as rewritable *body*. The LLM editor
# then reflowed that "body" into one run-on paragraph, producing the tour-557
# Stop-4 collapse: "Type/Specialty: … Specific Examples: … Orientation: <the
# whole narration on the Orientation line>". With these labels recognised as
# structural, each field line is preserved verbatim on its own line and only the
# true narration paragraphs (after the Orientation block) are sent to the editor.
_STRUCT_LABELS = ("Address:", "Coordinates:", "Type/Specialty:",
                  "Specific Examples:", "Operational Details:",
                  "Museum Information:", "Orientation:", "Directions:",
                  "Hours/admission source:", "Sources:")

# A proper noun for the "no new proper noun" guard: a capitalised word (optionally
# multi-word, hyphenated or with an apostrophe) that is not at the very start of a
# sentence-only context. We extract the SET of such tokens from a text and reject
# an edit that introduces one absent from the original.
_PROPER_NOUN = re.compile(
    r"\b([A-Z][a-zA-Z\u00C0-\u024F]+(?:['\u2019\-][A-Z]?[a-zA-Z\u00C0-\u024F]+)*)\b"
)

# Common sentence-initial / function words that are capitalised only because they
# begin a sentence — NOT proper nouns. Excluded from the proper-noun guard so a
# reorder that moves a different ordinary word to sentence-start is not punished.
_STOPWORDS = frozenset(w.lower() for w in (
    "The", "A", "An", "This", "That", "These", "Those", "It", "Its", "He", "She",
    "They", "Their", "His", "Her", "You", "Your", "We", "Our", "In", "On", "At",
    "By", "For", "From", "To", "With", "As", "And", "But", "Or", "Of", "After",
    "Before", "When", "While", "Here", "There", "Then", "Now", "Although",
    "Though", "Because", "Since", "Through", "During", "Within", "Across",
    "Between", "Among", "Over", "Under", "Above", "Below", "Into", "Onto",
    "Upon", "About", "Against", "Along", "Around", "Behind", "Beyond", "Near",
    "Beside", "Besides", "Despite", "Toward", "Towards", "Throughout", "Stand",
    "Standing", "Notice", "Look", "Observe", "Consider", "Imagine", "Step",
    "Move", "Walk", "Turn", "Begin", "Each", "Every", "Many", "Some", "Most",
    "Both", "Several", "Few", "One", "Two", "Three", "First", "Second", "Third",
    "What", "Which", "Who", "Whom", "Whose", "Where", "Why", "How", "If", "So",
    "Yet", "Still", "Today", "Here", "Once", "Rather", "Such", "No", "Not",
))


# ─────────────────────────────────────────────────────────────────────────────
# Gate
# ─────────────────────────────────────────────────────────────────────────────

def is_enabled() -> bool:
    """True when the editor is on. Default ON; ``STOP_EDITOR=0`` turns it off."""
    return os.environ.get("STOP_EDITOR", "1").strip() not in ("0", "false", "False", "no", "")


def already_edited(tour_text: str) -> bool:
    """True when this tour already carries the hidden edited marker."""
    return EDITED_MARKER in (tour_text or "")


# [LOCAL-630 item 7] A compiled matcher for the marker ON ITS OWN LINE, so it can
# be stripped from the DELIVERED tour_content (Michael's text view) at the final
# delivery boundary while the cache/pool copies keep it for idempotence.
_EDITED_MARKER_LINE_RE = re.compile(
    r"[ \t]*" + re.escape(EDITED_MARKER) + r"[ \t]*\n?")


def strip_marker(tour_text: str) -> str:
    """Remove the hidden idempotence marker from DELIVERED text.

    [LOCAL-630 item 7] The marker is an internal idempotence flag; it must never
    appear in the stored/delivered ``tour_content`` the user (and Michael's text
    view) reads. The cache/pool copies KEEP the marker so a reuse/re-run is still
    recognised as already-edited and never re-spends — only the copy handed to the
    delivery boundary is stripped. Idempotent; a no-op when the marker is absent.
    """
    if not tour_text or EDITED_MARKER not in tour_text:
        return tour_text or ""
    out = _EDITED_MARKER_LINE_RE.sub("", tour_text)
    return out.rstrip("\n") + ("\n" if tour_text.endswith("\n") else "")


def _mark_edited(tour_text: str) -> str:
    """Append the hidden idempotence marker if not already present."""
    if not tour_text or EDITED_MARKER in tour_text:
        return tour_text
    sep = "" if tour_text.endswith("\n") else "\n"
    return f"{tour_text}{sep}{EDITED_MARKER}\n"


# ─────────────────────────────────────────────────────────────────────────────
# Stop parsing — split a stop block into (preserved prefix, body, preserved tail)
# ─────────────────────────────────────────────────────────────────────────────

def _split_stop_block(block: str) -> Tuple[str, str, str, str]:
    """Split one stop block into (header_line, preserved_meta, body, tail_meta).

    * ``header_line``   — the ``Stop N: <title>`` line (and anything above it).
    * ``preserved_meta``— Address / Coordinates / Orientation block, verbatim.
    * ``body``          — the narration paragraph(s): the ONLY part rewritten.
    * ``tail_meta``     — the ``Directions:``/``Sources:`` lines, verbatim.

    Returns ("", "", block, "") if the block has no recognisable structure, so
    an atypical stop is still handed to the editor as pure body (safe: the
    validation and the preserve-nothing fallback still apply).
    """
    lines = (block or "").split("\n")
    # Locate the header line (Stop N:).
    header_idx = None
    for i, ln in enumerate(lines):
        if _STOP_HEADER.match(ln.strip()):
            header_idx = i
            break
    if header_idx is None:
        return ("", "", block, "")

    # Everything up to and including the header, plus the leading metadata block
    # (Address, Coordinates, Orientation) is the preserved prefix. The body is
    # the paragraphs AFTER the Orientation block and BEFORE the Directions line.
    header_line = "\n".join(lines[: header_idx + 1])

    # Walk from after the header, collecting metadata lines/paragraphs until the
    # first paragraph that is NOT a structural label — that is the body start.
    body_start = header_idx + 1
    i = header_idx + 1
    n = len(lines)
    # The Orientation value can span the rest of its paragraph (it is one logical
    # paragraph that may wrap). We keep consuming while a line either is blank, is
    # a structural label, or continues the Orientation paragraph.
    in_orientation = False
    last_meta_end = header_idx  # index of the last preserved-meta line
    while i < n:
        stripped = lines[i].strip()
        is_struct = any(stripped.startswith(lbl) for lbl in _STRUCT_LABELS)
        if stripped == "":
            i += 1
            continue
        if is_struct:
            if stripped.startswith("Orientation:"):
                in_orientation = True
                # Orientation paragraph runs until the next blank line that is
                # followed by a non-structural paragraph (the body).
                last_meta_end = i
                i += 1
                # consume the rest of the orientation paragraph (contiguous
                # non-blank lines)
                while i < n and lines[i].strip() != "":
                    last_meta_end = i
                    i += 1
                continue
            if stripped.startswith(("Directions:", "Sources:",
                                    "Hours/admission source:")):
                # Reached the tail — body is between body_start and here.
                break
            # Address / Coordinates — preserved meta before the body.
            last_meta_end = i
            i += 1
            continue
        # First non-blank, non-structural line AFTER we have seen metadata:
        # this is the body start.
        body_start = i
        break
    else:
        # Ran off the end with no body.
        preserved_meta = "\n".join(lines[header_idx + 1: last_meta_end + 1])
        return (header_line, preserved_meta, "", "")

    preserved_meta = "\n".join(lines[header_idx + 1: body_start]) \
        if body_start > header_idx + 1 else ""

    # Find the tail: the first Directions:/Sources: line at or after body_start.
    tail_start = None
    for j in range(body_start, n):
        s = lines[j].strip()
        if s.startswith(("Directions:", "Sources:", "Hours/admission source:")):
            tail_start = j
            break
    if tail_start is None:
        body = "\n".join(lines[body_start:])
        tail_meta = ""
    else:
        body = "\n".join(lines[body_start:tail_start]).rstrip("\n")
        tail_meta = "\n".join(lines[tail_start:])

    return (header_line, preserved_meta, body, tail_meta)


def _split_tour_into_stops(tour_text: str) -> List[Tuple[int, int]]:
    """Return [(start_index, end_index)] spans for each stop block in the tour.

    A stop block runs from its ``Stop N:`` header to just before the next header
    (or to the end of the text / the trailing conclusion for the last stop)."""
    heads = list(_STOP_HEADER.finditer(tour_text or ""))
    spans: List[Tuple[int, int]] = []
    for k, m in enumerate(heads):
        start = m.start()
        end = heads[k + 1].start() if k + 1 < len(heads) else len(tour_text)
        spans.append((start, end))
    return spans


# ─────────────────────────────────────────────────────────────────────────────
# The prompt
# ─────────────────────────────────────────────────────────────────────────────

_EDITOR_SYSTEM = (
    "You are a meticulous copy-editor for spoken audio-tour scripts. You repair "
    "prose that automated passes have damaged. You NEVER add a fact, date, "
    "number, name, place or claim that is not already in the text you are given. "
    "You only reorder, repair, delete, and lightly rephrase what is already there."
)

_EDITOR_PROMPT = """Copy-edit the STOP BODY below. It is spoken aloud on an audio tour. Earlier \
automated passes left it with defects: sentences out of order, broken clauses, \
dangling openers (\"As a result\", \"This move\", \"This detail\") whose cause was \
removed, dropped words, orphan one-word fragments, evasive filler, glosses jammed \
into names, and references to people who were never introduced.

Rewrite the body so a listener hears clean, coherent prose. Specifically:
- Reorder sentences into a coherent order. For history, go chronological, and \
lead with the work itself before its later story.
- Repair broken clauses and dangling openers. If an opener like \"As a result\" or \
\"This move\" has no cause in the text, either supply the cause FROM THE TEXT or \
rewrite the sentence so it stands on its own.
- Delete orphan sentence fragments and evasive filler (e.g. \"must be appreciated \
in person\").
- Do NOT let the stop END on an unpaid teaser — a closing gesture at a story the \
stop never tells (\"deeper stories\", \"hint at\", \"more to discover\", \
\"secrets\", \"beneath the calm\", \"waiting to be discovered\"). If the body \
already contains the facts that pay off such a promise, rewrite the ending to \
DELIVER that story in a concrete sentence (naming the fact, from the text). If the \
body does NOT contain those facts, DELETE the teaser sentence so the stop ends on \
something it actually told. Never leave an empty promise as the last sentence.
- Fix dropped words so every sentence is grammatical.
- Introduce a person on first mention using ONLY information already in this stop \
(e.g. if the text elsewhere says \"Archduke Ernest\", use that full form on first \
mention; if the text gives no such information, rephrase to avoid the bare name).
- Keep the same language and the same register/tone.
- Keep the length within about plus or minus 20 percent.

ABSOLUTE RULE: add NO fact, date, number, name, place or claim that is not \
already present in the body below. Do not research. Do not elaborate. If you are \
unsure whether something is supported, leave it out. When in doubt, prefer the \
original wording.

Output ONLY the rewritten body as plain prose paragraphs. No preamble, no \
headers, no labels, no quotation marks around the whole thing.

STOP TITLE: {title}

STOP BODY:
{body}
"""


def build_editor_prompt(title: str, body: str) -> str:
    """Build the user prompt for one stop. Exposed for the contract test."""
    return _EDITOR_PROMPT.format(title=(title or "").strip(), body=(body or "").strip())


# ─────────────────────────────────────────────────────────────────────────────
# The default LLM caller — the ONE place that touches the network
# ─────────────────────────────────────────────────────────────────────────────

def _default_editor_llm(prompt: str, api_key: str) -> Optional[str]:
    """One gpt-4.1 chat-completion, metered via ``cost_accumulator``. Returns the
    assistant text or None on any failure. Mirrors
    ``tour_conclusion._default_thematic_llm`` (the house metered client) so the
    OpenAI cost is folded into the per-tour accumulator exactly like every other
    LLM call."""
    if not api_key:
        return None
    import json as _json
    try:
        import requests as _req
    except Exception:
        return None
    model = os.environ.get("STOP_EDITOR_MODEL", "gpt-4.1")
    headers = {"Content-Type": "application/json",
               "Authorization": f"Bearer {api_key}"}
    data = {
        "model": model,
        "messages": [
            {"role": "system", "content": _EDITOR_SYSTEM},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.2,
        "max_tokens": 1200,
    }
    try:
        resp = _req.post("https://api.openai.com/v1/chat/completions",
                         headers=headers, data=_json.dumps(data), timeout=60)
        if resp.status_code != 200:
            return None
        j = resp.json()
        text = j["choices"][0]["message"]["content"].strip()
        # Meter the call via the tour's cost accumulator (the network meter).
        try:
            import cost_accumulator
            usage = j.get("usage", {}) or {}
            cost_accumulator.add_llm_usage(
                int(usage.get("prompt_tokens", 0) or 0),
                int(usage.get("completion_tokens", 0) or 0),
                model)
        except Exception:
            pass
        return text
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# Validation
# ─────────────────────────────────────────────────────────────────────────────

def _proper_nouns(text: str) -> set:
    """Return the set of proper-noun tokens in ``text`` (lowercased), excluding
    ordinary sentence-initial/function words."""
    out = set()
    for m in _PROPER_NOUN.finditer(text or ""):
        tok = m.group(1)
        if tok.lower() in _STOPWORDS:
            continue
        # A single all-caps-initial word that is the first token of a sentence AND
        # is an ordinary word would be filtered by _STOPWORDS; multi-word and
        # mid-sentence capitals are kept.
        out.add(tok.lower())
    return out


def _new_proper_nouns(edited: str, original: str) -> List[str]:
    """Proper nouns present in the edit but NOT in the original (case-insensitive,
    accent-insensitive on the first letter). A name the editor introduced that
    was not in the input is a fabrication and rejects the edit."""
    orig = _proper_nouns(original)
    # Also allow sub-token matches: "Ernest" is OK if original had
    # "Archduke Ernest" (the editor is told to USE the fuller form present in the
    # text). So treat the original's full token stream as the allowed vocabulary.
    orig_words = set(re.findall(r"[a-zA-Z\u00C0-\u024F]+", (original or "").lower()))
    new = []
    for tok in _proper_nouns(edited):
        if tok in orig:
            continue
        # token may be multi-word/hyphenated; accept if EVERY word part is in the
        # original word stream (a reordering/recombination of present words).
        parts = re.findall(r"[a-zA-Z\u00C0-\u024F]+", tok)
        if parts and all(p in orig_words for p in parts):
            continue
        # [LEAD 2026-10-08] An ordinary English word capitalised only because it starts a
        # sentence is not a name. "However" and "Begun" rejected good edits in Bench R4 (the
        # rejected "Begun" edit was the one that repaired "Began work on…" with no subject).
        # A token passes when it is a common lowercase dictionary word AND never appears
        # capitalised mid-sentence in the edit. Real names (Fouquart, Chabrier) are not
        # lowercase dictionary words.
        if _is_common_word(tok) and not re.search(r"[a-z,;]\s+" + re.escape(tok[:1].upper() + tok[1:]) + r"\b", edited or ""):
            continue
        new.append(tok)
    return new


_COMMON_WORDS = None


def _is_common_word(tok: str) -> bool:
    global _COMMON_WORDS
    if _COMMON_WORDS is None:
        try:
            import json as _j
            _COMMON_WORDS = frozenset(_j.load(open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "editor_common_words.json"))))
        except Exception:
            _COMMON_WORDS = frozenset()
    return (tok or "").lower() in _COMMON_WORDS


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-634] Dropped-word detection & repair
# ─────────────────────────────────────────────────────────────────────────────
#
# The deterministic splice/removal passes that run before the editor can delete a
# word from the MIDDLE of a sentence and leave the surrounding tokens stitched
# into an ungrammatical shape. Bench R1 showed two concrete shapes:
#
#   * tour 505: "Gris, working in Paris at the outbreak of was at a crossroads"
#       — the NOUN after a preposition ("the outbreak of WAR") was removed, so a
#       preposition is immediately followed by a finite verb / another preposition.
#   * tour 495: "This painting w. Velázquez, the leading painter…"
#       — a word was truncated to a bare one/two-letter fragment followed by a
#       period ("w."), an orphan initial that is not a real abbreviation.
#
# These patterns are deterministic to DETECT. The editor's job is to repair them;
# this module both (a) REJECTS an edit whose body still contains one (so the LLM
# copy-edit cannot ship the defect), and (b) applies a conservative deterministic
# repair as a last resort, so a stop whose LLM edit was rejected (or where the
# editor is off) still does not ship the raw dropped-word prose.

# A preposition / article immediately followed by a finite verb or another
# preposition, with no noun phrase between them: "the outbreak of was",
# "at the end of became", "with the of". The removed head noun left a hole.
_DANGLING_PREP_VERBS = (
    "was", "were", "is", "are", "has", "had", "have", "became", "would",
    "will", "could", "should", "began", "stood", "sat", "came", "went",
    "remained", "seemed", "appeared",
)
_DROPPED_PREP_RE = re.compile(
    r"(?i)\b(?:of|at|in|on|for|from|to|with|by|the|a|an)\s+(?:" +
    "|".join(_DANGLING_PREP_VERBS) + r")\b")

# A bare truncated-word fragment: a lone 1–2 letter token ending in a period that
# is NOT a legitimate abbreviation/initial. A real initial ("J. Arrowsmith") is a
# single UPPERCASE letter followed by a Capitalised surname; a real abbreviation
# ("St.", "Mt.") is on an allow-list. A dropped word is a LOWERCASE 1–2 letter
# fragment ("painting w. Velázquez"), or a single capital not followed by a
# capitalised word.
_ALLOWED_SHORT_ABBREV = frozenset((
    "st", "mt", "dr", "mr", "ms", "jr", "sr", "no", "ca", "cf", "vs", "pp",
    "ed", "al", "op", "ft", "in", "cm", "mm", "km",
))
# Match a lone 1–2 letter token + period, capturing the token and whether a
# capitalised word follows (an initial) for the discriminator in the helper.
_DROPPED_FRAGMENT_RE = re.compile(
    r"(?<![A-Za-z.])\b([A-Za-z]{1,2})\.(\s+)([A-Za-z]*)")


def _dropped_fragment_hits(text: str) -> List[str]:
    hits = []
    for m in _DROPPED_FRAGMENT_RE.finditer(text or ""):
        tok = m.group(1)
        follow = m.group(3) or ""
        if tok.lower() in _ALLOWED_SHORT_ABBREV:
            continue
        # A real initial is a SINGLE uppercase letter followed by a Capitalised
        # surname ("J. Arrowsmith"). Keep it.
        if len(tok) == 1 and tok.isupper() and follow[:1].isupper():
            continue
        hits.append(tok + ".")
    return hits


def detect_dropped_word(text: str) -> Optional[str]:
    """Return a short description of the FIRST dropped-word defect in ``text``,
    or None when the text is clean. Deterministic; no network.

    Two shapes (both seen in Bench R1):
      * a preposition/article immediately followed by a finite verb (a removed
        head noun: "the outbreak of was");
      * a bare 1–2 letter truncated-word fragment ("painting w. Velázquez").
    """
    if not text:
        return None
    m = _DROPPED_PREP_RE.search(text)
    if m:
        return f"dangling preposition before verb: '{m.group(0).strip()}'"
    frags = _dropped_fragment_hits(text)
    if frags:
        return f"truncated word fragment: '{frags[0]}'"
    return None


def repair_dropped_words(text: str) -> Tuple[str, int]:
    """Conservatively repair dropped-word shapes in ``text`` WITHOUT inventing a
    word. Returns ``(repaired, n_repaired)``.

    The only grammatical repair that adds no fact is to DELETE the broken clause
    and rejoin the sentence, because the removed word cannot be recovered. We do
    this at the sentence granularity: a sentence that still matches a dropped-word
    pattern after a light in-place fix is dropped, so the stop ships clean prose
    rather than a visible hole. Deterministic; adds no new word, number or name.
    """
    if not text:
        return text or "", 0
    # In-place fix for the truncated fragment shape: the orphan 1–2 letter token
    # plus its period is simply removed ("painting w. Velázquez" → "painting
    # Velázquez"), because the fragment carries no recoverable content and the
    # surrounding words are already present and correct.
    def _strip_frag(m: "re.Match") -> str:
        tok = m.group(1)
        ws = m.group(2) or " "
        follow = m.group(3) or ""
        if tok.lower() in _ALLOWED_SHORT_ABBREV:
            return m.group(0)
        if len(tok) == 1 and tok.isupper() and follow[:1].isupper():
            return m.group(0)  # a real initial — keep
        return ws + follow  # drop the orphan fragment + its period, keep spacing
    repaired = _DROPPED_FRAGMENT_RE.sub(_strip_frag, text)
    repaired = re.sub(r"\s{2,}", " ", repaired)

    # The dangling-preposition shape ("the outbreak of was at a crossroads") has
    # a hole that cannot be filled without inventing the missing noun. Drop the
    # whole sentence rather than ship the hole or guess the word.
    n = 0
    out_paras = []
    for para in re.split(r"\n{2,}", repaired):
        try:
            from sentence_split import split_sentences as _ss
            sents = _ss(para)
        except Exception:
            sents = [s.strip() for s in re.split(r"(?<=[.!?])\s+", para.strip())
                     if s.strip()]
        if not sents:
            out_paras.append(para)
            continue
        kept = []
        for s in sents:
            if _DROPPED_PREP_RE.search(s):
                n += 1
                continue
            kept.append(s)
        out_paras.append(" ".join(kept).strip())
    repaired = "\n\n".join(p for p in out_paras if p.strip()).strip()
    # Count the fragment removals too.
    n += len(_dropped_fragment_hits(text))
    return repaired, n


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-635] Broken sentence-join detection & repair
# ─────────────────────────────────────────────────────────────────────────────
#
# A removal/splice pass can delete the OBJECT of a clause and then stitch the
# surviving lead-in straight onto the NEXT sentence without a terminator, so a
# lowercase word runs directly into a capitalised sentence-starter. Bench R2,
# Tate Modern 515, Stop 2:
#
#   "…affected by the Spanish Civil War and the tragedies surrounding During
#    this time, he created a series…"
#
# "the tragedies surrounding" lost its object and "During this time, he created"
# — a new sentence — was concatenated with only a space. A listener hears a hard
# glitch. This is the D638 ``lowercase_sentence_join`` detector's shape:
#   lowercase word (3+ letters) + SPACE + {During|After|Before|In|The|This|When}
#   + space + lowercase.
#
# The repair invents no text: the capitalised word begins a real sentence, so we
# cut the orphaned lead-in back to the previous sentence boundary (or clause
# comma/'and'), terminate it with a period, and let the capitalised word start
# its own sentence. "…the Spanish Civil War and the tragedies surrounding During
# this time, he created…" → "…the Spanish Civil War. During this time, he
# created…". Deterministic; adds no new word, number or name.

# Capitalised words that legitimately begin a new sentence (the detector's set).
_JOIN_SENTENCE_STARTERS = ("During", "After", "Before", "In", "The", "This", "When")
_BROKEN_JOIN_RE = re.compile(
    r"\b([a-z]{3,})\s+(" + "|".join(_JOIN_SENTENCE_STARTERS) + r")\s+([a-z])")

# Dangling clause lead-ins: a trailing conjunction/participle fragment left when
# the clause object was removed. We cut the SHORTEST such trailing fragment (from
# the LAST boundary before the break) so the surviving sentence keeps as much
# real content as possible. The participle group ("surrounding", "including", …)
# is what typically lost its object; a trailing bare "and/with/of …" clause is
# cut only when it is short (no finite verb), never a whole fact-bearing clause.
_DANGLING_LEADIN_RE = re.compile(
    r"(?i)\s+(?:surrounding|including|featuring|involving|regarding|concerning|"
    r"amid|amidst|during|through|via)\s+[a-z][\w'’-]*(?:\s+[a-z][\w'’-]*){0,3}$"
    r"|\s+(?:and|but|or|with)\s+the\s+[a-z][\w'’-]*(?:\s+[a-z][\w'’-]*){0,3}$")


def detect_broken_join(text: str) -> Optional[str]:
    """Return a short description of the FIRST broken sentence-join in ``text``
    (a lowercase word running straight into a capitalised sentence-starter), or
    None when clean. Deterministic; mirrors the D638 lowercase_sentence_join
    detector."""
    if not text:
        return None
    m = _BROKEN_JOIN_RE.search(text)
    if m:
        return f"broken sentence join: '{m.group(1)} {m.group(2)} {m.group(3)}…'"
    return None


def repair_broken_joins(text: str) -> Tuple[str, int]:
    """Repair every broken sentence-join in ``text`` WITHOUT inventing a word.

    For each "<lowercase> <Starter> <lowercase>" break: the <Starter> begins a
    genuine new sentence, so we (a) trim the dangling clause lead-in that lost
    its object back to its boundary (comma / conjunction / participle), (b) add a
    sentence-terminating period, and (c) let the <Starter> word open its own
    sentence. If no clear lead-in boundary is found, we simply insert a period
    before the <Starter> (split the run in two) rather than drop content.
    Returns ``(repaired, n_repaired)``. Deterministic; adds no new token.
    """
    if not text:
        return text or "", 0
    n = 0
    out = text
    # Iterate until no broken join remains (guard against pathological loops).
    for _ in range(20):
        m = _BROKEN_JOIN_RE.search(out)
        if not m:
            break
        n += 1
        # Position of the capitalised starter word.
        starter_start = m.start(2)
        before = out[:starter_start]
        after = out[starter_start:]
        # Trim a dangling clause lead-in from the END of `before` ("… and the
        # tragedies surrounding " → "…"). Keep the preceding complete clause.
        trimmed = _DANGLING_LEADIN_RE.sub("", before.rstrip())
        trimmed = trimmed.rstrip()
        if not trimmed or not re.search(r"[A-Za-z0-9]", trimmed):
            # Nothing solid before the break — fall back to a bare split so we
            # never drop the whole lead; terminate the lowercase run.
            trimmed = before.rstrip().rstrip(",;:")
        # Ensure a terminator between the two sentences.
        if not trimmed.endswith((".", "!", "?")):
            trimmed = trimmed + "."
        out = trimmed + " " + after
    out = re.sub(r"\s{2,}", " ", out).strip()
    return out, n


def repair_dropped_words_and_joins(text: str) -> Tuple[str, int]:
    """Convenience: run both the dropped-word and the broken-join repairs. Used
    by the text-level delivery guard. Returns ``(repaired, total_fixed)``."""
    r1, n1 = repair_dropped_words(text)
    r2, n2 = repair_broken_joins(r1)
    return r2, (n1 + n2)


def repair_broken_joins_in_text(tour_text: str) -> Tuple[str, int]:
    """[LOCAL-635] Text-level broken-join guard for the normal delivery path.
    Repairs each stop body's prose (header/field lines preserved verbatim) so no
    tour ships a lowercase→Capital sentence collision. Returns
    ``(cleaned_text, n_repaired)``."""
    if not tour_text:
        return tour_text or "", 0
    total = 0
    out_lines: List[str] = []
    for raw in tour_text.split("\n"):
        stripped = raw.strip()
        if (not stripped
                or re.match(r'(?i)^Stop\s+\d+:\s', stripped)
                or re.match(r'(?i)^(?:Address|Coordinates|Directions|Sources|'
                            r'Museum Information|Type/Specialty|Specific Examples|'
                            r'Operational Details):', stripped)):
            out_lines.append(raw)
            continue
        if detect_broken_join(raw):
            repaired, k = repair_broken_joins(raw)
            total += k
            out_lines.append(repaired)
        else:
            out_lines.append(raw)
    return "\n".join(out_lines), total


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-635] Empty title-quote detection & fill
# ─────────────────────────────────────────────────────────────────────────────
#
# A title-substitution step can replace a work-title placeholder with an EMPTY
# string, leaving a bare quotation pair in the prose. Bench R2, Courtauld 485,
# Stop 2:
#
#   "Yet in “ ” the domestic replaces the maritime…"
#
# The work is *Young Woman Powdering Herself*; the title slot blanked out. A
# listener hears "Yet in … the domestic replaces" — a dropped title. The fix:
# never emit an empty quote. Fill the empty pair with the STOP's own title (the
# only grounded value available on the delivery path); if no title is known,
# collapse the empty quotes and surrounding spaces so no blank pair is spoken.
# Deterministic; the only text added is the stop's own title.

# An empty (or whitespace-only) quotation pair: straight, curly, or single.
_EMPTY_QUOTES_RE = re.compile(r'("\s*"|“\s*”|‘\s*’|\'\s*\')')


def detect_empty_title_quotes(text: str) -> bool:
    """True when ``text`` contains an empty/whitespace-only quotation pair (the
    D638 ``empty_title_quotes`` shape). Deterministic."""
    return bool(_EMPTY_QUOTES_RE.search(text or ""))


def fill_empty_title_quotes(text: str, title: str) -> Tuple[str, int]:
    """Replace every empty quotation pair in ``text`` with ``title`` (quoted), or
    — when ``title`` is empty — remove the blank pair and tidy spacing. Returns
    ``(filled, n_filled)``. Deterministic; adds only the supplied stop title."""
    if not text:
        return text or "", 0
    t = (title or "").strip().strip('"“”‘’\'').strip()
    n = 0

    def _sub(m: "re.Match") -> str:
        nonlocal n
        n += 1
        quote = m.group(1)
        if not t:
            return ""  # no title available — drop the blank pair entirely
        # Preserve the quote style that was used (curly vs straight).
        if quote.startswith("“"):
            return f"“{t}”"
        if quote.startswith("‘"):
            return f"‘{t}’"
        return f'"{t}"'

    out = _EMPTY_QUOTES_RE.sub(_sub, text)
    # Tidy doubled spaces / space-before-punct left by an empty removal.
    out = re.sub(r"\s{2,}", " ", out)
    out = re.sub(r"\s+([,.;:!?])", r"\1", out)
    return out, n


def fill_empty_title_quotes_in_text(tour_text: str) -> Tuple[str, int]:
    """[LOCAL-635] Text-level guard: fill any empty title quote in a stop body
    with that stop's title (from its Stop header). Header/field lines preserved.
    Returns ``(cleaned_text, n_filled)``. No empty quotes ever reach narration."""
    if not tour_text:
        return tour_text or "", 0
    total = 0
    current_title = ""
    out_lines: List[str] = []
    for raw in tour_text.split("\n"):
        stripped = raw.strip()
        hm = re.match(r'(?i)^Stop\s+\d+:\s*(.+?)\s*$', stripped)
        if hm:
            current_title = hm.group(1).strip()
            out_lines.append(raw)
            continue
        if (not stripped
                or re.match(r'(?i)^(?:Address|Coordinates|Directions|Sources|'
                            r'Museum Information|Type/Specialty|Specific Examples|'
                            r'Operational Details):', stripped)):
            out_lines.append(raw)
            continue
        if detect_empty_title_quotes(raw):
            filled, k = fill_empty_title_quotes(raw, current_title)
            total += k
            out_lines.append(filled)
        else:
            out_lines.append(raw)
    return "\n".join(out_lines), total


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-635] Garbled / truncated person-name detection & repair
# ─────────────────────────────────────────────────────────────────────────────
#
# A pass that strips a leading clause word and recapitalises the next token can
# EAT the start of a name: "Andrea Mantegna" → "Rea Mantegna" (the leading "And"
# of "Andrea" removed, "rea" recapitalised to "Rea"). Bench R2, Brera 513, Stop
# 1 opens "Rea Mantegna painted…" while the header and the rest of the stop say
# "Andrea Mantegna". A listener hears a famous name mangled on the opening line.
#
# The editor's contract (Michael): "reject an output in which a person's name
# differs from EVERY name in its input sources." We implement that as:
#   * a given-name form "<Y> <Surname>" is GARBLED when the same stop/sources
#     also contain a longer canonical "<X> <Surname>" whose given name X ENDS
#     with Y (a truncation: "Rea" is a tail of "Andrea") and X != Y;
#   * the garbled form is repaired to the canonical "<X> <Surname>" (invents no
#     text — the canonical form is already present), and
#   * validate_edit REJECTS an edit that introduces a name whose words match no
#     source name (the existing _new_proper_nouns gate), extended here to also
#     reject a truncated given-name variant of a source name.

# "<Given> <Surname>" where both are capitalised words (allow accented letters).
_NAME_PAIR_RE = re.compile(
    r"\b([A-Z\u00C0-\u017F][a-z\u00C0-\u017F]+)\s+"
    r"([A-Z\u00C0-\u017F][a-z\u00C0-\u017F]+)\b")


def _canonical_given_names(text: str) -> Dict[str, str]:
    """Map surname → the LONGEST given-name form seen with it in ``text``. Used to
    recognise a truncated given name ("Rea" vs canonical "Andrea") for the same
    surname."""
    by_surname: Dict[str, str] = {}
    for m in _NAME_PAIR_RE.finditer(text or ""):
        given, surname = m.group(1), m.group(2)
        if given.lower() in _STOPWORDS or surname.lower() in _STOPWORDS:
            continue
        cur = by_surname.get(surname)
        if cur is None or len(given) > len(cur):
            by_surname[surname] = given
    return by_surname


def _garbled_name_pairs(text: str, canonical: Optional[Dict[str, str]] = None
                        ) -> List[Tuple[str, str]]:
    """Return [(garbled "Y Surname", canonical "X Surname")] where Y is a strict
    truncated tail of a longer canonical given name X for the same surname.
    ``canonical`` defaults to the longest forms found in ``text`` itself."""
    canon = canonical if canonical is not None else _canonical_given_names(text)
    out: List[Tuple[str, str]] = []
    seen: set = set()
    for m in _NAME_PAIR_RE.finditer(text or ""):
        given, surname = m.group(1), m.group(2)
        if given.lower() in _STOPWORDS or surname.lower() in _STOPWORDS:
            continue
        full = canon.get(surname)
        if not full or full == given:
            continue
        # Y is a truncation of X when X ends with Y (case-insensitive) and is
        # strictly longer: "Andrea".endswith("rea") → "Rea" is garbled.
        if (len(given) < len(full)
                and full.lower().endswith(given.lower())):
            key = (given, surname)
            if key not in seen:
                seen.add(key)
                out.append((f"{given} {surname}", f"{full} {surname}"))
    return out


def detect_garbled_name(text: str, canonical: Optional[Dict[str, str]] = None
                        ) -> Optional[str]:
    """Return the first garbled name ("Y Surname") in ``text`` (a truncated
    given-name variant of a canonical source name), or None when clean."""
    pairs = _garbled_name_pairs(text, canonical)
    return pairs[0][0] if pairs else None


def repair_garbled_names(text: str, canonical: Optional[Dict[str, str]] = None
                         ) -> Tuple[str, int]:
    """Replace every truncated given-name variant with its canonical full form.
    Returns ``(repaired, n_repaired)``. Deterministic; the replacement form is
    already present in the text (invents nothing)."""
    if not text:
        return text or "", 0
    pairs = _garbled_name_pairs(text, canonical)
    out = text
    n = 0
    for garbled, full in pairs:
        new = re.sub(r"\b" + re.escape(garbled) + r"\b", full, out)
        if new != out:
            n += 1
            out = new
    return out, n


def repair_garbled_names_in_text(tour_text: str) -> Tuple[str, int]:
    """[LOCAL-635] Text-level garbled-name guard for the delivery path. Canonical
    given-name forms are derived from the WHOLE tour (header titles + bodies), so
    a corrupted first mention is repaired to the full form seen elsewhere. Header
    and field lines are left untouched EXCEPT a garbled name in a header is also
    repaired. Returns ``(cleaned_text, n_repaired)``."""
    if not tour_text:
        return tour_text or "", 0
    canonical = _canonical_given_names(tour_text)
    if not canonical:
        return tour_text, 0
    repaired, n = repair_garbled_names(tour_text, canonical)
    return repaired, n


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-638 Note 2] A stop must not END on an unpaid teaser
# ─────────────────────────────────────────────────────────────────────────────
#
# Michael listened to Frick tour 523 (D640):
#   "It ends with 'unexpected details hint at the deeper stories beneath the
#    calm'; I wish it says something about these deeper stories."
#
# A stop must not end on an unpaid teaser — a closing gesture at a story the stop
# never tells ("deeper stories", "hint at", "more to discover", "secrets",
# "waiting to be discovered", "beneath the surface"). The editor must either
# DELIVER the story the teaser points to (from the stop's own sources — the prompt
# asks for this) or DROP the teaser. The deterministic fallback below DROPS the
# trailing teaser sentence when the LLM has not delivered a concrete story, so the
# stop never ends on an empty promise.

# Teaser cue phrases: a vague gesture at an untold story.
_TEASER_CUE_RE = re.compile(
    r"(?i)\b("
    r"deeper\s+stor(?:y|ies)|hint(?:s|ing|ed)?\s+at\b|hints?\s+of\b|"
    r"more\s+to\s+(?:discover|explore|uncover|be\s+(?:discovered|found|told))|"
    r"secrets?\b|untold\s+stor|stor(?:y|ies)\s+(?:yet\s+)?to\s+be\s+told|"
    r"waiting\s+to\s+be\s+(?:discovered|uncovered|told|found)|"
    r"beneath\s+the\s+(?:surface|calm|stillness|quiet)|"
    r"mysteries?\s+(?:that|which|waiting|yet)|hidden\s+(?:stor|depths|meanings?)|"
    r"so\s+much\s+more\s+(?:to|than)|whispers?\s+of\b|"
    r"layers?\s+(?:of\s+(?:meaning|story|history)\s+)?(?:yet\s+)?to\s+(?:uncover|reveal)"
    r")\b")

# A concrete follow-through marker: the sentence is NOT a bare teaser because it
# states a specific noun/fact (a name, a year, a place) — it DELIVERS rather than
# merely gestures. Used to spare a sentence that happens to contain "secrets" but
# actually tells one ("the secret compartment held a 1527 letter from More").
# NOTE: the proper-name branch is CASE-SENSITIVE (no (?i)) so a sentence-initial
# "Its unexpected" is not mistaken for a two-word proper name.
_CONCRETE_PAYOFF_YEAR_RE = re.compile(r"\b\d{3,4}\b")
_CONCRETE_PAYOFF_NAME_RE = re.compile(r"\b[A-Z][a-z]{2,}\s+[A-Z][a-z]{2,}")
_CONCRETE_PAYOFF_CAUSE_RE = re.compile(
    r"(?i)\b(because|when|after|during|which\s+(?:is|was|shows|depicts|holds|held)|"
    r"executed|killed|died|destroyed|stolen|burned|exiled|imprisoned|beheaded|"
    r"so\s+that|resulted\s+in|led\s+to)\b")


def _has_concrete_payoff(text: str) -> bool:
    """True when ``text`` carries a concrete fact (a year, a two-word proper name,
    or a cause/consequence verb) — i.e. it DELIVERS, not merely gestures. Pure."""
    t = text or ""
    return bool(_CONCRETE_PAYOFF_YEAR_RE.search(t)
                or _CONCRETE_PAYOFF_NAME_RE.search(t)
                or _CONCRETE_PAYOFF_CAUSE_RE.search(t))


def _sentences_for_teaser(body: str) -> List[str]:
    """Split a stop body into sentences for the teaser check (keeps punctuation)."""
    if not body:
        return []
    return [m.group(0).strip()
            for m in re.finditer(r"[^.!?]*[.!?]+(?=\s|$)|[^.!?]+$", body)
            if m.group(0).strip()]


def ends_on_unpaid_teaser(body: str) -> bool:
    """[LOCAL-638 Note 2] True when the LAST sentence of ``body`` is an UNPAID
    teaser: it gestures at an untold story ("hint at the deeper stories beneath
    the calm") without delivering a concrete fact. A teaser sentence that actually
    pays off (names a year, a person, or a cause/consequence) is NOT flagged.
    Pure, deterministic."""
    sents = _sentences_for_teaser(body)
    if not sents:
        return False
    last = sents[-1]
    if not _TEASER_CUE_RE.search(last):
        return False
    # A teaser that delivers a concrete payoff IN THE SAME sentence is kept.
    # Strip the teaser clause itself before testing for a concrete payoff so the
    # proper-name test does not pass on words inside the teaser phrase.
    without_cue = _TEASER_CUE_RE.sub(" ", last)
    if _has_concrete_payoff(without_cue):
        return False
    return True


def drop_unpaid_teaser(body: str) -> Tuple[str, bool]:
    """[LOCAL-638 Note 2] Drop a trailing UNPAID teaser sentence from ``body``.

    Returns ``(new_body, dropped)``. Removes ONLY the final sentence, and only when
    it is an unpaid teaser (``ends_on_unpaid_teaser``). Deterministic, pure,
    idempotent; never touches a sentence that delivers a concrete story."""
    if not ends_on_unpaid_teaser(body):
        return body, False
    sents = _sentences_for_teaser(body)
    kept = sents[:-1]
    new_body = " ".join(s.strip() for s in kept).strip()
    new_body = re.sub(r"\s{2,}", " ", new_body)
    return new_body, True


def _teaser_delivered_by_edit(edited_body: str) -> bool:
    """True when the editor's rewrite ends on a teaser that it ALSO delivered (the
    final sentence pays off with a concrete fact). Used so an LLM edit that turned
    the empty promise into a real story is accepted, not dropped."""
    return bool(edited_body) and not ends_on_unpaid_teaser(edited_body)


def strip_unpaid_teaser_in_text(tour_text: str) -> Tuple[str, int]:
    """[LOCAL-638 Note 2] Text-level guard for EVERY delivery path: drop a trailing
    unpaid-teaser sentence from each stop body (the stop editor is disabled on
    cache/pool/by-reference paths, so this is the universal fallback).

    A stop body is the narration between its Orientation/field block and its
    Directions/Sources tail. Only the body's final sentence is considered, and only
    when it is an unpaid teaser. The teaser is dropped; a transition line that
    follows (the Directions tail) is preserved. Returns ``(cleaned, n_dropped)``.
    Deterministic, pure, idempotent."""
    if not tour_text:
        return tour_text or "", 0
    spans = _split_tour_into_stops(tour_text)
    if not spans:
        return tour_text, 0
    out = tour_text
    dropped = 0
    # A trailing conclusion/recap that may live inside the LAST stop's body span.
    _concl_re = re.compile(
        r"(?is)(\bThat['\u2019]s\s+\d+\s+stops?\b.*|"
        r"On this tour you have followed the thread\b.*|"
        r"From\s+.+?\s+to\s+.+?,\s+you have followed the thread\b.*|"
        r"^\s*Sources:\s.*)\Z")
    # Walk back-to-front so span offsets stay valid as we rewrite blocks.
    for (start, end) in reversed(spans):
        block = out[start:end]
        header_line, preserved_meta, body, tail_meta = _split_stop_block(block)
        if not (body or "").strip():
            continue
        # Protect a trailing conclusion/recap/Sources that landed in this body (it
        # happens on the LAST stop, whose span runs to end of text). Split it off,
        # run the teaser check on the real narration, then re-attach it verbatim.
        concl = ""
        m_concl = _concl_re.search(body)
        if m_concl:
            concl = body[m_concl.start():]
            narration = body[:m_concl.start()].rstrip()
        else:
            narration = body
        if not narration.strip():
            continue
        new_narration, did = drop_unpaid_teaser(narration)
        if not did or not new_narration.strip():
            continue
        new_body = new_narration
        if concl:
            new_body = new_narration.rstrip() + "\n\n" + concl.lstrip()
        new_block = _reassemble_block(block, header_line, preserved_meta,
                                      new_body, tail_meta)
        out = out[:start] + new_block + out[end:]
        dropped += 1
    return out, dropped


def validate_edit(
    edited_body: str,
    original_body: str,
    *,
    stop_title: str = "",
    venue_name: str = "",
    passages: Optional[List[str]] = None,
) -> Tuple[bool, str]:
    """Return (ok, reason). The edit is accepted only when ALL hold:

      * it is non-empty;
      * its length is within ±25 % of the original body;
      * it introduces no proper noun absent from the original body;
      * it contains NO dropped-word pattern (a removed-mid-sentence word that
        left a dangling preposition or a truncated fragment) — [LOCAL-634];
      * ``claim_check.check_paragraph`` finds NO new UNSUPPORTED/CONTRADICTED
        claim against the ORIGINAL body (+ any passages) as the evidence corpus —
        the same gate LOCAL-619B uses for the conclusion.

    On any failure the reason names the first failing check, for the log line.
    """
    e = (edited_body or "").strip()
    o = (original_body or "").strip()
    if not e:
        return (False, "empty")

    # Length guard (characters).
    if o:
        delta = abs(len(e) - len(o)) / max(1, len(o))
        if delta > MAX_LENGTH_DELTA:
            pct = int(round(delta * 100))
            sign = "+" if len(e) > len(o) else "-"
            return (False, f"length {sign}{pct}%")

    # Proper-noun guard.
    new_names = _new_proper_nouns(e, o)
    if new_names:
        return (False, f"new proper noun: {new_names[0]}")

    # [LOCAL-635] Garbled-name guard. Reject an edit in which a person's name is
    # a truncated variant that differs from every name in the INPUT SOURCES (the
    # original body + any research passages). Canonical given-name forms come
    # from the sources; a stop body that opens "Rea Mantegna" while the sources
    # say "Andrea Mantegna" is rejected so the original/repaired name ships.
    _src = o
    if passages:
        _src = o + "\n" + "\n".join(p for p in passages if p and p.strip())
    _canon = _canonical_given_names(_src)
    garbled = detect_garbled_name(e, _canon)
    if garbled:
        return (False, f"garbled name: {garbled}")

    # [LOCAL-634] Dropped-word guard. An edit that STILL contains a dropped-word
    # pattern (the editor was asked to repair these; an output that keeps one is
    # a failed edit) is REJECTED so the original — or the deterministic repair in
    # edit_stop — ships instead of the visible hole.
    dropped = detect_dropped_word(e)
    if dropped:
        return (False, f"dropped word: {dropped}")

    # [LOCAL-635] Broken sentence-join guard. An edit that still runs a lowercase
    # word straight into a capitalised sentence-starter ("…surrounding During
    # this time…") is a hard glitch; REJECT so the original/deterministic repair
    # ships instead.
    bj = detect_broken_join(e)
    if bj:
        return (False, f"broken join: {bj}")

    # [LOCAL-635] Empty title-quote guard. An edit that speaks a blank quotation
    # pair ("Yet in “ ” the domestic…") dropped a work title; REJECT so the
    # original/deterministic fill ships the stop title instead of blank quotes.
    if detect_empty_title_quotes(e):
        return (False, "empty title quotes")

    # Claim/G4 guard — ORIGINAL body (+ passages) is the evidence corpus.
    try:
        import claim_check
        corpus = [o]
        if passages:
            corpus.extend(p for p in passages if p and p.strip())
        result = claim_check.check_paragraph(
            e, stop_title=(stop_title or ""), venue_name=(venue_name or ""),
            passages=corpus, other_stop_passages=None)
        vc = result.get("verdict_counts", {}) or {}
        bad = int(vc.get("unsupported", 0)) + int(vc.get("contradicted", 0))
        if bad > 0:
            return (False, f"claim_check unsupported={vc.get('unsupported', 0)} "
                           f"contradicted={vc.get('contradicted', 0)}")
    except Exception as exc:  # pragma: no cover
        # If the checker cannot run, be conservative and REJECT the edit so the
        # original (always-safe) body ships — exactly LOCAL-619B's posture.
        return (False, f"claim_check error: {type(exc).__name__}")

    return (True, "ok")


# ─────────────────────────────────────────────────────────────────────────────
# Per-stop edit
# ─────────────────────────────────────────────────────────────────────────────

def edit_stop(
    stop_block: str,
    *,
    stop_number: int = 0,
    venue_name: str = "",
    passages: Optional[List[str]] = None,
    llm_fn: Optional[Callable[[str, str], Optional[str]]] = None,
    api_key: Optional[str] = None,
    log: Optional[Callable[[str], None]] = None,
) -> Tuple[str, bool, str]:
    """Edit ONE stop block. Returns (new_block, edited_flag, reason).

    The body narration is rewritten by the LLM, then validated; on any rejection
    the ORIGINAL block is returned unchanged (edited_flag=False). The header,
    Address/Coordinates/Orientation and Directions are always preserved.
    """
    api_key = api_key if api_key is not None else os.environ.get("OPENAI_API_KEY", "")
    fn = llm_fn or _default_editor_llm

    header_line, preserved_meta, body, tail_meta = _split_stop_block(stop_block)
    title = ""
    m = _STOP_HEADER.search(header_line or stop_block)
    if m:
        title = m.group(2).strip()

    if not (body or "").strip():
        return (stop_block, False, "no body")

    # [LOCAL-640] Fabricated single-name creator guard. Before the LLM edit, drop
    # any sentence in the BODY that introduces a single-surname creator ("composer
    # Losonczy created a musical piece …") whose surname is in NONE of the stop's
    # external sources (the ``passages`` corpus). Pinakothek der Moderne (tour 533)
    # shipped exactly that: a composer who does not exist, named only by a bare
    # surname, so the multi-word prose-entity gate never saw it and the stop was
    # not exhibition-scoped. This runs on EVERY stop body, is deterministic, adds
    # no text, and only ever DROPS when a non-empty corpus proves the name absent
    # (empty corpus → no drop, matching the grounding chain's false-rejection
    # posture). The cleaned body becomes the baseline the LLM edits AND the
    # fallback that ships on every rejection path below (via _fab_fallback_block),
    # so the fabricated name never reaches the listener even when the edit is
    # rejected.
    _fab_removed = False
    _fab_fallback_block = stop_block
    if passages:
        try:
            from prose_entity_grounding_gate import strip_fabricated_single_names
            _cleaned_body, _fab_dropped = strip_fabricated_single_names(
                body, list(passages))
            if _fab_dropped and _cleaned_body.strip():
                if log:
                    for _d in _fab_dropped:
                        log(f"[LOCAL-640] stop {stop_number}: dropped fabricated "
                            f"name '{_d['surname']}' ({_d['trigger']}): "
                            f"\"{_d['sentence'][:80]}\"")
                body = _cleaned_body
                _fab_removed = True
                _fab_fallback_block = _reassemble_block(
                    stop_block, header_line, preserved_meta, body, tail_meta)
        except Exception as _fab_err:  # pragma: no cover
            if log:
                log(f"[LOCAL-640] stop {stop_number}: fabricated-name guard "
                    f"skipped ({type(_fab_err).__name__})")

    if not (body or "").strip():
        # The fabrication removal emptied the body — ship the original block
        # rather than an empty stop (another gate owns a now-empty stop).
        return (stop_block, False, "body empty after fabricated-name strip")

    prompt = build_editor_prompt(title, body)
    try:
        edited_body = fn(prompt, api_key)
    except Exception as exc:
        edited_body = None
        reason = f"llm error: {type(exc).__name__}"
        if log:
            log(f"[LOCAL-628] stop {stop_number}: rejected({reason})")
        return (_fab_fallback_block, _fab_removed,
                "fabricated-name-stripped" if _fab_removed else reason)

    edited_body = (edited_body or "").strip().strip('"').strip()
    if not edited_body:
        reason = "empty llm output"
        # [LOCAL-634] Even with no usable LLM edit, do not ship a dropped-word
        # hole: apply the deterministic repair to the original body.
        if detect_dropped_word(body):
            repaired_body, n_fixed = repair_dropped_words(body)
            if (n_fixed > 0 and repaired_body.strip()
                    and not detect_dropped_word(repaired_body)):
                ok0, _r0 = validate_edit(
                    repaired_body, body, stop_title=title,
                    venue_name=venue_name, passages=passages)
                if ok0:
                    new_block = _reassemble_block(
                        stop_block, header_line, preserved_meta,
                        repaired_body, tail_meta)
                    if log:
                        log(f"[LOCAL-628] stop {stop_number}: dropped-word "
                            f"repaired deterministically ({n_fixed} fixed; "
                            f"no LLM edit)")
                    return (new_block, True, "dropped-word-repaired")
        # [LOCAL-638 Note 2] No usable LLM edit → original ships. If the original
        # ends on an unpaid teaser, drop it deterministically. Removing a sentence
        # introduces no new claim, so no claim_check re-validation is needed.
        if ends_on_unpaid_teaser(body):
            _cand0, _did0 = drop_unpaid_teaser(body)
            if _did0 and _cand0.strip():
                new_block = _reassemble_block(
                    stop_block, header_line, preserved_meta, _cand0, tail_meta)
                if log:
                    log(f"[LOCAL-628] stop {stop_number}: dropped unpaid "
                        f"teaser from original body (no LLM edit)")
                return (new_block, True, "teaser-dropped")
        if log:
            log(f"[LOCAL-628] stop {stop_number}: rejected({reason})")
        return (_fab_fallback_block, _fab_removed,
                "fabricated-name-stripped" if _fab_removed else reason)

    ok, reason = validate_edit(
        edited_body, body, stop_title=title, venue_name=venue_name,
        passages=passages)
    # [LOCAL-628] Optional, zero-cost before/after capture for live evidence.
    # Writes <dump_dir>/stop_<N>_{before,after,result}.txt when STOP_EDITOR_DUMP_DIR
    # is set. Never changes behaviour; purely diagnostic. Guarded.
    _dump_dir = os.environ.get("STOP_EDITOR_DUMP_DIR", "").strip()
    if _dump_dir:
        try:
            os.makedirs(_dump_dir, exist_ok=True)
            with open(os.path.join(_dump_dir, f"stop_{stop_number}_before.txt"),
                      "w", encoding="utf-8") as _bf:
                _bf.write(body)
            with open(os.path.join(_dump_dir, f"stop_{stop_number}_after.txt"),
                      "w", encoding="utf-8") as _af:
                _af.write(edited_body)
            with open(os.path.join(_dump_dir, f"stop_{stop_number}_result.txt"),
                      "w", encoding="utf-8") as _rf:
                _rf.write(f"edited={ok} reason={reason} "
                          f"len_before={len(body)} len_after={len(edited_body)}")
        except Exception:
            pass
    if not ok:
        # [LOCAL-634] Last-resort deterministic dropped-word repair. The LLM edit
        # was rejected (which includes the new dropped-word guard, or a transient
        # claim_check failure). If the ORIGINAL body itself carries a dropped-word
        # pattern, we must not ship that hole either. Apply the conservative
        # deterministic repair (removes an orphan fragment; drops a sentence with
        # an unrecoverable hole) to the ORIGINAL body. The repaired body adds no
        # word/number/name, so it is validated and shipped; otherwise the original
        # is kept exactly as before.
        if detect_dropped_word(body):
            repaired_body, n_fixed = repair_dropped_words(body)
            if (n_fixed > 0 and repaired_body.strip()
                    and not detect_dropped_word(repaired_body)):
                ok2, reason2 = validate_edit(
                    repaired_body, body, stop_title=title,
                    venue_name=venue_name, passages=passages)
                if ok2:
                    new_block = _reassemble_block(
                        stop_block, header_line, preserved_meta,
                        repaired_body, tail_meta)
                    if log:
                        log(f"[LOCAL-628] stop {stop_number}: dropped-word "
                            f"repaired deterministically ({n_fixed} fixed)")
                    return (new_block, True, "dropped-word-repaired")
        # [LOCAL-638 Note 2] The LLM edit was rejected, so the ORIGINAL body ships.
        # If the original ends on an unpaid teaser, drop it deterministically so a
        # rejected edit never ships an empty promise. Dropping a sentence adds no
        # new claim, so no claim_check re-validation is needed.
        if ends_on_unpaid_teaser(body):
            _candidate, _did = drop_unpaid_teaser(body)
            if _did and _candidate.strip():
                new_block = _reassemble_block(
                    stop_block, header_line, preserved_meta, _candidate, tail_meta)
                if log:
                    log(f"[LOCAL-628] stop {stop_number}: dropped unpaid "
                        f"teaser from original body (edit rejected: {reason})")
                return (new_block, True, "teaser-dropped")
        if log:
            log(f"[LOCAL-628] stop {stop_number}: rejected({reason})")
        return (_fab_fallback_block, _fab_removed,
                "fabricated-name-stripped" if _fab_removed else reason)

    # [LOCAL-638 Note 2] The stop must not end on an unpaid teaser. The prompt asks
    # the LLM to DELIVER or DROP it; as a deterministic guarantee, if the accepted
    # edit STILL ends on an unpaid teaser (the LLM gestured without delivering),
    # drop that trailing teaser sentence so the stop ends on content it told.
    _teaser_dropped = False
    if ends_on_unpaid_teaser(edited_body):
        _candidate, _did = drop_unpaid_teaser(edited_body)
        if _did and _candidate.strip():
            edited_body = _candidate
            _teaser_dropped = True

    # Reassemble: preserved prefix + edited body + preserved tail.
    new_block = _reassemble_block(
        stop_block, header_line, preserved_meta, edited_body, tail_meta)
    if log:
        log(f"[LOCAL-628] stop {stop_number}: edited"
            + (" (dropped unpaid teaser)" if _teaser_dropped else ""))
    return (new_block, True, "edited")


def _reassemble_block(stop_block: str, header_line: str, preserved_meta: str,
                      body: str, tail_meta: str) -> str:
    """Reassemble a stop block from its preserved prefix + body + preserved tail,
    keeping the block's own trailing-whitespace shape so stop separation in the
    whole-tour text is unchanged."""
    parts = []
    if header_line:
        parts.append(header_line)
    if preserved_meta:
        parts.append("")
        parts.append(preserved_meta)
    parts.append("")
    parts.append(body)
    if tail_meta:
        parts.append("")
        parts.append("")
        parts.append(tail_meta)
    new_block = "\n".join(parts)
    trailing = stop_block[len(stop_block.rstrip("\n")):]
    return new_block.rstrip("\n") + trailing


# ─────────────────────────────────────────────────────────────────────────────
# Whole-tour entry point — the single call the pipeline makes
# ─────────────────────────────────────────────────────────────────────────────

def edit_tour_text(
    tour_text: str,
    *,
    venue_name: str = "",
    passages_by_stop: Optional[Dict] = None,
    llm_fn: Optional[Callable[[str, str], Optional[str]]] = None,
    api_key: Optional[str] = None,
    log: Optional[Callable[[str], None]] = None,
) -> str:
    """Edit every stop body in a whole-tour text and return the new text.

    * No-op (returns input unchanged) when the editor is disabled or the tour is
      already marked edited — so a cache/pool hit or a re-run never re-spends.
    * Each stop is edited independently; a per-stop rejection keeps that stop's
      original body. The hidden edited marker is appended once at the end.

    ``passages_by_stop`` maps a stop number (int) or a stop title (str) to a list
    of corpus passages used as ADDITIONAL evidence in validation. The original
    stop body is always evidence; passages are optional and only ever ADD
    support, never remove it.
    """
    if not tour_text or not is_enabled():
        return tour_text
    if already_edited(tour_text):
        return tour_text

    _logf = log or (lambda s: print(s))

    spans = _split_tour_into_stops(tour_text)
    if not spans:
        # No stops to edit — still mark so we never re-enter.
        return _mark_edited(tour_text)

    out_parts: List[str] = []
    cursor = 0
    n_edited = 0
    n_rejected = 0

    # Pre-compute each span's (pre-text, block, stop_no, title, passages). This is
    # pure string slicing — no network — and identical regardless of the flag.
    _plan = []
    _cur = 0
    for (start, end) in spans:
        _pre = tour_text[_cur:start] if start > _cur else ""
        block = tour_text[start:end]
        m = _STOP_HEADER.search(block)
        stop_no = int(m.group(1)) if m else 0
        title = m.group(2).strip() if m else ""
        passages = None
        if passages_by_stop:
            passages = (passages_by_stop.get(stop_no)
                        or passages_by_stop.get(title)
                        or passages_by_stop.get(f"__stop_{stop_no}__"))
        _plan.append((_pre, block, stop_no, title, passages))
        _cur = end
    _tail = tour_text[_cur:] if _cur < len(tour_text) else ""

    def _edit_one(_block, _stop_no, _title, _passages):
        return edit_stop(
            _block, stop_number=_stop_no, venue_name=venue_name,
            passages=_passages, llm_fn=llm_fn, api_key=api_key, log=_logf)

    # [LOCAL-651] FAST_PIPELINE: edit every stop CONCURRENTLY (each edit_stop is
    # independent — it edits one block and returns it; the ONE cross-stop pass,
    # the trailing conclusion, is built later in the pipeline, after this). When
    # the flag is OFF, edits run serially in order exactly as before. Either way
    # the ordered assembly, counters and marker below are identical.
    _use_parallel = (_fast_pipeline is not None and _fast_pipeline.is_enabled()
                     and len(_plan) > 1)
    if _use_parallel:
        try:
            _jobs = [(lambda p=p: _edit_one(p[1], p[2], p[3], p[4])) for p in _plan]
            _edited_results = _fast_pipeline.run_parallel(_jobs, label='stop_editor')
        except Exception as _ed_err:
            _logf(f"[LOCAL-651] parallel editor fell back to serial "
                  f"(non-fatal): {type(_ed_err).__name__}: {_ed_err}")
            _edited_results = [_edit_one(p[1], p[2], p[3], p[4]) for p in _plan]
    else:
        _edited_results = [_edit_one(p[1], p[2], p[3], p[4]) for p in _plan]

    for (_pre, _block, _stop_no, _title, _passages), (new_block, edited, _reason) in zip(_plan, _edited_results):
        if _pre:
            out_parts.append(_pre)
        if edited:
            n_edited += 1
        else:
            n_rejected += 1
        out_parts.append(new_block)

    if _tail:
        out_parts.append(_tail)

    new_text = "".join(out_parts)
    _logf(f"[LOCAL-628] editor pass complete: {n_edited} edited, "
          f"{n_rejected} kept original")
    return _mark_edited(new_text)


def repair_stray_quotes_in_text(tour_text: str) -> Tuple[str, int]:
    """[LEAD 2026-10-08] Drop a lone straight double quote in a line that holds an odd number
    of them, when it sits at a sentence end or right after a title that was never opened
    (Frick 523: 'Your first stop is Officer and Laughing Girl."'). Header and field lines
    are left untouched."""
    out, n = [], 0
    for line in (tour_text or "").split("\n"):
        if line.count('"') % 2 == 1 and not re.match(r"^(Stop \d+:|Address:|Coordinates:|Sources:)", line):
            fixed = re.sub(r'(?<=[.!?])"(?=\s|$)', "", line, count=1)
            if fixed == line:
                fixed = re.sub(r'(?<=\w)"(?=[\s.,;:!?]|$)', "", line, count=1)
            if fixed != line:
                n += 1
                line = fixed
        out.append(line)
    return "\n".join(out), n
