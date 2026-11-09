"""stop_title_dedup.py — LOCAL-722: one normalisation for "the same work twice".

Why this module exists
----------------------
Fresh 6-stop "Courtauld Gallery, London" museum tours were refused with
``error / factual_integrity`` because ``D3(e) No duplicate stops (FACTUAL)``
fired: the SAME work was delivered as two stops even though the LOCAL-212
"Selected stops" list held it only once.

Two observed shapes of the duplicate:
  * LOCAL-721's gpt-4.1 run — "Landscape with the Flight into Egypt" delivered
    twice.
  * LEAD's Sonnet run — ``'A Bar at the Folies-Bergère' = 'A Bar at the
    Folies-Bergère.' (same work)`` — the SAME title with a trailing period.

A listener who typed one of London's best-documented museums saw only
"We couldn't verify enough facts…". That is wrong twice over: the facts were
fine, and a duplicate is a correctable delivery defect — the same corrective
G4 already uses for ungrounded sentences (drop/replace and re-check), not a
reason to throw away the whole tour.

The normalisation
-----------------
``normalize_stop_title`` is the SINGLE definition of "the same work" used by
both the prevention path (dedup through delivery) and the D3(e) QA check:
casefold, strip accents, strip punctuation/quotes/italics, collapse whitespace.
It is deliberately identical to ``story_miner._normalize`` (and to the inline
normalisation D3(e) has always used) so the guard and the check can never drift:

    "A Bar at the Folies-Bergère."  →  "a bar at the folies bergere"
    "A Bar at the Folies-Bergère"   →  "a bar at the folies bergere"   (merge)

    "Self-Portrait"                     →  "self portrait"
    "Self-Portrait with Bandaged Ear"   →  "self portrait with bandaged ear"
    (DIFFERENT normals — two different works are NEVER merged)

Both are NFKD-based and punctuation-insensitive, so a hyphen, a trailing
period, curly quotes, or an accent can never make one work look like two — or
two works look like one.
"""
import re
import unicodedata

__all__ = [
    "normalize_stop_title",
    "find_duplicate_stop_titles",
    "dedupe_delivered_stops",
]

# A ``Stop N:`` header on its own line. The title is everything after the colon.
_STOP_HEADER_RE = re.compile(r'^Stop\s+(\d+):\s*(.*)$', re.MULTILINE)

# [LOCAL-883] A block whose prose body is shorter than this (characters, fields
# and the Orientation label excluded) is treated as a STUB: on a title collision
# a stub never beats a real block. Tuned so a lone Directions hand-off counts as
# a stub while any genuine one-sentence body does not.
_STUB_BODY_CHARS = 40


def normalize_stop_title(title: str) -> str:
    """Normalise a stop/work title so two labels for the same work collapse.

    casefold → strip accents (NFKD, drop combining marks) → replace every
    non-word / non-space char (punctuation, quotes, italics markers, hyphens)
    with a space → collapse whitespace.

    Mirrors ``story_miner._normalize`` exactly; kept here too so the dedup
    guard has no hard import dependency on the heavy story_miner module and can
    be unit-tested in isolation. (The two are asserted equal by the test suite.)
    """
    if not title:
        return ""
    nfkd = unicodedata.normalize('NFKD', title.lower())
    stripped = ''.join(c for c in nfkd if not unicodedata.combining(c))
    stripped = re.sub(r'[^\w\s]', ' ', stripped)
    return ' '.join(stripped.split())


def find_duplicate_stop_titles(stop_titles):
    """Return ``[(duplicate_title, first_title), …]`` for same-work repeats.

    Order follows the stop order; the FIRST occurrence of a normalised title is
    the keeper, every later occurrence is reported as a duplicate of it. This is
    the exact pairing D3(e) prints (``'<dup>' = '<first>' (same work)``).
    """
    first_by_norm = {}
    dups = []
    for title in stop_titles:
        norm = normalize_stop_title(title)
        if not norm:
            continue
        if norm in first_by_norm:
            dups.append((title, first_by_norm[norm]))
        else:
            first_by_norm[norm] = title
    return dups


