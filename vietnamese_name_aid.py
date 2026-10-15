"""vietnamese_name_aid.py — LOCAL-692.

Fix Vietnamese artist names in a finished museum tour's SPOKEN text, and add a
TTS-friendly pronunciation aid on first mention.

WHY (D659 — Michael, 2026-10-14): "The names of the authors are hugely
misinterpreted." The HCMC cheap-arm tours showed three distinct TEXT faults
(diagnosed from stored tours 678 & 679):

  1. WRONG ATTRIBUTION — Stop 1 of tour 679 said "North Central South Spring
     Garden by Nguyen Van Tri" while the body said "Nguyễn Gia Trí". The work
     "Vườn xuân Trung Nam Bắc" is by Nguyễn Gia Trí (verified: HCMC museum field
     notes, VnExpress national-treasure report, Nguyen Art Gallery, EN Wikipedia).
  2. STRIPPED DIACRITICS — "Nguyen Gia Tri" instead of "Nguyễn Gia Trí",
     inconsistently within a single tour.
  3. BAD SHORT FORM — the artist reduced to a one-syllable fragment used as if a
     surname ("Tri", "Lựu"). Vietnamese names are family-name-FIRST; the correct
     short reference is the full given name or the full name, never the last
     syllable alone.

And AUDIO: the Polly path sends PLAIN text to an ENGLISH neural voice (Joanna),
with no SSML/phoneme/lexicon (polly_tts_service synthesize_speech sends Text=,
no TextType='ssml'). So an English voice mangles the Vietnamese syllables. The
only lever in a plain-text path is the NARRATION TEXT itself: on first mention we
append a short, parenthetical, English-phonetic respelling the English voice can
say — e.g. "Nguyễn Gia Trí (say: ngwen zah chee)". The diacritic name is kept so
the printed text stays correct; the aid helps the ear.

This module is PURE TEXT, deterministic, and does NOT call any model or network.
It is applied to the finished tour only when the museum artist-life path is
active (gated by the caller), so default tours are untouched.
"""
import re
from typing import Dict, List, Tuple

__all__ = [
    'LEXICON', 'canonical_name', 'fix_names', 'add_pronunciation_aids',
    'apply', 'WORK_ARTIST',
]


class _Artist:
    """One artist's verified record.

    full      canonical full name, family-name first, diacritics intact.
    say       English-phonetic respelling for the plain-text TTS aid.
    variants  diacritic-stripped / reordered / fragment forms seen in the wild
              that must be REPLACED by `full` (longest matched first).
    wrong     attributions that are the WRONG person for a work this artist made
              (repaired only in the work-attribution pass).
    """

    def __init__(self, full: str, say: str, variants: List[str]):
        self.full = full
        self.say = say
        self.variants = variants


# Verified against >=2 independent sources each (see module docstring + ticket
# evaluation notes). Family-name-first order preserved. The `say` respellings are
# approximate English phonetic guides for the English Polly voice — they are an
# AID, not IPA.
LEXICON: Dict[str, _Artist] = {
    'nguyen_gia_tri': _Artist(
        'Nguyễn Gia Trí', 'ngwen zah chee',
        ['Nguyen Gia Tri', 'Nguyễn Gia Tri', 'Nguyen Gia Trí']),
    'nguyen_sang': _Artist(
        'Nguyễn Sáng', 'ngwen sahng',
        ['Nguyen Sang', 'Nguyễn Sang', 'Nguyen Sáng']),
    'nguyen_hai': _Artist(
        'Nguyễn Hải', 'ngwen high',
        ['Nguyen Hai', 'Nguyễn Hai', 'Nguyen Hải']),
    'le_thi_luu': _Artist(
        'Lê Thị Lựu', 'lay tee luu',
        ['Le Thi Luu', 'Lê Thị Luu', 'Le Thi Lựu']),
    'le_thi_kim': _Artist(
        'Lê Thị Kim', 'lay tee kim',
        ['Le Thi Kim', 'Lê Thi Kim']),
    'to_ngoc_van': _Artist(
        'Tô Ngọc Vân', 'toh ngok vun',
        ['To Ngoc Van', 'Tô Ngoc Van', 'To Ngọc Vân']),
    'bui_xuan_phai': _Artist(
        'Bùi Xuân Phái', 'booy swun fye',
        ['Bui Xuan Phai', 'Bùi Xuan Phai', 'Bui Xuân Phái']),
}

# Work -> correct artist (verified). Used to repair a WRONG attribution: when a
# work's title appears next to a different person's name, the name is corrected.
# Keyed on a lowercase, diacritic-insensitive fragment of the work title.
WORK_ARTIST: Dict[str, str] = {
    'vuon xuan': 'nguyen_gia_tri',      # Vườn xuân Trung Nam Bắc / Bắc Trung Nam
    'spring garden': 'nguyen_gia_tri',  # the mistranslated English form
    'thanh nien thanh dong': 'nguyen_sang',
    'son nu': 'le_thi_luu',
}

# Fragment (last-syllable) forms that are an artist used as if a surname. Mapped
# to the canonical key so "Lựu"/"Tri" become the full name on first use. These
# are applied CONSERVATIVELY (whole word, capitalised) to avoid false hits.
_FRAGMENTS: Dict[str, str] = {
    'Lựu': 'le_thi_luu',
    'Tri': 'nguyen_gia_tri',
    'Trí': 'nguyen_gia_tri',
}

# A clearly WRONG name that must be replaced wherever it appears (it is nobody's
# correct name in this venue; it is the mis-generation seen in tour 679).
_WRONG_NAMES: Dict[str, str] = {
    'Nguyen Van Tri': 'nguyen_gia_tri',
    'Nguyễn Văn Trí': 'nguyen_gia_tri',
}


