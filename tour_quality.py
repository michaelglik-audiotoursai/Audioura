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
  offsite_entity  a place presented AS PART OF THE TOUR that is neither the venue
                  nor a stop — "St. Mary's Cathedral ... mark the endpoints" on a
                  Boston airport (the cathedral is in Sydney); "That's 4 stops —
                  Mary Immaculate of Lourdes" naming a different church in the recap
                  (LOCAL-539). The test is FRAMING, not distance: the same church,
                  named "a short distance away in Newton Upper Falls" in a stop body,
                  is legitimate contrast; named as a covered stop in the epilog, it
                  is the defect.

**What it deliberately cannot judge: whether a tour is INTERESTING.** That is the
thing Michael reads for, and no counter substitutes for it. The loop is therefore
allowed to iterate on measurable defects and must hand the judgement call back.
"""

import os
import re

REQUIRED_CLEAN = ('truncated', 'repeated', 'refuted', 'bare_death', 'distance',
                  'fabricated_attribution', 'self_contradiction',
                  'offsite_entity')

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
# [LOCAL-537] A given+surname of at least two tokens. The bare single token is
# too noisy for the possessive rule below ("Mary's", "Christ's", "That's"), so the
# possessive frame demands a full name.
_NAME2 = r'[A-Z][a-z]{2,}(?:\s+(?:[A-Z]\.|[A-Z][a-z]{2,})){1,2}'
# [LOCAL-537] Honorific abbreviations that sit BETWEEN a trigger word and the name
# and, being one or two letters, break the _NAME shape so the whole match failed.
# "pioneer priest Fr John Therry" scored zero people until this let the introducer
# step over "Fr" and anchor _NAME on "John Therry". These are only ALLOWED here,
# never REQUIRED, so a name with no honorific still matches.
_HONORIFIC = r'(?:Fr|St|Ss|Mr|Mrs|Ms|Dr|Rev|Msgr|Sr|Jr|Prof)\.?\s+'
_PERSON = re.compile(
    r'\b(?:(?:' + _PERSON_TITLE + r')\.?\s+'
    r'|(?:' + _PERSON_ROLE + r')s?\s*,?\s+(?:named\s+)?'
    r'|(?:' + _PERSON_FRAME + r')\s+)'
    r'(?:' + _HONORIFIC + r')?'
    r'(' + _NAME + r')'
    # "...attendants Betty Ann Ong AND Madeline Amy Sweeney" -- one introducer,
    # two people. Without this the second name is invisible.
    r'(?:\s+and\s+(?:' + _HONORIFIC + r')?(' + _NAME + r'))?')
# [LOCAL-537] A name in possessive form is the same person as the bare form
# ("Gustave Eiffel's iconic Control Tower" names Eiffel, whom NO title/role/frame
# introduces). Requiring the FULL given+surname (_NAME2, two+ tokens) is what keeps
# this from turning every "Mary's" / "Peter's Basilica" / "That's 4 stops" into a
# person. Place and organisation phrases that survive that ("Boston Logan's", "New
# England's", "Boston Globe's") are removed by _NOT_A_NAME on their first or last
# token -- see the words added there. De-dup by surname folds the possessive back
# onto the bare mention, so it never double-counts.
_PERSON_POSSESSIVE = re.compile(r'\b(' + _NAME2 + r')(?:\'|\u2019)s\b')
# [LOCAL-537] An occupation appositive AFTER the name is as good a signal as one
# before it: "Trippe, the founder and later Pan American World Airways" was
# invisible because _PERSON only looks for a role that PRECEDES the name.
_PERSON_APPOSITIVE = re.compile(
    r'\b(' + _NAME + r'),\s+(?:the\s+|a\s+|an\s+)?(?:' + _PERSON_ROLE + r')s?\b')

# ─── [LOCAL-542] Four more shapes in which this pipeline names a person ───────
# LOCAL-537 fixed LOGAN_1 (4) but CHURCH_1 still returned 8 of the 17 people in it.
# The nine it missed do NOT share a role word or a title — adding their introducers
# to _PERSON_ROLE (already 40+ words) would be the enumeration trap D476 names and
# LOCAL-530 fell into twice. Each rule below keys on a GRAMMATICAL construction, not
# a hand-listed verb/noun:
#
#   _PERSON_AGENT      the passive agent: a past participle governs "by <Name>"
#                      ("Designed by Jean Bazaine", "described by John Chrysostom",
#                      "propagated by figures like Don Bosco and Vincent Pallotti").
#                      The verb is matched as a CLASS (any word ending -ed/-en), so
#                      no verb list is maintained. Requires a two-token name, which
#                      is what keeps "by September"/"by These" out.
#   _PERSON_HON_INTRO  a standalone honorific abbreviation ("Fr. Timothy Danahy").
#                      A full given+surname is required so a dangling "Fr." before a
#                      sentence continuation ("Fr. During the war") is not a person.
#   _PERSON_APPOS_LIST an apposition list after a role noun + colon: "three longtime
#                      congregants: Gilda "Jill" D'Amore, her husband Bruno D'Amore,
#                      and ... Lucia Arpino". Punctuation-driven, not a role list.
#   _PERSON_TITLED     keeps the TITLE in the fullest form ("Mother Teresa", not
#                      "Teresa"); de-dup by surname still folds it onto bare mentions.
#
# A name word may now carry an internal apostrophe (D'Amore, O'Brien) and skip a
# quoted nickname (Gilda "Jill" D'Amore) — both are structural features of names.
# These are kept SEPARATE from _NAME/_NAME2 (which the tested possessive/appositive
# rules reuse) so this change cannot perturb LOCAL-537's behaviour.
_PNAME_W = r"(?:[A-Z][a-z]{2,}|[A-Z]['\u2019][A-Z][a-z]+|[A-Z]\.)"
_PNAME_QNICK = r'(?:["\u201c\u2018][A-Z][a-z]+["\u201d\u2019]\s+)?'
_PNAME = r"[A-Z][a-z]{2,}(?:\s+" + _PNAME_QNICK + _PNAME_W + r"){0,2}"
_PNAME2 = r"[A-Z][a-z]{2,}(?:\s+" + _PNAME_QNICK + _PNAME_W + r"){1,2}"

_PERSON_TITLED = re.compile(
    r'\b((?:' + _PERSON_TITLE + r')\.?\s+(?:' + _HONORIFIC + r')?' + _PNAME + r')')
_PERSON_AGENT = re.compile(
    r'\b[A-Za-z]{3,}(?:ed|en)\b\s*(?:in\s+[^.]{0,25}?)?\bby\s+'
    r'(?:figures?\s+like\s+|the\s+|a\s+|an\s+)?'
    r'(?:(?:' + _PERSON_TITLE + r')\.?\s+)?(?:' + _HONORIFIC + r')?(' + _PNAME2 + r')'
    r'(?:\s+and\s+(?:(?:' + _PERSON_TITLE + r')\.?\s+)?(?:' + _HONORIFIC + r')?('
    + _PNAME2 + r'))?')
_PERSON_HON_INTRO = re.compile(
    r'(?<![A-Za-z.])(?:Fr|Mr|Mrs|Ms|Dr|Rev|Msgr|Sr|Prof)\.\s+(' + _PNAME2 + r')')
_PERSON_APPOS_LIST = re.compile(
    r'(?:congregants?|victims?|members?|parishioners?|residents?|founders?|'
    r'donors?|survivors?|children|parents?|siblings?|family)\s*:\s+'
    r'(' + _PNAME2 + r'(?:[^.]*?,\s*(?:and\s+)?(?:her\s+\w+\s+|his\s+\w+\s+|'
    r"\w+['\u2019]s\s+\w+,?\s+)?" + _PNAME2 + r')+)')

# Organisation head-nouns the agent rule can capture ("Conceived by Moskow Linn
# Architects"), plus collective role plurals a title can precede ("Rev.
# Parishioners"). A small, GENERATIVE class of institution/collective words, not a
# name list — none of these is ever a person's identifying token.
_PERSON_ORG_SUFFIX = {
    'administration', 'corps', 'guard', 'architects', 'architect', 'studios',
    'studio', 'systems', 'colors', 'colours', 'works', 'immaculate', 'help',
    'parishioners', 'congregants', 'members', 'residents', 'faithful',
}
# Closed-class leading words a name-shaped match may start with but a person never
# does (determiners, deictics, subordinators). Grammatical, not enumeration.
_PERSON_LEAD_STOP = {
    'every', 'these', 'this', 'that', 'those', 'many', 'some', 'during', 'their',
    'your', 'our', 'his', 'her', 'its', 'the', 'each', 'both', 'all', 'any',
    'inside', 'outside', 'after', 'before', 'while',
}
# Title / rank words that are introducers, never the person's identifying token.
# Stripping them lets prefix-subsumption see "General Edward Lawrence Logan" and
# "Edward Lawrence Logan" as one person, and "Mother Teresa" keep its title.
_PERSON_TITLE_WORD = {
    'rev', 'fr', 'dr', 'mr', 'mrs', 'ms', 'msgr', 'sr', 'jr', 'st', 'chaplain',
    'father', 'mother', 'sister', 'deacon', 'bishop', 'cardinal', 'pope', 'saint',
    'reverend', 'monsignor', 'archbishop', 'major', 'general', 'governor', 'mayor',
    'senator', 'president', 'captain', 'lieutenant', 'colonel', 'sir', 'lord',
}

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


# [2026-09-23] "funded by Irish immigrants" -> a person called Irish. Attribution
# frames often take a people-group rather than a person.
_NOT_A_NAME = {
    'irish', 'italian', 'german', 'french', 'polish', 'english', 'scottish',
    'spanish', 'portuguese', 'greek', 'chinese', 'japanese', 'russian', 'dutch',
    'swiss', 'belgian', 'mexican', 'american', 'canadian', 'australian',
    'catholic', 'protestant', 'jewish', 'muslim', 'christian', 'orthodox',
    'local', 'native', 'colonial', 'federal', 'royal', 'imperial',
    # [LOCAL-537] Place / organisation tokens that appear inside a possessive place
    # phrase the new _PERSON_POSSESSIVE rule would otherwise count as a person. Each
    # is motivated by verbatim text in TOURS_FOR_REVIEW/round7-9:
    #   "Boston Logan's iconic ...", "East Boston's tidal flats"  -> first token
    #   "New England's busiest", "Massachusetts Legislature's decision",
    #   "Boston Globe's Spotlight", "Middlesex District Attorney's office".
    # 'logan' is deliberately ABSENT: it is the surname of a real person (Major
    # General Edward Lawrence Logan), and blocking it re-hid the tour's namesake.
    'boston', 'east', 'west', 'north', 'south', 'new', 'massachusetts',
    'middlesex', 'england', 'globe', 'legislature', 'attorney', 'district',
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


# ─── Self-contradiction (LOCAL-536) ──────────────────────────────────────────
# Round 9 scored defects:{} on both tours yet each contains contradictions that
# need NO knowledge of the world — only a comparison of the tour against its own
# other sentences. Every fix of the attribution class so far matched a surface form
# (a verb, a year, a "by"); the generator is not bound to a surface form, and
# LOCAL-527's gate was already evaded by "Gustave Eiffel's iconic Control Tower".
# Self-contradiction has no such weakness: it needs no corpus and no grounded call.
#
# The hard rule (D577): every sub-check fires ONLY on a positive, quotable PAIR of
# statements from the same tour. If it cannot produce both quotes it does not raise.
# It never decides which statement is right — the contradiction is the finding.

from sentence_split import split_sentences as _split_sentences  # noqa: E402


def _sentences(text):
    """All sentences in the tour, flattened across lines."""
    out = []
    for line in (text or '').splitlines():
        out.extend(_split_sentences(line.strip()))
    return out


# The named structures a tour attributes design/authorship to. A "structure" here
# is the head noun the possessive or the passive frame attaches to — tower, church,
# terminal, cathedral, chapel, altar, window, bridge, building, hall, dome, spire.
_STRUCTURE_NOUN = (r'tower|church|cathedral|chapel|basilica|terminal|concourse|'
                   r'altar|window|windows|bridge|building|hall|dome|spire|'
                   r'facade|nave|narthex|pulpit|steeple|monument|memorial|'
                   r'station|hangar|pavilion|rotunda|gate|gateway')
# A capitalised agent name (person, firm, or "Firm & Firm, Inc."). Allows the
# ampersand-joined architectural-firm form and a trailing ", Inc."/"LLC". Each
# token must be Capitalised so a run of lowercase clause words cannot be swallowed
# as an "agent"; 1–4 tokens keeps it to a name, not a sentence.
_AGENT = (r'[A-Z][A-Za-z.\'’]+(?:\s+(?:&\s+)?[A-Z][A-Za-z.\'’]+){0,3}'
          r'(?:,?\s+(?:Inc|LLC|Ltd|Co|Corp)\.?)?')
# Verbs that attribute authorship of a STRUCTURE (not of an artwork — "created"/
# "painted" belong to art attribution, deliberately excluded to avoid firing on
# legitimate "Nu bleu IV, created by Matisse" content).
_MAKE_VERB = r'designed|built|constructed|erected|founded|established|crafted|engineered'

# Possessive frame: "Gustave Eiffel's iconic Control Tower" — the form LOCAL-527's
# gate was rewritten INTO, with no verb, no year and no "by". A REAL apostrophe is
# required (the '\u2019|\u0027' is not optional): without it, every plural noun
# ("windows", "Christians", "departures") read as a possessive and the check fired
# on scenery. The agent must be a capitalised name AND the structure head noun must
# itself be Capitalised (a NAMED structure — "Control Tower", not a generic "tower"
# in a direction line). Adjectives between are lowercase.
_POSSESSIVE_ATTRIB = re.compile(
    r'\b(' + _AGENT + r')(?:\u2019|\')s\s+'         # "Gustave Eiffel's" — apostrophe required
    r'(?:[a-z]+\s+){0,3}'                            # "iconic", "famous", ...
    r'([A-Z][a-z]+\s+)?'                             # optional Capitalised modifier "Control"
    r'((?i:' + _STRUCTURE_NOUN + r'))\b')
# Passive frame: "Designed by the Boston architectural firms Kubitz & Papi, Inc.
# and Desmond & Lord, Inc., this tower ...". Filler after "by" may contain
# capitalised descriptor words ("Boston"), so it is matched loosely (any non-period
# run, non-greedy) up to the agent, and the agent is anchored as the capitalised
# name-run that sits immediately before ", this/the <structure>". "Inc." periods
# are tolerated because the agent group itself consumes them.
_PASSIVE_ATTRIB = re.compile(
    r'\b(?i:' + _MAKE_VERB + r')\s+by\b'
    r'[\s\S]{0,90}?'                                 # "the Boston architectural firms ... Inc. and ... Inc.,"
    r'(' + _AGENT + r')'                             # the agent immediately before the structure
    r'\s*,?\s+(?:this|the)\s+'
    r'(?:[a-z]+\s+){0,2}'
    r'((?i:' + _STRUCTURE_NOUN + r'))\b')


def _norm_structure(word):
    return word.lower().rstrip('s')


def _norm_agent(name):
    """Collapse an agent to a comparison key. Firms keep their distinctive first
    token; people keep the surname. 'Kubitz & Papi, Inc.' -> 'kubitz', 'Gustave
    Eiffel' -> 'eiffel'."""
    n = re.sub(r',?\s+(?:Inc|LLC|Ltd|Co|Corp)\.?$', '', name.strip(), flags=re.I)
    if '&' in n:
        return n.split('&')[0].strip().lower()
    toks = n.split()
    return toks[-1].lower() if toks else n.lower()


