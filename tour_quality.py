"""Score a generated tour against the defects Michael has actually reported.

Michael, 2026-09-21: *"at some point I will rely on your judgement and the
described 3 steps can be done by you automatically informing me but not continue
without my permission unless I stop you. How can we make this happen?"*

The three steps are: generate a batch → notice one is much better → diagnose and
fix → regenerate. The loop cannot run itself while a human is the only instrument,
so this is the instrument. It measures ONLY defects with an objective signature —
every one of them something Michael found by reading and then had to explain:

  no_story        zero named people (Logan, three rounds running)
  thin            fewer stops delivered than requested (the Pulpit, D578)
  truncated       "Founded in 1868 by St." / "engaged of Public Works"
  repeated        the same episode told at two stops (Mother Teresa)
  refuted         a bound place too far away (Archbishop of Los Angeles, D577)
  bare_death      a named violent death with no circumstances
  distance        a kilometre figure on a building tour
  spliced         "...aviation sector.3 million passengers" — a cut sentence rejoined
  foreign_venue   another airport's facts asserted as this one's (the Atlanta bug)
  fabricated_attribution  "constructed in 1887-1889 by Gustave Eiffel" on an airport,
                  "Founded in 1868 by St. Mary Help of Christians" on the church of
                  that dedication — a builder/founder frame filled with a nearby
                  famous name or the venue's own patron saint (LOCAL-527, D577)

**What it deliberately cannot judge: whether a tour is INTERESTING.** That is the
thing Michael reads for, and no counter substitutes for it. The loop is therefore
allowed to iterate on measurable defects and must hand the judgement call back.
"""

import os
import re

REQUIRED_CLEAN = ('truncated', 'repeated', 'refuted', 'bare_death', 'distance',
                  'fabricated_attribution',
                  # [LOCAL-538] a dangling complement or reference is a broken
                  # sentence — round 9 scored CLEAN while carrying both, and that
                  # was the bug this ticket exists to fix.
                  'dangling_complement', 'dangling_reference')

_STOP = re.compile(r'^Stop (\d+):\s*(.+)$', re.M)
_YEAR = re.compile(r'\b(1[5-9]\d\d|20\d\d)\b')
# [2026-09-23, kiro critic] The first version counted a name ONLY when a title
# preceded it, then de-duped — so it was a count of title+name bigrams, not of
# people. "architect James Murphy", "crafted by local artisans Eric Boeglin", and
# the murder victims all scored zero, and LEAD read the resulting 1-vs-5 gap
# between Logan and the church as a real difference in story density. It may not be.
#
# A bare capitalised bigram is far too noisy ("After World", "Airport Concourse",
# "Christian Europe"), so a name counts when a TITLE or a ROLE introduces it — the
# contexts in which this pipeline actually names people.
_PERSON_TITLE = (r'Governor|Mayor|Father|Cardinal|Archbishop|Mother|Sister|President|'
                 r'Rev\.?|Dr\.?|Sir|Captain|Chef|Bishop|Pope|Saint|Msgr\.?|General|'
                 r'Senator|Justice|Lord|Abbot|Prior|Deacon')   # NOT 'Lady': "Our Lady Help of Christians" is a church, not a person
_PERSON_ROLE = (r'architect|designer|builder|artisan|artisans|artist|sculptor|painter|'
                r'engineer|founder|donor|patron|benefactor|pastor|priest|rector|'
                r'organist|composer|mason|craftsman|craftsmen|activist|pilot|'
                r'controller|curator|historian|photographer|author|writer|'
                # [2026-09-23] added after a second critic listed people the counter
                # still missed: "flight attendants Betty Ann Ong", "hijackers,
                # including Mohamed Atta", "the landing of Charles Lindbergh".
                r'attendant|attendants|hijacker|hijackers|aviator|aviators|'
                r'passenger|passengers|officer|officers|soldier|soldiers|nun|nuns|'
                r'pioneer|pioneers|immigrant|immigrants|worker|workers|'
                r'mayor|governor|senator|nurse|doctor|teacher|singer|musician')
