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
_STRUCT_LABELS = ("Address:", "Coordinates:", "Orientation:", "Directions:",
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
        new.append(tok)
    return new


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

    prompt = build_editor_prompt(title, body)
    try:
        edited_body = fn(prompt, api_key)
    except Exception as exc:
        edited_body = None
        reason = f"llm error: {type(exc).__name__}"
        if log:
            log(f"[LOCAL-628] stop {stop_number}: rejected({reason})")
        return (stop_block, False, reason)

    edited_body = (edited_body or "").strip().strip('"').strip()
    if not edited_body:
        reason = "empty llm output"
        if log:
            log(f"[LOCAL-628] stop {stop_number}: rejected({reason})")
        return (stop_block, False, reason)

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
        if log:
            log(f"[LOCAL-628] stop {stop_number}: rejected({reason})")
        return (stop_block, False, reason)

    # Reassemble: preserved prefix + edited body + preserved tail.
    parts = []
    if header_line:
        parts.append(header_line)
    if preserved_meta:
        parts.append("")
        parts.append(preserved_meta)
    parts.append("")
    parts.append(edited_body)
    if tail_meta:
        parts.append("")
        parts.append("")
        parts.append(tail_meta)
    new_block = "\n".join(parts)
    # Preserve the block's own trailing whitespace shape so stop separation in
    # the whole-tour text is unchanged.
    trailing = stop_block[len(stop_block.rstrip("\n")):]
    new_block = new_block.rstrip("\n") + trailing
    if log:
        log(f"[LOCAL-628] stop {stop_number}: edited")
    return (new_block, True, "edited")


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
    for (start, end) in spans:
        # Preserve any text before the first stop (title/category banner) and
        # between stop spans (there is none — spans are contiguous by header).
        if start > cursor:
            out_parts.append(tour_text[cursor:start])
        block = tour_text[start:end]
        m = _STOP_HEADER.search(block)
        stop_no = int(m.group(1)) if m else 0
        title = m.group(2).strip() if m else ""
        passages = None
        if passages_by_stop:
            passages = (passages_by_stop.get(stop_no)
                        or passages_by_stop.get(title)
                        or passages_by_stop.get(f"__stop_{stop_no}__"))
        new_block, edited, _reason = edit_stop(
            block, stop_number=stop_no, venue_name=venue_name,
            passages=passages, llm_fn=llm_fn, api_key=api_key, log=_logf)
        if edited:
            n_edited += 1
        else:
            n_rejected += 1
        out_parts.append(new_block)
        cursor = end

    if cursor < len(tour_text):
        out_parts.append(tour_text[cursor:])

    new_text = "".join(out_parts)
    _logf(f"[LOCAL-628] editor pass complete: {n_edited} edited, "
          f"{n_rejected} kept original")
    return _mark_edited(new_text)