# Owner words that make a possessive an OWNERSHIP claim ("the Airport's Control
# Tower", "the Church's altar"), never an authorship claim. A possessive whose
# owner ends in one of these is the venue owning its own part — not a designer —
# and must not be compared as an attribution.
_PLACE_OWNER = {
    'airport', 'church', 'cathedral', 'basilica', 'chapel', 'terminal',
    'parish', 'museum', 'university', 'college', 'city', 'town', 'state',
    'commonwealth', 'authority', 'company', 'corporation', 'nation', 'country',
}


def _find_attribution_conflict(text):
    """Sub-check 1. Same named structure credited to two DIFFERENT agents.

    Returns (structure, quote_a, quote_b) or None. Extracts (structure, agent)
    pairs from possessive AND passive frames anywhere in the tour; two distinct
    agents for one structure is the defect."""
    seen = {}   # structure -> (agent_key, agent_display, quote)
    for sent in _sentences(text):
        pairs = []   # (structure_word, agent, is_possessive)
        for m in _POSSESSIVE_ATTRIB.finditer(sent):
            pairs.append((m.group(3), m.group(1), True))
        for m in _PASSIVE_ATTRIB.finditer(sent):
            pairs.append((m.group(2), m.group(1), False))
        for struct_word, agent, is_poss in pairs:
            struct = _norm_structure(struct_word)
            akey = _norm_agent(agent)
            if not akey or len(akey) < 3:
                continue
            # A possessive owned by the venue itself ("the Airport's Control
            # Tower") is ownership, not authorship — never an attribution.
            if is_poss and any(w in _PLACE_OWNER for w in agent.lower().split()):
                continue
            if struct in seen:
                prev_key, _prev_disp, prev_quote = seen[struct]
                if prev_key != akey and prev_quote != sent:
                    return (struct_word, prev_quote, sent)
            else:
                seen[struct] = (akey, agent, sent)
    return None


