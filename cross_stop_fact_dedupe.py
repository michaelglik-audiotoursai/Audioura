"""
Cross-stop fact dedupe (LOCAL-607 defect 3) — one story, one telling.
=====================================================================
Michael, on McMullen tour 399: *"The Lynch/McMullen donations, the 1993 Devlin
Hall founding and the 2016 Brighton relocation are retold in stops 1, 2, 3 and 7
… listening once is good … at every stop is annoying. Don't we have a check to
remove the same story from multiple stops?"*

We DID have one — "No cross-stop repetition (>0.85)" — but it compares WHOLE-STOP
text similarity, so a donor story reworded for each stop (different sentences,
same fact) sails straight through. This module adds the missing layer: a
deterministic, LLM-free **fact** dedupe that works at the SENTENCE level.

What it does
------------
1. Split every stop's narration into sentences.
2. FINGERPRINT the sentences that carry a repeatable FACT:
     * a YEAR (1400–2099) plus a PROPER NOUN, or
     * a DONOR / ACQUISITION verb (donated, gifted, bequeathed, acquired,
       renamed, relocated, founded, established …).
   The fingerprint is the normalised (year, sorted-proper-nouns / verb-lemma)
   signature of the fact, NOT the exact wording — so "John and Jacqueline
   McMullen donated … in 1996" and "In 1996 … the McMullens' gift renamed …"
   collapse to the same fingerprint and are caught though the words differ.
3. KEEP the first occurrence in TOUR ORDER; drop the sentence from every later
   stop. The first telling stays where the listener first meets it.
4. MUSEUM-HISTORY facts (founding, renaming, relocation, donors / patrons) belong
   to Stop 1's opening section. They are removed from stops 2…N entirely — UNLESS
   the later stop's OWN work was the donated object, in which case ONE sentence of
   acquisition is allowed to stay (Michael's exception: "unless the stop's own
   work was the donated object, and then use one sentence").

Deterministic and pure: no network, no LLM, no randomness. Operates on the
delivered tour TEXT and returns the rewritten text plus a log of what was dropped,
so the orchestrator can print the dedupe lines Michael asked for.
"""
import re
from dataclasses import dataclass, field
from typing import List, Dict, Tuple, Optional


# ── Fact signals ─────────────────────────────────────────────────────────────

_YEAR_RE = re.compile(r'\b(1[4-9]\d{2}|20\d{2})\b')

# Donor / acquisition / museum-history verbs (lemma keys). A sentence that
# carries one of these states a repeatable institutional fact.
_DONOR_VERBS = {
    "donat": "donate", "donated": "donate", "donation": "donate",
    "gift": "gift", "gifted": "gift",
    "bequeath": "bequeath", "bequest": "bequeath",
    "acquir": "acquire", "acquisition": "acquire",
    "renam": "rename", "renamed": "rename", "renaming": "rename",
    "reloc": "relocate", "relocated": "relocate", "relocation": "relocate",
    "found": "found", "founded": "found", "founding": "found",
    "establish": "establish", "established": "establish",
    "moved": "relocate", "move": "relocate",
}
_DONOR_VERB_RE = re.compile(
    r'\b(donat\w*|gift\w*|bequeath\w*|bequest|acquir\w*|acquisition|'
    r'renam\w*|reloc\w*|found|founded|founding|founder|founders|'
    r'establish\w*|moved)\b', re.IGNORECASE)

# Museum-history markers: a fact about the INSTITUTION (not the work, not the
# artist) — founding, renaming, relocation, the donors/patrons behind it. These
# belong to Stop 1. NOTE: 'found'/'founded'/'founding' are matched explicitly so
# the common noun 'foundation' (a base) is NOT mistaken for an institutional
# founding; and 'relocate'/'moved'/'found' only count as MUSEUM history when the
# sentence also names the INSTITUTION — otherwise "Subleyras relocated to Rome"
# (the artist's life) or "Peale found inspiration" would be wrongly stripped.
_HISTORY_VERB_RE = re.compile(
    r'\b(renam\w*|reloc\w*|found|founded|founding|establish\w*|moved|'
    r'donat\w*|gift\w*|bequeath\w*|bequest|patron|patronage|benefactor)\b',
    re.IGNORECASE)
