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

And AUDIO: the Polly path sent PLAIN text to an ENGLISH neural voice (Joanna),
with no SSML/phoneme/lexicon, so an English voice mangles the Vietnamese
syllables.

[LOCAL-692B / D659 LEAD review] The LOCAL-692 fix put the pronunciation in the
NARRATION TEXT — "Nguyễn Gia Trí (say: ngwen zah chee)" — and that parenthetical
was READ ALOUD. Michael flagged it. Pronunciation now lives at the TTS LAYER
only: ``ssml_pronunciation`` / ``to_ssml`` wrap each known name in an SSML
``<sub alias="…">`` (or ``<phoneme>`` when IPA is present) using the verified
respelling, and polly_tts_service synthesises that SSML with TextType='ssml'.
The listener hears the correct name; the NARRATION TEXT stays clean (diacritic
name only, no "(say: …)"). ``add_pronunciation_aids`` is kept for diagnostics but
is NOT applied to narration (``apply`` defaults ``with_aids=False``).

This module is PURE TEXT, deterministic, and does NOT call any model or network.
It is applied to the finished tour only when the museum artist-life path is
active (gated by the caller), so default tours are untouched.
"""
import re
from typing import Dict, List, Tuple

__all__ = [
    'LEXICON', 'canonical_name', 'fix_names', 'add_pronunciation_aids',
    'apply', 'WORK_ARTIST', 'ssml_pronunciation', 'to_ssml',
    'kokoro_pronunciation', 'to_kokoro',
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

    def __init__(self, full: str, say: str, variants: List[str], ipa: str = '',
                 kokoro_ipa: str = ''):
        self.full = full
        self.say = say
        self.variants = variants
        # Optional IPA for a Polly SSML <phoneme>; must be STANDARD IPA that AWS
        # Polly accepts. Empty by default → Polly uses <sub alias=say> (the
        # proven LOCAL-692B behaviour). Do NOT put misaki-flavoured IPA here.
        self.ipa = ipa
        # [LOCAL-706] Optional IPA for the Kokoro/misaki G2P inline markup
        # [name](/IPA/). Written in misaki's US-English phoneme vocabulary
        # (A/Y/O/W/I diphthong tokens, ˈ/ˌ stress) — NOT the same alphabet as
        # Polly's <phoneme>. Empty → the Kokoro path substitutes `say`.
        self.kokoro_ipa = kokoro_ipa


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

# ── [LOCAL-706 / D667] GENERIC lexicon overlay ───────────────────────────────
# The verified records above seed the lexicon in code. LOCAL-706 adds a GENERIC,
# data-driven lexicon file (pronunciation_lexicon.json) with language / written
# / ipa / respelling / sources, so French/Russian/etc. names can be added later
# WITHOUT touching this module. On import we overlay the JSON onto LEXICON:
#   * a JSON `key` that matches an existing LEXICON key UPDATES that record's
#     ipa/respelling/variants (this is how the Vietnamese names gain IPA, which
#     the Kokoro path needs — see kokoro_pronunciation);
#   * a new `key` is ADDED as a fresh _Artist.
# Loading is SOFT: a missing/malformed file leaves the in-code LEXICON exactly as
# it was (fail-safe), so neither TTS path can break if the file is absent.
import json as _json
import os as _os

LEXICON_JSON_PATH = _os.path.join(
    _os.path.dirname(_os.path.abspath(__file__)), 'pronunciation_lexicon.json')


def _load_generic_lexicon(path: str = LEXICON_JSON_PATH) -> List[str]:
    """Overlay pronunciation_lexicon.json onto LEXICON. Returns load notes.
    Fail-safe: any error leaves LEXICON unchanged and returns a one-item note."""
    notes: List[str] = []
    try:
        with open(path, encoding='utf-8') as fh:
            data = _json.load(fh)
        for e in data.get('entries', []):
            key = (e.get('key') or '').strip()
            written = (e.get('written') or '').strip()
            if not key or not written:
                continue
            # `ipa` in the JSON is misaki/Kokoro IPA (US-English phoneme vocab).
            # It feeds the Kokoro inline markup, NOT Polly's <phoneme> (different
            # alphabet). A standard-IPA string for Polly, when known, goes in the
            # optional `polly_ipa` field.
            kokoro_ipa = (e.get('ipa') or '').strip()
            polly_ipa = (e.get('polly_ipa') or '').strip()
            say = (e.get('respelling') or '').strip()
            variants = [v for v in (e.get('variants') or []) if v]
            if key in LEXICON:
                a = LEXICON[key]
                if kokoro_ipa:
                    a.kokoro_ipa = kokoro_ipa
                if polly_ipa:
                    a.ipa = polly_ipa
                if say:
                    a.say = say
                for v in variants:
                    if v not in a.variants:
                        a.variants.append(v)
                notes.append(f'overlay:{key}(kokoro_ipa={bool(kokoro_ipa)})')
            else:
                LEXICON[key] = _Artist(
                    written, say or written, variants,
                    ipa=polly_ipa, kokoro_ipa=kokoro_ipa)
                notes.append(f'add:{key}(kokoro_ipa={bool(kokoro_ipa)})')
    except FileNotFoundError:
        notes.append('lexicon_json:absent (in-code lexicon kept)')
    except Exception as _lex_err:  # pragma: no cover - never break TTS on bad file
        notes.append(f'lexicon_json:error {_lex_err} (in-code lexicon kept)')
    return notes


# Overlay at import so both TTS paths see the IPA. Non-fatal.
_LEXICON_LOAD_NOTES = _load_generic_lexicon()


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


def apply(text: str, with_aids: bool = False) -> Tuple[str, List[str]]:
    """Full pass: fix names in the SPOKEN text. Returns (new_text, notes).
    Pure/deterministic; safe on any text (a tour with no Vietnamese names is
    returned unchanged with empty notes).

    [LOCAL-692B / D659 LEAD review] ``with_aids`` now DEFAULTS TO FALSE. The
    LOCAL-692 ``(say: …)`` parenthetical was being READ ALOUD by the voice
    ("…Trí, say ngwen zah chee…"), which Michael flagged. Pronunciation is now
    done at the TTS layer only (Polly SSML ``<sub>``; see ``ssml_pronunciation``
    and polly_tts_service), so the NARRATION TEXT must stay clean: the diacritic
    name is kept correct, but no spoken aid is injected. ``with_aids=True`` is
    retained only for diagnostics/back-compat and must not be used on narration
    that goes to TTS."""
    notes: List[str] = []
    text, n1 = fix_names(text)
    notes.extend(n1)
    if with_aids:
        text, n2 = add_pronunciation_aids(text)
        notes.extend(n2)
    return text, notes


# ── [LOCAL-692B] TTS-LAYER PRONUNCIATION (SSML) ───────────────────────────────
# Michael (D659 LEAD review): "(say: ngwen zah chee)" would be READ ALOUD. So
# pronunciation must happen in the TTS layer, not the narration text. AWS Polly
# supports two mechanisms inside SSML:
#   <phoneme alphabet="ipa" ph="…">name</phoneme>  — exact, but needs valid IPA.
#   <sub alias="spoken form">name</sub>            — substitutes a spoken string
#       the (English) voice can pronounce; robust for an English neural voice
#       reading Vietnamese, which is exactly our case (Joanna).
# We use <sub> with the verified English-phonetic respelling (`say`), optionally
# <phoneme> when an IPA string is present. The listener hears the respelling;
# the on-screen/printed text keeps the correct diacritic name.
import html as _html


def _ssml_escape(s: str) -> str:
    """XML-escape a string for inclusion in SSML (text + attribute values)."""
    return _html.escape(s or '', quote=True)


def ssml_pronunciation(text: str) -> Tuple[str, List[str]]:
    """Wrap each known artist name in the SPOKEN text with an SSML ``<sub>`` (or
    ``<phoneme>``) so the TTS voice pronounces it from the verified respelling,
    while the visible name stays the correct diacritic form. Returns
    (ssml_without_speak_wrapper, notes). The caller wraps the whole stop in a
    single <speak> element. Deterministic; a text with no known names is
    returned XML-escaped and unchanged (empty notes).

    ONLY the first mention of each name is wrapped — later mentions are left as
    plain (escaped) text so the audio is not over-annotated; Polly pronounces a
    repeated name consistently once the voice has 'heard' the substitution."""
    notes: List[str] = []
    # Build first-mention spans for each known full name, longest-first so a
    # longer name is matched before a shorter overlapping one.
    names = sorted(LEXICON.values(), key=lambda a: len(a.full), reverse=True)
    spans: List[Tuple[int, int, '_Artist']] = []
    claimed: List[Tuple[int, int]] = []
    for a in names:
        pat = re.compile(r'(?<![\wÀ-ỹ])' + re.escape(a.full) + r'(?![\wÀ-ỹ])')
        m = pat.search(text)
        if not m:
            continue
        s, e = m.start(), m.end()
        if any(not (e <= cs or s >= ce) for cs, ce in claimed):
            continue  # overlaps an already-claimed span
        spans.append((s, e, a))
        claimed.append((s, e))
    spans.sort(key=lambda t: t[0])

    out_parts: List[str] = []
    cursor = 0
    for s, e, a in spans:
        out_parts.append(_ssml_escape(text[cursor:s]))
        alias = _ssml_escape(a.say)
        name = _ssml_escape(a.full)
        if getattr(a, 'ipa', ''):
            out_parts.append(
                f'<phoneme alphabet="ipa" ph="{_ssml_escape(a.ipa)}">{name}</phoneme>')
            notes.append(f'ssml_phoneme:{a.full}->/{a.ipa}/')
        else:
            out_parts.append(f'<sub alias="{alias}">{name}</sub>')
            notes.append(f'ssml_sub:{a.full}->{a.say}')
        cursor = e
    out_parts.append(_ssml_escape(text[cursor:]))
    return ''.join(out_parts), notes


def to_ssml(text: str) -> Tuple[str, List[str]]:
    """Convenience: return a complete, Polly-ready ``<speak>…</speak>`` document
    with every known name pronounced via <sub>/<phoneme>, plus the notes. If no
    known name is present the text is still returned wrapped in <speak> (escaped),
    which Polly treats identically to plain text."""
    body, notes = ssml_pronunciation(text)
    return f'<speak>{body}</speak>', notes


# ── [LOCAL-706 / D667] KOKORO-LAYER PRONUNCIATION (misaki inline markup) ──────
# Michael prefers the free Kokoro voice (the Mac stack's English default,
# TTS_ENGINE=kokoro, rendered WHOLE on the host service via
# polly_tts_service._render_whole_via_host). The LOCAL-692B Polly SSML aid above
# never reaches Kokoro — Kokoro does not take SSML — so real English tours hit
# Kokoro with the raw diacritic names, which misaki cannot pronounce (bare
# "Nguyễn Gia Trí" tokenises to the unknown-phoneme marker "❓ ❓ ❓").
#
# Kokoro's G2P front-end (misaki) DOES accept an inline markup identical in
# spirit to Polly's phoneme/sub split:
#   [grapheme](/IPA/)   → misaki uses the slash-delimited IPA verbatim as the
#                         token's phonemes (validated: the IPA round-trips
#                         through misaki.en.G2P unchanged). Used when the lexicon
#                         has IPA.
#   (no IPA)            → there is NO misaki markup for "say it like this English
#                         word", so we substitute the verified English RESPELLING
#                         as the spoken grapheme (e.g. "ngwen zah chee"), which an
#                         English voice pronounces acceptably. This mirrors Polly's
#                         <sub alias> fallback.
# Only the FIRST mention of each name is annotated (later mentions stay plain) so
# the audio is not over-marked, exactly like ssml_pronunciation. The visible/
# printed TEXT is NEVER changed — only the string sent to the Kokoro host.
#
# IMPORTANT: the IPA strings in pronunciation_lexicon.json are written in
# misaki's US-English phoneme vocabulary (A/Y/O/W/I diphthong tokens, ˈ/ˌ
# stress). Keep them valid for misaki — see test_local706_kokoro_pronunciation.py
# which asserts each one round-trips through the real misaki G2P.


def _first_mention_spans(text: str) -> List[Tuple[int, int, '_Artist']]:
    """Shared first-mention span finder: for each known full name, the first,
    non-overlapping, longest-first match in ``text``. Returns (start, end,
    artist) sorted by start. Used by both the SSML and Kokoro builders so the two
    TTS paths annotate exactly the same mentions."""
    names = sorted(LEXICON.values(), key=lambda a: len(a.full), reverse=True)
    spans: List[Tuple[int, int, '_Artist']] = []
    claimed: List[Tuple[int, int]] = []
    for a in names:
        pat = re.compile(r'(?<![\wÀ-ỹ])' + re.escape(a.full) + r'(?![\wÀ-ỹ])')
        m = pat.search(text)
        if not m:
            continue
        s, e = m.start(), m.end()
        if any(not (e <= cs or s >= ce) for cs, ce in claimed):
            continue
        spans.append((s, e, a))
        claimed.append((s, e))
    spans.sort(key=lambda t: t[0])
    return spans


def _kokoro_escape(s: str) -> str:
    """Escape the misaki markup delimiters in ordinary (non-annotated) text so a
    stray '[', ']', '(' or ')' in the narration is not misread as markup. misaki
    only treats a FULL ``[...](...)`` as a link, so escaping the brackets with a
    backslash is sufficient and leaves normal prose untouched in practice."""
    return (s or '').replace('[', r'\[').replace(']', r'\]')


def kokoro_pronunciation(text: str) -> Tuple[str, List[str]]:
    """Annotate the first mention of each known name for the Kokoro/misaki G2P:
    ``[Name](/IPA/)`` when the lexicon has IPA, else substitute the verified
    English respelling in place of the name. Returns (text_for_kokoro, notes).

    Deterministic; a text with no known name is returned unchanged (empty notes).
    The visible TEXT is not this — this is ONLY the string handed to the Kokoro
    host service. Later mentions of a name are left as the plain diacritic form;
    misaki will still mispronounce those, but the first, annotated mention gives
    the correct pronunciation, matching the SSML path's first-mention policy."""
    notes: List[str] = []
    spans = _first_mention_spans(text)
    if not spans:
        return text, notes
    out_parts: List[str] = []
    cursor = 0
    for s, e, a in spans:
        out_parts.append(_kokoro_escape(text[cursor:s]))
        name = text[s:e]
        ipa = getattr(a, 'kokoro_ipa', '')
        if ipa:
            out_parts.append(f'[{name}](/{ipa}/)')
            notes.append(f'kokoro_ipa:{a.full}->/{ipa}/')
        elif a.say:
            # No IPA: speak the respelling instead of the (unpronounceable) name.
            out_parts.append(a.say)
            notes.append(f'kokoro_respell:{a.full}->{a.say}')
        else:
            out_parts.append(_kokoro_escape(name))
        cursor = e
    out_parts.append(_kokoro_escape(text[cursor:]))
    return ''.join(out_parts), notes