# Phrases in a body that assert the titled subject is ABSENT. Title-to-body only.
_ABSENCE = re.compile(
    r'in\s+the\s+absence\s+of|'
    r'there\s+(?:is|are)\s+no\b|'
    r'does\s+not\s+hold|do\s+not\s+hold|'
    r'no\s+longer\s+(?:has|holds|have)|'
    r'(?:may|does|do|did)\s+not\s+hold|'
    r'without\s+(?:any\s+)?', re.I)
# Words too generic to treat as the titled "thing" when checking absence.
_TITLE_STOPWORDS = {
    'stop', 'the', 'a', 'an', 'of', 'and', 'area', 'main', 'central', 'entry',
    'point', 'focal', 'worship', 'space', 'terminal',
}


def _title_keyword(title):
    """The content noun of a stop title, lowercased. 'Stained Glass Windows' ->
    'stained glass windows'; keeps multiword cores so 'stained glass' can be sought
    in the body verbatim."""
    return re.sub(r'\s+', ' ', title.strip().lower())


def _find_absent_subject(text):
    """Sub-check 2. A stop's title names a thing and the stop's own body says that
    thing is absent. Returns (title, quote) or None. Title-to-body only — no
    cross-stop inference."""
    # Split the tour into per-stop blocks keyed by title.
    blocks = _stop_blocks(text)
    for title, body in blocks:
        key = _title_keyword(title)
        # Reduce the title to its distinctive noun phrase (drop stopwords).
        core_tokens = [t for t in re.split(r'\W+', key) if t and t not in _TITLE_STOPWORDS]
        if not core_tokens:
            continue
        # The multiword core, e.g. "stained glass". Use the last 2 content tokens
        # as the phrase to look for near an absence marker.
        core = ' '.join(core_tokens[-2:]) if len(core_tokens) >= 2 else core_tokens[-1]
        core_singular = core.rstrip('s')
        for sent in _split_sentences(body):
            low = sent.lower()
            if not _ABSENCE.search(low):
                continue
            # The absence marker must be about the titled thing: the core phrase
            # (or its singular) appears in the same sentence.
            if core in low or core_singular in low:
                return (title, sent.strip())
    return None