# Frames that introduce a person without any role word at all.
_PERSON_FRAME = (r'(?:landing|visit|arrival|death|funeral|memory|honou?r|legacy|'
                 r'portrait|statue|grave|story)\s+of|including|alongside|'
                 r'named\s+(?:for|after)|'
                 # Attribution: "constructed in 1887-1889 by Gustave Eiffel" named a
                 # person the counter could not see at all.
                 # The verb is often not adjacent to "by": "constructed in
                 # 1887-1889 by Gustave Eiffel". Allow a short gap, but stop at a
                 # sentence boundary so it cannot reach across clauses.
                 r'(?:led|built|constructed|designed|founded|painted|sculpted|carved|'
                 r'commissioned|donated|funded|conceived|created)\b[^.]{0,40}?\bby')
# NO re.IGNORECASE. With it, [A-Z] matches lowercase too, and the pattern happily
# captured "Cuenin d", "Law r", "of P" and "here" — a count of 13 "people" in a
# tour with four. Titles are capitalised in prose and roles are lowercase, so the
# alternation spells both out instead.
# A given name plus up to two further tokens, each either a middle initial
# ("H.") or another name word -- "Betty Ann Ong", "Walter H. Cuenin".
# The period on an initial is REQUIRED: with it optional, [A-Z]\.? matched the
# first letter of the surname and the name came out as "Betty A" / "Charles L".
_NAME = r'[A-Z][a-z]{2,}(?:\s+(?:[A-Z]\.|[A-Z][a-z]{2,})){0,2}'
_PERSON = re.compile(
    r'\b(?:(?:' + _PERSON_TITLE + r')\.?\s+'
    r'|(?:' + _PERSON_ROLE + r')s?\s*,?\s+(?:named\s+)?'
    r'|(?:' + _PERSON_FRAME + r')\s+)'
    r'(' + _NAME + r')'
    # "...attendants Betty Ann Ong AND Madeline Amy Sweeney" -- one introducer,
    # two people. Without this the second name is invisible.
    r'(?:\s+and\s+(' + _NAME + r'))?')
# a fragment ending on a title with no name after it
_TRUNC = re.compile(r'\b(St|Fr|Dr|Mr|Mrs|Rev|Msgr|Jr|Sr|Prof)\.\s+(?=[A-Z][a-z]+\s+'
                    r'(?:you|As|The|It|This|Its|Their|He|She|We)\b)')
# [2026-09-23] The \b above is load-bearing. Without it "He" matched the start of
# "Help", so round 8's "Founded in 1868 by St. Mary Help of Christians" scored as a
# truncated fragment -- the ONLY defect reported on that tour, and spurious. The
# real error in that same sentence (the church's dedication turned into a founder)
# went unflagged.
_MANGLED = re.compile(r'\b(?:engaged|which|that|and|of)\s+of\s+[A-Z]')
# [2026-09-23, LOCAL-530, kiro critic LOCAL-517 on LOGAN_2] Control Tower stop:
# "They authorized of Public Works to lease this land to the U.S. Army." The
# object noun is gone -- it read "the Department of Public Works", and a gate
# excised the head noun "Department" (an unglossed reference), gluing the verb
# straight onto "of". Verified by reproducing _excise_governed_construction with
# entity="Department" -> the exact sentence, and it passed the gate's own
# well-formedness guards (see D583/LOCAL-475 for the same gate producing broken
# English). The gate fix is in unglossed_reference_gate.py; this is the scorer's
# net, so that if the shape ever ships again the loop flags it for regeneration.
#
# _MANGLED already caught the round-3 sibling ("engaged of Public Works") because
# 'engaged' happened to be in its alternation, but the round-7 verb ('authorized')
# was not -- a hand-listed set of verbs is the enumeration trap D476 warns about.
# The signature is structural: a TRANSITIVE verb that governs a direct object
# ("authorized [a body]"), left directly abutting "of" with the object deleted.
# Restricted to verbs of official action on an institution -- the family the gate
# strips -- so it never fires on the legitimate "-ed of" idioms (comprised of,
# composed of, consisted of, deprived of, accused of, approved of, died of,
# informed of, conceived of, made of). Across all 46 tours in TOURS_FOR_REVIEW it
# fires exactly twice, both true positives, no false positives.
_VERB_NEEDS_OBJECT = (
    r'authoriz|authorised|engag|establish|appoint|commission|task|direct|'
    r'instruct|order|permit|enabl|allow|assign|designat|elect|nominat|'
    r'compel|urg|request|requir|forbid|forbad|prohibit|mandat')
