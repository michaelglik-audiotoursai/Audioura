#!/usr/bin/env python3
"""spoken_text_hygiene.py — D523: the last pass before a human hears it.

Two defects that survived every gate because no gate was looking at the assembled
text as SOUND rather than as claims.

**1. Template seams.** `"At this work: Le Lézard aux plumes d'or, witness Miró's
surreal exploration…"` — spoken aloud that is "at this work colon". The prompt
asks for "<fact> at <stop name>" and the model answers with a label. A strip for
exactly this already existed at `generate_tour_text.py:15498` but was applied only
to Part 4, and the 12:23 tour put it in the stop-1 ORIENTATION, which comes from a
different generator. So the strip moves here, where it sees the finished tour and
cannot be routed around.

**2. A full stop with no space after it.** `"…mythic creature.Published by Louis
Broder…"`, `"…printed works.This exhibition…"`, `"…depth.Boris Fridman…"`. Five
sightings in six runs — LEAD reported it as a "known defect" three times without
fixing it, on the grounds that it was upstream. It is upstream, and it is also two
lines to repair here, and a listener hears a word that does not exist.

Both are applied to the assembled tour, after every gate has had its say, so
nothing downstream can reintroduce them.
"""
import re
from collections import defaultdict

__all__ = ['clean_spoken_text', 'MISSING_SPACE_RE', 'TEMPLATE_SEAM_RE',
           'DANGLING_PHRASE_RE', 'normalize_proper_noun_spellings',
           'strip_sources_and_urls', 'SOURCES_HEADING_RE', 'URL_RE',
           'strip_degenerate_from_to_recap',
           'flag_sentence', 'grammar_splice_lint', 'strip_citation_tails',
           'CITATION_TAIL_RE', 'AS_OF_TAIL_RE',
           'strip_recruitment_sentences', 'RECRUITMENT_SENTENCE_RE',
           'strip_promotional_sentences', 'PROMOTIONAL_SENTENCE_RE',
           'strip_truncated_tail_sentences', 'disclose_or_drop_folklore',
           'strip_contradicted_former_use', 'fix_opera_house_government_use',
           'audit_seating_capacity', 'strip_orientation_filler',
           'fix_intro_grammar', 'fix_orphan_closing',
           'strip_empty_current_affairs_note']

# "At this work:", "in the stop:", "At this piece:" — the preposition keeps its
# original case, because replacing with a literal "At " produced "Then, At Au
# Soleil du Plafond" when this lived in the Part 4 verifier.
TEMPLATE_SEAM_RE = re.compile(
    r'\b(at|in|for)\s+th(?:is|e)\s+(?:work|stop|piece|item|location)\s*:\s*',
    re.IGNORECASE)

# A sentence-ending full stop with the next sentence jammed against it. TWO
# lowercase letters before and a capital plus TWO lowercase after, which is what
# keeps every abbreviation and every domain out of range:
#   christies.com   lowercase after the dot        — no match
#   U.S.A.          single letters before the dot  — no match
#   Ph.D            single letter after            — no match
#
# **The quote had to be allowed for.** The first version was
# `([a-zà-ÿ]{2})\.([A-ZÀ-Ý][a-zà-ÿ]{2})` and the very next tour shipped
# `…blend of text and imagery."Au Soleil du Plafond" thus advances…` — a quotation
# mark between the stop and the capital, which the pattern could not cross. The
# defect checker had the identical blind spot and reported the tour clean.
#   "Au Soleil"     ONE lowercase after the capital — so the tail is {1,}, not
#                   {2}, which is what let the quote case through a second time.
MISSING_SPACE_RE = re.compile(
    r'([a-zà-ÿ]{2})\.(["“”\'‘’]?)([A-ZÀ-Ý][a-zà-ÿ]+)')

# A participial phrase whose object was deleted by an upstream gate.
#
# Measured in the same run: `[LOCAL-392] Torf Gallery -> DEGRADED (name dropped)`
# left "The eleven lithographs, housed in are rarely on view…". The gate was right
# to drop an ungrounded gallery name and wrong to leave the preposition holding
# nothing. Repairing the sentence is not that gate's job, but it is somebody's.
DANGLING_PHRASE_RE = re.compile(
    r',\s*[a-zà-ÿ]+ed\s+(?:in|at|on|by|for|from)\s+(?=(?:are|is|was|were)\b)',
    re.IGNORECASE)

# [LOCAL-626 item 3] SECOND-PERSON MARKETING / RECRUITMENT register, stripped from
# the WHOLE spoken tour (about-museum opening AND every stop body). Tour 485 spoke
# the Courtauld Institute admissions page in Stop 1: "You'll learn from leaders …
# forge a career in the wider professional art world and beyond."; "Study in the
# heart of London with world-renowned specialists …". This mirrors the narrower
# about_museum_stop._RECRUITMENT_RE but runs on the FINAL text, so the same copy
# can never survive in a stop body the About gate does not screen. Kept narrow
# (second person + a recruitment object) so tour second-person framing ("as you
# look closer", "you can see the brushwork") is never dropped.
RECRUITMENT_SENTENCE_RE = re.compile(
    r"(?i)("
    r"\byou(?:'ll|\s+will|\s+can)?\s+(?:learn|study|gain|develop|acquire|"
    r"join|forge|build|launch|pursue|master|train|graduate|enrol|enroll|apply)\b|"
    r"\bstudy\s+(?:with|at|under|alongside|in\s+the\s+heart\s+of)\b|"
    r"\bforge\s+a\s+career\b|\blaunch\s+your\s+career\b|\bbuild\s+a\s+career\b|"
    r"\bcareer\s+in\s+the\b|"
    r"\b(?:enrol|enroll|apply)\s+(?:now|today|on(?:line)?)\b|"
    r"\bapply\s+for\s+(?:a|our|the)\b|"
    r"\bour\s+(?:world-?renowned|leading|flagship|degree)?\s*programmes?\b|"
    r"\bworld-?renowned\s+programmes?\b|"
    r"\bjoin\s+(?:us|our\s+community|a\s+community\s+of)\b"
    r")")


def strip_recruitment_sentences(text: str) -> tuple:
    """[LOCAL-626 item 3] Drop whole sentences in second-person marketing /
    recruitment register. Returns (cleaned_text, dropped_count). Pure: splits on
    sentence boundaries, drops any sentence RECRUITMENT_SENTENCE_RE matches, and
    rejoins — paragraph structure (blank lines) is preserved."""
    if not text or not RECRUITMENT_SENTENCE_RE.search(text):
        return text or "", 0
    dropped = 0
    out_paras = []
    for para in text.split("\n\n"):
        # Split into sentences keeping the terminator with each sentence.
        parts = re.split(r'(?<=[.!?])\s+', para)
        kept = []
        for p in parts:
            if p.strip() and RECRUITMENT_SENTENCE_RE.search(p):
                dropped += 1
                continue
            kept.append(p)
        out_paras.append(" ".join(k for k in kept if k is not None).strip()
                         if parts and len(parts) > 1 else "".join(kept))
    cleaned = "\n\n".join(out_paras)
    # Collapse any doubled spaces introduced by the drop.
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned, dropped

# Labels that are structure, not speech. Michael, 2026-08-24: Orientation and
# Directions stay, "because they let listeners know that they are not part of the
# stop description" — so they are deliberately absent here.
SPOKEN_LABEL_RE = re.compile(r'\b(?:Closing|Narration|Body|Summary)\s*:\s*')