def _stop_blocks(text):
    """Return [(title, body_text), ...] — the text of each stop from its 'Stop N:'
    header up to the next one."""
    lines = (text or '').splitlines()
    blocks = []
    cur_title = None
    cur = []
    for line in lines:
        m = _STOP.match(line.strip())
        if m:
            if cur_title is not None:
                blocks.append((cur_title, '\n'.join(cur)))
            cur_title = m.group(2).strip()
            cur = []
        elif cur_title is not None:
            cur.append(line)
    if cur_title is not None:
        blocks.append((cur_title, '\n'.join(cur)))
    return blocks


# The closing summary has two halves that each name stops:
#   "That's N stops — <preview A> and <preview B>. This tour covered <X> and <Y>."
# In EVERY healthy tour the two halves name a DIFFERENT pair of the delivered stops
# (a teaser pair, then a covered pair), and the epilog only ever highlights two of
# the four — so "omits a delivered stop" is the normal format and must NOT be
# flagged (it fires on every tour, which is worse than none, D577). The only
# quotable contradiction is an EXTRA: a name the epilog claims the tour covered or
# previewed that corresponds to NO delivered stop. Round 9 CHURCH_1 previews "Mary
# Immaculate of Lourdes" — a different church its own stop 2 distinguishes.
_EPILOG_COVERED = re.compile(r"[Tt]his tour covered\s+(.+?)\.\s*$", re.S)
_EPILOG_PREVIEW = re.compile(
    r"That'?s\s+\d+\s+stops?\s*[\u2012-\u2015\u2212—–-]+\s*(.+?)\.\s*"
    r"(?:This tour covered|$)", re.S | re.I)