_OBJECT_DROPPED = re.compile(
    r'\b(?:' + _VERB_NEEDS_OBJECT + r')(?:ed|es|e)?\s+of\s+[A-Z]')
# [2026-09-21, Michael on LOGAN_1] "...ensuring Boston's competitive edge in the
# aviation sector.3 million passengers in 2025." A sentence was cut and the
# remainder spliced on with no space, so the tour states ".3 million" — the leading
# digits gone. Two signatures: a full stop immediately followed by a digit, and a
# sentence that BEGINS with a decimal fragment.
_SPLICE = re.compile(r'[a-z]\.\d|(?:^|\s)\.\d+\s+\w')
# [2026-09-23, kiro critic on CHURCH_2] "during the height of the Archdiocesethe
# clergy abuse crisis" — the same splice defect, but joining two WORDS instead of a
# word and a number, so _SPLICE missed it entirely.
#
# English is full of words that merely END in these ("breathe", "understand",
# "together"), so the rule is deliberately narrow: the glued-on function word must
# follow a stem of 6+ letters, which no common English word does for this suffix
# set. _SPLICE_OK carries the exceptions found so far.
_WORD_SPLICE = re.compile(r'\b([a-z]{6,})(the|this|that|when|after|which|were)\b', re.I)
_SPLICE_OK = {'breathe', 'understand', 'together', 'whitewashed'}
# [2026-09-23, kiro critic LOCAL-517 on LOGAN_3] "Terminal A Ticketing / Check-In
# -- an exhibit at this venue. Detailed information was not available at generation
# time." The critic: "a blank stop -- a placeholder shipped as content... the single
# worst stop in the batch and the clearest thing tour_quality.py should have caught
# but apparently did not (it is not truncation, not a repeat, not a refuted claim --
# it is an admitted void)." Verified: LOGAN_3 scored ZERO defects.
_PLACEHOLDER = re.compile(
    r'(?:detailed\s+)?information\s+(?:was|is)\s+not\s+available'
    r'|not\s+available\s+at\s+generation\s+time'
    r'|no\s+(?:further\s+)?(?:details?|information)\s+(?:was|is|were)\s+(?:found|available)'
    r'|an\s+exhibit\s+at\s+this\s+venue', re.I)
_KM = re.compile(r'\b\d+(?:\.\d+)?\s*(?:km|kilometre|kilometer)s?\b', re.I)


# ─── Dangling reference (LOCAL-538) ──────────────────────────────────────────
# Round 9 scored CLEAN while carrying two sentences broken in exactly the way
# LOCAL-530 exists to catch, in shapes its "<verb> of <Capital>" regex cannot see.
# Both are one grammatical fault: a phrase that REQUIRES a complement, standing
# without one. LOCAL-530's own warning applies — "a hand-listed set of verbs is
# the enumeration trap D476 warns about" — so neither check below is a list of the
# words to catch. Each is a GRAMMATICAL CLASS (an agentive suffix; a [+eventive]
# noun class; a personal pronoun) filtered by a structural test on the surrounding
# syntax. The words that appear in the alternations are members of a linguistic
# class, not a catalogue of the specific referents seen in round 9.

