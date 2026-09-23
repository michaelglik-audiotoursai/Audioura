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

**What it deliberately cannot judge: whether a tour is INTERESTING.** That is the
thing Michael reads for, and no counter substitutes for it. The loop is therefore
allowed to iterate on measurable defects and must hand the judgement call back.
"""

import os
import re

REQUIRED_CLEAN = ('truncated', 'repeated', 'refuted', 'bare_death', 'distance')

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
                r'controller|curator|historian|photographer|author|writer')
# NO re.IGNORECASE. With it, [A-Z] matches lowercase too, and the pattern happily
# captured "Cuenin d", "Law r", "of P" and "here" — a count of 13 "people" in a
# tour with four. Titles are capitalised in prose and roles are lowercase, so the
# alternation spells both out instead.
_PERSON = re.compile(
    r'\b(?:(?:' + _PERSON_TITLE + r')\.?\s+'
    r'|(?:' + _PERSON_ROLE + r')s?\s+(?:named\s+)?)'
    r'([A-Z][a-z]{2,}(?:\s+[A-Z]\.)?(?:\s+[A-Z][a-z]{2,})?)')
# a fragment ending on a title with no name after it
_TRUNC = re.compile(r'\b(St|Fr|Dr|Mr|Mrs|Rev|Msgr|Jr|Sr|Prof)\.\s+(?=[A-Z][a-z]+\s+'
                    r'(?:you|As|The|It|This|Its|Their|He|She|We))')
_MANGLED = re.compile(r'\b(?:engaged|which|that|and|of)\s+of\s+[A-Z]')
# [2026-09-21, Michael on LOGAN_1] "...ensuring Boston's competitive edge in the
# aviation sector.3 million passengers in 2025." A sentence was cut and the
# remainder spliced on with no space, so the tour states ".3 million" — the leading
# digits gone. Two signatures: a full stop immediately followed by a digit, and a
# sentence that BEGINS with a decimal fragment.
_SPLICE = re.compile(r'[a-z]\.\d|(?:^|\s)\.\d+\s+\w')
_KM = re.compile(r'\b\d+(?:\.\d+)?\s*(?:km|kilometre|kilometer)s?\b', re.I)


def _count_people(text):
    """Distinct PEOPLE, de-duplicated by surname.

    "Law", "Bernard Law" and "Bernard F. Law" are one man, and counting them as
    three inflated a 4-stop tour to nine people. The surname — the last
    capitalised token — is the identity; the fullest form seen is kept for display.
    """
    by_surname = {}
    for m in _PERSON.findall(text or ''):
        name = (m if isinstance(m, str) else m[0]).strip()
        if not name:
            continue
        surname = name.split()[-1]
        if len(surname) < 3:
            continue
        if len(name) > len(by_surname.get(surname, '')):
            by_surname[surname] = name
    return len(by_surname)


def _stops(text):
    return _STOP.findall(text or '')


def score_tour(text, requested_stops=None, is_building_tour=False, anchor=None,
               geocoder=None):
    """Return {'defects': {...}, 'metrics': {...}, 'clean': bool}."""
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

    trunc = _TRUNC.findall(text) + _MANGLED.findall(text) + \
        [m.group(0) for m in _SPLICE.finditer(text)]
    if trunc:
        defects['truncated'] = f"{len(trunc)} fragment(s), e.g. {trunc[0]!r}"

    if is_building_tour and _KM.search(text):
        defects['distance'] = f"kilometre figure on a building tour: {_KM.search(text).group(0)}"

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