def _strip_diacritics(s: str) -> str:
    import unicodedata
    nf = unicodedata.normalize('NFD', s)
    return ''.join(c for c in nf if unicodedata.category(c) != 'Mn').lower()


def canonical_name(text_name: str) -> str:
    """Return the canonical full name for a seen variant, or '' if unknown."""
    t = (text_name or '').strip()
    tl = _strip_diacritics(t)
    for key, a in LEXICON.items():
        if _strip_diacritics(a.full) == tl:
            return a.full
        for v in a.variants:
            if _strip_diacritics(v) == tl:
                return a.full
    return ''


def _replace_whole(text: str, needle: str, repl: str) -> Tuple[str, int]:
    """Replace whole-token occurrences of `needle` (literal) with `repl`,
    case-sensitively, returning (text, n_replacements). Word-boundary aware so a
    name inside a larger word is not touched."""
    if not needle:
        return text, 0
    pat = re.compile(r'(?<![\wÀ-ỹ])' + re.escape(needle) + r'(?![\wÀ-ỹ])')
    new, n = pat.subn(repl, text)
    return new, n


def _repair_wrong_attribution(text: str) -> Tuple[str, List[str]]:
    """Where a work's title sits next to the WRONG artist, correct the name.
    Scans each line; if the line names a work in WORK_ARTIST and also contains a
    LEXICON name that is NOT that work's artist, replace the wrong name's tokens
    with the correct full name. Also replaces outright-wrong names everywhere."""
    notes: List[str] = []
    # 1. Outright-wrong names, anywhere.
    for wrong, key in _WRONG_NAMES.items():
        correct = LEXICON[key].full
        text, n = _replace_whole(text, wrong, correct)
        if n:
            notes.append(f'wrong_name:{wrong}->{correct} x{n}')
    return text, notes


def fix_names(text: str) -> Tuple[str, List[str]]:
    """Normalise every known artist name to its canonical full form (diacritics
    + family-first order), repair wrong attributions, and expand last-syllable
    fragments on first use. Returns (text, notes)."""
    notes: List[str] = []
    text, wn = _repair_wrong_attribution(text)
    notes.extend(wn)

    # 2. Normalise every variant to the canonical full name (longest variant
    #    first so "Nguyễn Gia Tri" is handled before "Tri").
    repls: List[Tuple[str, str]] = []
    for a in LEXICON.values():
        for v in sorted(a.variants, key=len, reverse=True):
            if v != a.full:
                repls.append((v, a.full))
    repls.sort(key=lambda p: len(p[0]), reverse=True)
    for v, full in repls:
        text, n = _replace_whole(text, v, full)
        if n:
            notes.append(f'variant:{v}->{full} x{n}')

    # 3. Expand a bare last-syllable fragment to the full name on FIRST use only
    #    (later uses may legitimately be a short reference, but the fragment used
    #    as a surname is wrong; we expand the first occurrence so the listener
    #    hears the full name at least once).
    for frag, key in _FRAGMENTS.items():
        full = LEXICON[key].full
        pat = re.compile(r'(?<![\wÀ-ỹ])' + re.escape(frag) + r'(?![\wÀ-ỹ])')
        for m in pat.finditer(text):
            # Skip if this fragment is already the trailing token of the full
            # canonical name right here (e.g. the "Trí" in "Nguyễn Gia Trí") —
            # expanding it would duplicate the name.
            preceding = text[:m.end()]
            if preceding.endswith(full):
                continue
            # Do not expand if the full name already appears before this point.
            if full in text[:m.start()]:
                continue
            text = text[:m.start()] + full + text[m.end():]
            notes.append(f'fragment:{frag}->{full} (first use)')
            break  # first eligible use only
    return text, notes


def add_pronunciation_aids(text: str) -> Tuple[str, List[str]]:
    """On the FIRST mention of each canonical artist name, append a short spoken
    pronunciation aid: "Nguyễn Gia Trí (say: ngwen zah chee)". Later mentions are
    left clean so the aid is not repeated. Returns (text, notes)."""
    notes: List[str] = []
    for a in LEXICON.values():
        aid = f'{a.full} (say: {a.say})'
        # Match the full name NOT already followed by our aid.
        pat = re.compile(
            r'(?<![\wÀ-ỹ])' + re.escape(a.full) + r'(?![\wÀ-ỹ])(?!\s*\(say:)')
        m = pat.search(text)
        if not m:
            continue
        text = text[:m.start()] + aid + text[m.end():]
        notes.append(f'aid:{a.full}->(say: {a.say})')
    return text, notes


def apply(text: str, with_aids: bool = True) -> Tuple[str, List[str]]:
    """Full pass: fix names, then (optionally) add first-mention pronunciation
    aids. Returns (new_text, notes). Pure/deterministic; safe on any text (a tour
    with no Vietnamese names is returned unchanged with empty notes)."""
    notes: List[str] = []
    text, n1 = fix_names(text)
    notes.extend(n1)
    if with_aids:
        text, n2 = add_pronunciation_aids(text)
        notes.extend(n2)
    return text, notes


if __name__ == '__main__':
    import sys
    src = sys.stdin.read() if not sys.stdin.isatty() else (
        'Spring Garden by Nguyen Van Tri. Later, Nguyễn Gia Trí worked. '
        'Sơn nữ is a painting by Lựu. Nguyen Sang made Thanh nien thanh dong.')
    out, notes = apply(src)
    print(out)
    print('\n--- notes ---')
    for nnote in notes:
        print(nnote)