# An institution reference: the sentence is about the venue/organisation, not a
# person. Required for a sentence to count as MUSEUM history.
_INSTITUTION_RE = re.compile(
    r'\b(museum|college|university|gallery|galleries|institution|institute|'
    r'collection|campus|hall|the\s+mcmullen|boston\s+college|foundation\s+of\s+the)\b',
    re.IGNORECASE)
# Donor/acquisition verbs are institutional regardless of an explicit venue noun
# (a work being donated/gifted/bequeathed/acquired IS the museum's acquisition
# history); relocation/founding/moving need the institution reference above.
_ACQUISITION_VERB_RE = re.compile(
    r'\b(donat\w*|gift\w*|bequeath\w*|bequest|acquir\w*|acquisition|'
    r'renam\w*|patron|patronage|benefactor)\b', re.IGNORECASE)

# A proper noun: a capitalised word not at sentence start, or a known multi-word
# name. We take capitalised tokens length >= 3 and drop a leading-word artefact.
_PROPER_RE = re.compile(r'\b([A-Z][a-zA-Z\u00C0-\u017F&.\'-]{2,})\b')
# Common sentence-initial / non-name capitalised words to ignore as proper nouns.
_STOPWORDS_CAP = {
    "The", "This", "That", "These", "Those", "In", "On", "At", "By", "For",
    "From", "With", "His", "Her", "Their", "Its", "A", "An", "As", "It",
    "However", "Before", "After", "During", "Within", "Here", "Thanks",
    "Much", "Eventually", "Curators", "Accompanying", "Grounded", "Founded",
    "Created", "Painted", "Observe", "Stand", "Position", "Standing",
}


def _proper_nouns(sentence: str) -> List[str]:
    """Return the distinctive proper nouns in a sentence (lowercased, sorted)."""
    found = []
    for m in _PROPER_RE.finditer(sentence):
        w = m.group(1)
        if w in _STOPWORDS_CAP:
            continue
        found.append(w.lower())
    # Dedup, keep stable.
    seen = set()
    out = []
    for w in found:
        if w not in seen:
            seen.add(w)
            out.append(w)
    return sorted(out)


def _donor_verb_lemmas(sentence: str) -> List[str]:
    """Return the donor/acquisition verb lemmas present in a sentence."""
    lemmas = set()
    for m in _DONOR_VERB_RE.finditer(sentence):
        tok = m.group(1).lower()
        # Map to a lemma via prefix.
        for pref, lemma in _DONOR_VERBS.items():
            if tok.startswith(pref):
                lemmas.add(lemma)
                break
    return sorted(lemmas)


def fact_fingerprint(sentence: str) -> Optional[Tuple]:
    """Return a repeatable fact fingerprint for a sentence, or None.

    A sentence carries a repeatable fact when it has:
      * a YEAR plus at least one proper noun  → (year, proper-nouns…), or
      * a donor/acquisition verb              → (verb-lemmas…, key proper nouns)

    The fingerprint is wording-independent: it is built from the year, the sorted
    distinctive proper nouns, and/or the donor-verb lemmas. Two differently worded
    sentences that assert the same institutional fact produce the SAME fingerprint.
    Returns None for a sentence that carries no such fact (it is never deduped).
    """
    years = _YEAR_RE.findall(sentence or "")
    propers = _proper_nouns(sentence or "")
    verbs = _donor_verb_lemmas(sentence or "")

    if years and propers:
        # Year-anchored institutional fact: key on (first-year, up to 3 propers).
        return ("year", years[0], tuple(propers[:3]))
    if verbs:
        # Donor/acquisition fact without a clean year: key on (verbs, 2 propers).
        return ("verb", tuple(verbs), tuple(propers[:2]))
    return None