def _split_into_blocks(tour_text: str):
    """Split delivered text into (preamble, [stop_blocks], tail_in_last_block).

    A stop block is a ``Stop N:`` header line plus everything up to (but not
    including) the next ``Stop N:`` header. The preamble is whatever precedes
    the first header (the spoken title line). The conclusion / offer / Sources
    live inside the LAST stop block — they are rebuilt downstream by
    ``tour_conclusion.rebuild_conclusion`` once the delivered stop set is final,
    so we do not need to separate them here.

    Returns ``(preamble, blocks)`` where each block is
    ``{'num': int, 'title': str, 'text': str}`` and ``text`` is the verbatim
    block INCLUDING its header line.
    """
    matches = list(_STOP_HEADER_RE.finditer(tour_text))
    if not matches:
        return tour_text, []
    preamble = tour_text[:matches[0].start()]
    blocks = []
    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(tour_text)
        blocks.append({
            'num': int(m.group(1)),
            'title': m.group(2).strip(),
            'text': tour_text[start:end],
        })
    return preamble, blocks


def dedupe_delivered_stops(tour_text: str):
    """Drop stop blocks that repeat an earlier stop's work (same normalised title).

    Keeps the FIRST occurrence of each normalised title and removes every later
    duplicate BLOCK (header + body). Surviving ``Stop N:`` headers are renumbered
    1..k so the delivered text stays well-formed. The conclusion ("That's N
    stops"), the orientation "first stop" name and the inter-stop Directions are
    NOT patched here — the caller runs this BEFORE
    ``tour_conclusion.rebuild_conclusion`` / ``normalise_stop_headers``, which
    rebuild those from the final stop set.

    Deterministic and idempotent: a second call on already-deduped text changes
    nothing (no normalised title repeats, numbering already 1..k).

    Returns ``(new_text, dropped)`` where ``dropped`` is
    ``[(duplicate_title, first_title), …]`` in stop order. When nothing is a
    duplicate, returns the input text unchanged (same object identity not
    guaranteed) and an empty list.
    """
    if not tour_text:
        return tour_text, []

    preamble, blocks = _split_into_blocks(tour_text)
    if len(blocks) < 2:
        return tour_text, []

    first_by_norm = {}
    kept = []
    dropped = []
    # [LOCAL-883] When two blocks share a normalised title (e.g. "War Remnants
    # Museum" vs "War Remnants Museum."), the LOCAL-722 rule keeps the FIRST — but
    # a reordered / budget-starved run can emit a near-empty STUB (just a
    # Directions hand-off) before the real, fact-rich block, and keeping the stub
    # drops the content, leaving a 1-sentence stop. So the first is kept UNLESS it
    # is a stub and the later block carries real body; then the richer block takes
    # the earlier slot. A tie, or two real blocks, keeps the first exactly as
    # before (back-compat with LOCAL-722).
    pos_by_norm = {}            # norm -> index in `kept`

    def _body_weight(block_text: str) -> int:
        # count non-field, non-header prose characters as a cheap richness measure.
        w = 0
        for ln in (block_text or "").split("\n"):
            s = ln.strip()
            if not s or _STOP_HEADER_RE.match(s):
                continue
            if re.match(r"(?i)^(coordinates|type/specialty|specific examples|"
                        r"directions|address|sources?|operational details):", s):
                continue
            m = re.match(r"(?i)^orientation:\s*(.*)$", s)
            w += len(m.group(1)) if m else len(s)
        return w

    for b in blocks:
        norm = normalize_stop_title(b['title'])
        # A header with an empty title is left in place (nothing to dedup on);
        # the D3(d)/header guards handle malformed headers separately.
        if norm and norm in first_by_norm:
            # a duplicate of an earlier title. LOCAL-722 keeps the FIRST occurrence;
            # but when that first occurrence is a near-empty STUB (a reordered /
            # budget-starved run can emit just a Directions hand-off before the
            # real, fact-rich block) keeping it would ship the stub and drop the
            # content. So: if the earlier kept block is a stub AND this later block
            # has real body, swap the later block into the earlier's slot. Otherwise
            # keep the first, exactly as before.
            idx = pos_by_norm[norm]
            earlier = kept[idx]
            earlier_w, later_w = _body_weight(earlier['text']), _body_weight(b['text'])
            if earlier_w < _STUB_BODY_CHARS <= later_w:
                dropped.append((earlier['title'], b['title']))
                kept[idx] = b
                first_by_norm[norm] = b['title']
            else:
                dropped.append((b['title'], first_by_norm[norm]))
            continue
        if norm:
            first_by_norm[norm] = b['title']
            pos_by_norm[norm] = len(kept)
        kept.append(b)

    if not dropped:
        return tour_text, []

    # Renumber surviving headers 1..k (only the header line of each block).
    rebuilt = [preamble]
    for new_num, b in enumerate(kept, start=1):
        block_text = _STOP_HEADER_RE.sub(
            lambda m, _n=new_num: f"Stop {_n}: {m.group(2).strip()}",
            b['text'],
            count=1,
        )
        rebuilt.append(block_text)
    return ''.join(rebuilt), dropped