_EPILOG_LINE = re.compile(r"^That'?s\s+\d+\s+stops?\b", re.I)


def _epilog_text(text):
    """The trailing summary paragraph, or ''. It is the last non-empty block that
    starts with "That's N stops"."""
    paras = [p.strip() for p in (text or '').split('\n') if p.strip()]
    for p in reversed(paras):
        if _EPILOG_LINE.match(p):
            return p
    return ''


def _delivered_titles(text):
    return [t for t, _ in _stop_blocks(text)]


def _covered_names(epilog):
    """Stop names the epilog claims the tour 'covered'. Splits the tail on ' and '
    / ','."""
    m = _EPILOG_COVERED.search(epilog)
    if not m:
        return []
    tail = m.group(1)
    parts = re.split(r'\s+and\s+|,\s*', tail)
    return [p.strip() for p in parts if p.strip()]


# The leading proper-noun phrase of a preview clause: "Mary Immaculate of Lourdes
# showcases..." -> "Mary Immaculate of Lourdes"; "the nave at Boston Globe's..." ->
# "the nave". Captures an optional leading "the", then a run of Capitalised words
# (allowing "of"/"the"/"A" joiners) OR a single lowercase venue-part word after
# "the".
_PREVIEW_HEAD = re.compile(
    r'^(?:the\s+([a-z]+)\b'                            # "the nave"
    r'|([A-Z][A-Za-z’\'.]+(?:\s+(?:of|the|de|del|and|[A-Z][A-Za-z’\'.]+))*))')


def _preview_names(epilog):
    """Leading name of each ' and '-joined preview clause in the 'That's N stops —'
    half. Returns [name, ...]."""
    m = _EPILOG_PREVIEW.search(epilog)
    if not m:
        return []
    body = m.group(1)
    out = []
    for clause in re.split(r'\s+and\s+', body):
        clause = clause.strip()
        hm = _PREVIEW_HEAD.match(clause)
        if not hm:
            continue
        name = hm.group(1) or hm.group(2)
        if name:
            out.append(name.strip())
    return out


def _title_matches(name, titles):
    """True if `name` corresponds to one of the delivered stop titles, by
    case-insensitive substring in either direction (so 'Control Tower' matches the
    stop titled 'Control Tower', and 'Terminal A Baggage Claim' matches
    'Terminal A Baggage Claim')."""
    n = name.lower().strip()
    for t in titles:
        tl = t.lower().strip()
        if n == tl or n in tl or tl in n:
            return True
    return False


def _find_epilog_stop_mismatch(text):
    """Sub-check 3. The closing summary names a stop/place that was NOT delivered.
    Returns (name, quote) or None. Only the EXTRA direction is reported: an epilog
    name matching no delivered stop. Omission is the normal epilog format and is
    deliberately NOT flagged (it would fire on every tour). The name must look like
    a proper place reference (a multiword Capitalised phrase), so a bare 'the nave'
    that simply is not one of the two teased stops does not count."""
    epilog = _epilog_text(text)
    if not epilog:
        return None
    titles = _delivered_titles(text)
    if not titles:
        return None
    for name in _covered_names(epilog) + _preview_names(epilog):
        if _title_matches(name, titles):
            continue
        # Require a proper NAMED entity: at least two Capitalised tokens, so a
        # generic lowercase word or a single common noun cannot trip it. This is
        # what makes "Mary Immaculate of Lourdes" fire while "the nave" (which is
        # a delivered stop anyway) or a one-word teaser does not.
        cap_tokens = [t for t in name.split() if t[:1].isupper()]
        if len(cap_tokens) < 2:
            continue
        # A PERSON named in a teaser ("... Betty Ann Ong and Madeline Amy Sweeney
        # acted heroically") is not a stop. A place reference contains a
        # place/joiner marker ("of", "the", or a venue-type word); a bare run of
        # given-name + surname does not. Require such a marker so people are
        # excluded but "Mary Immaculate of Lourdes" (has "of") still fires.
        low = name.lower()
        place_markers = (' of ', ' the ', ' de ', ' del ')
        venue_words = ('church', 'cathedral', 'chapel', 'basilica', 'terminal',
                       'tower', 'airport', 'station', 'hall', 'museum', 'parish',
                       'lourdes', 'immaculate', 'lady', 'saint', 'st.')
        if any(mk in f' {low} ' for mk in place_markers) or \
                any(w in low for w in venue_words):
            return (name, epilog)
    return None