# A. RELATIONAL NOUN WITH NO COMPLEMENT — LOGAN_1 (round 9), Control Tower, verbatim:
#
#   "Trippe, the founder and later Pan American World Airways, helped connect
#    Boston to New York, marking the city as a pivotal node..."
#
# "the founder" is a relational noun: it needs "of <what>". Here the "of" was
# deleted and the given name (Juan) with it, so LOCAL-530's _OBJECT_DROPPED — which
# matches the "of" — has nothing to match. The signature is structural and does not
# name "founder": an appositive ", the <AGENTIVE>" (a deverbal agentive/relational
# nominal, marked by the -er/-or/-ist suffix — the grammar of agent nouns, not a
# list) coordinated by "and"/"," DIRECTLY to a proper-noun phrase that STANDS ALONE
# (a comma or period follows it, not a lowercase head noun), with NO "of",
# possessive, or "who" complement in the coordinator span or immediately after the
# proper noun. A correct sentence puts the "of" back — "the founder of Pan
# American", "the founder and chairman of Pan American" — and both clear. Over all
# 48 files in TOURS_FOR_REVIEW this fires exactly once, on the sentence above, and
# on nothing else (measured; see SUBMISSION_LOCAL-538.md).
_RELATIONAL_NO_COMPLEMENT = re.compile(
    r',\s+the\s+([a-z]+(?:er|or|ist))\b'            # appositive relational/agentive noun
    r'(\s+(?:and|,)\s+(?:later|then|also|former|current)?\s*)'  # coordinator (+ optional temporal adverb)
    r'([A-Z][a-zA-Z]+(?:\s+[A-Z][a-zA-Z]+)*)'       # the coordinated proper-noun phrase
    r'(\s*[,.]|\s+[a-z]+)')                          # what follows it
# The "of"/possessive/"who" that a relational noun needs, seen at the complement
# site: inside the coordinator span (group 2) or right after the proper noun.
_COMPLEMENT_IN_COORD = re.compile(r"\bof\b|['\u2019]s\b|\bwho\b")
_COMPLEMENT_AFTER = re.compile(r"^\s*(?:of|behind|for)\b|^\s*['\u2019]s\b|^\s*,?\s*who\b")


def _find_relational_no_complement(text):
    """Return [(relnoun, span_text)] for relational nouns standing without their
    complement, per the structure documented above. Empty list = none."""
    out = []
    for m in _RELATIONAL_NO_COMPLEMENT.finditer(text or ''):
        relnoun, coord, _propn, follow = m.groups()
        if _COMPLEMENT_IN_COORD.search(coord):
            continue                                 # "founder and chairman OF ..." — complement present
        after = text[m.end():m.end() + 40]
        if _COMPLEMENT_AFTER.match(after):
            continue                                 # "founder and CEO OF Acme" — complement is merely late
        if re.match(r'\s+[a-z]', follow):
            continue                                 # "director and Oscar winner" — 'winner' heads the proper noun
        out.append((relnoun, m.group(0).strip()))
    return out


# B. DEMONSTRATIVE / PRONOUN WITH NO ANTECEDENT — CHURCH_1 (round 9), Stained Glass
# Windows, verbatim:
#
#   "In the absence of stained glass, we find the church's story told through
#    different means. This event, deeply etched into the church's modern history,
#    demonstrates that while the church may not hold stained glass windows..."
#
# No event has been narrated — not in this stop, not in the one before. "This event"
# points at nothing. The hard part is that encapsulating anaphora is ORDINARY, GOOD
# English: "This decision", "This recognition", "This moment" legitimately package a
# preceding clause without repeating a head noun ("achieved certification. This
# recognition..."). Firing on those would be worse than no check. The structural
# escape is the noun's semantic class: an EVENTIVE noun (event, incident, episode,
# ceremony, visit, ...) denotes a HAPPENING and so demands that a happening was
# narrated — and a narrated happening is normally DATED or NAMES an actor. So an
# eventive anaphor that opens a stop body (first or second body sentence) whose
# preceding two sentences carry NEITHER a year NOR a multi-word proper noun has
# nothing to bind to. Abstract summarisers (recognition/decision/choice) are NOT in
# the class — they can package a state or a description, so they are never flagged.
# Over all 48 files this fires exactly once, on the sentence above. (A regex cannot
# decide the general abstract case — whether "recognition" matches an earlier
# "certification" is semantic; restricting to the [+eventive] class is what makes a
# purely structural, zero-false-positive check possible. See SUBMISSION_LOCAL-538.md.)
_EVENTIVE_ANAPHOR = re.compile(
    r'^(This|These)\s+(?:[a-z]+\s+){0,2}'
    r'(event|incident|episode|ceremony|gathering|confrontation|'
    r'meeting|visit|attack|disaster|tragedy|celebration|protest)\b', re.I)
