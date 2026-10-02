#!/usr/bin/env python3
"""check_known_defects.py — the three defects Michael said to WATCH, not fix.

His ruling, 2026-08-24: fix the append (D518) and the closing (D519) only; look for
these in the new tour and say whether they appear.

  (a) cross-stop name contamination — "the Louis Broder Tériade", where Broder is
      stop 1's publisher and Tériade is stop 2's. Seen in two runs, produced by
      two different generators, which is why shared per-tour context is the
      suspect rather than either writer.
  (b) the priest/nobility self-contradiction inside stop 3. D518 should kill this
      one as a side effect — CHECK, do not assume.
  (c) a missing space after a full stop (`depth.Boris Fridman`), third sighting.

Usage: python3 check_known_defects.py TOUR_FILE.txt
Exit 0 always — this reports, it does not gate.
"""
import re
import sys


def stops_of(text):
    """Split a generated tour into (heading, body) per stop."""
    parts = re.split(r'\n(?=Stop \d+:)', text)
    return [(p.split('\n', 1)[0].strip(),
             p.split('\n', 1)[1] if '\n' in p else '') for p in parts[1:]]


def defect_a(text, stops):
    """Two people's names fused into one noun phrase, across stops.

    Generalised past the one string: 'the X Y' where X is a person named in their
    own right elsewhere in the tour and Y is another capitalised name.

    **The tail name is NOT required to appear anywhere else, and that correction
    matters.** The first version of this check demanded it, and so reported the
    17:46 run clean — where the tour says "the Louis Broder Tériade revived the
    stalled undertaking" and the word Tériade appears exactly once, inside the
    fusion. Requiring corroboration made the check blind to the worst case of the
    thing it was written to find.
    """
    hits = []
    for m in re.finditer(r'\bthe ((?:[A-ZÀ-Ý][\w’\'-]+ ){1,3})([A-ZÀ-Ý][\w’\'-]+)\b', text):
        head, tail = m.group(1).strip(), m.group(2)
        words = head.split()
        if len(words) < 2:
            continue
        first_person = ' '.join(words[-2:])
        # X must stand on its own somewhere else — that is what makes the phrase
        # a fusion of two names rather than one long proper noun.
        if len(re.findall(re.escape(first_person), text)) >= 2:
            hits.append(m.group(0))
    return hits


def defect_b(text):
    """The same subject given two incompatible descriptions inside one tour."""
    pairs = [('Egyptian priest', 'Egyptian nobility'),
             ('was not a Hebrew', 'rather than Hebrew origin')]
    return [(a, b) for a, b in pairs if a in text and b in text]


def defect_c(text):
    """A full stop with no space after it, mid-sentence — `depth.Boris`."""
    body = re.sub(r'https?://\S+', ' ', text)
    body = re.sub(r'\b[A-Za-z0-9.-]+\.(com|org|net|edu|fr|gov|uk)\b', ' ', body)
    # A quotation mark may sit between the stop and the capital, and the next
    # word may have a single lowercase letter ("Au"). The first version required
    # neither and reported TOUR_D523_UNBOUND clean while it contained
    # `imagery."Au Soleil du Plafond"`. Same blind spot as the repair it checks.
    return re.findall(r'[a-zà-ÿ]{2}\.["\u201c\u2018\']?[A-ZÀ-Ý][a-zà-ÿ]+', body)


def defect_d(text):
    """[D521] A bracketed citation, which is read aloud as noise."""
    import sys as _s
    _s.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
    from story_append_merge import _CITATION_BRACKET_RE
    return [m.group(0).strip() for m in _CITATION_BRACKET_RE.finditer(text)]


def defect_e(text):
    """[D521] A sentence that performs the same action twice on the same things."""
    import sys as _s
    _s.path.insert(0, __import__('os').path.dirname(__import__('os').path.abspath(__file__)))
    from story_append_merge import dedupe_within_sentence, sentences_of
    return [s for s in sentences_of(text) if dedupe_within_sentence(s) != s]


