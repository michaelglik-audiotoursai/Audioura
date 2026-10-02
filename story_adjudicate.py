#!/usr/bin/env python3
"""story_adjudicate.py — D509: challenge every claim, keep what survives.

Michael, 2026-08-22, after two rounds of correcting LEAD by hand:

    "Now it seems to me the story makes only better as it becomes more accurate.
     ... I am okay to re-ask Gemini and pay for the results, but I am not okay
     to dismiss all its stories."

**What produced the accurate version was not verification. It was CHALLENGE.**

    round 1  Gemini asserts a story with real substance and loose edges
    step 2   we find specific contradicting evidence — a lot numbered 23/100,
             a dealer page saying *paper shortage* and *stones sanded*
    step 3   we put the contradiction back AS THE QUESTION
    round 2  Gemini retracts ("the claim of zinc plates was an error") or
             resolves with structure (defect = technical, shortage = logistical)

Round 2 is better because it was made to answer for round 1. That is D367,
Michael's own amendment to D366, which has existed since 2026-08-11 and was
never built:

    "Two sourced claims disagree -> build the story on the disagreement.
     An unsourced claim disagrees with a sourced one -> targeted re-query.
     Never assert an unattested claim and then contradict it."

**And the loop does not police itself.** Round 2 of the live exchange moved
"30 parchment" to "30 Rives BFK" — the source it came from says *Japanese (50)
and parchment (30)*, and that the *Rives* was the edition destroyed. It also
invented "Mourlot workshop records confirm", an appeal to authority with no
source, attached to a conclusion (stones) that IS corroborated elsewhere. Each
round gets more accurate and more confidently specific at once, so the evidence
must come from RETRIEVAL at every round, never from the model's memory.

**Michael's ruling on unattested claims, 2026-08-22 — option (c), extended:**

    "keep the underlying fact if it's independently corroborated and drop only
     the appeal to authority ... but I would also include mentioning that 'some
     sources disagree' and spell out the disagreement, increasing the story size
     if it is small enough, as it is intriguing for listeners and underscores
     our accuracy."

So a disagreement is not a problem to be resolved down to one side. It is
material, and it is told.
"""
import os
import re
from typing import Dict, List, Optional

from text_fold import fold

__all__ = ['claims_of', 'challenge_queries_for', 'ADJUDICATION_PROMPT',
           'STATUSES', 'count_statuses', 'ungrounded_names']

STATUSES = ('CONFIRMED', 'CORRECTED', 'DISPUTED', 'UNATTESTED')


def count_statuses(adjudication: str) -> dict:
    """Tally the verdict lines.

    The status word is commonly preceded by a bullet or bold marker — Gemini
    writes `* CONFIRMED ...` as often as `CONFIRMED ...`. A naive `^STATUS`
    match reported 0/0/0/0 on 30 of 37 answers that had adjudicated perfectly
    well; the instrument was wrong, not the model.
    """
    import re as _re
    return {s: len(_re.findall(rf'^[\s>*\-•]*\**\s*{s}\b', adjudication or '',
                               _re.M | _re.I)) for s in STATUSES}

_STOP = {'the', 'and', 'for', 'with', 'from', 'that', 'this', 'was', 'were',
         'had', 'has', 'have', 'been', 'his', 'her', 'its', 'their', 'which',
         'because', 'when', 'after', 'before', 'into', 'onto', 'than', 'then',
         'they', 'them', 'these', 'those', 'about', 'would', 'could', 'also'}

# A claim worth challenging carries something checkable: a number, a material,
# a technique, a date, a named party. A sentence of pure evaluation has nothing
# to check and nothing to correct.
_CHECKABLE = re.compile(
    r'\b(1[4-9]\d{2}|20[0-2]\d)\b'                       # a year
    r'|\b\d{1,4}\s*(?:copies|sets|sheets|plates|lithographs|proofs)\b'
    r'|\b(?:stone|zinc|aluminium|aluminum|plate|press|paper|vellum|parchment|'
    r'japon|japanese|rives|arches|wove)\w*\b'
    r'|\b(?:destroy|abandon|scrap|reject|refuse|erase|efface|sand|cancel|'
    r'commission|publish|print|delay|halt|die[ds]?)\w*\b',
    re.IGNORECASE)


