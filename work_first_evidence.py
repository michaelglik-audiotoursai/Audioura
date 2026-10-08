#!/usr/bin/env python3
"""work_first_evidence.py — LOCAL-617: make museum stops work-first.

Michael's ruling (2026-10-07): museum tours "spend a lot of time repeating the
significance of the art works for the museum and college and donations… not as
much about the actual work, and the painters, and what people said about the
paintings… something that provides emotional context."

The independent critic (``critique.sh``) scored tours 399, 403–417 and the
LOCAL-616 runs at 2.5–4/10 and, on every one, the dominant Critical/Major defect
is criterion 1: a stop talks about the museum — donors, bequests, provenance,
founding, renovations, loans, the curator's tenure — instead of the WORK, the
ARTIST, what critics said, and the human/emotional reading.

This module is the deterministic lever against that defect. It is pure (no
network, no LLM, no DB) so every rule is unit-testable and cannot drift at
runtime. It provides:

  classify_sentence(sentence, venue_tokens=…, work_subject=…) -> str
      one of 'work' | 'artist' | 'reception' | 'emotion' | 'institutional'
      | 'other'. Deterministic lexicon + light subject detection.

  is_institutional(sentence, …) -> bool
      convenience: classify_sentence(...) == 'institutional'.

  is_own_acquisition(sentence, work_subject=…) -> bool
      True when an institutional sentence IS this work's own acquisition story
      (a gift/bequest/purchase/acquisition OF the work in front of the listener),
      which the contract allows at most once per stop.

  filter_snippets_work_first(snippets, work_subject=…, venue_tokens=…) -> (kept, report)
      the EVIDENCE FILTER (item 2): classify each snippet, drop snippets whose
      sentences are purely institutional, pass at most ONE institutional snippet
      per stop and only when it is the work's own acquisition story.

  filter_stop_body_work_first(body, …, is_opening_section=False) -> (new_body, report)
      the NARRATION ENFORCEMENT (item 2/3): on the delivered stop prose, keep at
      most ONE institutional sentence per stop (the own-acquisition one if
      present), and only drop when the stop still has work/artist/reception/
      emotion substance to stand on. The Stop-1 opening section (D611, the
      "About <museum>" story) is exempt and returned unchanged.

  narration_contract_instruction(...) -> str
      the per-stop prompt block for item 3 (what the work shows; the artist at
      that moment; one attributed reception item IF present; the emotional
      reading; no invented quotes; write less when thin).

  check_attribution(stop_artist, catalogue_creator) -> dict
      item 4: the stop's spoken artist must match the catalogue/SPARQL creator;
      on a real mismatch, report the correction and which sentence to drop.

  recompute_shortfall_on_delivered(...) -> str
      item 5: recompute the honest shortfall sentence on the FINAL delivered
      count, so a late gate that drops a stop never leaves a stale "has N stops"
      claim behind.
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

__all__ = [
    "classify_sentence",
    "is_institutional",
    "is_own_acquisition",
    "split_sentences",
    "filter_snippets_work_first",
    "filter_stop_body_work_first",
    "narration_contract_instruction",
    "check_attribution",
    "recompute_shortfall_on_delivered",
    "institutional_share",
    "filter_tour_text_work_first",
    "reconcile_shortfall_in_text",
    "count_delivered_stops",
    "is_institutional_theme",
    "looks_like_non_artwork_listing",
    "dedupe_conclusion",
    "repair_truncated_tail",
    "repair_broken_sentences",
]


# ─────────────────────────────────────────────────────────────────────────────
# Lexicon. Grounded in the real criterion-1 defects the critic flagged on tours
# 414/415/416/417: founding, donor/bequest, acquisition/accession, renovation
# budgets, loans, the museum's mission, the curator's tenure, civic/family
# history of the collection's namesake.
# ─────────────────────────────────────────────────────────────────────────────

# INSTITUTIONAL — about the museum / college / collection as an institution, its
# money, its people, its building, its policies — NOT about the work or the artist.
_INSTITUTIONAL_RE = re.compile(
    r"(?i)\b("
    # founding / establishment of the institution
    r"founded|founding|co-?founded|established|establishment|incorporated|"
    r"chartered|inaugurat(?:ed|ion)|opened\s+(?:its|in)\s|"
    # donors / gifts / bequests / philanthropy (the collection's benefactors)
    r"donor|donors|donat(?:ed|ion|ions)|benefactor|philanthrop|bequeath(?:ed)?|"
    r"bequest|endow(?:ed|ment)|gift\s+of|generous\s+(?:gift|donation)|"
    r"patron(?:age)?|trustee|board\s+of\s+(?:directors|trustees)|"
    # acquisition / accession / provenance of the collection
    r"accession(?:ed|\s+number)?|acquisition|provenance|"
    r"gifted\s+(?:the|this|it)|donated\s+(?:the|this|it)|"
    r"(?:gift(?:ed)?|bequeath(?:ed)?|donat(?:ed|ion))\s+(?:the\s+)?"
    r"(?:painting|work|piece|sculpture|print|canvas|drawing|portrait)\s+to|"
    # money / building / renovation / budget
    r"renovat(?:ed|ion)|refurbish(?:ed|ment)|expansion|wing\s+(?:was|opened)|"
    r"budget|million\s+(?:euro|dollar|pound)|\u20ac\s?\d|\$\s?\d|"
    r"square\s+(?:feet|metres|meters)|"
    # loans / institutional exchange
    r"on\s+loan|loaned\s+(?:to|from|by)|lent\s+(?:to|by)|loan\s+from\s+the|"
    # mission / institutional identity statements
    r"mission\s+(?:of|is|to)|the\s+museum'?s?\s+(?:mission|collection|holdings|"
    r"decision|growth|history)|non-?profit|501\(c\)|"
    # the museum / college / institution as the sentence's topic verbs
    r"museum\s+(?:was|acquired|purchased|received|holds?|houses?|owns?|"
    r"redistribut(?:ed|e))|"
    r"collection\s+(?:was|grew|includes?|comprises?|now\s+(?:holds|numbers))|"
    # civic / state redistribution (the 1811 French State example)
    r"the\s+(?:french\s+)?state\s+(?:decided|redistribut)|"
    # curator / director tenure as institutional history
    r"conservateur|curator\s+(?:of\s+the\s+museum|from\s+\d{4})|"
    r"director\s+(?:of\s+the\s+museum|from\s+\d{4})|"
    # a benefactor's death / legacy — the collection's namesake, not the work
    r"passed\s+away,?\s+leaving|leaving\s+behind\s+a\s+(?:significant\s+)?legacy|"
    r"legacy\s+(?:of\s+generosity|continues?|lives?\s+on)|"
    # softer provenance / transfer phrasing the critic flagged (tours 418/421):
    r"municipally\s+owned|publicly\s+(?:owned|accessible)|"
    r"(?:the\s+)?(?:painting|work|artwork|piece)'?s?\s+location\s+changed|"
    r"this\s+transfer\s+(?:preserved|allowed|brought|made)|"
    r"transferred\s+to\s+(?:the\s+)?(?:museum|collection|state)|"
    r"(?:museum|collection|gallery)'?s?\s+(?:dedication|commitment)\s+to|"
    r"emerged\s+from\s+(?:the\s+)?(?:sweeping\s+)?(?:cultural\s+)?reforms|"
    r"cultural\s+reforms\s+of\s+the\s+period|"
    r"ecclesiastical\s+confiscations|secularis|secular[iz]ation|"
    r"relocat(?:ed|ion)\s+of\s+(?:\w+\s+){0,3}(?:artworks?|works?|paintings?|collection)|"
    r"(?:artworks?|works?|paintings?)\s+(?:were\s+)?relocated|"
    r"confiscated\s+ecclesiastical|government\s+decree\s+that\s+confiscat|"
    r"evacuat(?:ed|ion)\s+(?:during|by|to)|"
    r"part\s+of\s+(?:the\s+)?(?:city'?s?|museum'?s?)\s+(?:rich\s+)?"
    r"(?:artistic\s+)?heritage|"
    r"became\s+(?:a\s+)?(?:pivotal\s+)?part\s+of\s+(?:the\s+)?(?:museum|collection)|"
    r"enter(?:ed|ing)\s+the\s+collection|removed\s+from\s+its\s+(?:religious\s+)?setting|"
    r"removed\s+from\s+(?:its|the)\s+(?:original\s+)?(?:church|convent|chapel|altar)"
    r")\b"
)

# OWN-ACQUISITION — the sentence is an institutional one BUT it tells the
# acquisition story of THIS work (allowed once per stop). It must name an
# acquisition verb AND point at the work (this/the painting/the work/it).
_ACQUISITION_VERB_RE = re.compile(
    r"(?i)\b(gift(?:ed)?(?:\s+(?:of|to|by))?|donat(?:ed|ion)|bequeath(?:ed)?|bequest|"
    r"purchas(?:ed|e)|acquir(?:ed|ition)|accession(?:ed)?|"
    r"enter(?:ed|ing)\s+the\s+collection|came\s+to\s+the\s+museum|"
    r"removed\s+from\s+its\s+(?:religious\s+)?setting|"
    r"was\s+given\s+to|presented\s+to|left\s+to\s+the)\b"
)

# A sentence that opens with a demonstrative pointing at a PRIOR sentence — if
# that antecedent was an institutional sentence we dropped, this one is left
# dangling ("This event resulted in…", "This transfer brought…").
_DANGLING_REF_RE = re.compile(
    r"(?i)^\s*(this|that|these|those)\s+"
    r"(event|transfer|revelation|initiative|confiscation|expropriation|"
    r"relocation|decree|acquisition|donation|gift|move|change|decision|process)\b")


def _opens_with_dangling_ref(sentence: str) -> bool:
    return bool(_DANGLING_REF_RE.search(sentence or ""))
_WORK_DEICTIC_RE = re.compile(
    r"(?i)\b(this\s+(?:work|painting|piece|sculpture|print|canvas|drawing|"
    r"photograph|portrait|panel|artwork)|the\s+(?:work|painting|piece|sculpture|print|"
    r"canvas|drawing|photograph|portrait|panel|artwork)|\bit\s+was\b|\bit\s+entered\b)"
)

# RECEPTION — what a critic, historian, or contemporary said about the work.
# These are the attributed-opinion sentences Michael wants ("what people said").
_RECEPTION_RE = re.compile(
    r"(?i)\b("
    r"critic|critics|reviewer|historian|scholar|contemporaries|"
    r"wrote\s+(?:that|of|about)|described\s+(?:it|the\s+work|the\s+painting)\s+as|"
    r"called\s+(?:it|the\s+work|the\s+painting)|hailed|praised|dismissed|"
    r"denounced|celebrated\s+(?:as|for)|regarded\s+as|considered\s+(?:a|one\s+of|"
    r"to\s+be)|acclaim(?:ed)?|controvers|scandal|caused\s+a\s+stir|"
    r"according\s+to|in\s+the\s+words\s+of|observed\s+that|noted\s+that"
    r")\b"
)

# EMOTION / human reading — the felt, sensory, bodily, human-meaning layer.
_EMOTION_RE = re.compile(
    r"(?i)\b("
    r"feel|feels|felt|feeling|grief|grieving|joy|joyful|tender|tenderness|"
    r"longing|loneliness|lonely|intimacy|intimate|tension|unease|"
    r"melancholy|sorrow|anguish|despair|hope|hopeful|serene|serenity|"
    r"you\s+(?:sense|feel|notice|might\s+feel|cannot\s+help)|"
    r"invites?\s+you\s+to\s+(?:feel|linger|pause|reflect)|"
    r"the\s+(?:eyes?|gaze|hands?|face|body|posture)\s+(?:seem|appear|betray|"
    r"suggest|hold)|"
    r"as\s+if|a\s+sense\s+of|haunt(?:ed|ing)|aching|yearning|"
    r"stillness|silence\s+of|the\s+(?:quiet|hush)"
    r")\b"
)

# ARTIST — the maker, their life, their circumstances at the moment of making.
_ARTIST_RE = re.compile(
    r"(?i)\b("
    r"paint(?:ed|er|ing)\s+(?:this|it|the\s+work)|the\s+artist|"
    r"he\s+(?:was|had|painted|made|created|began|returned|moved|struggled|died)|"
    r"she\s+(?:was|had|painted|made|created|began|returned|moved|struggled|died)|"
    r"at\s+the\s+(?:age|time)\s+of|at\s+(?:this\s+)?(?:point|moment)\s+in\s+(?:his|her)\s+(?:life|career)|"
    r"(?:his|her)\s+(?:studio|wife|husband|lover|brother|sister|father|mother|"
    r"patron|rival|teacher|student|final\s+years|early\s+(?:career|work)|"
    r"breakdown|exile|illness|death|hand)|"
    r"commissioned\s+(?:him|her|the\s+artist|by)|"
    r"(?:just|only|shortly)\s+(?:before|after)\s+(?:he|she)"
    r")\b"
)

# WORK — the object itself: what it shows, its composition, technique, materials,
# the depicted figures, colour, light, form. The ekphrasis Michael DOES want
# (unlike the About stop's artwork-framing ban, here describing the work is good).
_WORK_RE = re.compile(
    r"(?i)\b("
    r"depicts?|depicted|portrays?|shows?\s+(?:a|an|the|two|three|us)|"
    r"in\s+the\s+(?:foreground|background|centre|center|distance)|"
    r"the\s+composition|brushwork|brushstrokes?|palette|colou?r|light|shadow|"
    r"chiaroscuro|impasto|canvas|oil\s+on|tempera|fresco|bronze|marble|"
    r"lithograph|etching|drypoint|woodcut|watercolou?r|charcoal|"
    r"figure|figures|the\s+(?:woman|man|child|saint|virgin|madonna|angel|"
    r"sitter|subject)\s+(?:holds?|wears?|gazes?|stands?|sits?|looks?|turns?)|"
    r"gesture|drapery|folds?\s+of|the\s+(?:scene|landscape|still\s+life|interior)|"
    r"rendered|modelled|modeled|textured|luminous|muted|vivid"
    r")\b"
)


def split_sentences(text: str) -> List[str]:
    """Abbreviation-safe sentence split, reusing the shared helper when present."""
    if not text:
        return []
    try:  # prefer the project's splitter so behaviour matches the rest of the pipeline
        from sentence_split import split_sentences as _ss
        return [s.strip() for s in _ss(text) if s and s.strip()]
    except Exception:
        return [s.strip() for s in re.split(r"(?<=[.!?])\s+", text) if s and s.strip()]


def _mentions_venue(sentence: str, venue_tokens: Optional[Sequence[str]]) -> bool:
    if not venue_tokens:
        return False
    low = sentence.lower()
    return any(tok and len(tok) >= 3 and tok.lower() in low for tok in venue_tokens)


def classify_sentence(sentence: str,
                      venue_tokens: Optional[Sequence[str]] = None,
                      work_subject: str = "") -> str:
    """Classify ONE sentence into the work-first taxonomy.

    Returns one of: 'work', 'artist', 'reception', 'emotion', 'institutional',
    'other'. Deterministic. Priority order matters:

      1. own-acquisition institutional sentences classify as 'institutional'
         (so the caller can keep at most one), BUT a sentence that is mainly a
         reception/emotion/work statement with an incidental institutional word
         is not stolen into 'institutional'.
      2. reception (attributed opinion) outranks the rest — it is the rarest and
         most valuable signal and often co-occurs with emotion words.
      3. then work, then artist, then emotion, then institutional, then other.

    ``work_subject`` (the work's title/figures) and ``venue_tokens`` (the museum
    name words) sharpen the institutional-vs-work decision: a sentence whose
    subject is the venue leans institutional; one whose subject is the work leans
    work/artist.
    """
    s = (sentence or "").strip()
    if not s:
        return "other"

    inst = bool(_INSTITUTIONAL_RE.search(s))
    recep = bool(_RECEPTION_RE.search(s))
    work = bool(_WORK_RE.search(s))
    artist = bool(_ARTIST_RE.search(s))
    emotion = bool(_EMOTION_RE.search(s))

    # An attributed opinion is reception even if it also carries emotion words.
    if recep and not _is_institutional_dominant(s, inst, recep, work, artist, emotion):
        return "reception"

    # An own-acquisition sentence (gift/bequest/purchase OF this work) is the one
    # institutional sentence the contract permits — classify it institutional so
    # the caller can keep exactly one, even when it names a person (which could
    # otherwise read as 'other').
    if is_own_acquisition(s, work_subject) and not (work or artist):
        return "institutional"

    # A clearly institutional sentence (donor/founding/acquisition/budget/loan)
    # with NO competing work/artist substance is institutional.
    if inst and _is_institutional_dominant(s, inst, recep, work, artist, emotion):
        return "institutional"

    if work:
        return "work"
    if artist:
        return "artist"
    if emotion:
        return "emotion"
    if inst:
        # institutional signal present but something else also matched weakly:
        # treat as institutional only if nothing richer was found above.
        return "institutional"
    return "other"


def _is_institutional_dominant(s: str, inst: bool, recep: bool, work: bool,
                               artist: bool, emotion: bool) -> bool:
    """Decide whether institutional content DOMINATES the sentence.

    Institutional wins when the institutional signal is present AND the sentence
    does not primarily describe the work or the artist. Reception/emotion alone
    do NOT rescue a donor sentence ("Frizzoni bequeathed the painting, a tender
    gift" is still provenance), but a sentence that actually describes the work
    or the artist's life is not stolen into institutional.
    """
    if not inst:
        return False
    # If the sentence substantively describes the work or the artist, it is not
    # institutional-dominant — the museum word is incidental.
    if work or artist:
        return False
    return True


def is_institutional(sentence: str,
                     venue_tokens: Optional[Sequence[str]] = None,
                     work_subject: str = "") -> bool:
    return classify_sentence(sentence, venue_tokens, work_subject) == "institutional"


def is_own_acquisition(sentence: str, work_subject: str = "") -> bool:
    """True when an institutional sentence is THIS work's own acquisition story.

    Requires an acquisition verb (gift/bequest/purchase/acquired/accessioned)
    AND a deictic pointing at the work (this painting / the work / it entered …),
    OR an explicit mention of the work's subject/title. This is the one
    institutional sentence the contract permits per stop.
    """
    s = (sentence or "").strip()
    if not s:
        return False
    if not _ACQUISITION_VERB_RE.search(s):
        return False
    if _WORK_DEICTIC_RE.search(s):
        return True
    if work_subject:
        subj = work_subject.lower()
        # match any significant word of the work subject
        for w in re.findall(r"\b\w{4,}\b", subj):
            if w in s.lower():
                return True
    return False


def institutional_share(text: str,
                        venue_tokens: Optional[Sequence[str]] = None,
                        work_subject: str = "") -> float:
    """Fraction of sentences in ``text`` classified institutional (for measurement)."""
    sents = split_sentences(text)
    if not sents:
        return 0.0
    inst = sum(1 for s in sents
               if classify_sentence(s, venue_tokens, work_subject) == "institutional")
    return inst / len(sents)


# ─────────────────────────────────────────────────────────────────────────────
# item 2 — EVIDENCE FILTER (snippets, before narration)
# ─────────────────────────────────────────────────────────────────────────────

def _snippet_is_institutional(snip: Dict,
                              work_subject: str,
                              venue_tokens: Optional[Sequence[str]]) -> Tuple[bool, bool]:
    """Return (is_institutional_snippet, is_own_acquisition_snippet).

    A snippet is institutional when the MAJORITY of its classifiable sentences
    are institutional and none describe the work or artist. It is own-acquisition
    when any sentence is this work's own acquisition story.
    """
    text = f"{snip.get('title', '')}. {snip.get('snippet', '')}".strip()
    sents = split_sentences(text) or [text]
    labels = [classify_sentence(s, venue_tokens, work_subject) for s in sents]
    inst = sum(1 for l in labels if l == "institutional")
    rich = sum(1 for l in labels if l in ("work", "artist", "reception", "emotion"))
    own_acq = any(is_own_acquisition(s, work_subject) for s in sents)
    is_inst = inst > 0 and rich == 0
    return is_inst, own_acq


def filter_snippets_work_first(snippets: List[Dict],
                               work_subject: str = "",
                               venue_tokens: Optional[Sequence[str]] = None
                               ) -> Tuple[List[Dict], Dict]:
    """[LOCAL-617 item 2] Keep work-first evidence; cap institutional snippets.

    Rules:
      • A snippet with ANY work/artist/reception/emotion sentence is KEPT (it
        carries the material the narration needs).
      • A purely-institutional snippet is DROPPED, except at most ONE is kept and
        only when it is this work's OWN acquisition story.
      • Order is preserved (the caller already ranked them).

    Returns (kept_snippets, report).
    """
    kept: List[Dict] = []
    dropped_institutional = 0
    kept_own_acquisition = False
    report = {
        "input": len(snippets),
        "dropped_institutional": 0,
        "kept_own_acquisition": False,
        "output": 0,
    }
    for snip in snippets:
        is_inst, own_acq = _snippet_is_institutional(snip, work_subject, venue_tokens)
        if not is_inst:
            kept.append(snip)
            continue
        # purely institutional snippet
        if own_acq and not kept_own_acquisition:
            kept.append(snip)
            kept_own_acquisition = True
            continue
        dropped_institutional += 1
    report["dropped_institutional"] = dropped_institutional
    report["kept_own_acquisition"] = kept_own_acquisition
    report["output"] = len(kept)
    return kept, report


# ─────────────────────────────────────────────────────────────────────────────
# item 2/3 — NARRATION ENFORCEMENT (delivered stop prose)
# ─────────────────────────────────────────────────────────────────────────────

def filter_stop_body_work_first(body: str,
                                venue_tokens: Optional[Sequence[str]] = None,
                                work_subject: str = "",
                                is_opening_section: bool = False
                                ) -> Tuple[str, Dict]:
    """[LOCAL-617 item 2/3] Enforce at most ONE institutional sentence per stop.

    On the delivered stop prose, drop institutional sentences, keeping at most
    one — the work's own-acquisition sentence if present, otherwise none. The
    stop is only trimmed when it RETAINS work/artist/reception/emotion substance,
    so we never strip a stop down to nothing (D577: never turn a working stop
    into no stop).

    The Stop-1 opening section (D611 — the sourced "About <museum>" story) is
    EXEMPT: ``is_opening_section=True`` returns the body unchanged. The caller is
    responsible for passing that flag only for the opening section, not the
    work-stop body that follows it.

    Returns (new_body, report).
    """
    report = {
        "institutional_total": 0,
        "institutional_kept": 0,
        "institutional_dropped": 0,
        "exempt_opening": bool(is_opening_section),
        "changed": False,
    }
    if is_opening_section or not body or not body.strip():
        return body, report

    sents = split_sentences(body)
    if len(sents) <= 1:
        return body, report

    labels = [classify_sentence(s, venue_tokens, work_subject) for s in sents]
    inst_idx = [i for i, l in enumerate(labels) if l == "institutional"]
    rich_idx = [i for i, l in enumerate(labels)
                if l in ("work", "artist", "reception", "emotion")]
    report["institutional_total"] = len(inst_idx)

    if not inst_idx:
        return body, report

    # Nothing rich to stand on → leave the stop unchanged (never empty a stop).
    if not rich_idx:
        report["institutional_kept"] = len(inst_idx)
        return body, report

    # Choose the ONE institutional sentence to keep: the own-acquisition one,
    # but NOT one that opens with a demonstrative pointing at a dropped sentence
    # ("This event resulted in…", "This transfer…") — keeping it would leave a
    # dangling reference once its antecedent institutional sentence is removed.
    keep_i = None
    for i in inst_idx:
        if is_own_acquisition(sents[i], work_subject) and not _opens_with_dangling_ref(sents[i]):
            keep_i = i
            break

    kept_sents: List[str] = []
    dropped = 0
    kept_inst = 0
    for i, s in enumerate(sents):
        if i in inst_idx:
            if i == keep_i and kept_inst == 0:
                kept_sents.append(s)
                kept_inst += 1
            else:
                dropped += 1
            continue
        # A surviving sentence that opens with a demonstrative referring to a
        # dropped institutional antecedent is now dangling — drop it too, but only
        # if it is not itself rich (we never drop a work/artist/reception/emotion
        # sentence). "This event resulted in the artwork entering the collection."
        if (_opens_with_dangling_ref(s) and i not in rich_idx
                and dropped > 0 and (i - 1) in inst_idx and (i - 1) != keep_i):
            dropped += 1
            continue
        kept_sents.append(s)

    report["institutional_kept"] = kept_inst
    report["institutional_dropped"] = dropped
    new_body = " ".join(kept_sents).strip()
    report["changed"] = (dropped > 0)
    # Belt-and-braces: never return empty.
    if not new_body:
        return body, report
    return new_body, report


# ─────────────────────────────────────────────────────────────────────────────
# item 3 — NARRATION CONTRACT (prompt instruction)
# ─────────────────────────────────────────────────────────────────────────────

def narration_contract_instruction(work_title: str = "",
                                   artist: str = "",
                                   has_reception_evidence: bool = False) -> str:
    """[LOCAL-617 item 3] The per-stop narration contract, as a prompt block.

    Order: (a) what the work shows and how; (b) the artist at that moment of
    their life; (c) ONE attributed reception item only if present in the
    evidence; (d) the emotional/human reading. No invented quotes. When the
    evidence for (b) or (c) is thin, write LESS, not filler.
    """
    _title = work_title.strip() or "this work"
    _artist = artist.strip()
    reception_clause = (
        "  (c) ONE thing a named critic or historian said about it — ATTRIBUTED "
        "to that person — but ONLY because the reference material contains it. "
        "Do NOT invent a quotation or a critic.\n"
        if has_reception_evidence else
        "  (c) SKIP any 'critics said' sentence — the reference material contains "
        "no attributed reception. Do NOT invent a critic, a quotation, or a "
        "reaction.\n"
    )
    return f"""
NARRATION CONTRACT (LOCAL-617 — museum stop, in THIS order):
  (a) What {_title} SHOWS and HOW — the figures, the composition, the colour and
      light, the technique. Put the listener in front of the object first.
  (b) {('Where ' + _artist + ' was in life at the moment this was made') if _artist else 'Where the artist was in life at the moment this was made'}
      — the circumstance, not a résumé. One or two sentences.
{reception_clause}  (d) The emotional or human reading — what it is like to stand before it,
      what it is about as human experience.

DO NOT narrate the MUSEUM instead of the work: no donor, bequest, acquisition,
accession, provenance, founding, renovation, budget, loan, or mission sentences.
(At most ONE sentence may tell THIS work's own acquisition story, and only if it
is genuinely about this object.) When the evidence for (b) or (c) is thin, write
LESS — a shorter, true stop beats padded institutional history. NEVER invent a
quotation, a critic's name, a date, or a reaction the sources do not state.
"""


# ─────────────────────────────────────────────────────────────────────────────
# item 4 — ATTRIBUTION CHECK
# ─────────────────────────────────────────────────────────────────────────────

# Known given-name variants so "Johannes van Eyck" vs "Jan van Eyck" is a match,
# not a mismatch, while "van Eyck" vs "Memling" is a real mismatch.
_NAME_VARIANTS = {
    "johannes": {"jan", "john", "johann"},
    "jan": {"johannes", "john", "johann"},
    "john": {"johannes", "jan", "johann"},
    "pieter": {"peter", "pietro"},
    "peter": {"pieter", "pietro"},
    "guillaume": {"william", "willem"},
    "william": {"guillaume", "willem"},
    "francesco": {"francis", "franz"},
    "giovanni": {"john", "jean"},
}

_NAME_NOISE = re.compile(
    r"(?i)\b(attributed\s+to|workshop\s+of|circle\s+of|follower\s+of|after|"
    r"studio\s+of|school\s+of|the\s+younger|the\s+elder|van|von|de|della|del|"
    r"di|le|la|du|des|der)\b")


def _name_tokens(name: str) -> List[str]:
    n = _NAME_NOISE.sub(" ", (name or ""))
    return [t for t in re.findall(r"[A-Za-zÀ-ÿ'\-]{2,}", n.lower())]


def _surname(name: str) -> str:
    toks = _name_tokens(name)
    return toks[-1] if toks else ""


def check_attribution(stop_artist: str, catalogue_creator: str) -> Dict:
    """[LOCAL-617 item 4] Verify the stop's artist matches the catalogue creator.

    The spoken stop artist (what the narration says) must match the work's
    catalogue/SPARQL creator. On a real mismatch (different surname, not a mere
    given-name/spelling variant), the catalogue creator wins and the conflicting
    sentence must be dropped.

    Returns:
      {
        'match': bool,            # True if they agree (or either is unknown)
        'use': str,               # the name to use (catalogue creator on mismatch)
        'mismatch': bool,         # True on a real surname mismatch
        'drop_conflicting': bool, # True → caller drops the sentence naming stop_artist
        'reason': str,
      }
    """
    sa = (stop_artist or "").strip()
    cc = (catalogue_creator or "").strip()
    # Unknown on either side → nothing to reconcile; keep what we have.
    if not sa or not cc:
        return {"match": True, "use": sa or cc, "mismatch": False,
                "drop_conflicting": False, "reason": "insufficient data"}

    sa_sur, cc_sur = _surname(sa), _surname(cc)
    if sa_sur and sa_sur == cc_sur:
        # same surname — a given-name/spelling variant or a subset. Prefer the
        # fuller (catalogue) name so a bare surname upgrades to the full name.
        fuller = cc if len(_name_tokens(cc)) >= len(_name_tokens(sa)) else sa
        return {"match": True, "use": fuller, "mismatch": False,
                "drop_conflicting": False, "reason": "surname match"}

    # Given-name variant with same surname is handled above (same surname).
    # If surnames differ, check whether the WHOLE names are variant-equivalent
    # (e.g. one-name artists "Memling" vs "Hans Memling").
    sa_toks, cc_toks = set(_name_tokens(sa)), set(_name_tokens(cc))
    if sa_toks and cc_toks:
        if sa_toks <= cc_toks or cc_toks <= sa_toks:
            # subset-equivalent (e.g. "Memling" vs "Hans Memling") — prefer the
            # fuller name, which is normally the catalogue creator.
            fuller = cc if len(cc_toks) >= len(sa_toks) else sa
            return {"match": True, "use": fuller, "mismatch": False,
                    "drop_conflicting": False, "reason": "subset match"}
        # given-name variant equivalence on an otherwise shared surname
        if sa_sur == cc_sur:
            return {"match": True, "use": cc, "mismatch": False,
                    "drop_conflicting": False, "reason": "name variant"}

    # Real mismatch: catalogue creator wins; drop the conflicting sentence.
    return {
        "match": False,
        "use": cc,
        "mismatch": True,
        "drop_conflicting": True,
        "reason": f"stop artist '{sa}' != catalogue creator '{cc}'",
    }


# ─────────────────────────────────────────────────────────────────────────────
# item 5 — FRESH-PATH SHORTFALL RECOMPUTE
# ─────────────────────────────────────────────────────────────────────────────

def recompute_shortfall_on_delivered(venue_name: str,
                                     exhibitions_on_view: int,
                                     final_delivered_stops: int,
                                     requested_stops: Optional[int],
                                     mode: str = "museum") -> str:
    """[LOCAL-617 item 5] Rebuild the honest shortfall sentence on the FINAL count.

    D616/D612 build the shortfall sentence from the count known when the
    shortfall logic runs. If a LATE gate then drops a stop (e.g. Granet delivered
    2/3 after the sentence already said 3), the stale sentence contradicts the
    delivered tour. This recomputes it from ``final_delivered_stops`` — the count
    actually shipped — so the sentence can never claim a stop the tour did not
    make.

    Delegates to about_museum_stop.build_shortfall_sentence so there is ONE
    builder (never a second). Returns the (possibly empty) sentence; empty when
    the ask was met on the final count.
    """
    try:
        from about_museum_stop import build_shortfall_sentence
    except Exception:
        return ""
    return build_shortfall_sentence(
        venue_name=venue_name,
        exhibitions_on_view=exhibitions_on_view,
        delivered_stops=final_delivered_stops,
        requested_stops=requested_stops,
        mode=mode,
    )


# ─────────────────────────────────────────────────────────────────────────────
# tour-level application: filter each stop body, exempt the Stop-1 opening section
# ─────────────────────────────────────────────────────────────────────────────

# Markers of the D611 opening section (the sourced "About <museum>" story and the
# practical-notes/shortfall prolog of Stop 1). Any paragraph that opens with one
# of these is the opening section and is left untouched.
_OPENING_MARKERS = re.compile(
    r"(?i)^\s*(before we look at anything|here is the story of|"
    r"before you go in|a word about the building|"
    r"you are at |this opening stop is about|"
    r".{0,80}\b(is open|admission is|opening hours|check opening hours)\b|"
    r".{0,120}\b(currently has \d+ exhibition|stops? rather than the \d+ you asked for))"
)

_STOP_HEADER_RE = re.compile(r"(?mi)^(Stop\s+\d+\s*[:\-][^\n]*)$")


def _is_opening_paragraph(paragraph: str) -> bool:
    return bool(_OPENING_MARKERS.search(paragraph.strip()))


def filter_tour_text_work_first(tour_text: str,
                                venue_tokens: Optional[Sequence[str]] = None,
                                stop_subjects: Optional[Dict[int, str]] = None
                                ) -> Tuple[str, Dict]:
    """[LOCAL-617 item 2/3] Apply the stop-body filter across a whole delivered tour.

    Splits the tour on real ``Stop N:`` headers, and for each stop's body:
      • Paragraphs that ARE the D611 opening section (About story, practical
        notes, shortfall) are kept verbatim (exempt).
      • Every other paragraph is run through ``filter_stop_body_work_first`` so at
        most one institutional sentence (the own-acquisition one) survives per
        stop — and only when the stop still has work/artist/reception/emotion
        substance to stand on.

    Pure string→string. Preamble before the first Stop header (and the conclusion
    after the last stop body) is left untouched. Returns (new_text, report).

    ``stop_subjects`` optionally maps 1-based stop index → work subject/title to
    sharpen own-acquisition detection.
    """
    report = {"stops": 0, "institutional_dropped": 0, "changed": False}
    if not tour_text or not tour_text.strip():
        return tour_text, report

    parts = _STOP_HEADER_RE.split(tour_text)
    # parts = [preamble, header1, body1, header2, body2, ...]
    if len(parts) < 3:
        return tour_text, report  # no stop headers → nothing to do

    out = [parts[0]]
    i = 1
    stop_index = 0
    total_dropped = 0
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        stop_index += 1
        report["stops"] += 1
        subject = (stop_subjects or {}).get(stop_index, "")

        # Split the body into paragraphs; keep opening-section paragraphs intact.
        paras = re.split(r"(\n\s*\n)", body)  # keep separators
        new_paras: List[str] = []
        for seg in paras:
            if seg.strip() == "" or re.fullmatch(r"\n\s*\n", seg):
                new_paras.append(seg)
                continue
            if stop_index == 1 and _is_opening_paragraph(seg):
                new_paras.append(seg)  # exempt opening section
                continue
            filtered, prep = filter_stop_body_work_first(
                seg, venue_tokens=venue_tokens, work_subject=subject,
                is_opening_section=False)
            total_dropped += prep.get("institutional_dropped", 0)
            new_paras.append(filtered)
        out.append(header)
        out.append("".join(new_paras))
        i += 2

    report["institutional_dropped"] = total_dropped
    report["changed"] = total_dropped > 0
    return "".join(out), report


# ─────────────────────────────────────────────────────────────────────────────
# item 5/6 — reconcile a stale shortfall sentence against the DELIVERED count
# ─────────────────────────────────────────────────────────────────────────────

def count_delivered_stops(tour_text: str) -> int:
    """Count the real ``Stop N:`` headers in a delivered tour."""
    if not tour_text:
        return 0
    return len(_STOP_HEADER_RE.findall(tour_text))


# A shortfall sentence from build_shortfall_sentence, so we can rewrite its
# delivered-count clause: "… this tour has <N> stop(s) rather than the <R> you
# asked for."
_SHORTFALL_TAIL_RE = re.compile(
    r"(?i)(this tour has\s+)(\d+)(\s+stops?\s+rather than the\s+)(\d+)(\s+you asked for)")
# The outdoor confirm clause: "We could confirm <N> stop(s) along this route, so …"
_CONFIRM_RE = re.compile(
    r"(?i)(we could confirm\s+)(\d+)(\s+stops?\s+along this route)")


def reconcile_shortfall_in_text(tour_text: str,
                                final_delivered_stops: Optional[int] = None
                                ) -> Tuple[str, Dict]:
    """[LOCAL-617 item 5/6] Correct a stale shortfall sentence to the real count.

    When a LATE gate drops a stop after the shortfall sentence was composed (the
    Granet case: the sentence said "3 stops" but only 2 shipped), the delivered
    count in the tour text contradicts the stops actually present. This rewrites
    the "this tour has N stops rather than the R you asked for" clause (and the
    outdoor "we could confirm N stops" clause) to the real delivered count. If the
    corrected delivered count now EQUALS or EXCEEDS the requested count (the ask
    was met after all), the whole shortfall sentence is removed so the tour never
    claims a shortfall it did not have.

    Pure string→string. ``final_delivered_stops`` defaults to the real Stop-header
    count in the text. Returns (new_text, report).
    """
    report = {"delivered": 0, "rewritten": False, "removed": False}
    if not tour_text:
        return tour_text, report
    delivered = (final_delivered_stops if final_delivered_stops is not None
                 else count_delivered_stops(tour_text))
    report["delivered"] = delivered
    if delivered <= 0:
        return tour_text, report

    text = tour_text

    m = _SHORTFALL_TAIL_RE.search(text)
    if m:
        stated_delivered = int(m.group(2))
        requested = int(m.group(4))
        if delivered >= requested:
            # ask met after late changes → remove the whole shortfall sentence.
            text = _remove_sentence_containing(text, m.start())
            report["removed"] = True
            report["rewritten"] = True
        elif stated_delivered != delivered:
            stop_word = "stop" if delivered == 1 else "stops"
            # rebuild "<delivered> <stops> rather than the <requested>"
            replacement = (f"{m.group(1)}{delivered} {stop_word} rather than the "
                           f"{requested}{m.group(5)}")
            text = text[:m.start()] + replacement + text[m.end():]
            report["rewritten"] = True

    m2 = _CONFIRM_RE.search(text)
    if m2:
        stated = int(m2.group(2))
        if stated != delivered:
            stop_word = "stop" if delivered == 1 else "stops"
            replacement = f"{m2.group(1)}{delivered} {stop_word} along this route"
            text = text[:m2.start()] + replacement + text[m2.end():]
            report["rewritten"] = True

    return text, report


def _remove_sentence_containing(text: str, idx: int) -> str:
    """Remove the single sentence that contains character offset ``idx``."""
    # sentence starts after the previous terminator, ends at the next one.
    start = idx
    while start > 0 and text[start - 1] not in ".!?\n":
        start -= 1
    end = idx
    while end < len(text) and text[end] not in ".!?\n":
        end += 1
    if end < len(text):
        end += 1  # include the terminator
    removed = text[start:end]
    out = (text[:start] + text[end:])
    # tidy double spaces / stray leading space left behind
    out = re.sub(r"[ \t]{2,}", " ", out)
    out = re.sub(r"\n[ \t]+\n", "\n\n", out)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# institutional THEME guard — a tour theme that frames the stops around the
# museum/collection/donations rather than the works and artists.
# ─────────────────────────────────────────────────────────────────────────────

# A theme NAME/description is institutional when it is ABOUT the institution,
# its money, its acquisitions, its founding, its policies — the exact framing the
# critic flagged ("19th-Century Institutional Foundations", "the museum's growth",
# "donor legacy", "expropriation and the collection").
_INSTITUTIONAL_THEME_RE = re.compile(
    r"(?i)\b("
    r"institution(?:al)?|founding|foundations?|donor|donation|benefactor|"
    r"bequest|acquisition|accession|provenance|collection'?s?\s+(?:growth|history|"
    r"formation|origins?)|museum'?s?\s+(?:growth|history|mission|founding)|"
    r"expropriation|confiscation|desamortiz|nationaliz|redistribut|"
    r"patronage|philanthrop|endowment|the\s+making\s+of\s+(?:a|the)\s+(?:museum|"
    r"collection)"
    r")\b"
)

# Signals that keep an otherwise-institutional-sounding theme if it is really
# about the ART (so "foundations of modern abstraction" is not caught).
_THEME_ART_RESCUE_RE = re.compile(
    r"(?i)\b(abstraction|portrait|landscape|still\s+life|colou?r|light|form|"
    r"brushwork|devotion|faith|myth|identity|exile|grief|love|war|nature|body|"
    r"movement|realism|impressionism|surrealism|baroque|modernism)\b"
)


def is_institutional_theme(theme_name: str, theme_description: str = "") -> bool:
    """True when a tour THEME frames the stops institutionally, not around the art.

    The critic flagged themes like "19th-Century Institutional Foundations" that
    drag donor/confiscation/collection history into every stop. A theme is
    institutional when its name or description carries an institutional term and
    is NOT rescued by an art-subject term.
    """
    text = f"{theme_name or ''} {theme_description or ''}".strip()
    if not text:
        return False
    if not _INSTITUTIONAL_THEME_RE.search(text):
        return False
    # If the theme is really about the art despite an institutional word, keep it.
    if _THEME_ART_RESCUE_RE.search(theme_name or ""):
        return False
    return True


# ─────────────────────────────────────────────────────────────────────────────
# NON-ARTWORK LISTING guard — a candidate "stop title" that is actually a price,
# an opening-hours line, or an event/guided-tour listing scraped from a calendar
# or pricing feed, in ANY language. The Kunstmuseum Basel run (tour 418) made
# "Kosten: Eintritt Sammlung" (German "Cost: Collection admission") and "Mit der
# wissenschaftlichen Assistentin Amélie Joller" (a guided-tour listing) into
# artwork stops — the critic's two Critical defects. These are a different KIND
# of thing from an artwork, caught structurally rather than by any one language's
# vocabulary.
# ─────────────────────────────────────────────────────────────────────────────

# Price / admission labels in several European languages the pipeline meets.
_PRICE_LABEL_RE = re.compile(
    r"(?i)^\s*("
    r"kosten|eintritt|preis|preise|tarif|tarife|tarifs?|precio|precios|"
    r"prix|entr[ée]e|entrada|admission|price|cost|fee|fees|ticket[s]?|"
    r"gratuit|gratis|free\s+admission"
    r")\b")
_PRICE_VALUE_RE = re.compile(
    r"(?i)([$€£]\s?\d|\bchf\s?\d|\d+\s?(?:eur|usd|gbp|chf|dollars?|euros?|francs?)\b)")

# Opening-hours listing.
_HOURS_LISTING_RE = re.compile(
    r"(?i)^\s*("
    r"[öo]ffnungszeiten|horaires?|horario|opening\s+hours|hours|"
    r"geschlossen|closed\s+(?:on|mon|tue|wed)|ferm[ée]"
    r")\b")

# Guided-tour / event listing: starts with a "with <role/person>" preposition in
# a European language, or names a staff role joined to a tour/talk.
_EVENT_LISTING_RE = re.compile(
    r"(?i)^\s*("
    r"mit\s+(?:der|dem|den|die)\s|avec\s+|con\s+(?:el|la|los)\s|with\s+(?:the\s+)?"
    r"(?:curator|assistant|guide|director|lecturer)|"
    r"f[üu]hrung|visite\s+guid[ée]e|visita\s+guiada|guided\s+tour|"
    r"workshop|vortrag|conf[ée]rence|lecture\s+by|talk\s+by|gespr[äa]ch"
    r")\b")
# A staff/academic role token that, inside a short "title", marks an event
# listing rather than a work ("wissenschaftlichen Assistentin" = research assistant).
_STAFF_ROLE_RE = re.compile(
    r"(?i)\b(assistent(?:in)?|wissenschaftlich|kurator(?:in)?|curator|"
    r"conservateur|conservatrice|docent|guide|r[ée]f[ée]rent)\b")

# Museum PROGRAMME / EVENT names (multilingual) that a calendar feed exposes
# alongside works. The Kunstmuseum Basel run made "Europäischer Tag der
# Restaurierung", "Mitmach-Mittwoch", "Familientag" and a "Tango Salon" into
# artwork stops — events, days, workshops and family programmes, not works.
_EVENT_NAME_RE = re.compile(
    r"(?i)\b("
    r"tag\s+der\s+\w+|europ[äa]ischer\s+tag|mitmach|familientag|familiensonntag|"
    r"kindertag|offene\s+werkstatt|werkstatt|workshop|atelier\s+f[üu]r|"
    r"ferienworkshop|mittwoch|sonntag[s]?f[üu]hrung|"
    r"restaurierung|tag\s+des\s+offenen|lange\s+nacht|nuit\s+des\s+mus[ée]es|"
    r"d[íi]a\s+(?:de\s+la\s+familia|internacional)|jornada|"
    r"tango\s+salon|soir[ée]e|matin[ée]e|vernissage|finissage|"
    r"family\s+day|open\s+day|late\s+night|members?\s+(?:evening|day)"
    r")\b")


def looks_like_non_artwork_listing(title: str) -> bool:
    """True when a candidate stop title is a price/hours/event listing, not a work.

    Deterministic and multilingual-by-structure. Catches:
      • price/admission lines: "Kosten: Eintritt Sammlung", "Prix: 15 €",
        "Admission", "Eintritt CHF 26";
      • opening-hours lines: "Öffnungszeiten", "Opening hours", "Geschlossen …";
      • event / guided-tour listings: "Mit der wissenschaftlichen Assistentin
        Amélie Joller", "Visite guidée", "Führung", "Lecture by …".

    A genuine artwork title ("Madonna of the Napkin", "San Francisco abrazando a
    Cristo en la Cruz") is never caught: it opens with neither a price/hours label
    nor an event preposition, and carries no price value or staff-role token.
    """
    t = (title or "").strip()
    if not t:
        return False
    # price / admission
    if _PRICE_LABEL_RE.search(t):
        return True
    if _PRICE_VALUE_RE.search(t) and len(t.split()) <= 8:
        # a short line dominated by a price value is a pricing row, not a work
        return True
    # opening hours
    if _HOURS_LISTING_RE.search(t):
        return True
    # event / guided-tour listing
    if _EVENT_LISTING_RE.search(t):
        return True
    # museum programme / event name (restoration day, family day, workshop, salon)
    if _EVENT_NAME_RE.search(t):
        return True
    # a short "title" that opens with "Mit/Avec/With/Con" AND names a staff role
    if _STAFF_ROLE_RE.search(t) and re.match(r"(?i)^\s*(mit|avec|with|con)\b", t):
        return True
    return False


# ─────────────────────────────────────────────────────────────────────────────
# item 6 — conclusion de-duplication (never two recaps that can disagree)
# ─────────────────────────────────────────────────────────────────────────────

_RECAP_THATS_RE = re.compile(r"(?i)that'?s\s+\d+\s+stops?\b")
_TOUR_COVERED_RE = re.compile(r"(?i)this\s+tour\s+covered\b[^.!?]*[.!?]")


def dedupe_conclusion(tour_text: str) -> Tuple[str, Dict]:
    """[LOCAL-617 item 6] Keep ONE conclusion, never two recaps that can disagree.

    The critic flagged tours whose ending had BOTH a "That's N stops — …" recap
    AND a "This tour covered X and Y." line that named a different set of stops —
    a self-contradiction (tour 419/421). When both are present, drop the plain
    "This tour covered …" sentence and keep the richer recap. Pure string→string.
    """
    report = {"removed_redundant_covered": False}
    if not tour_text:
        return tour_text, report
    if _RECAP_THATS_RE.search(tour_text) and _TOUR_COVERED_RE.search(tour_text):
        new_text = _TOUR_COVERED_RE.sub("", tour_text)
        new_text = re.sub(r"[ \t]{2,}", " ", new_text)
        new_text = re.sub(r"\n[ \t]+", "\n", new_text)
        report["removed_redundant_covered"] = True
        return new_text, report
    return tour_text, report


# A sentence that ends on a word still expecting an object — the generator cut it
# mid-clause ("…showcases Murillo's talent for."). These final tokens mean the
# object is missing.
_TRUNCATED_TAIL_RE = re.compile(
    r"(?i)\b("
    r"talent\s+for|ability\s+to|known\s+for|famous\s+for|devoted\s+to|"
    r"dedicated\s+to|thanks\s+to|because\s+of|such\s+as|including|featuring|"
    r"as\s+well\s+as|in\s+order\s+to|skill\s+in|mastery\s+of|gift\s+for|"
    r"capturing|showcasing|depicting|portraying|rendering|conveying|evoking|"
    r"exploring|revealing|the|a|an|his|her|their|its|of|to|for|and|"
    r"with|that|which|was|were|is|are"
    r")\s*[.!?]?\s*$")


def repair_truncated_tail(tour_text: str) -> Tuple[str, Dict]:
    """[LOCAL-617 item 6] Never ship a conclusion that ends mid-clause.

    The critic flagged a closing like "San Francisco … showcases Murillo's talent
    for." — a template cut mid-token. When the FINAL sentence of the tour ends on
    a word that still expects an object, drop that broken sentence so the tour
    ends on its previous complete sentence. Pure string→string.
    """
    report = {"repaired": False}
    if not tour_text or not tour_text.strip():
        return tour_text, report
    stripped = tour_text.rstrip()
    # consider the last sentence
    sents = re.split(r"(?<=[.!?])\s+", stripped)
    if not sents:
        return tour_text, report
    last = sents[-1].strip()
    if last and _TRUNCATED_TAIL_RE.search(last) and len(sents) >= 2:
        # remove the final broken sentence
        idx = stripped.rfind(last)
        if idx > 0:
            new_text = stripped[:idx].rstrip()
            report["repaired"] = True
            # preserve a trailing newline convention
            return new_text + "\n", report
    return tour_text, report


# ─────────────────────────────────────────────────────────────────────────────
# [LOCAL-617 item 3/8] Broken-sentence repair. The critic flagged, on EVERY one
# of the three live tours, sentences the generator shipped corrupted:
#   • a MISSING SUBJECT after an intro adverbial — "During this period, was
#     refining his techniques" (tour 429), where the {artist} slot rendered empty;
#   • a DUPLICATED adjacent clause — "a profound act of devotion, of Assisi in a
#     profound act of devotion" (tour 427), a template splice gone wrong.
# Both read as a data gap / factual red flag (criterion 8) to a listener. These
# are deterministic, local text corruptions — repair them without the LLM.
# ─────────────────────────────────────────────────────────────────────────────

# An intro adverbial phrase, a comma, then a CONJUGATED verb with no subject
# between the comma and the verb. "During this period, was refining…",
# "In 1890, painted the canvas…", "At this moment, had become…". The verb set is
# the auxiliaries/common past verbs that cannot legally open a main clause with no
# subject. We require a leading intro phrase so we never touch an imperative.
_MISSING_SUBJECT_RE = re.compile(
    r"(?i)^\s*"
    r"(?:(?:during|in|at|after|before|by|throughout|around|amid|following|"
    r"while|when|as|though|although|despite)\b[^,.;]{0,60}),\s+"
    r"(was|were|had|has|would|could|began|started|continued|returned|became|"
    r"painted|created|made|refining|developing|working|producing)\b"
)

# A clause of >= 3 words that repeats verbatim later in the SAME sentence,
# separated by a comma or connective — the splice artifact the critic saw.
_DUP_CLAUSE_RE = re.compile(
    r"(?i)\b((?:\w+\s+){2,6}\w+)\b(.{0,40}?)\b\1\b")


def repair_broken_sentences(tour_text: str, stop_subjects: Optional[Dict[int, str]] = None
                            ) -> Tuple[str, Dict]:
    """[LOCAL-617 item 3/8] Drop/clean sentences the generator shipped corrupted.

    Two deterministic corruptions the critic flagged on tours 427/428/429:

    1. **Missing-subject clause** ("During this period, was refining his
       techniques") — an intro adverbial, a comma, then a conjugated verb with no
       subject. The subject slot rendered empty. These are dropped (the stop keeps
       its other, complete sentences); never the only sentence of a stop (D577).
    2. **Duplicated adjacent clause** ("…a profound act of devotion, of Assisi in
       a profound act of devotion") — collapse the verbatim repeat to one copy.

    Pure string→string. Operates per paragraph so a drop never crosses a stop
    boundary and a stop is never emptied.
    """
    report = {"missing_subject_dropped": 0, "dup_clauses_collapsed": 0}
    if not tour_text or not tour_text.strip():
        return tour_text, report

    out_paras: List[str] = []
    for para in tour_text.split("\n"):
        if not para.strip():
            out_paras.append(para)
            continue
        # Header lines (Stop N:, Tour-Category:, titles) are left untouched.
        if re.match(r"(?i)^\s*(stop\s+\d+\s*:|tour-category:|##|\*\*)", para):
            out_paras.append(para)
            continue
        sents = split_sentences(para)
        if not sents:
            out_paras.append(para)
            continue
        kept: List[str] = []
        for s in sents:
            # (2) collapse a verbatim duplicated clause inside the sentence first
            m = _DUP_CLAUSE_RE.search(s)
            if m and len(m.group(1).split()) >= 3:
                s2 = _DUP_CLAUSE_RE.sub(lambda mm: mm.group(1), s, count=1)
                s2 = re.sub(r"\s{2,}", " ", s2).replace(" ,", ",").strip()
                if s2 and s2 != s:
                    report["dup_clauses_collapsed"] += 1
                    s = s2
            # (1) drop a missing-subject clause — but never the last substance in
            # the paragraph.
            if _MISSING_SUBJECT_RE.search(s):
                report["missing_subject_dropped"] += 1
                continue
            kept.append(s)
        if not kept:
            # every sentence was broken — keep the ORIGINAL rather than empty the
            # stop (D577); a broken stop still beats a vanished one.
            out_paras.append(para)
            continue
        out_paras.append(" ".join(kept))

    new_text = "\n".join(out_paras)
    report["changed"] = (report["missing_subject_dropped"] > 0
                         or report["dup_clauses_collapsed"] > 0)
    return new_text, report