def defect_f(text):
    """[D521] A structural label that is spoken but tells the listener nothing.

    Orientation and Directions are deliberately absent from this list — Michael
    kept them, because they say what kind of thing is coming.

    **Not anchored to line start, and that is the point.** The first version was
    (`^\\s*(Closing|…):`) and it reported every tour clean, including the two that
    plainly contain the label — because the epilog puts the recap and the closing
    on ONE line, so "Closing:" is mid-line. Same failure class as the first
    version of check (a): an instrument that cannot see the case you already know
    about is worth nothing.
    """
    return re.findall(r'\b(Closing|Narration|Body|Description|Summary):', text)


def defect_i(text):
    """[D523] A preposition whose object an upstream gate deleted."""
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from spoken_text_hygiene import DANGLING_PHRASE_RE
    return [m.group(0).strip() for m in DANGLING_PHRASE_RE.finditer(text)]


def defect_g(text):
    """[D523] A DIFFERENT exhibition named as though the listener were in it.

    The 12:23 tour told a visitor standing in *Unbound* that the work "became an
    integral part of the exhibition 'Dali: Disruption and Devotion'". Quoted
    exhibition titles that are not the one being toured are the signal.
    """
    requested = re.search(r'Tour:\s*(.+?)\s+-\s+\w+ Tour', text)
    req = (requested.group(1) if requested else '').lower()
    out = []
    for m in re.finditer(r'exhibition\s+[\u201c"\u2018\']([^\u201d"\u2019\']{4,60})[\u201d"\u2019\']', text, re.I):
        name = m.group(1)
        if name.lower() not in req and not any(w in req for w in name.lower().split() if len(w) > 5):
            out.append(name)
    return out


def defect_h(text):
    """[D523] A claim we have positively established to be wrong, stated alone.

    Unlike (b), which needs BOTH versions present, this fires on the wrong one by
    itself — the case the 12:23 tour shipped and nothing caught.
    """
    import sys as _s, os as _o
    _s.path.insert(0, _o.path.dirname(_o.path.abspath(__file__)))
    from known_fact_corrections import CORRECTIONS
    return [m.group(0) for pat, _r, _w in CORRECTIONS
            for m in [pat.search(text)] if m]


def main(path):
    text = open(path, encoding='utf-8').read()
    stops = stops_of(text)
    print(f"{path} — {len(text)} chars, {len(stops)} stop(s)\n")

    a = defect_a(text, stops)
    print(f"(a) cross-stop name fusion : {'FOUND ' + str(a) if a else 'not found'}")
    b = defect_b(text)
    print(f"(b) priest/nobility clash  : {'FOUND ' + str(b) if b else 'not found'}")
    c = defect_c(text)
    print(f"(c) missing space after '.': {'FOUND ' + str(c) if c else 'not found'}")

    d = defect_d(text)
    print(f"(d) bracketed citations    : {'FOUND ' + str(d[:4]) if d else 'not found'}")
    e = defect_e(text)
    print(f"(e) said twice in 1 sentence: {'FOUND ' + str([s[:70] for s in e]) if e else 'not found'}")
    f = defect_f(text)
    print(f"(f) spoken structural label : {'FOUND ' + str(set(f)) if f else 'not found'}")

    g = defect_g(text)
    print(f"(g) a different exhibition  : {'FOUND ' + str(g) if g else 'not found'}")
    h = defect_h(text)
    print(f"(h) established wrong fact  : {'FOUND ' + str(h) if h else 'not found'}")

    i = defect_i(text)
    print(f"(i) preposition with no object: {'FOUND ' + str(i) if i else 'not found'}")

    print(f"\n(D519) 'Treat Page' in the tour: "
          f"{'PRESENT — ' + str(text.count('Treat Page')) + 'x' if 'Treat Page' in text else 'absent'}")
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else 'TOUR_LOOP_20260823_1821.txt'))