def is_museum_history(sentence: str) -> bool:
    """True when a sentence states a MUSEUM-HISTORY fact (institution, not artist).

    Two ways a sentence qualifies as institutional history that belongs in Stop 1:
      * it carries an ACQUISITION verb (donated / gifted / bequeathed / acquired /
        renamed / patron …) — a work entering the museum IS the museum's history; or
      * it carries a FOUNDING / RELOCATION / MOVED verb AND names the INSTITUTION
        (museum, college, gallery, collection, campus, hall) — so the artist's own
        life ("Subleyras relocated to Rome in 1728", "Peale found inspiration in
        her teacher's work") is NOT mistaken for the museum relocating or founding.
    """
    s = sentence or ""
    if _ACQUISITION_VERB_RE.search(s):
        return True
    _FOUNDING_RELOC_RE = re.compile(
        r'\b(reloc\w*|found|founded|founding|establish\w*|moved)\b', re.IGNORECASE)
    if _FOUNDING_RELOC_RE.search(s) and _INSTITUTION_RE.search(s):
        return True
    return False


# ── Stop parsing (narration body only) ───────────────────────────────────────

_STOP_HEADER = re.compile(r'^(Stop (\d+):\s*.+?)\s*$', re.M)
_FIELD_OR_SEQ = re.compile(
    r'^(?:Address|Coordinates|Type/Specialty|Specific Examples|'
    r'Operational Details|Museum Information|Orientation|Directions):', re.M)


def _split_sentences(text: str) -> List[str]:
    """Split narration into sentences using the ONE shared splitter.

    [LOCAL-614 item 1] The old body here was ``re.split(r'(?<=[.!?])\\s+', …)``,
    which treats an initial's full stop ("Isabella V.", "Gail L.") as a sentence
    boundary. A later dedupe drop then kept only half the sentence, shipping
    "…named The Charles S. and Isabella V.This transition…" and "…along with Gail
    L. The expertise…". ``sentence_split.split_sentences`` already guards a single
    capital letter + period (an initial) and common abbreviations, so delegating
    to it means a name's initial is never a split point. One shared splitter.
    """
    try:
        from sentence_split import split_sentences as _shared
    except Exception:  # pragma: no cover - shared module always present in repo
        return [s.strip() for s in re.split(r'(?<=[.!?])\s+', (text or "").strip())
                if s.strip()]
    return _shared(text or "")


@dataclass
class DedupeResult:
    tour_text: str
    dropped: List[Dict] = field(default_factory=list)  # {stop, reason, sentence}

    @property
    def dropped_count(self) -> int:
        return len(self.dropped)

    def log_lines(self) -> List[str]:
        """Human-readable dedupe log lines for the orchestrator to print."""
        out = []
        for d in self.dropped:
            out.append(
                f"[LOCAL-607] dedupe: dropped from Stop {d['stop']} "
                f"({d['reason']}): \"{d['sentence'][:90]}\"")
        return out


def _stop_title_from_header(header: str) -> str:
    m = re.match(r'Stop \d+:\s*(.+)', header)
    title = m.group(1).strip() if m else header
    # Strip ' by artist' / ', year' decoration for the work-match test.
    title = re.sub(r',\s*\d{3,4}\s*$', '', title)
    title = re.sub(r'\s+by\s+.+$', '', title)
    return title.strip()