# [LOCAL-879 §6] PROMOTIONAL / SUPERLATIVE marketing copy, unattributed, repeated
# as narration. Tour 547's Book Street carried "a diamond-valued location … a
# distinctive cultural brand of the city" and "the Notting Hill of Ho Chi Minh";
# Thi Bar carried "one of the only real gay bars". This is web promo copy, not a
# sourced fact. A SENTENCE carrying one of these promo markers is dropped from
# the spoken tour. Kept narrow (brochure superlatives / city-branding / "the X of
# Y" boosterism) so an ordinary descriptive sentence is never dropped.
PROMOTIONAL_SENTENCE_RE = re.compile(
    r"(?i)("
    r"\bdiamond[- ]valued\b"
    r"|\bdistinctive cultural brand\b"
    r"|\bcultural brand of the\b"
    r"|\bthe notting hill of\b"
    r"|\bthe (?:paris|venice|london|champs[- ]?élysées|times square) of\b"
    r"|\bone of the only\b"
    # [LOCAL-880 §8] extend the promo filter: wave 38 Stop 8 "You can't miss this
    # unique multi-story complex" and Stop 3 "recognized as a distinctive cultural
    # brand" (the latter already caught by 'distinctive cultural brand' above).
    r"|\bcan'?t\s+miss\b"
    r"|\byou\s+(?:simply\s+)?(?:can'?t|cannot|won'?t\s+want\s+to)\s+miss\b"
    r"|\brecognized as a (?:distinctive|unique|famous)\b"
    r"|\ba?\s*(?:true|real) (?:hidden )?(?:gem|paradise|oasis|haven)\b"
    r"|\b(?:world[- ]?class|must[- ]see|must[- ]visit|iconic destination|"
    r"premier destination|unrival+ed|unparalleled|second to none|"
    r"crown jewel|jewel in the crown|bustling hub of|vibrant hub of)\b"
    r"|\bnot to be missed\b"
    r")")


def strip_promotional_sentences(text: str) -> tuple:
    """[LOCAL-879 §6] Drop whole sentences carrying unattributed promotional /
    superlative marketing copy. Returns (cleaned_text, dropped_count). Pure:
    splits on sentence boundaries, drops any sentence PROMOTIONAL_SENTENCE_RE
    matches, rejoins; paragraph structure is preserved."""
    if not text or not PROMOTIONAL_SENTENCE_RE.search(text):
        return text or "", 0
    try:
        from sentence_split import split_sentences as _ss
    except Exception:  # pragma: no cover
        _ss = lambda t: re.split(r'(?<=[.!?])\s+', t)
    dropped = 0
    out_paras = []
    for para in text.split("\n\n"):
        # Preserve a leading structural label on a line ("Orientation:").
        parts = _ss(para)
        if len(parts) <= 1:
            # Single fragment: still drop it if it is pure promo, else keep.
            if para.strip() and PROMOTIONAL_SENTENCE_RE.search(para) \
                    and not re.match(r"(?i)^\s*(orientation|directions|coordinates"
                                     r"|type/specialty|specific examples|address"
                                     r"|sources?|stop\s*\d+)\s*:", para):
                dropped += 1
                out_paras.append("")
            else:
                out_paras.append(para)
            continue
        kept = []
        for p in parts:
            if p.strip() and PROMOTIONAL_SENTENCE_RE.search(p):
                dropped += 1
                continue
            kept.append(p)
        out_paras.append(" ".join(k for k in kept if k).strip())
    cleaned = "\n\n".join(out_paras)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, dropped


# ─── [LOCAL-880 §2] TRUNCATED SENTENCE — never end on an adjective/determiner ───
#
# Wave 38 Stop 1 shipped "…French architect Jules Bourard won with a proposal
# inspired directly by the iconic." The object of "the iconic" (Notre-Dame de
# Paris) was cut, leaving a sentence that ends on a determiner+adjective with no
# noun. A sentence must never end on a determiner, a preposition, or a bare
# adjective that is clearly expecting a noun. Such a sentence is a fragment: it is
# DROPPED (we cannot know the missing noun, and a guess would be invention).
#
# Deterministic and narrow: only a sentence ending in one of these clear
# dangles — "the iconic", "by the", "inspired by the famous", "such as the" —
# is dropped. An ordinary sentence ending on a noun/verb/adverb is untouched.
_TRUNCATED_TAIL_RE = re.compile(
    r"(?i)\b(?:"
    r"the|a|an|this|that|these|those|its|his|her|their|our|your|"          # determiner
    r"of|by|with|from|to|for|in|on|at|as|into|onto|upon|than|"            # preposition
    r"and|or|but|"                                                        # conjunction
    r"iconic|famous|renowned|celebrated|legendary|nearby|adjacent|"       # dangling adj
    r"original|various|several|certain|such|other|another|same|"
    r"grand|great|vast|huge|tall|large|small|ancient|historic"
    r")\s*[.!?]\s*$")
# an adjective directly before the terminator, preceded by a determiner, with no
# noun: "...by the iconic.", "...a proposal inspired directly by the iconic."
_DET_ADJ_TAIL_RE = re.compile(
    r"(?i)\b(?:the|a|an|this|that|its|his|her|their|our|your)\s+"
    r"(?:[a-zà-ÿ]+ly\s+)?"
    r"(?:iconic|famous|renowned|celebrated|legendary|original|grand|great|"
    r"magnificent|striking|elegant|classic|historic|ancient|modern|"
    r"distinctive|monumental)\s*[.!?]\s*$")


def strip_truncated_tail_sentences(text: str) -> tuple:
    """[LOCAL-880 §2] Drop a sentence that ends on a determiner / preposition /
    conjunction / dangling adjective expecting a noun that was cut off. Returns
    (cleaned, dropped). Pure; preserves paragraph and label structure."""
    if not text:
        return text or "", 0
    try:
        from sentence_split import split_sentences as _ss
    except Exception:  # pragma: no cover
        _ss = lambda t: re.split(r'(?<=[.!?])\s+', t)

    def _is_truncated(s: str) -> bool:
        s = s.strip()
        if not s:
            return False
        return bool(_TRUNCATED_TAIL_RE.search(s) or _DET_ADJ_TAIL_RE.search(s))

    dropped = 0
    out_paras = []
    for para in text.split("\n\n"):
        if re.match(r"(?i)^\s*(orientation|directions|coordinates|type/specialty"
                    r"|specific examples|address|sources?|stop\s*\d+)\s*:", para):
            # a labelled line: still scrub a trailing truncated sentence inside it
            # but keep the label; handle via sentence split below only for the
            # prose part after an Orientation: label.
            m = re.match(r"(?i)^(\s*orientation:\s*)(.*)$", para, re.S)
            if m and m.group(2).strip():
                kept = []
                for p in _ss(m.group(2)):
                    if _is_truncated(p):
                        dropped += 1
                        continue
                    kept.append(p)
                out_paras.append(m.group(1) + " ".join(k for k in kept if k).strip())
                continue
            out_paras.append(para)
            continue
        parts = _ss(para)
        kept = []
        for p in parts:
            if _is_truncated(p):
                dropped += 1
                continue
            kept.append(p)
        out_paras.append(" ".join(k for k in kept if k).strip())
    cleaned = "\n\n".join(out_paras)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, dropped