# The pronoun sibling (the task's second case): round 7's "Her presence, though
# unexpected..." with no woman named anywhere. A sentence-initial SINGULAR GENDERED
# pronoun with NO person introduced earlier IN THE WHOLE TOUR (searched backwards
# across stops, per the task). Restricted to she/he/her/his/him: a singular gendered
# pronoun demands a specific NAMED INDIVIDUAL, whereas "they/their" routinely corefer
# with a plural COMMON-NOUN group ("military officers ... They argue", "parishioners
# ... Their protest") that is a legitimate antecedent the person-frame does not name
# — flagging those is exactly the "fires on ordinary English" failure to avoid.
# Person detection reuses the scorer's own _PERSON frame, defined below. No tour
# currently on disk has this defect, so it fires nowhere in the corpus (0 false
# positives) and stands as a net for the shape when it ships.
_LEAD_PRONOUN = re.compile(
    r'(?:(?<=[.!?]\s)|(?<=\n))(She|He|Her|His|Him)\b')
_YEAR_ANCHOR = re.compile(r'\b(1[5-9]\d\d|20\d\d)\b')
_PROPER_ANCHOR = re.compile(r'\b[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+')

_STOP_OR_SCHEMA = re.compile(
    r'^(?:Address|Coordinates|Type/Specialty|Specific Examples|'
    r'Operational Details|Orientation|Directions|Tour-Category):', re.I)


def _stop_body_blocks(text):
    """Yield (title, body) per stop — body is narration only (schema/nav lines
    stripped), so the anaphor position test sees what the listener hears."""
    stops = list(_STOP.finditer(text or ''))
    for k, sm in enumerate(stops):
        start = sm.end()
        end = stops[k + 1].start() if k + 1 < len(stops) else len(text)
        block = text[start:end]
        body_lines = [ln.strip() for ln in block.splitlines()
                      if ln.strip() and not _STOP_OR_SCHEMA.match(ln.strip())]
        yield sm.group(2), '\n'.join(body_lines)


def _split_sentences_simple(t):
    return re.split(r'(?<=[.!?])\s+', t or '')


def _find_dangling_references(text):
    """Return [(kind, snippet)] for dangling demonstratives/pronouns.

    kind is 'demonstrative' for an eventive anaphor opening a stop with no dated or
    named happening in the two sentences before it, or 'pronoun' for a
    sentence-initial personal pronoun with no person named earlier in the whole tour.
    """
    out = []
    # B1 — eventive demonstrative anaphor with no antecedent happening.
    for title, body in _stop_body_blocks(text):
        sents = _split_sentences_simple(body)
        for si in range(1, min(3, len(sents))):          # 2nd or 3rd body sentence
            s = sents[si].strip()
            if not _EVENTIVE_ANAPHOR.match(s):
                continue
            window = ' '.join(sents[max(0, si - 2):si])   # preceding two sentences
            if _YEAR_ANCHOR.search(window) or _PROPER_ANCHOR.search(window):
                continue
            out.append(('demonstrative', s[:80]))
    # B2 — personal pronoun with no person named anywhere earlier in the tour.
    for m in _LEAD_PRONOUN.finditer(text or ''):
        if _PERSON.search((text or '')[:m.start()]):
            continue
        out.append(('pronoun', (text or '')[m.start():m.start() + 60].replace('\n', ' ')))
    return out


# [2026-09-23] "funded by Irish immigrants" -> a person called Irish. Attribution
# frames often take a people-group rather than a person.
_NOT_A_NAME = {
    'irish', 'italian', 'german', 'french', 'polish', 'english', 'scottish',
    'spanish', 'portuguese', 'greek', 'chinese', 'japanese', 'russian', 'dutch',
    'swiss', 'belgian', 'mexican', 'american', 'canadian', 'australian',
    'catholic', 'protestant', 'jewish', 'muslim', 'christian', 'orthodox',
    'local', 'native', 'colonial', 'federal', 'royal', 'imperial',
}


try:                                    # single source of truth for "not a person"
    from derepetition_guard import _NOT_PERSON
except Exception:                       # pragma: no cover - keep the scorer standalone
    _NOT_PERSON = set()