# The orientation previews the route; LOGAN_1 states its endpoints TWICE in
# consecutive sentences and gives different answers. "mark the endpoints" /
# "spans from X to Y" name places that must be delivered stops.
_ENDPOINTS_MARK = re.compile(
    r'([^.]+?)\bmark(?:s)?\s+the\s+endpoints\b', re.I)


def _orientation_text(text):
    """Stop-1 orientation body: the text of the first 'Orientation:' block."""
    m = re.search(r'^\s*Orientation:\s*(.+)$', text or '', re.M)
    if not m:
        return ''
    return m.group(1).strip()


# Candidate proper-noun endpoint names in an "X ... mark the endpoints" clause.
_ENDPOINT_NAME = re.compile(
    r"([A-Z][A-Za-z’'.]+(?:\s+[A-Z][A-Za-z’'.]+){0,4})")
_ENDPOINT_SKIP = {'the', 'and', 'a', 'an', 'of', 'iconic', 'bustling', 'efficient'}


def _find_orientation_stop_mismatch(text):
    """Sub-check 4. The stop-1 orientation previews endpoints that do not match the
    delivered stop list. Returns (endpoint_name, quote) or None."""
    orient = _orientation_text(text)
    if not orient:
        return None
    titles = _delivered_titles(text)
    if not titles:
        return None
    for sent in _split_sentences(orient):
        mm = _ENDPOINTS_MARK.search(sent)
        if not mm:
            continue
        clause = mm.group(1)
        # Names in the "... mark the endpoints" clause.
        names = []
        for nm in _ENDPOINT_NAME.findall(clause):
            toks = [t for t in nm.split() if t.lower() not in _ENDPOINT_SKIP]
            if not toks:
                continue
            cleaned = ' '.join(toks)
            # Drop a leading possessive owner: "Gustave Eiffel's iconic Control
            # Tower" -> keep "Control Tower" (the structure), not the person.
            names.append(cleaned)
        # A named endpoint that matches NO delivered stop title is the finding.
        for nm in names:
            base = re.sub(r"[’'](?:s)?$", '', nm)
            if not _title_matches(base, titles):
                # Skip a name that is only a possessive owner of a following
                # structure that DOES match (avoid crediting "Gustave Eiffel").
                if any(_title_matches(part, titles) for part in [base]):
                    continue
                return (nm, sent.strip())
    return None


def _find_self_contradictions(text):
    """Run all four sub-checks. Returns a list of (subcheck, quote_a, quote_b)
    tuples; each entry carries the two offending quotes so the decision is
    inspectable. Empty when the tour does not contradict itself."""
    out = []
    ac = _find_attribution_conflict(text)
    if ac:
        struct, qa, qb = ac
        out.append(('attribution_conflict',
                    f"one structure ({struct}) credited to two agents",
                    qa, qb))
    ab = _find_absent_subject(text)
    if ab:
        title, quote = ab
        out.append(('absent_subject',
                    f"stop titled '{title}' but its body says the subject is absent",
                    f"[title] {title}", quote))
    em = _find_epilog_stop_mismatch(text)
    if em:
        name, quote = em
        out.append(('epilog_stop_mismatch',
                    f"closing summary names a stop/place not delivered: {name}",
                    quote,
                    "[delivered] " + ' | '.join(_delivered_titles(text))))
    om = _find_orientation_stop_mismatch(text)
    if om:
        name, quote = om
        out.append(('orientation_stop_mismatch',
                    f"orientation previews an endpoint not in the stop list: {name}",
                    quote,
                    "[delivered] " + ' | '.join(_delivered_titles(text))))
    return out