# ─── [LOCAL-880 §3] FOLKLORE DISCLOSURE (D760) or drop ──────────────────────────
#
# Wave 38 Stop 1 stated a legend flat: "Witnesses have reported a mysterious
# single tear shedding from a statue here." A miracle/legend must be DISCLOSED as
# such (D760 — "A story told in 2005 claims…"), not asserted as fact. With no year
# to anchor the disclosure we prefix a neutral "According to a local legend,"; the
# known Saigon case (the 2005 Notre-Dame statue-tear rumour) gets the dated form.
_FOLKLORE_CUE_RE = re.compile(
    r"(?i)\b(?:a )?(?:mysterious|miraculous|unexplained)\b[^.]*\b"
    r"(?:tear|weeping|wept|crying|cried|bleeding|bled|apparition|miracle|ghost|"
    r"haunt\w*)\b"
    r"|\bwitnesses have reported\b"
    r"|\bis said to (?:weep|cry|bleed|shed a tear|heal|grant)\b"
    r"|\breported (?:a )?(?:mysterious|miraculous)\b")
_ALREADY_DISCLOSED_RE = re.compile(
    r"(?i)^\s*(?:according to|a (?:story|legend|rumou?r) (?:told|that)|"
    r"legend (?:has it|says|holds)|local (?:lore|legend)|it is said|"
    r"some say|tradition holds|folklore)\b")


def disclose_or_drop_folklore(text: str, *, drop: bool = False) -> tuple:
    """[LOCAL-880 §3] Disclose a flatly-stated miracle/legend sentence (D760) by
    prefixing a 'According to a local legend,' (or the dated form for the known
    2005 statue-tear rumour), or DROP it when ``drop=True``. Returns
    (cleaned, n_changed). Idempotent (an already-disclosed sentence is skipped)."""
    if not text or not _FOLKLORE_CUE_RE.search(text):
        return text or "", 0
    try:
        from sentence_split import split_sentences as _ss
    except Exception:  # pragma: no cover
        _ss = lambda t: re.split(r'(?<=[.!?])\s+', t)
    changed = 0
    out_paras = []
    for para in text.split("\n\n"):
        label = ""
        body = para
        m = re.match(r"(?i)^(\s*orientation:\s*)(.*)$", para, re.S)
        if m:
            label, body = m.group(1), m.group(2)
        parts = _ss(body)
        new_parts = []
        for p in parts:
            ps = p.strip()
            if ps and _FOLKLORE_CUE_RE.search(ps) and not _ALREADY_DISCLOSED_RE.match(ps):
                if drop:
                    changed += 1
                    continue
                # dated disclosure for the known 2005 Saigon statue-tear rumour
                if re.search(r"(?i)\btear\b", ps) and re.search(r"(?i)\bstatue\b", ps):
                    lead = "A story told in 2005 claims that "
                else:
                    lead = "According to a local legend, "
                low = ps[0].lower() + ps[1:]
                new_parts.append(lead + low)
                changed += 1
            else:
                new_parts.append(p)
        rebuilt = " ".join(x for x in new_parts if x and x.strip()).strip()
        out_paras.append((label + rebuilt) if label else rebuilt)
    cleaned = "\n\n".join(out_paras)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, changed


# ─── [LOCAL-880 §1] CONTRADICTED FORMER-USE — drop even if the correct fact is
#     also present. Belt-and-braces to the claim-gate fix, applied to the final
#     assembled text per stop block. Wave 38 Stop 5 shipped BOTH the sourced
#     "once housed the United States Information Agency" AND the false "served as
#     the US military's intelligence headquarters" in the same paragraph. When a
#     stop block names the Information Agency, drop any sentence in THAT block
#     that calls the building an intelligence headquarters/HQ. ──────────────────
_INTEL_HQ_SENT_RE = re.compile(
    r"(?i)\bintelligence\s+(?:headquarters|hq|agency|service|centre|center)\b")
_INFO_AGENCY_SENT_RE = re.compile(
    r"(?i)\b(?:united states information agency|u\.?\s?s\.?\s?i\.?\s?a\.?|"
    r"information agency)\b")
_STOP_HEADER_SPLIT_RE = re.compile(r"(?mi)^(Stop\s+\d+:\s*.+)$")


def _iter_stop_blocks(text: str):
    """Yield (header_or_None, block_text): the preamble, then each 'Stop N:'
    header with the text up to the next header."""
    parts = _STOP_HEADER_SPLIT_RE.split(text or "")
    yield (None, parts[0])
    i = 1
    while i < len(parts):
        hdr = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        yield (hdr, body)
        i += 2


def strip_contradicted_former_use(text: str) -> tuple:
    """[LOCAL-880 §1] Within any stop block that names the Information Agency as
    the building's former use, drop any sentence that instead calls it an
    intelligence headquarters. Returns (cleaned, dropped). Self-contained."""
    if not text or not _INTEL_HQ_SENT_RE.search(text):
        return text or "", 0
    try:
        from sentence_split import split_sentences as _ss
    except Exception:  # pragma: no cover
        _ss = lambda t: re.split(r'(?<=[.!?])\s+', t)
    dropped = 0
    out = []
    for hdr, body in _iter_stop_blocks(text):
        if hdr:
            out.append(hdr)
        if body and _INTEL_HQ_SENT_RE.search(body) and _INFO_AGENCY_SENT_RE.search(body):
            new_paras = []
            for para in body.split("\n\n"):
                if re.match(r"(?i)^\s*(coordinates|type/specialty|specific examples"
                            r"|directions|address|sources?)\s*:", para):
                    new_paras.append(para)
                    continue
                label = ""
                seg = para
                m = re.match(r"(?i)^(\s*orientation:\s*)(.*)$", para, re.S)
                if m:
                    label, seg = m.group(1), m.group(2)
                kept = []
                for p in _ss(seg):
                    if p.strip() and _INTEL_HQ_SENT_RE.search(p):
                        dropped += 1
                        continue
                    kept.append(p)
                new_paras.append((label + " ".join(k for k in kept if k).strip())
                                 if label else " ".join(k for k in kept if k).strip())
            out.append("\n\n".join(new_paras))
        else:
            out.append(body)
    cleaned = "".join(out)
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned)
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, dropped


# ─── [LOCAL-880 §10] OPERA HOUSE GOVERNMENT USE — the evidence says it housed the
#     Lower House of the National Assembly (1956–75), NOT that it was "the meeting
#     place for both houses". Correct the false claim in the Opera House block. ──
_BOTH_HOUSES_RE = re.compile(
    r"(?i)[^.]*\b(?:meeting place|seat|home)\b[^.]*\bfor both\b[^.]*\.")
_LEGISLATURE_SPLIT_RE = re.compile(
    r"(?i)[^.]*\b(?:meeting place|seat|home|transformed into|became)\b[^.]*"
    r"\bboth\b[^.]*?(?:houses|chambers)?[^.]*\.")
_OPERA_GOVT_FIX = (" From 1956 to 1975 the building housed the Lower House of "
                   "South Vietnam's National Assembly.")


