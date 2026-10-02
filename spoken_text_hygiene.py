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
           'DANGLING_PHRASE_RE', 'normalize_proper_noun_spellings']

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

# Labels that are structure, not speech. Michael, 2026-08-24: Orientation and
# Directions stay, "because they let listeners know that they are not part of the
# stop description" — so they are deliberately absent here.
SPOKEN_LABEL_RE = re.compile(r'\b(?:Closing|Narration|Body|Summary)\s*:\s*')


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