def dedupe_tour_facts(tour_text: str,
                      stop1_owns_history: bool = True) -> DedupeResult:
    """Remove repeated facts across stops; keep the first in tour order.

    Walks the delivered tour text stop by stop. Within each stop it inspects the
    narration BODY sentences only (never Orientation/Directions/structured field
    lines — those are not facts). For each sentence that carries a fact fingerprint
    (``fact_fingerprint``):

      * If the fingerprint has been seen in an EARLIER stop, the sentence is a
        repeat and is DROPPED.
      * Otherwise it is kept and the fingerprint is remembered.

    Additionally, when ``stop1_owns_history`` is True, a MUSEUM-HISTORY sentence
    (``is_museum_history``) in stops 2…N is dropped even on first sight — those
    facts belong to Stop 1's opening section — UNLESS it is the FIRST acquisition
    sentence about the stop's OWN work (one sentence allowed, Michael's exception).

    Deterministic: the same input always yields the same output. Returns the
    rewritten tour text and the drop log.
    """
    text = tour_text or ""
    headers = list(_STOP_HEADER.finditer(text))
    if not headers:
        return DedupeResult(tour_text=text, dropped=[])

    seen_fingerprints = {}  # fingerprint -> stop index (1-based) where first seen
    dropped = []
    # We rebuild the text by replacing each stop's body region.
    pieces = []
    last_end = 0

    for idx, hdr in enumerate(headers):
        stop_num = int(hdr.group(2))
        body_start = hdr.end()
        body_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        stop_title = _stop_title_from_header(hdr.group(1))

        # Emit everything up to and including this header untouched.
        pieces.append(text[last_end:body_start])
        body = text[body_start:body_end]
        last_end = body_end

        # Work line-by-line so field/sequence lines are preserved verbatim and
        # only free-prose paragraphs are deduped.
        out_lines = []
        own_work_acq_used = False
        for raw_line in body.split("\n"):
            line = raw_line
            stripped = line.strip()
            # Preserve blank lines and structured/sequence lines verbatim.
            if not stripped or _FIELD_OR_SEQ.match(stripped):
                out_lines.append(line)
                continue
            # A prose paragraph: dedupe sentence by sentence.
            sentences = _split_sentences(stripped)
            if len(sentences) <= 1 and not fact_fingerprint(stripped):
                out_lines.append(line)
                continue
            kept_sentences = []
            for sent in sentences:
                fp = fact_fingerprint(sent)
                drop = False
                reason = ""
                if fp is not None:
                    first_stop = seen_fingerprints.get(fp)
                    if first_stop is not None and first_stop != stop_num:
                        drop = True
                        reason = f"repeat of fact first told in Stop {first_stop}"
                    else:
                        # First sighting of this fact.
                        if (stop1_owns_history and stop_num > 1
                                and is_museum_history(sent)):
                            # Museum-history fact in a later stop. Allow ONE
                            # acquisition sentence if it is about this stop's OWN
                            # work (the work was the donated object).
                            _about_own_work = (
                                stop_title and stop_title.lower() in sent.lower())
                            if _about_own_work and not own_work_acq_used:
                                own_work_acq_used = True
                                seen_fingerprints[fp] = stop_num
                            else:
                                drop = True
                                reason = ("museum-history fact belongs to Stop 1")
                        else:
                            seen_fingerprints[fp] = stop_num
                if drop:
                    dropped.append({
                        "stop": stop_num, "reason": reason, "sentence": sent})
                else:
                    kept_sentences.append(sent)
            if kept_sentences:
                # Preserve the line's leading indentation.
                indent = line[:len(line) - len(line.lstrip())]
                out_lines.append(indent + " ".join(kept_sentences))
            # If every sentence was dropped, the paragraph is removed (its blank
            # neighbours remain and are collapsed below).

        new_body = "\n".join(out_lines)
        # Collapse the blank-line runs a removed paragraph leaves behind.
        new_body = re.sub(r'\n{3,}', '\n\n', new_body)
        pieces.append(new_body)

    pieces.append(text[last_end:])
    result_text = "".join(pieces)
    result_text = re.sub(r'\n{3,}', '\n\n', result_text)
    return DedupeResult(tour_text=result_text, dropped=dropped)