def fix_opera_house_government_use(text: str) -> tuple:
    """[LOCAL-880 §10] Replace the false 'meeting place for both houses' claim in
    the Opera House block with the sourced fact (Lower House of the National
    Assembly, 1956–75). Returns (cleaned, n_fixed)."""
    if not text:
        return text or "", 0
    n = 0
    out = []
    for hdr, body in _iter_stop_blocks(text):
        if hdr:
            out.append(hdr)
        if hdr and re.search(r"(?i)opera", hdr) and body:
            new_body, c1 = _BOTH_HOUSES_RE.subn(_OPERA_GOVT_FIX, body)
            if c1 == 0:
                new_body, c1 = _LEGISLATURE_SPLIT_RE.subn(_OPERA_GOVT_FIX, body)
            n += c1
            out.append(new_body)
        else:
            out.append(body)
    cleaned = re.sub(r"[ \t]{2,}", " ", "".join(out))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, n


# ─── [LOCAL-880 §9] UNSOURCED SEATING CAPACITY — state a number only if sourced.
#     Wave 38 said "500-seat"; wave 37 said ~800 — it varies run to run, so it is
#     not reliably sourced. Keep the number ONLY if it appears in the stop's
#     evidence; else drop the number, keep the sentence. ───────────────────────
_CAPACITY_RE = re.compile(
    r"(?i)(?:around |about |approximately |roughly |nearly )?"
    r"(\d{3,4})[- ]?(?:seat|seats|seater)\b"
    r"|\bseat(?:ed|s|ing)?\s+(?:around |about |approximately |roughly )?(\d{3,4})\b")


def audit_seating_capacity(text: str, evidence_text: str = "") -> tuple:
    """[LOCAL-880 §9] For the Opera House block, keep a seating-capacity number
    ONLY if that exact figure appears in ``evidence_text``; else rewrite to drop
    the number. Returns (cleaned, report) with 'kept'/'removed'/'source_sentence'."""
    rep = {"kept": None, "removed": None, "source_sentence": ""}
    if not text:
        return text or "", rep
    ev = (evidence_text or "")
    ev_nums = set(re.findall(r"(\d{3,4})\s*(?:seat|seats|seater|people|persons)",
                             ev.lower()))
    out = []
    for hdr, body in _iter_stop_blocks(text):
        if hdr:
            out.append(hdr)
        if hdr and re.search(r"(?i)opera", hdr) and body and _CAPACITY_RE.search(body):
            def _repl(m):
                num = m.group(1) or m.group(2)
                if num and num in ev_nums:
                    rep["kept"] = num
                    for sent in re.split(r'(?<=[.!?])\s+', ev):
                        if num in sent and re.search(r"(?i)seat", sent):
                            rep["source_sentence"] = sent.strip()[:200]
                            break
                    return m.group(0)
                rep["removed"] = num
                whole = m.group(0)
                if re.search(r"(?i)seat(?:ed|ing)?", whole):
                    return "venue"
                return "venue"
            new_body = _CAPACITY_RE.sub(_repl, body)
            new_body = re.sub(r"(?i)\ba\s+venue\s+venue\b", "a venue", new_body)
            new_body = re.sub(r"(?i)\bvenue\s+venue\b", "venue", new_body)
            out.append(new_body)
        else:
            out.append(body)
    cleaned = re.sub(r"[ \t]{2,}", " ", "".join(out))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned, rep


# ─── [LOCAL-880 §4] ORIENTATION FILLER — never ship the placeholder ────────────
_ORIENTATION_FILLER_RE = re.compile(
    r"(?im)^\s*Orientation:\s*Position yourself to best view this location\.?\s*$")
_ORIENTATION_FILLER_INLINE_RE = re.compile(
    r"(?i)\bPosition yourself to best view this location\.?\s*")


def strip_orientation_filler(text: str) -> tuple:
    """[LOCAL-880 §4] Remove the 'Position yourself to best view this location.'
    placeholder. A whole Orientation line that is ONLY the filler is removed; an
    inline occurrence is stripped. Returns (cleaned, n_removed)."""
    if not text or "Position yourself to best view this location" not in text:
        return text or "", 0
    n = len(_ORIENTATION_FILLER_RE.findall(text)) + \
        len(_ORIENTATION_FILLER_INLINE_RE.findall(text))
    out = _ORIENTATION_FILLER_RE.sub("", text)
    out = _ORIENTATION_FILLER_INLINE_RE.sub("", out)
    out = re.sub(r"(?im)^\s*Orientation:\s*$\n?", "", out)  # empty label left behind
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n{3,}", "\n\n", out)
    return out, n


# ─── [LOCAL-880 §5] INTRO GRAMMAR — the opening title line ─────────────────────
# Wave 38 opened "Step-by-step audio guided tour of Ho Chi Minh City, Vietnam, is
# a walking tour." (a subject with no predicate agreement). Wave 37 had a bare
# fragment "…Vietnam, walking tour." Normalise to a clean sentence.
_INTRO_BROKEN_RE = re.compile(
    r"(?im)^\s*Step-by-step audio[- ]?guided tour of (.+?)[,.]?\s*"
    r"(?:is a |,\s*)?(walking|biking|cycling|driving|road[- ]?trip)\s+tour\.?\s*$")


def fix_intro_grammar(text: str) -> tuple:
    """[LOCAL-880 §5] Rewrite a broken opening line into a clean sentence:
    'This is a step-by-step audio-guided walking tour of <place>.' Returns
    (cleaned, n_fixed). Only the first matching line is touched."""
    if not text:
        return text or "", 0
    m = _INTRO_BROKEN_RE.search(text)
    if not m:
        return text, 0
    place = m.group(1).strip().rstrip(",").strip()
    mode = m.group(2).strip().lower()
    fixed = f"This is a step-by-step audio-guided {mode} tour of {place}."
    return text[:m.start()] + fixed + text[m.end():], 1


# ─── [LOCAL-880 §6] ORPHAN CLOSING — name real threads or a clean one-line close ─
# LOCAL-879 removed the circular "one thread runs through: the places you chose"
# lead-in and left the fragment "Each was picked by you, and together they trace
# your own route through the city." Replace that orphan with a clean close that
# names up to three real stop titles from the tour.
_ORPHAN_CLOSING_RE = re.compile(
    r"(?i)\s*Each was picked by you, and together they trace your own route "
    r"through the city\.\s*")