# ─── Off-site entity presented as part of the tour (LOCAL-539) ───────────────
# Round 9 shipped two tours that named a place AS PART OF THE TOUR when it was
# neither the venue nor any stop:
#
#   LOGAN_1 (Boston airport), stop-1 orientation:
#       "St. Mary's Cathedral, dedicated by pioneer priest Fr John Therry, and
#        Gustave Eiffel's iconic Control Tower mark the endpoints."
#     — St Mary's Cathedral and Fr John Therry are in Sydney, Australia; the
#       endpoints had already been named (Main Concourse / Baggage Claim).
#   CHURCH_1 (Newton MA church), epilog recap:
#       "That's 4 stops — Mary Immaculate of Lourdes showcases collaborative
#        stained glass art..."
#     — Mary Immaculate of Lourdes is a DIFFERENT church, in Newton Upper Falls.
#
# THE DISTINCTION IS FRAMING, NOT DISTANCE. A tour may talk about anywhere on
# earth. What it may not do is claim a place is one of ITS OWN stops when it is
# not. The very same CHURCH_1, in its stop-2 body, says "A short distance away in
# Newton Upper Falls... At Mary Immaculate of Lourdes, the windows reveal a tale of
# artistic collaboration that never graced Our Lady Help of Christians" — the same
# church, correctly framed as elsewhere. That passage carries no membership frame,
# so it is not flagged. Only the epilog, which puts the church in the "That's N
# stops" slot, is. This is why the check keys on the FRAME, not on geography, and
# does not build a proximity threshold — geo_refutation already owns distance.
#
# A "membership frame" is a phrase that asserts X belongs to the tour's itinerary:
#   * "... X ... mark(s) the endpoints"            (tour-span claim)
#   * "That's N stops — X ..."                      (epilog recap, first named place)
#   * "This tour covered/covers X ..."              (epilog recap)
#   * "your next stop, X" / "next stop is X"        (navigation)
# The named place captured by such a frame is a defect iff it is NOT the venue and
# NOT one of the stop names. Distance is never consulted.

# A proper-name place: capitalised words, allowing "St.", "'", "-", and the
# lowercase connectors that appear INSIDE multiword place names ("of", "the").
_OFFSITE_PLACE = r"[A-Z][\w.'\-]+(?:\s+(?:of|the|de|del|upon|and|at|on|'s)?\s*[A-Z][\w.'\-]+)*"

_MEMBERSHIP_FRAMES = (
    # "<Place> ... mark(s) the endpoint(s)" — the tour-span claim. Non-greedy and
    # capped so it cannot run across a sentence boundary into the next clause.
    re.compile(r"(?P<place>" + _OFFSITE_PLACE + r")[^.\n]{0,160}?\bmarks?\s+the\s+endpoints?\b"),
    # epilog recap: the FIRST named place after "That's N stops —" is the slot a
    # tour fills with one of its own stops; a non-stop there is the defect. Only the
    # first place is taken — the rest of the recap is story prose full of people and
    # events that must not be scanned as itinerary.
    re.compile(r"That'?s\s+\d+\s+stops?(?:\s+and\s+[^—\-–\n]*)?\s*[—\-–]\s*(?P<place>" + _OFFSITE_PLACE + r")"),
    # "This tour covered/covers <Place>"
    re.compile(r"[Tt]his\s+tour\s+cover(?:ed|s)\s+(?P<place>" + _OFFSITE_PLACE + r")"),
    # navigation: "your next stop, <Place>" / "next stop is <Place>"
    re.compile(r"next\s+stop(?:\s+is|,)?\s+(?P<place>" + _OFFSITE_PLACE + r")"),
)

_TOUR_TITLE = re.compile(r'^Step-by-Step Audio Guided Tour:\s*(.+?)(?:,|$)', re.M)


def _norm_place(s):
    """Lowercase, strip punctuation to bare words for own-place matching."""
    return re.sub(r'[^a-z0-9 ]', ' ', (s or '').lower()).split()


def _own_places(text):
    """The venue name and every stop name — the places a tour legitimately owns.

    Returned as a list of token-sets so containment can be tested robustly:
    "Concourse" in a recap matches the stop "Terminal A Main Concourse", and
    "St. Mary's Cathedral" matches nothing here.
    """
    names = []
    m = _TOUR_TITLE.search(text or '')
    if m:
        names.append(m.group(1).strip())
    names.extend(s.strip() for _, s in _STOP.findall(text or ''))
    return [set(_norm_place(n)) for n in names if _norm_place(n)]


# Leading words that are never the head of a place name — an article the frame
# regex may capture when the true stop name starts lowercase ("The church...").
_PLACE_LEADING_STOP = {'the', 'a', 'an', 'this', 'that', 'these', 'those'}


def find_offsite_entities(text):
    """Return [(place, frame_excerpt), ...] for places framed as part of the tour
    that are neither the venue nor any stop.

    Framing only — geography is never consulted (that is geo_refutation's job).
    """
    own = _own_places(text)
    out, seen = [], set()
    for rx in _MEMBERSHIP_FRAMES:
        for m in rx.finditer(text or ''):
            raw = m.group('place').strip().rstrip('.,;:')
            toks = _norm_place(raw)
            # Drop a leading bare article the regex may have grabbed ("The church").
            while toks and toks[0] in _PLACE_LEADING_STOP:
                toks = toks[1:]
            if not toks:
                continue
            place = set(toks)
            # Own iff the captured place shares its meaningful tokens with a venue
            # or stop name — subset in either direction (partial stop references
            # like "Concourse" for "Terminal A Main Concourse" resolve as own).
            is_own = any(place <= o or o <= place for o in own if o)
            if is_own:
                continue
            key = ' '.join(toks)
            if key in seen:
                continue
            seen.add(key)
            out.append((raw, m.group(0).strip()))
    return out