def claims_of(sentences: List[Dict], limit: int = 5) -> List[Dict]:
    """The sentences worth challenging, richest first.

    `sentences` are D505-judged dicts. Irrelevant ones are dropped — a claim
    about somebody else is not this stop's problem — and what remains is ranked
    by how much checkable content it carries, because the challenge budget is
    a few queries per stop and not a few dozen.
    """
    out = []
    for j in sentences:
        if j.get('verdict') == 'irrelevant':
            continue
        text = (j.get('sentence') or '').strip()
        # Strip list bullets and Gemini's leaked grounding structures.
        text = re.sub(r'^[\*\-•]\s*', '', text)
        text = re.sub(r'\[?PerQueryResult\(.*', '', text).strip()
        if len(text) < 30:
            continue
        hits = len(set(m.group(0).lower() for m in _CHECKABLE.finditer(text)))
        if not hits:
            continue
        out.append({'claim': text, 'checkable_terms': hits,
                    'sources': j.get('sources') or []})
    out.sort(key=lambda c: -c['checkable_terms'])
    # De-duplicate near-identical claims; Gemini repeats itself across answers.
    kept: List[Dict] = []
    for c in out:
        f = fold(c['claim'])[:70]
        if any(f[:50] in fold(k['claim']) for k in kept):
            continue
        kept.append(c)
        if len(kept) >= limit:
            break
    return kept


def challenge_queries_for(claim: str, work_title: str,
                          agents: Optional[List[str]] = None,
                          limit: int = 2) -> List[str]:
    """Queries that interrogate THE CLAIM, not the work.

    D507's keyword form asks about the object and returns the same documents for
    every credit_line. A challenge query must contain the claim's own
    distinctive terms — the numbers, the papers, the verb — so that a page
    disagreeing about *those* can surface.
    """
    work = re.sub(r'\s*\([^)]*\)\s*', ' ', work_title or '').strip()
    terms = []
    for m in _CHECKABLE.finditer(claim):
        t = m.group(0).strip().lower()
        if t and t not in terms and fold(t) not in _STOP:
            terms.append(t)
    # Rare content words the checkable pattern missed.
    for w in re.findall(r"[A-Za-zÀ-ÿ'’\-]{6,}", claim):
        if len(terms) >= 6:
            break
        lw = w.lower()
        if lw in _STOP or lw in terms:
            continue
        terms.append(lw)

    out = []
    if work:
        out.append(f'"{work}" ' + ' '.join(terms[:4]))
        if len(terms) > 4:
            out.append(f'"{work}" ' + ' '.join(terms[4:8]))
    for a in (agents or [])[:1]:
        if work and len(out) < limit + 1:
            out.append(f'{a} "{work}" ' + ' '.join(terms[:3]))
    return [q for q in out if q.strip()][:limit]


# The round-2 prompt. Evidence comes from retrieval and is quoted verbatim; the
# model is asked to adjudicate against it, not to recall.
ADJUDICATION_PROMPT = """You wrote this about {work} in the exhibition "{exhibition}":

--- YOUR EARLIER ANSWER ---
{answer}
--- END ---

Independent sources were then retrieved. Here is what they actually say, quoted:

--- RETRIEVED EVIDENCE ---
{evidence}
--- END ---

Do TWO things.

PART 1 — ADJUDICATE. For each factual claim in your earlier answer, output one line:

  CONFIRMED  <claim> — <which source supports it>
  CORRECTED  <what you said> -> <what the sources say> — <which source>
  DISPUTED   <claim> — source A says X; source B says Y
  UNATTESTED <claim> — no retrieved source supports this

Rules you must follow:
- Judge ONLY against the retrieved evidence above. Do not rely on memory.
- If you cited an authority the evidence does not show (for example "workshop
  records confirm"), that phrasing is UNATTESTED even when the underlying fact
  is CONFIRMED by another source. Say so separately.
- Two sources genuinely disagreeing is DISPUTED, not an error to resolve.

PART 2 — WRITE THE STORY. 3 to 6 sentences, for a visitor standing in front of
the work.

- Use ONLY claims you marked CONFIRMED or CORRECTED.
- THIS IS READ ALOUD. Never write a source, domain or URL in square brackets.
  "[christies.com, sothebys.com]" is heard as noise and there is no way for a
  listener to look it up. No brackets of any kind, no footnote markers.
- Name a source ONLY where sources DISAGREE, and then say it inside the sentence
  in words a listener understands — the institution, not the domain:
      GOOD  "Christie's records eleven finished plates; Sotheby's lists twelve."
      GOOD  "Some accounts say the sheets were lambskin, others sheepskin."
      BAD   "The edition ran to eleven plates [christies.com]."
  Where the sources agree, state the fact plainly and cite nothing.
- Where a DISPUTED claim is interesting, TELL THE DISAGREEMENT: "some sources say
  X, others say Y". Do not pick a side and do not hide it. This is wanted.
- Drop UNATTESTED claims. If the underlying fact is confirmed elsewhere, keep the
  fact and drop the appeal to authority.
- Something must HAPPEN: someone did something and it mattered.
- No praise, no describing how it looks, no telling the visitor what to feel.

Output PART 1 then PART 2 with those headings."""