def fix_orphan_closing(text: str, stop_titles=None) -> tuple:
    """[LOCAL-880 §6] Replace the orphan closing fragment with a clean close. When
    2–3 real stop titles are given, name them; else a clean one-line close.
    Returns (cleaned, n_fixed)."""
    if not text or not _ORPHAN_CLOSING_RE.search(text):
        return text or "", 0
    titles = [t.strip() for t in (stop_titles or []) if t and t.strip()]
    # prefer first and last and a distinctive middle one
    picked = []
    if len(titles) >= 2:
        picked = [titles[0], titles[-1]]
        if len(titles) >= 5:
            picked.insert(1, titles[len(titles) // 2])
    if picked:
        names = ", ".join(picked[:-1]) + f" and {picked[-1]}" if len(picked) > 1 else picked[0]
        close = (f"From {names}, this route is the one you chose through the city. "
                 f"That is your tour.")
    else:
        close = "This route is the one you chose through the city."
    out = _ORPHAN_CLOSING_RE.sub(" " + close + " ", text)
    out = re.sub(r"[ \t]{2,}", " ", out)
    return out, 1


# ─── [LOCAL-880 §7] CURRENT-AFFAIRS NOTE — omit when nothing was found ──────────
# Wave 38 appended "A note on current affairs: … we found no verified developments
# from the past five years…". Say the note only when there IS something to say;
# drop the empty disclaimer.
_CURRENT_AFFAIRS_EMPTY_RE = re.compile(
    r"(?is)\s*A note on current affairs:\s*.*?"
    r"(?:no verified developments|nothing (?:verified|to report)|"
    r"found no (?:verified )?(?:developments|updates|news))"
    r".*?(?:\.|current local news source\.?)\s*")


def strip_empty_current_affairs_note(text: str) -> tuple:
    """[LOCAL-880 §7] Remove a current-affairs note that reports nothing was
    found. Returns (cleaned, n_removed)."""
    if not text or "note on current affairs" not in text.lower():
        return text or "", 0
    out, n = _CURRENT_AFFAIRS_EMPTY_RE.subn("", text)
    out = re.sub(r"\n{3,}", "\n\n", out).rstrip() + ("\n" if text.endswith("\n") else "")
    return out, n


# -------- [LOCAL-623 defect 4] Strip provenance / citation tails from speech ---
#
# Tour 468 spoke "An optional climate contribution ticket can be added for €1, as
# published by the museum in October 2026." — a source-citation tail a listener
# hears aloud. Provenance (what source stated the fact, and when) belongs in the
# TEXT-view Sources line, never in speech (the same rule D617 used to move the
# source DOMAIN out of narration). This strips the trailing clause, keeping the
# fact: "…added for €1."  The patterns match the honesty-stamp phrasings the
# pipeline emits ("as published/listed/stated/noted by the museum in <month> <yr>",
# with or without the month) and are collapsed to the preceding sentence end.
CITATION_TAIL_RE = re.compile(
    r'\s*[,;]?\s*as\s+(?:published|listed|stated|noted|reported|confirmed|'
    r'recorded|advertised|shown|given)\s+'
    r'(?:by|on|in|at|per)\s+'
    r'(?:[^.?!]|\.(?=[A-Za-z0-9]))*?'   # tolerate domain dots ("griffinmuseum.org")
    r'(?:in\s+[A-Z][a-z]+\s+\d{4}|\d{4})?\s*'
    r'(?=[.?!](?:\s|$|["”\')])|$)',     # a SENTENCE terminator, not a domain dot
    re.IGNORECASE)

# A bare "(as of October 2026)" / ", as of October 2026" dateline tail.
AS_OF_TAIL_RE = re.compile(
    r'\s*[,(]?\s*as\s+of\s+(?:[A-Z][a-z]+\s+)?\d{4}\s*\)?(?=[.?!]|$)',
    re.IGNORECASE)


def strip_citation_tails(text: str) -> tuple:
    """Remove spoken provenance/citation tails ("as published by the museum in
    October 2026", "as of October 2026") from narration, keeping the fact itself.

    Returns ``(cleaned, n_removed)``. Deterministic and pure. Only the trailing
    attribution clause is removed; the sentence's terminal punctuation is kept.
    """
    if not text:
        return text or '', 0
    removed = 0

    def _sub(m):
        nonlocal removed
        removed += 1
        return ''

    out = CITATION_TAIL_RE.sub(_sub, text)
    out = AS_OF_TAIL_RE.sub(_sub, out)
    if removed:
        out = re.sub(r'\s+([.,;:!?])', r'\1', out)
        out = re.sub(r'  +', ' ', out)
    return out, removed


# -------- [LOCAL-529] One name, four spellings --------------------------------
#
# The round-7 critique (LOCAL-517) found Logan's original airfield name spelled
# four ways across the batch — and, worst of all, TWICE inside ONE tour:
# LOGAN_1 says "Boston Air Port, also called Jefferies Field" in its Concourse
# stop and "marked Jeffrey Field, as it was then known" in its Control Tower stop.
# A listener who hears one tour name a place two ways has caught the system being
# careless. Jeffery (LOGAN_2 x2) and Jeffries (LOGAN_3 x1) are internally
# consistent within their own files; the defect is WITHIN a tour, not across the
# batch, so the repair is within a tour too.
#
# Two hard constraints, both from the critique's own acceptance note:
#   • "Jeffries Point" (a real East Boston neighbourhood) is NOT the airfield
#     "Jeffrey Field" — different head noun, must survive untouched.
#   • "Logan" and "Logan Airport" are not the same token; two different people
#     with similar surnames must both survive.
#
# So the grouping key is the HEAD NOUN that immediately follows the name
# (Field vs Point), and only names that are near-identical spellings of each
# other — same first letter, within a small edit distance, same length class —
# are ever pooled. Distinct names never collide because they are not near-
# identical; same name under a different head noun never collides because the
# head noun keys them apart.
#
# This never invents a spelling and never reaches outside the text for a "true"
# one (Gemini is down and the task is deterministic by charter). It only makes a
# single tour agree with itself: the winner is the spelling that already appears
# most often IN THIS TOUR, ties broken by first appearance so the earliest-heard
# spelling is the one that stays.

# A proper-noun modifier (one capitalised word, optionally hyphenated/apostrophe'd)
# directly in front of a capitalised HEAD noun: "Jefferies Field", "Jeffries Point".
_NAME_BEFORE_HEAD_RE = re.compile(
    r"\b([A-Z][a-zà-ÿ]+(?:['\-][A-Za-zà-ÿ]+)?)\s+"
    r"(Field|Point|Airfield|Airport|Terminal|Tower|Square|Station|Park|Hall|"
    r"Street|Avenue|Bridge|Harbor|Harbour|Island|Gallery|Museum|Cathedral|"
    r"Church|Chapel|College|University|Hospital|Building|Wing|Center|Centre)\b")


def _shared_prefix_len(a: str, b: str) -> int:
    a, b = a.lower(), b.lower()
    n = 0
    for x, y in zip(a, b):
        if x == y:
            n += 1
        else:
            break
    return n


def _edit_distance_le(a: str, b: str, limit: int = 2) -> bool:
    """True if a and b are within `limit` single-character edits (Levenshtein).

    Case-insensitive; callers only ever pass tokens that both began capitalised.
    """
    a, b = a.lower(), b.lower()
    if a == b:
        return True
    la, lb = len(a), len(b)
    if abs(la - lb) > limit:
        return False
    prev = list(range(lb + 1))
    for i in range(1, la + 1):
        cur = [i] + [0] * lb
        best = cur[0]
        for j in range(1, lb + 1):
            cost = 0 if a[i - 1] == b[j - 1] else 1
            cur[j] = min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + cost)
            if cur[j] < best:
                best = cur[j]
        if best > limit:
            return False
        prev = cur
    return prev[lb] <= limit


# Small, auditable anchor sets for spelling families that the general rule cannot
# link on string distance alone because their two extremes are 3 edits apart
# (e.g. "Jefferies" vs "Jeffrey"). This is the same layered idea as
# `known_fact_corrections`: a specific, evidence-backed table on top of a general
# mechanism. It does NOT pick the winner — the winner is still whatever the tour
# uses most, ties to the earliest. It only says "these are the same name".
#   Evidence: CRITIQUE_ROUND7_517.md and TOURS_FOR_REVIEW/round7/LOGAN_{1,2,3}.txt
#   — Jefferies (LOGAN_1), Jeffery (LOGAN_2 x2), Jeffrey (LOGAN_1), Jeffries
#     (LOGAN_3, but as "Jeffries Point" — a different HEAD noun, so never pooled
#     with the airfield "* Field" mentions by construction).
_NAME_ANCHOR_FAMILIES = [
    {'jefferies', 'jeffery', 'jeffrey', 'jeffries'},
]


def _anchor_family(name: str):
    low = name.lower()
    for fam in _NAME_ANCHOR_FAMILIES:
        if low in fam:
            return id(fam)
    return None


def _names_are_near_identical(a: str, b: str) -> bool:
    """Two proper-noun spellings of (very probably) the SAME name.

    Tight by design — a false positive here merges two distinct names, which the
    task forbids. Three independent ways to qualify, all conservative:
      1. Same known anchor family (Jefferies/Jeffery/Jeffrey/Jeffries).
      2. Within 2 edits AND agreeing on a >=3-character prefix. The prefix guard
         is what rejects Channing/Manning (0 prefix) and Boston/Weston (0),
         while the distance guard rejects Jefferson/Jefferies (3 edits).
      3. Identical (covered by rule 2's distance 0).
    """
    if a == b:
        return True
    fa, fb = _anchor_family(a), _anchor_family(b)
    if fa is not None and fa == fb:
        return True
    return _edit_distance_le(a, b, 2) and _shared_prefix_len(a, b) >= 3


def normalize_proper_noun_spellings(text: str):
    """Make a single tour agree with itself on near-identical proper nouns.

    Returns (normalized_text, report). `report['groups']` lists one entry per
    name group that actually had more than one spelling:
    {'head', 'winner', 'changed': [(from, to, count), ...]}.

    Never touches a name that appears only one way, never merges names under
    different head nouns (Field vs Point), never merges names that are not
    near-identical spellings of one another.
    """
    report = {'groups': []}
    if not text:
        return text or '', report

    # 1. Collect every "<Name> <Head>" mention, keyed by the head noun.
    #    buckets[head] = {name: [first_index, count]}
    buckets = defaultdict(dict)
    for m in _NAME_BEFORE_HEAD_RE.finditer(text):
        name, head = m.group(1), m.group(2)
        rec = buckets[head].setdefault(name, [m.start(), 0])
        rec[1] += 1

    # 2. Within each head-noun bucket, cluster names that are near-identical
    #    spellings. A cluster with a single spelling is left alone.
    replacements = {}  # (name, head) -> winning_name
    for head, names in buckets.items():
        items = list(names.items())  # [(name, [first_index, count]), ...]
        used = [False] * len(items)
        for i in range(len(items)):
            if used[i]:
                continue
            cluster = [i]
            used[i] = True
            for j in range(i + 1, len(items)):
                if used[j]:
                    continue
                if any(_names_are_near_identical(items[k][0], items[j][0])
                       for k in cluster):
                    cluster.append(j)
                    used[j] = True
            if len(cluster) < 2:
                continue  # only one spelling of this name — nothing to fix
            members = [items[k] for k in cluster]
            # Winner: most frequent; ties broken by earliest appearance.
            winner = min(members, key=lambda it: (-it[1][1], it[1][0]))[0]
            changed = []
            for name, (first_idx, count) in members:
                if name != winner:
                    replacements[(name, head)] = winner
                    changed.append((name, winner, count))
            if changed:
                report['groups'].append(
                    {'head': head, 'winner': winner, 'changed': changed})

    if not replacements:
        return text, report

    # 3. Apply — only the exact "<Name> <Head>" pairs we decided on. A bare
    #    "Jeffery" with no head noun, or the same word before a different head,
    #    is never touched.
    def _sub(m):
        name, head = m.group(1), m.group(2)
        win = replacements.get((name, head))
        return f"{win} {head}" if win else m.group(0)

    out = _NAME_BEFORE_HEAD_RE.sub(_sub, text)
    return out, report


# -------- [LOCAL-602 r2 / D617 item 9] No URL, no "Sources" in spoken text ----
#
# A listener never hears a URL. The r1 WNDR run's spoken audio_N.txt files carried
# the venue's own-page URLs and a trailing "Sources:" block verbatim, because the
# packer (break_text_to_pois.process_tour_file) writes each stop's text to disk
# unchanged. A speech synthesiser reads "https colon slash slash wndrmuseum dot
# com slash installations slash boston slash flex" aloud — unlistenable. Sources
# belong in the TEXT view (the web page / full tour text), as one short line; they
# are never spoken.
#
# This strip is deterministic and runs in the packer, on each stop's spoken text,
# AFTER every content gate has had its say. It removes:
#   * a trailing "Sources:" / "Sources (…):" block to the next blank line / end
#     (the block the generator folds after the last stop, and any per-stop variant);
#   * every bare http(s):// or www. URL token anywhere in the body;
#   * a now-empty bullet / "Source:" label left behind.

# A "Sources" heading in any of the shapes the pipeline emits:
#   "Sources:", "Sources (the museum's own pages):", "Source:".
SOURCES_HEADING_RE = re.compile(
    r'(?is)^[\t ]*sources?\b[^\n:]*:.*?(?=\n[\t ]*\n|\Z)', re.MULTILINE)

# A URL: http(s):// … or a bare www. … up to whitespace or a closing bracket.
URL_RE = re.compile(r'(?i)\b(?:https?://|www\.)[^\s<>()\[\]"\']+')

# A list bullet or inline "Source:" label whose URL we just removed.
_EMPTY_SOURCE_LINE_RE = re.compile(
    r'(?im)^[\t ]*(?:[-*\u2022]\s*)?(?:source\s*:)?\s*$')


def strip_sources_and_urls(text: str) -> tuple:
    """Remove every URL and any 'Sources:' block from SPOKEN text.

    Returns ``(cleaned, report)`` with ``report = {'urls': n, 'sources_blocks': n}``.
    Deterministic and side-effect free. Used by the packer so no spoken
    ``audio_N.txt`` ever contains ``http``/``www.`` or a read-aloud source list
    (D617 item 9). The full-text / web view keeps its Sources line; only the
    SPOKEN file is stripped.
    """
    report = {'urls': 0, 'sources_blocks': 0}
    if not text:
        return text or '', report

    ends_nl = text.endswith('\n')
    out = text
    # 1. "Sources:" block(s) — heading to the next blank line or end of text.
    report['sources_blocks'] = len(SOURCES_HEADING_RE.findall(out))
    out = SOURCES_HEADING_RE.sub('', out)

    # 2. Any remaining bare URLs anywhere in the body.
    report['urls'] = len(URL_RE.findall(out))
    out = URL_RE.sub('', out)

    # 3. Tidy up bullets / "Source:" labels orphaned by the URL removal and
    #    collapse the blank-line gaps the removals leave behind.
    out = _EMPTY_SOURCE_LINE_RE.sub('', out)
    out = re.sub(r'(?im)^[\t ]*source\s*:\s*$', '', out)
    out = re.sub(r'[ \t]+\n', '\n', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    out = out.strip()
    return (out + '\n') if ends_nl else out, report


# -------- [LOCAL-602 r2 / D617 item 12] No "From X to X" recap under 2 stops ---
#
# The single-story recap reads "From {first} to {last}, you have followed the
# thread of a single story." With ONE stop first == last and it becomes "From
# WNDR Museum — Overview to WNDR Museum — Overview, you have followed …" — a
# nonsense sentence the r1 overview shipped. The assembler-level guards
# (stop_pool_assembly._closing_recap, tour_cache_layer1._repair_recap) prevent it
# at the source; this is a tour-wide safety net for any path that still emits it:
# remove the whole recap sentence when its two endpoints are the SAME stop.

_FROM_TO_RECAP_RE = re.compile(
    r'(?is)(?<![^.\s])From\s+(.+?)\s+to\s+(.+?),\s*you have followed[^.?!]*[.?!]')


def _norm_endpoint(s: str) -> str:
    return re.sub(r'\s+', ' ', (s or '')).strip().lower().rstrip('.')


def strip_degenerate_from_to_recap(text: str) -> tuple:
    """Remove a 'From X to Y, you have followed …' recap when X == Y.

    Returns ``(cleaned, n_removed)``. Deterministic, pure. A genuine multi-stop
    recap (X != Y) is left untouched.
    """
    if not text:
        return text or '', 0
    removed = 0

    def _sub(m):
        nonlocal removed
        if _norm_endpoint(m.group(1)) == _norm_endpoint(m.group(2)):
            removed += 1
            return ''
        return m.group(0)

    out = _FROM_TO_RECAP_RE.sub(_sub, text)
    if removed:
        out = re.sub(r'[ \t]+\n', '\n', out)
        out = re.sub(r'\n{3,}', '\n\n', out)
        out = out.strip() + ('\n' if text.endswith('\n') else '')
    return out, removed


# -------- [LOCAL-618 #2] Deterministic grammar & splice lint ------------------
#
# The critic's Sevilla runs shipped garbled clauses: "Gertrud Dübi…-Müller first
# came into the world" (an ellipsis-hyphen splice), sentences with no verb,
# dangling fragments, and a stray opening quote with no close. No gate was reading
# the FINAL spoken text as grammar. This lint flags four deterministic defect
# classes per sentence, then DROPS the flagged sentence (or hands exactly one to a
# cheap, metered LLM rewrite if a rewrite_fn is supplied). Pure except for the
# optional injected rewrite_fn, so the rules are unit-tested offline.

# An ellipsis / stray dots fused to a hyphen inside or between words:
#   "Dübi…-Müller", "Dübi...-Müller", "text .-and"
_SPLICE_RE = re.compile(r'(?:\u2026|\.{2,})\s*-|-\s*(?:\u2026|\.{2,})')

# A finite-verb signal. If a sentence of real length contains none of these, it is
# almost certainly a dangling fragment (a caption, a stray noun phrase). Kept
# deliberately broad to avoid false drops: common auxiliaries, copulas, modals,
# and the regular -ed / -s verb endings are all treated as "has a verb".
_VERB_HINTS = {
    'is', 'are', 'was', 'were', 'be', 'been', 'being', 'am',
    'has', 'have', 'had', 'do', 'does', 'did',
    'will', 'would', 'shall', 'should', 'can', 'could', 'may', 'might', 'must',
    'make', 'makes', 'made', 'show', 'shows', 'see', 'stand', 'look', 'hold',
    'holds', 'held', 'paint', 'paints', 'painted', 'depict', 'depicts', 'come',
    'came', 'became', 'turns', 'turn', 'began', 'begin', 'find', 'finds',
    'carry', 'carries', 'carried', 'remains', 'remain', 'remained', 'sits',
    'sit', 'sat', 'lies', 'lie', 'rises', 'rose', 'took', 'take', 'takes',
    'gives', 'give', 'gave', 'tells', 'tell', 'told', 'wrote', 'write', 'writes',
    'built', 'build', 'opened', 'open', 'closed', 'founded', 'created', 'explore',
    'explores', 'reveals', 'reveal', 'captures', 'capture', 'offers', 'offer',
    # Common irregular past tenses — these have no -ed ending and would otherwise
    # read as "verbless" false positives (observed: "kept", "stood", "hung").
    'kept', 'keep', 'keeps', 'stood', 'hung', 'hangs', 'hang', 'went', 'go',
    'goes', 'ran', 'run', 'runs', 'won', 'win', 'lost', 'lose', 'sold', 'sell',
    'bought', 'buy', 'brought', 'bring', 'taught', 'teach', 'caught', 'catch',
    'left', 'leave', 'met', 'meet', 'set', 'put', 'cut', 'let', 'spent', 'spend',
    'sent', 'send', 'drew', 'draw', 'draws', 'drawn', 'grew', 'grow', 'grows',
    'knew', 'know', 'knows', 'saw', 'seen', 'fell', 'fall', 'falls', 'rose',
    'risen', 'spoke', 'speak', 'speaks', 'broke', 'break', 'breaks', 'chose',
    'choose', 'drove', 'drive', 'held', 'led', 'lead', 'leads', 'fled', 'flee',
    'became', 'becomes', 'become', 'stands', 'depicting', 'portrays', 'portray',
}


def _balanced(text: str) -> bool:
    """Parentheses and double-quote marks are balanced in `text`."""
    depth = 0
    for ch in text:
        if ch == '(':
            depth += 1
        elif ch == ')':
            depth -= 1
            if depth < 0:
                return False
    if depth != 0:
        return False
    # Straight double quotes must be even; curly open/close must match.
    if text.count('"') % 2 != 0:
        return False
    if text.count('\u201c') != text.count('\u201d'):
        return False
    return True


def _has_verb(sentence: str) -> bool:
    words = re.findall(r"[A-Za-zà-ÿ']+", sentence.lower())
    if not words:
        return False
    for w in words:
        if w in _VERB_HINTS:
            return True
        # Regular past-tense/participle ending on a word of real length. A bare
        # "-ing" gerund ("painting", "frame") is NOT counted — it is just as often
        # a noun, and counting it masks genuine verbless fragments.
        if len(w) > 3 and w.endswith('ed'):
            return True
        # 3rd-person-singular present ("serves", "fosters", "ranges", "invites").
        # Accept any -s word of real length that is not an obvious plural-only /
        # possessive form; a false accept (missing a true verbless fragment) is far
        # safer than a false reject (dropping a grammatical sentence).
        if len(w) > 3 and w.endswith('s') and not w.endswith('ss') and not w.endswith("'s"):
            return True
    return False


# A line that is practical-facts / structured data, not a prose sentence: hours,
# prices, GPS coordinates, admission lines. These legitimately lack a finite verb
# and legitimately repeat tokens (AM/PM, day names); the lint must leave them be.
_STRUCTURED_LINE_RE = re.compile(
    r'(?i)(\d{1,2}:\d{2}|\bGPS\b|coordinates|\$\d|admission|\bAM\b|\bPM\b|'
    r'\bopen\b.*\b(?:mon|tue|wed|thu|fri|sat|sun)|closed\s+(?:mon|tue|wed|thu|fri|sat|sun))')


def _repeated_word_pair(sentence: str) -> bool:
    """A consecutive repeated bigram: 'the the', 'came into came into'.

    Skipped entirely on structured/practical lines (hours, prices, coordinates),
    where day-name and AM/PM repetition is legitimate.
    """
    if _STRUCTURED_LINE_RE.search(sentence):
        return False
    words = [w.lower() for w in re.findall(r"[A-Za-zà-ÿ']+", sentence)]
    # Immediate single-word doubling.
    for i in range(len(words) - 1):
        if words[i] == words[i + 1] and len(words[i]) > 1:
            return True
    # Repeated adjacent bigram: w0 w1 w0 w1.
    for i in range(len(words) - 3):
        if words[i] == words[i + 2] and words[i + 1] == words[i + 3] and len(words[i]) > 1:
            return True
    return False


def flag_sentence(sentence: str) -> list:
    """Return a list of defect codes for a single sentence (empty = clean).

    Codes: 'splice', 'unbalanced', 'verbless', 'repeated_pair'. Short sentences
    (< 5 words) are exempt from the verbless check — labels, exclamations and
    one-clause pointers legitimately lack a finite verb.
    """
    codes = []
    s = sentence.strip()
    if not s:
        return codes
    if _SPLICE_RE.search(s):
        codes.append('splice')
    if not _balanced(s):
        codes.append('unbalanced')
    _nwords = len(re.findall(r"[A-Za-zà-ÿ']+", s))
    if _nwords >= 5 and not _STRUCTURED_LINE_RE.search(s) and not _has_verb(s):
        codes.append('verbless')
    if _repeated_word_pair(s):
        codes.append('repeated_pair')
    return codes


def grammar_splice_lint(text: str, rewrite_fn=None, verbose: bool = False) -> tuple:
    """Flag and repair garbled sentences in FINAL spoken text.

    For each sentence, `flag_sentence` reports deterministic defects. A flagged
    sentence is DROPPED, unless `rewrite_fn` is supplied — then exactly ONE flagged
    sentence (the first) is handed to the cheap LLM rewrite; if the rewrite comes
    back clean it replaces the original, otherwise the sentence is dropped. The
    rewrite is metered by the caller (rewrite_fn owns cost accounting).

    Returns ``(cleaned, report)`` where report = {
        'flagged': n, 'dropped': n, 'rewritten': n, 'by_code': {code: n}
    }. Deterministic given a deterministic rewrite_fn; pure when rewrite_fn is None.
    """
    report = {'flagged': 0, 'dropped': 0, 'rewritten': 0, 'by_code': {}}
    if not text or not text.strip():
        return text or '', report

    ends_nl = text.endswith('\n')
    # Work paragraph by paragraph so structure (labels, blank lines) is preserved.
    paragraphs = text.split('\n\n')
    out_paragraphs = []
    _rewrite_used = False

    for para in paragraphs:
        # Keep a leading structural label (Orientation:, Directions:) attached.
        label = ''
        body = para
        m = re.match(r'^([A-Z][a-z]+:\s*)', para)
        if m:
            label, body = m.group(1), para[m.end():]

        sentences = re.split(r'(?<=[.!?])\s+', body)
        kept = []
        for sent in sentences:
            codes = flag_sentence(sent)
            if not codes:
                kept.append(sent)
                continue
            report['flagged'] += 1
            for c in codes:
                report['by_code'][c] = report['by_code'].get(c, 0) + 1
            # Try a single cheap LLM rewrite, if offered and not yet used.
            if rewrite_fn is not None and not _rewrite_used:
                _rewrite_used = True
                try:
                    fixed = (rewrite_fn(sent) or '').strip()
                except Exception:
                    fixed = ''
                if fixed and not flag_sentence(fixed):
                    kept.append(fixed)
                    report['rewritten'] += 1
                    continue
            # Otherwise drop the flagged sentence.
            report['dropped'] += 1

        new_body = ' '.join(k.strip() for k in kept if k.strip())
        rebuilt = (label + new_body).strip()
        # Never let a repair empty a paragraph that had content: if everything was
        # dropped, keep the original paragraph rather than ship a hole.
        if not rebuilt and para.strip():
            rebuilt = para.strip()
            report['dropped'] = max(0, report['dropped'] - len(sentences))
        out_paragraphs.append(rebuilt)

    cleaned = '\n\n'.join(p for p in out_paragraphs)
    cleaned = re.sub(r'\n{3,}', '\n\n', cleaned).strip()
    if verbose and report['flagged']:
        print(f"  [LOCAL-618 #2] grammar/splice lint: {report['flagged']} flagged, "
              f"{report['dropped']} dropped, {report['rewritten']} rewritten "
              f"({report['by_code']})")
    return (cleaned + '\n') if ends_nl else cleaned, report


def clean_spoken_text(text: str, verbose: bool = False) -> tuple:
    """Return (cleaned, report). Never reorders, never rewrites — only repairs."""
    report = {'seams': 0, 'missing_spaces': 0, 'labels': 0, 'dangling': 0,
              'name_spellings': 0}
    if not text:
        return text or '', report

    report['seams'] = len(TEMPLATE_SEAM_RE.findall(text))
    out = TEMPLATE_SEAM_RE.sub(lambda m: m.group(1) + ' ', text)

    report['missing_spaces'] = len(MISSING_SPACE_RE.findall(out))
    out = MISSING_SPACE_RE.sub(r'\1. \2\3', out)

    report['dangling'] = len(DANGLING_PHRASE_RE.findall(out))
    out = DANGLING_PHRASE_RE.sub(' ', out)

    report['labels'] = len(SPOKEN_LABEL_RE.findall(out))
    out = SPOKEN_LABEL_RE.sub('', out)

    # [LOCAL-623 defect 4] Strip spoken provenance/citation tails ("as published
    # by the museum in October 2026") — the fact stays, the source attribution is
    # for the text-view Sources, not for speech.
    out, _cit = strip_citation_tails(out)
    report['citation_tails'] = _cit

    # [LOCAL-626 item 3] Drop second-person marketing/recruitment sentences from
    # the whole spoken tour (about-museum opening AND stop bodies) — the Courtauld
    # Institute admissions copy that reached tour 485.
    out, _recruit = strip_recruitment_sentences(out)
    report['recruitment'] = _recruit

    # [LOCAL-879 §6] Drop unattributed promotional/superlative marketing copy
    # ("a diamond-valued location", "the Notting Hill of Ho Chi Minh", "one of the
    # only real gay bars") repeated as narration.
    out, _promo = strip_promotional_sentences(out)
    report['promotional'] = _promo

    # [LOCAL-880 §2] Drop a sentence truncated to end on a determiner/preposition/
    # dangling adjective ("…inspired directly by the iconic.").
    out, _trunc = strip_truncated_tail_sentences(out)
    report['truncated'] = _trunc

    # [LOCAL-880 §3] Disclose a flatly-stated miracle/legend (D760) rather than
    # asserting it ("Witnesses have reported a mysterious single tear…").
    out, _folk = disclose_or_drop_folklore(out)
    report['folklore_disclosed'] = _folk

    # [LOCAL-529] One name, four spellings — make the tour agree with itself.
    out, _name_rep = normalize_proper_noun_spellings(out)
    report['name_spellings'] = sum(
        sum(c for _, _, c in g['changed']) for g in _name_rep['groups'])
    report['name_groups'] = _name_rep['groups']

    if verbose and (any(v for k, v in report.items()
                        if k not in ('name_groups',))):
        print(f"  [D523] spoken-text hygiene: {report['seams']} template seam(s), "
              f"{report['missing_spaces']} missing space(s), "
              f"{report['labels']} spoken label(s), "
              f"{report['dangling']} dangling phrase(s) removed")
        for g in _name_rep['groups']:
            froms = ', '.join(f"{f}->{t} (x{c})" for f, t, c in g['changed'])
            print(f"  [LOCAL-529] name spelling normalised near '{g['head']}': "
                  f"{froms}")
    return out, report