# ─── Fabricated builder/founder attribution (LOCAL-527) ──────────────────────
# Round 7 and round 8 both shipped an airport whose Control Tower was "constructed
# in 1887-1889 by Gustave Eiffel" (that is the Eiffel Tower), and a church "Founded
# in 1868 by St. Mary Help of Christians" (the church's own dedication turned into a
# person). The frame "<built|founded|constructed|...> in <YEAR> by <NAME>" is being
# filled with whatever famous-sounding name is nearby and nothing checked it. The
# scorer already parsed this frame — but only to COUNT the person, never to judge
# whether the attribution was true. This adds the judgement.
#
# The verb and the "by NAME" are often separated by the year span, so match the
# whole shape in one pass and stop at a sentence boundary so it cannot reach across
# clauses. The dash between years may be a hyphen or an en/em dash.
_ATTRIB_FRAME = re.compile(
    # Verbs that FOUND or CONSTRUCT a place. Deliberately excludes "designed" and
    # "created" — those are the normal verbs of art attribution ("Nu bleu IV,
    # created in 1952 by Henri Matisse"), which is legitimate tour content, not a
    # venue-founding claim. The three real defects are all "constructed"/"built"/
    # "founded", so this covers them without swallowing art tours.
    r'\b(built|constructed|founded|established|erected)\b'
    r'[^.]{0,30}?'                                  # "... in", optional filler
    r'\bin\s+(1[5-9]\d\d|20\d\d)'                    # the year the frame anchors on
    r'(?:\s*[-\u2012-\u2015\u2212]\s*\d{2,4})?'      # optional "-1889" span
    r'\s+by\s+'
    r'(?:(?:St|Fr|Dr|Mr|Mrs|Rev|Msgr|Sir|Sister|Mother|Father)\.?\s+)?'  # optional honorific
    r'(' + _NAME +
    # "...by St. Mary Help of Christians": keep the dedication tail ("of Christians")
    # so a patron-title founder is captured whole, not clipped at "Mary Help".
    r'(?:\s+(?:of|the|for|de|del|of\s+the)\s+[A-Z][a-z]{2,})*'
    r')',
    re.I)

# The venue's own dedication is who a church is FOR, never who founded it. "Our Lady
# Help of Christians" is a title of the Virgin Mary; a founder attributed to any part
# of that title is the dedication misread as a person. These are the multiword title
# cores that must never surface as a founder of the venue that bears them.
_DEDICATION_CORES = (
    'help of christians', 'our lady', 'perpetual help', 'sacred heart',
    'holy cross', 'holy trinity', 'good shepherd', 'blessed sacrament',
    'immaculate conception', 'guardian angels', 'precious blood',
)


def _find_fabricated_attributions(text):
    """Return a list of (kind, verb, year, name) attribution defects.

    kind is 'dedication' when the attributed founder is the venue's own dedication
    (catchable offline with certainty), or 'unverified' when it is a plain builder/
    founder attribution with no grounding to confirm it (catchable offline only as
    unverified — refuting it needs a source; see D577).
    """
    out = []
    for m in _ATTRIB_FRAME.finditer(text or ''):
        verb = m.group(1)
        year = m.group(2)
        name = (m.group(3) or '').strip()
        if not name:
            continue
        first = name.split()[0].lower()
        last = name.split()[-1].lower()
        # A people-group ("funded in 1868 by Irish immigrants") or a venue part is
        # not a fabricated person — those are handled elsewhere.
        if first in _NOT_A_NAME or last in _NOT_A_NAME:
            continue
        if first in _NOT_PERSON or last in _NOT_PERSON:
            continue
        low = name.lower()
        # (a) dedication / patron-saint rendered as founder — deterministic offline.
        # The attributed "founder" carries a Marian/patronal title core ("...by St.
        # Mary Help of Christians"): no church is FOUNDED BY the saint it is
        # dedicated TO. The title core in the founder name is conclusive on its own.
        ded = next((core for core in _DEDICATION_CORES if core in low), None)
        if ded is not None:
            out.append(('dedication', verb, year, name))
            continue
        # (b) otherwise it is a builder/founder attribution we cannot confirm.
        out.append(('unverified', verb, year, name))
    return out