# ─── [D510] Entity linking — the "printer Celestin" class ─────────────────────
# Michael, 2026-08-22: *"Don't drop false positive 10.2 'printer Celestin' —
# that's a separate bug from adjudicator confirming invented entity. Needs
# entity linking check, not just page-fetch."*
#
# He is right that it is separate. Page-fetch fixes FALSE NEGATIVES — true
# claims rejected because the evidence was truncated. This is the FALSE
# POSITIVE: the adjudicator marked "printer Celestin" CONFIRMED when that name
# appears in no retrieved source at all.
#
# The check is mechanical and needs no model: every person named in the
# delivered story must appear in the evidence that was actually retrieved, or
# in the stop's own matrix. A name in neither was introduced by the writer.

_NAME = re.compile(r"[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]{2,}(?:\s+[A-ZÀ-Þ][A-Za-zÀ-ÿ'’\-]+)*")

# Capitalised tokens that are not people: sentence starts, months, places and
# the vocabulary of the domain itself.
_NOT_A_PERSON = {
    'the', 'this', 'that', 'these', 'those', 'while', 'when', 'after', 'before',
    'because', 'although', 'however', 'sources', 'source', 'records', 'record',
    'january', 'february', 'march', 'april', 'may', 'june', 'july', 'august',
    'september', 'october', 'november', 'december', 'paris', 'london', 'boston',
    'new york', 'madrid', 'barcelona', 'france', 'spain', 'world war',
    'museum', 'gallery', 'exhibition', 'lithograph', 'lithographs', 'edition',
    'plate', 'plates', 'stone', 'stones', 'paper', 'book', 'suite', 'portfolio',
    'in', 'at', 'on', 'by', 'his', 'her', 'their', 'its', 'it', 'he', 'she',
}


def ungrounded_names(story: str, evidence_text: str, matrix: Optional[Dict] = None,
                     extra: Optional[List[str]] = None) -> List[str]:
    """People named in the story who appear in NO retrieved evidence.

    Returns the offending names. Empty is the pass condition.

    Deliberately mechanical: no model is asked whether a name is real, because a
    model is what introduced it. The test is presence in text we actually
    fetched, or in the museum's own matrix.
    """
    haystack = fold(evidence_text or '')
    for v in (matrix or {}).values():
        if isinstance(v, str) and v:
            haystack += ' ' + fold(v)
    for e in (extra or []):
        haystack += ' ' + fold(e)

    bad = []
    for m in _NAME.finditer(story or ''):
        name = m.group(0).strip()
        # [D510 r2] Strip the possessive BEFORE matching. "Miró's" and "Gris's"
        # were reported ungrounded while Miró and Gris are in every source —
        # the apostrophe-s simply broke the comparison. Flagging a grounded
        # name is worse than useless: it would block a good story.
        name = re.sub(r"['’]s$", '', name).strip()
        f = fold(name)
        if f in _NOT_A_PERSON or len(f) < 4:
            continue
        # A SINGLE capitalised word needs evidence that the story treats it as
        # a name. Two rules, and they are position rules rather than a word list:
        #
        #   - at a SENTENCE START anything is capitalised. The first run flagged
        #     "Working", "Consequently", "Instead", "Around", "Decades",
        #     "Accounts", "Released" — none is a person.
        #   - preceded by a ROLE WORD it is a name regardless of position.
        #     "printer Celestin" is the case this whole check exists for, and a
        #     bare two-token rule loses it, since "printer" is lowercase.
        if len(f.split()) < 2:
            before = (story or '')[:m.start()].rstrip()
            role_before = bool(re.search(
                r'\b(printer|publisher|artist|dealer|poet|collector|donor|'
                r'engraver|bookbinder|patron|author|editor|craftsman|'
                r'lithographer|photographer|sculptor|architect|chef)\s*$',
                before, re.I))
            at_sentence_start = (not before) or before.endswith(('.', '!', '?', ':'))
            if at_sentence_start and not role_before:
                continue
            if not role_before and not re.search(r'[a-z,]\s*$', before):
                continue
        if any(t in _NOT_A_PERSON for t in f.split()):
            continue
        # [D515] A capitalised word FOLLOWED by a role word is modifying that
        # role, not naming anyone: "the Parisian publisher Art & Valeur",
        # "the French poet", "the Catalan printer". Measured 2026-08-23 —
        # `Parisian` was flagged ungrounded and discarded a candidate before the
        # gate was consulted. This is the mirror of the role_before rule above:
        # the role word tells you which side the name is on.
        after = (story or '')[m.end():].lstrip()
        if re.match(r'^(printer|publisher|artist|dealer|poet|collector|donor|'
                    r'engraver|bookbinder|patron|author|editor|craftsman|'
                    r'lithographer|photographer|sculptor|architect|chef|'
                    r'atelier|workshop|firm|house|gallery|museum)\b',
                    after, re.I):
            continue
        # Present whole, or by any of its tokens longer than three characters —
        # evidence says "Mourlot" where the story says "Mourlot Frères".
        if f in haystack:
            continue
        if any(t in haystack for t in f.split() if len(t) > 3):
            continue
        if name not in bad:
            bad.append(name)
    return bad