def _count_people(text):
    """Distinct PEOPLE, de-duplicated by surname.

    "Law", "Bernard Law" and "Bernard F. Law" are one man, and counting them as
    three inflated a 4-stop tour to nine people. The surname — the last
    capitalised token — is the identity; the fullest form seen is kept for display.

    [LOCAL-542] Collects from the title/role/frame rule (_PERSON), the possessive
    and trailing-appositive rules (LOCAL-537), and four grammatical shapes that
    carry no role word: the passive agent (_PERSON_AGENT), a standalone honorific
    (_PERSON_HON_INTRO), a role-noun apposition list (_PERSON_APPOS_LIST), and a
    titled name kept in full (_PERSON_TITLED). See the comments on those patterns
    for why each is a construction and not another hand-listed introducer.
    """
    text = text or ''
    by_surname = {}
    candidates = []
    for m in _PERSON.findall(text):
        # Every group is a person: group 2 is the "X and Y" partner when present.
        candidates.extend([m] if isinstance(m, str) else [g for g in m if g])
    # [LOCAL-537] The possessive ("Gustave Eiffel's") and the trailing appositive
    # ("Trippe, the founder") carry no preceding trigger word.
    candidates.extend(_PERSON_POSSESSIVE.findall(text))
    candidates.extend(_PERSON_APPOSITIVE.findall(text))
    # [LOCAL-542] Four more constructions (see pattern comments above).
    for m in _PERSON_AGENT.findall(text):
        candidates.extend([g for g in m if g])
    candidates.extend(_PERSON_HON_INTRO.findall(text))
    candidates.extend(_PERSON_TITLED.findall(text))
    for m in _PERSON_APPOS_LIST.findall(text):
        candidates.extend(re.findall(_PNAME2, m))

    for name in candidates:
        name = name.strip()
        if not name:
            continue
        toks = name.split()
        first, surname = toks[0], toks[-1]
        if len(surname.strip('.')) < 3:
            continue
        # [LOCAL-542] A name never begins with a determiner/deictic ("These", "Every
        # July", "Inside"). Closed grammatical class, checked on the leading token.
        if first.lower() in _PERSON_LEAD_STOP:
            continue
        low = {first.lower(), surname.lower()}
        # A frame like "including Terminal B" hands us scenery. The person-cap
        # already maintains this vocabulary (D584); share it rather than keeping
        # two lists that drift apart. _NOT_A_NAME catches people-groups and possessive
        # place phrases; _PERSON_ORG_SUFFIX catches institution head-nouns the agent
        # rule can pull ("Conceived by Moskow Linn Architects"). Both ends are tested.
        if low & _NOT_PERSON or low & _NOT_A_NAME or low & _PERSON_ORG_SUFFIX:
            continue
        # A title word alone is never a surname ("tended by Chaplain Rev." is the
        # introducer pair, not a person named "Rev").
        if surname.lower().strip('.') in _PERSON_TITLE_WORD:
            continue
        surname_key = surname.lower().strip('.')
        if len(name) > len(by_surname.get(surname_key, '')):
            by_surname[surname_key] = name

    # [LOCAL-542] Prefix subsumption: a name whose token sequence (titles removed)
    # is a prefix of another's is the same person truncated — bare "Sean" under
    # "Archbishop Sean O'Malley", "Edward Lawrence" under "Edward Lawrence Logan".
    # Keep the longer form, drop the prefix, so one person is not counted twice
    # under two surname keys. Surname de-dup still collapses "Law"/"Bernard Law".
    def _core(n):
        return tuple(t.lower().strip('.') for t in n.split()
                     if t.lower().strip('.') not in _PERSON_TITLE_WORD)
    cores = {k: _core(v) for k, v in by_surname.items()}
    for k in list(by_surname):
        ck = cores[k]
        if not ck:                      # nothing but titles left -> not a person
            del by_surname[k]
            continue
        if any(k2 != k and len(c2) > len(ck) and c2[:len(ck)] == ck
               for k2, c2 in cores.items()):
            del by_surname[k]
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

    # Off-site entity presented as part of the tour (LOCAL-539). A place named in a
    # membership frame ("X marks the endpoints", "That's N stops — X", "This tour
    # covered X") that is neither the venue nor a stop. FRAMING, not distance —
    # geo_refutation owns geography; this owns the claim of membership.
    offsite = find_offsite_entities(text)
    if offsite:
        place, frame = offsite[0]
        defects['offsite_entity'] = (
            f"{len(offsite)} place(s) framed as part of the tour but not a "
            f"stop/venue, e.g. \"{place}\" in: {frame[:100]}")

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

    # Self-contradiction (LOCAL-536). Four independent sub-checks, each reported
    # with BOTH offending quotes so the decision is inspectable. Every sub-check
    # fires only on a positive, quotable pair from the same tour (D577): if it
    # cannot produce both quotes it does not raise. It never decides which
    # statement is right — the contradiction itself is the finding.
    contradictions = _find_self_contradictions(text)
    if contradictions:
        subcheck, why, qa, qb = contradictions[0]
        defects['self_contradiction'] = (
            f"{len(contradictions)} contradiction(s); {subcheck}: {why} "
            f"({qa!r} vs {qb!r})")

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