def _count_people(text):
    """Distinct PEOPLE, de-duplicated by surname.

    "Law", "Bernard Law" and "Bernard F. Law" are one man, and counting them as
    three inflated a 4-stop tour to nine people. The surname — the last
    capitalised token — is the identity; the fullest form seen is kept for display.
    """
    by_surname = {}
    candidates = []
    for m in _PERSON.findall(text or ''):
        # Every group is a person: group 2 is the "X and Y" partner when present.
        candidates.extend([m] if isinstance(m, str) else [g for g in m if g])
    for name in candidates:
        name = name.strip()
        if not name:
            continue
        surname = name.split()[-1]
        if len(surname) < 3:
            continue
        # A frame like "including Terminal B" hands us scenery. The person-cap
        # already maintains this vocabulary (D584); share it rather than keeping
        # two lists that drift apart.
        if surname.lower() in _NOT_PERSON or name.split()[0].lower() in _NOT_PERSON:
            continue
        if surname.lower() in _NOT_A_NAME:
            continue
        if len(name) > len(by_surname.get(surname, '')):
            by_surname[surname] = name
    return len(by_surname)


def _stops(text):
    return _STOP.findall(text or '')


def score_tour(text, requested_stops=None, is_building_tour=False, anchor=None,
               geocoder=None, verify_attribution=None):
    """Return {'defects': {...}, 'metrics': {...}, 'clean': bool}.

    verify_attribution, when given, is called as verify_attribution(name, year,
    text) and must return truthy if a source confirms that person built/founded the
    venue in that year. It clears an otherwise-unverified attribution frame. It does
    NOT clear a dedication-as-founder error, which is wrong regardless of any source.
    Gemini is the natural implementation but is not required — offline, an unverified
    frame is flagged rather than refuted (D577).
    """
    text = text or ''
    stops = _stops(text)
    metrics = {
        'stops_delivered': len(stops),
        'stops_requested': requested_stops,
        'dates': len(_YEAR.findall(text)),
        'named_people': _count_people(text),
        'chars': len(text),
    }
    defects = {}

    if requested_stops and len(stops) < requested_stops:
        defects['thin'] = f"{len(stops)}/{requested_stops} stops delivered"
    if metrics['named_people'] == 0:
        defects['no_story'] = "no named people anywhere in the tour"

    blank = sorted({m.group(0).strip().lower() for m in _PLACEHOLDER.finditer(text)})
    if blank:
        defects['placeholder'] = (f"{len(blank)} stop(s) admit having no content: "
                                  + '; '.join(blank[:3]))

    trunc = _TRUNC.findall(text) + _MANGLED.findall(text) + \
        _OBJECT_DROPPED.findall(text) + \
        [m.group(0) for m in _SPLICE.finditer(text)]
    if trunc:
        defects['truncated'] = f"{len(trunc)} fragment(s), e.g. {trunc[0]!r}"

    if is_building_tour and _KM.search(text):
        defects['distance'] = f"kilometre figure on a building tour: {_KM.search(text).group(0)}"

    # Dangling reference (LOCAL-538). Both are one grammatical fault — a phrase that
    # requires a complement, standing without one — in shapes LOCAL-530 cannot see.
    #   dangling_complement  a relational noun ("the founder") whose "of <what>" was
    #                        deleted (round 9 LOGAN_1).
    #   dangling_reference   a demonstrative/pronoun ("This event", "Her presence")
    #                        with no antecedent introduced earlier (round 9 CHURCH_1).
    rel_nc = _find_relational_no_complement(text)
    if rel_nc:
        defects['dangling_complement'] = (
            f"{len(rel_nc)} relational noun(s) without complement, "
            f"e.g. {rel_nc[0][1]!r}")
    dangling = _find_dangling_references(text)
    if dangling:
        kinds = sorted({k for k, _ in dangling})
        defects['dangling_reference'] = (
            f"{len(dangling)} dangling {'/'.join(kinds)} reference(s), "
            f"e.g. {dangling[0][1]!r}")

    # Fabricated builder/founder attribution (LOCAL-527). Two kinds:
    #   dedication  the founder IS the venue's own dedication/patron saint — a
    #               deterministic offline error, always a defect.
    #   unverified  a plain "<built|founded|constructed> in <YEAR> by <NAME>" that
    #               nothing has confirmed. Offline it can only be flagged as
    #               unverified, never refuted (that needs a source — D577). If a
    #               grounding source is supplied that confirms the name, it clears.
    attribs = _find_fabricated_attributions(text)
    if attribs:
        confirm = None
        if callable(verify_attribution):
            def confirm(name, year):
                try:
                    return bool(verify_attribution(name, year, text))
                except Exception:
                    return False
        unresolved = []
        for kind, verb, year, name in attribs:
            if kind == 'unverified' and confirm and confirm(name, year):
                continue                       # a source vouches for it — keep it
            unresolved.append((kind, verb, year, name))
        if unresolved:
            kind, verb, year, name = unresolved[0]
            if kind == 'dedication':
                why = (f"dedication/patron rendered as founder: "
                       f"\"{verb} in {year} by {name}\"")
            else:
                why = (f"unverified attribution: \"{verb} in {year} by {name}\" "
                       f"(no source confirms it)")
            defects['fabricated_attribution'] = (
                f"{len(unresolved)} attribution(s); {why}")

    try:
        from derepetition_guard import _tokenize, _jaccard_similarity
        from sentence_split import split_sentences
        # Measure repeated CONTENT, not repeated navigation. Between two stops in
        # one building the directions are formulaic by nature — "As you exit the
        # Concourse, head towards the main terminal building" / "As you exit the
        # Jetbridge, walk towards the main terminal building" — and counting those
        # as duplicates buried the defect Michael actually reported, which was the
        # same STORY told at two stops (Mother Teresa at stops 1 and 2).
        _body = '\n'.join(
            ln for ln in (text or '').splitlines()
            if not re.match(r'^(Directions|Orientation|Address|Coordinates|'
                            r'Type/Specialty|Specific Examples|Operational Details):',
                            ln.strip()))
        seen, dupes = [], 0
        for s in split_sentences(_body):
            if len(s.split()) < 8:
                continue
            t = _tokenize(s)
            if any(_jaccard_similarity(t, p) >= 0.6 for p in seen):
                dupes += 1
            else:
                seen.append(t)
        if dupes:
            defects['repeated'] = f"{dupes} near-duplicate sentence(s)"
    except Exception:
        pass

    try:
        from tragedy_context_gate import find_uncontextualised_deaths
        bare = find_uncontextualised_deaths(text)
        if bare:
            defects['bare_death'] = f"{len(bare)} death(s) named without circumstances"
    except Exception:
        pass

    if anchor and geocoder:
        try:
            from geo_refutation import refute_claims
            rec = refute_claims(text, anchor, geocoder)
            if rec['refuted']:
                r = rec['refuted'][0]
                defects['refuted'] = f"{r['place']} at {r['km']}km"
        except Exception:
            pass

    return {'defects': defects, 'metrics': metrics,
            'clean': not any(k in defects for k in REQUIRED_CLEAN)}


def score_batch(paths, requested_stops=None, is_building_tour=False,
                anchor=None, geocoder=None):
    """Score a batch and say whether it is consistent — the signal Michael used.

    He noticed one tour was much better than the others. `spread` is that, measured:
    a batch whose best and worst differ sharply is not ready however good the best
    one is.
    """
    rows = []
    for p in paths:
        try:
            text = open(p, errors='ignore').read()
        except Exception:
            continue
        r = score_tour(text, requested_stops, is_building_tour, anchor, geocoder)
        r['path'] = os.path.basename(p)
        rows.append(r)
    if not rows:
        return {'rows': [], 'consistent': False, 'summary': 'no tours scored'}
    people = [r['metrics']['named_people'] for r in rows]
    clean = [r['clean'] for r in rows]
    return {
        'rows': rows,
        'people_min': min(people), 'people_max': max(people),
        'spread': max(people) - min(people),
        'all_clean': all(clean),
        'consistent': all(clean) and min(people) > 0 and (max(people) - min(people)) <= 2,
        'summary': (f"{sum(clean)}/{len(rows)} clean, named people "
                    f"{min(people)}–{max(people)}"),
    }