# ─── [D515] "Positively identified as factually wrong" ────────────────────────
#
# Michael, 2026-08-23, replacing the multi-key gate:
#
#   "The only reason for not accepting/fail should be positively identified as
#    factual wrong events."
#
# That phrase has to be given a narrow, mechanical meaning or it becomes the old
# gate under a new name. The four adjudication statuses are NOT four grades of
# wrongness:
#
#   UNATTESTED  we found no source        -> NOT wrong. D510 measured that most
#                                            of these were our own truncation.
#   DISPUTED    sources disagree          -> NOT wrong. The prompt asks for the
#                                            disagreement to be TOLD.
#   CORRECTED   a source contradicts it   -> wrong when it was written, and PART 2
#                                            is instructed to use the corrected
#                                            version. Usually already fixed.
#   CONFIRMED   supported                 -> not wrong.
#
# So the only positive identification available is: **the adjudicator corrected a
# claim, and the delivered story still asserts the version it corrected.** That is
# a fact we hold to be false, in text we are about to publish. Everything else is
# an absence of evidence, which is what Michael's rule refuses to treat as a fail.
#
# Matching is by distinguishing tokens rather than substring: the adjudicator
# paraphrases, so `"1974" -> "1975"` is caught by 1974 surviving with no 1975
# present, and a rewording that keeps the meaning is not flagged.

_CORRECTED_LINE = re.compile(
    r'^[\s>*\-•]*\**\s*CORRECTED\b[:\s]*(.+?)\s*(?:->|→|=>)\s*(.+?)\s*(?:—|--|–)\s*.*$',
    re.M | re.I)


def _distinguishing(a: str, b: str) -> set:
    """Tokens that carry a's meaning and are absent from b."""
    ta = {t for t in re.findall(r'[\w’\']+', fold(a)) if len(t) > 3 and t not in _STOP}
    tb = {t for t in re.findall(r'[\w’\']+', fold(b)) if len(t) > 3 and t not in _STOP}
    return ta - tb


def surviving_errors(story: str, adjudication: str) -> List[Dict]:
    """Corrections the delivered story ignored — the D515 veto.

    Returns [{'wrong', 'right', 'tokens'}]; empty is the pass condition.

    Deliberately conservative: it fires only when EVERY distinguishing token of
    the corrected-away version is present in the story and NONE of the correction's
    own distinguishing tokens is. A story that adopted the correction, or reworded
    around it, is not flagged — false vetoes are exactly what this rule exists to
    stop.
    """
    # Token SET membership, not substring. Written as substring first, and the
    # first test caught it: `release` (from the correction) is inside `released`
    # (in the story), so every real error looked adopted and the veto never
    # fired. A veto that cannot fire is the same failure class as D242.
    story_tokens = set(re.findall(r'[\w’\']+', fold(story or '')))
    out = []
    for wrong, right in _CORRECTED_LINE.findall(adjudication or ''):
        w_only = _distinguishing(wrong, right)
        r_only = _distinguishing(right, wrong)
        if not w_only:
            continue
        if not all(t in story_tokens for t in w_only):
            continue
        if any(t in story_tokens for t in r_only):
            continue
        out.append({'wrong': wrong.strip(), 'right': right.strip(),
                    'tokens': sorted(w_only)})
    return out