def dedupe_stop_units(ordered_units: List[Dict],
                      stop1_owns_history: bool = True) -> Tuple[List[Dict], List[Dict]]:
    """Dedupe facts across a list of ordered stop-unit dicts (narration in place).

    Same policy as ``dedupe_tour_facts`` but operates directly on the assembly's
    stop units (each a dict with 'title' and 'narration'), BEFORE rendering, so
    the conclusion builder reads already-deduped narration. Keeps the first
    occurrence of each fact in tour order; strips later-stop museum-history
    sentences (Stop 1 owns them) except one acquisition sentence about the stop's
    own work.

    Returns (new_units, dropped) where new_units is a NEW list of unit dicts with
    rewritten narration (originals untouched) and dropped is the drop log.
    """
    seen_fingerprints = {}
    dropped = []
    new_units = []
    for i, unit in enumerate(ordered_units):
        stop_num = i + 1
        title = (unit.get("title") or "").strip()
        bare_title = re.sub(r',\s*\d{3,4}\s*$', '', title)
        bare_title = re.sub(r'\s+by\s+.+$', '', bare_title).strip()
        narration = unit.get("narration") or ""
        out_paras = []
        own_work_acq_used = False
        for para in re.split(r'\n{2,}', narration):
            sentences = _split_sentences(para)
            if not sentences:
                out_paras.append(para)
                continue
            kept = []
            for sent in sentences:
                fp = fact_fingerprint(sent)
                drop = False
                reason = ""
                if fp is not None:
                    first_stop = seen_fingerprints.get(fp)
                    if first_stop is not None and first_stop != stop_num:
                        drop = True
                        reason = f"repeat of fact first told in Stop {first_stop}"
                    else:
                        if (stop1_owns_history and stop_num > 1
                                and is_museum_history(sent)):
                            _about_own_work = (
                                bare_title and bare_title.lower() in sent.lower())
                            if _about_own_work and not own_work_acq_used:
                                own_work_acq_used = True
                                seen_fingerprints[fp] = stop_num
                            else:
                                drop = True
                                reason = "museum-history fact belongs to Stop 1"
                        else:
                            seen_fingerprints[fp] = stop_num
                if drop:
                    dropped.append({
                        "stop": stop_num, "reason": reason, "sentence": sent})
                else:
                    kept.append(sent)
            if kept:
                out_paras.append(" ".join(kept))
        new_narration = "\n\n".join(p for p in out_paras if p.strip()).strip()
        nu = dict(unit)
        nu["narration"] = new_narration
        new_units.append(nu)
    return new_units, dropped


# ── QA check: "No repeated story across stops" ───────────────────────────────

def count_repeated_facts_across_stops(tour_text: str) -> List[Dict]:
    """Count surviving duplicate facts across stops (QA check support).

    Returns a list of {fingerprint, stops} for every fact fingerprint that appears
    in MORE THAN ONE stop's narration — i.e. the duplicates the dedupe should have
    removed. An empty list means "No repeated story across stops" passes.
    """
    text = tour_text or ""
    headers = list(_STOP_HEADER.finditer(text))
    if not headers:
        return []
    fp_to_stops = {}
    for idx, hdr in enumerate(headers):
        stop_num = int(hdr.group(2))
        body_start = hdr.end()
        body_end = headers[idx + 1].start() if idx + 1 < len(headers) else len(text)
        body = text[body_start:body_end]
        for raw_line in body.split("\n"):
            stripped = raw_line.strip()
            if not stripped or _FIELD_OR_SEQ.match(stripped):
                continue
            for sent in _split_sentences(stripped):
                fp = fact_fingerprint(sent)
                if fp is None:
                    continue
                fp_to_stops.setdefault(fp, set()).add(stop_num)
    repeats = []
    for fp, stops in fp_to_stops.items():
        if len(stops) > 1:
            repeats.append({"fingerprint": fp, "stops": sorted(stops)})
    return repeats