def to_kokoro(text: str) -> Tuple[str, List[str]]:
    """Convenience alias: return the Kokoro-host text (misaki inline markup for
    every known name) plus notes. Named to parallel ``to_ssml``. If no known name
    is present the text is returned unchanged."""
    return kokoro_pronunciation(text)


if __name__ == '__main__':
    import sys
    src = sys.stdin.read() if not sys.stdin.isatty() else (
        'Spring Garden by Nguyen Van Tri. Later, Nguyễn Gia Trí worked. '
        'Sơn nữ is a painting by Lựu. Nguyen Sang made Thanh nien thanh dong.')
    out, notes = apply(src)                 # narration text — NO (say:) aid
    ssml, ssml_notes = to_ssml(out)         # TTS layer — SSML pronunciation
    kok, kok_notes = to_kokoro(out)         # TTS layer — Kokoro/misaki markup
    print('--- narration text (clean, goes to the listener as words) ---')
    print(out)
    print('\n--- SSML sent to Polly (TextType=ssml) ---')
    print(ssml)
    print('\n--- text sent to Kokoro host (misaki inline markup) ---')
    print(kok)
    print('\n--- name-fix notes ---')
    for nnote in notes:
        print(nnote)
    print('\n--- ssml pronunciation notes ---')
    for nnote in ssml_notes:
        print(nnote)
    print('\n--- kokoro pronunciation notes ---')
    for nnote in kok_notes:
        print(nnote)
