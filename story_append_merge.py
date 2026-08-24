#!/usr/bin/env python3
"""story_append_merge.py — D518: the story REPLACES the prose it overlaps.

Michael, 2026-08-24: *"saying things twice is the worst for listeners — they hear
that and get annoyed. Moreover, selecting the story topic based on the sentences
made this problem so we need to fix it."*

**The second sentence is the diagnosis, and it is right.** The loop's credit_lines
are mined from the stop's own prose (`story_seeds.seeds_for_stop(stop_text, ...)`),
so the loop is *guaranteed* to research whatever the prose already said and then
say it again, better. The duplication is structural, not stylistic — which is why
`description.rstrip() + ' ' + story` could never be made to read well by tuning the
writer. Measured on the 2026-08-23 tour, three stops of three:

  stop 1  prose: "In 1956, Louis Broder, the publisher of this edition, began a
                  partnership with Joan Miró…"
          story: "In 1967, Joan Miró and publisher Louis Broder completed an
                  initial edition…"
  stop 2  prose tells Gris's death, the eleven plates and the 1955 revival;
          the story tells all three again, with sources
  stop 3  prose: "Moses was not a Hebrew but an Egyptian **priest**"
          story: "Moses was of Egyptian **nobility** rather than Hebrew origin"

Stop 3 is the case that makes this more than a style bug: the append put the
CORRECTED fact next to the UNCORRECTED one and kept both, inside one stop.

**So the fix is subtraction, not rewriting.** For each prose sentence, ask whether
the story already covers it; drop the ones it does. No model call, no network — the
overlap is visible in the shared names, years and numbers, which is exactly what
the seeds were mined from in the first place.

## What counts as "the story already says this"

Two signals, deliberately different in kind:

  ANCHOR OVERLAP    the proper names, years and quantities the two share. Two
                    sentences about the same episode name the same people and the
                    same year. This is the primary test because anchors are what a
                    listener notices being repeated.
  CONTENT OVERLAP   plain lexical coverage, as a backstop for a sentence that
                    repeats a claim while naming nobody.

A sentence is dropped when it shares **at least 2 anchors AND half its anchors**
with the story, or when 60% of its content words are already in the story.

**The work's own title is excluded from the anchor set on both sides.** Nearly
every sentence in a stop names the work; sharing the title is not evidence that two
sentences say the same thing, and without this exclusion a purely descriptive
sentence ("the edition is bound in publisher's vellum") gets dropped for the crime
of naming the book. That was the first thing the fixtures caught.

**At most 60% of the prose is ever removed** (`MAX_DROP_RATIO`), highest-overlap
first. A story that appears to subsume an entire stop is far more likely to be an
overlap metric behaving badly than a stop worth deleting, and a listener would
rather hear one repeated sentence than a stop that has lost its description.
"""
import os
import re
import unicodedata
from typing import Dict, List, Optional, Sequence, Set, Tuple

__all__ = ['merge_story_into_description', 'sentences_of', 'anchors_of',
           'MIN_SHARED_ANCHORS', 'ANCHOR_COVERAGE_DROP', 'CONTENT_COVERAGE_DROP',
           'MAX_DROP_RATIO']

MIN_SHARED_ANCHORS = int(os.environ.get('STORY_MERGE_MIN_ANCHORS', '2'))
ANCHOR_COVERAGE_DROP = float(os.environ.get('STORY_MERGE_ANCHOR_COV', '0.5'))
CONTENT_COVERAGE_DROP = float(os.environ.get('STORY_MERGE_CONTENT_COV', '0.6'))
MAX_DROP_RATIO = float(os.environ.get('STORY_MERGE_MAX_DROP_RATIO', '0.6'))
ORPHAN_BUDGET = int(os.environ.get('STORY_MERGE_ORPHAN_BUDGET', '2'))

# Capitalised words that are capitalised for grammar, not because they name
# anything. Without this list every sentence-initial "The" is an anchor and every
# pair of sentences looks related.
_NOT_A_NAME = {
    'a', 'an', 'the', 'this', 'that', 'these', 'those', 'his', 'her', 'its',
    'their', 'our', 'your', 'my', 'it', 'he', 'she', 'they', 'we', 'you', 'i',
    'in', 'on', 'at', 'by', 'for', 'from', 'with', 'within', 'without', 'to',
    'of', 'as', 'and', 'or', 'but', 'so', 'yet', 'nor', 'if', 'then', 'than',
    'when', 'while', 'where', 'because', 'after', 'before', 'during', 'since',
    'until', 'through', 'across', 'between', 'among', 'over', 'under', 'about',
    'nearly', 'almost', 'depending', 'decades', 'later', 'today', 'now', 'here',
    'there', 'both', 'each', 'every', 'some', 'many', 'most', 'few', 'several',
    'one', 'two', 'three', 'four', 'five', 'six', 'seven', 'eight', 'nine',
    'ten', 'first', 'second', 'third', 'last', 'next', 'other', 'another',
    'such', 'no', 'not', 'only', 'also', 'still', 'even', 'just', 'more',
    'work', 'works', 'edition', 'book', 'page', 'pages', 'artist', 'artists',
    'museum', 'gallery', 'exhibition', 'collection', 'sources', 'source',
    'what', 'which', 'who', 'whose', 'how', 'why',
}

# Content words carrying no topic. Kept small on purpose: the content test is a
# backstop, and an over-long stoplist makes every short sentence look covered.
_STOPWORDS = _NOT_A_NAME | {
    'was', 'were', 'is', 'are', 'be', 'been', 'being', 'has', 'have', 'had',
    'having', 'do', 'does', 'did', 'will', 'would', 'can', 'could', 'shall',
    'should', 'may', 'might', 'must', 'into', 'onto', 'upon', 'out', 'up',
    'down', 'off', 'again', 'once', 'own', 'same', 'very', 'too', 'per',
    'thus', 'however', 'therefore', 'rather', 'well', 'much', 'like',
}

_NUMBER_WORDS = {
    'one': '1', 'two': '2', 'three': '3', 'four': '4', 'five': '5', 'six': '6',
    'seven': '7', 'eight': '8', 'nine': '9', 'ten': '10', 'eleven': '11',
    'twelve': '12', 'thirteen': '13', 'fourteen': '14', 'fifteen': '15',
    'sixteen': '16', 'seventeen': '17', 'eighteen': '18', 'nineteen': '19',
    'twenty': '20', 'thirty': '30', 'forty': '40', 'fifty': '50',
    'sixty': '60', 'seventy': '70', 'eighty': '80', 'ninety': '90',
    'hundred': '100', 'thousand': '1000',
}

# A sentence opening with a bare pronoun and a verb points BACKWARDS at whatever
# came before it. Drop the sentence it pointed at and the pointer dangles: stop 3
# lost "Salvador Dalí created illustrations for Freud's book" as a duplicate and
# then opened on "This marked a significant moment in Dalí's career" — marked
# *what*? So the repair is part of the fix, not a nicety.
#
# Deliberately conservative on both sides. The opener must be a BARE pronoun
# ("This was", "It marked"), never a pronoun carrying its own noun ("This work",
# "These lithographs"), which resolves to the stop's subject and stands alone. A
# miss keeps the sentence, which is the status quo.
_ANAPHORIC_OPENERS = {'this', 'that', 'it', 'they', 'these', 'those', 'such',
                      'he', 'she', 'there', 'here'}
_OPENER_VERBS = {
    'is', 'was', 'were', 'are', 'be', 'been', 'being', 'has', 'have', 'had',
    'will', 'would', 'can', 'could', 'may', 'might', 'must', 'shall', 'should',
    'do', 'does', 'did', 'also', 'then', 'however', 'later', 'too', 'again',
    'became', 'begins', 'began', 'stands', 'shows', 'makes', 'made', 'brings',
    'gives', 'holds', 'remains', 'comes', 'goes', 'took', 'set', 'led',
}

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_TOKEN_RE = re.compile(r"[\w'’\-]+", re.UNICODE)
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])["”’\')\]]*\s+')


def _fold(s: str) -> str:
    """Accent-strip and lowercase. Mirrors `text_fold.fold`, without the import.

    This module is called from inside the generator's exception-wrapped phase and
    must not fail on a missing sibling; the behaviour is small enough to own.
    """
    if not s:
        return ''
    decomposed = unicodedata.normalize('NFD', str(s).lower())
    return ''.join(c for c in decomposed
                   if unicodedata.category(c) != 'Mn')


def sentences_of(text: str) -> List[str]:
    """Split into sentences, keeping every one — including the malformed.

    Unlike the loop's own `_sentences`, this does NOT drop short fragments: these
    sentences are going back into the tour, so anything dropped here is deleted
    from the product. A missing space after a full stop (`depth.Boris`) leaves two
    sentences joined; they travel as one unit and are kept or dropped together,
    which is correct — that defect is upstream and not this function's to invent a
    fix for.
    """
    if not text or not text.strip():
        return []
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text.strip()) if s.strip()]


def _stem(word: str) -> str:
    """Crudest useful stem: enough that `published` matches `publication`'s root
    only when it really is the same word family, and `plates` matches `plate`."""
    w = word
    for suffix in ("'s", "’s"):
        if w.endswith(suffix):
            w = w[:-len(suffix)]
    for suffix in ('ies',):
        if len(w) > 4 and w.endswith(suffix):
            return w[:-3] + 'y'
    for suffix in ('ing', 'ed', 'es', 's'):
        if len(w) > len(suffix) + 3 and w.endswith(suffix):
            return w[:-len(suffix)]
    return w


def anchors_of(sentence: str, exclude: Optional[Set[str]] = None) -> Set[str]:
    """The proper names, years and quantities in one sentence.

    An anchor is a capitalised word that is not merely sentence-initial grammar, a
    four-digit year, or a number — including a number spelled out, so the prose's
    `11 vivid lithographs` and the story's `eleven finished lithographs` are the
    same anchor rather than two.
    """
    exclude = exclude or set()
    found: Set[str] = set()
    for m in re.finditer(r'\b(1[0-9]{3}|20[0-9]{2})\b', sentence):
        found.add(m.group(1))
    for m in re.finditer(r'\b\d+\b', sentence):
        found.add(str(int(m.group(0))))
    for token in _TOKEN_RE.findall(sentence):
        folded = _fold(token).strip("'’-")
        if not folded or folded in exclude:
            continue
        if folded in _NUMBER_WORDS:
            found.add(_NUMBER_WORDS[folded])
            continue
        if len(folded) < 2 or folded in _NOT_A_NAME:
            continue
        if token[:1].isupper():
            found.add(folded)
    return found


def _content(sentence: str, exclude: Optional[Set[str]] = None) -> Set[str]:
    exclude = exclude or set()
    out: Set[str] = set()
    for token in _WORD_RE.findall(sentence):
        folded = _fold(token)
        if len(folded) < 3 or folded in _STOPWORDS or folded in exclude:
            continue
        out.add(_stem(folded))
    return out


def _title_tokens(*titles: str) -> Set[str]:
    """Every word of the work's own titles, folded.

    Excluded from anchors on both sides: naming the work is what a stop about the
    work does, in every sentence, and counting it as shared evidence made a
    description of the binding look like a duplicate of the story.
    """
    out: Set[str] = set()
    for t in titles:
        for token in _TOKEN_RE.findall(t or ''):
            folded = _fold(token).strip("'’-")
            if folded and len(folded) > 1:
                out.add(folded)
    return out


def _is_orphaned_opener(sentence: str) -> bool:
    """Does this sentence start by pointing at a sentence that is no longer there?"""
    words = _TOKEN_RE.findall(sentence)
    if len(words) < 2:
        return False
    if _fold(words[0]) not in _ANAPHORIC_OPENERS:
        return False
    second = _fold(words[1])
    return second in _OPENER_VERBS or (len(second) > 4 and second.endswith('ed'))


def _overlap(prose_sentence: str, story_anchors: Set[str], story_content: Set[str],
             excluded: Set[str]) -> Dict:
    p_anchors = anchors_of(prose_sentence, exclude=excluded)
    p_content = _content(prose_sentence, exclude=excluded)
    shared_anchors = p_anchors & story_anchors
    shared_content = p_content & story_content
    anchor_cov = (len(shared_anchors) / len(p_anchors)) if p_anchors else 0.0
    content_cov = (len(shared_content) / len(p_content)) if p_content else 0.0
    covered = (
        (len(shared_anchors) >= MIN_SHARED_ANCHORS and anchor_cov >= ANCHOR_COVERAGE_DROP)
        or content_cov >= CONTENT_COVERAGE_DROP
    )
    return {
        'sentence': prose_sentence,
        'shared_anchors': sorted(shared_anchors),
        'anchor_coverage': round(anchor_cov, 3),
        'content_coverage': round(content_cov, 3),
        'covered': covered,
        'rank': round(0.6 * anchor_cov + 0.4 * content_cov, 4),
    }


def merge_story_into_description(description: str, story: str,
                                 work_titles: Sequence[str] = (),
                                 verbose: bool = False) -> Tuple[str, Dict]:
    """Join the gated story to the stop's prose, minus the prose it repeats.

    Returns `(merged_text, report)`. `report` carries `dropped` (the sentences
    removed, with the overlap that condemned each) and `kept`, so a run can be
    audited from the log without re-deriving the arithmetic.

    An empty story returns the description untouched — a stop that published
    nothing is not a stop to edit.
    """
    report = {'dropped': [], 'kept': [], 'n_prose': 0, 'n_dropped': 0,
              'capped': False, 'orphans': [], 'story_first': False}
    if not (story or '').strip():
        return description, report
    if not (description or '').strip():
        return story.strip(), report

    excluded = _title_tokens(*work_titles)
    prose = sentences_of(description)
    report['n_prose'] = len(prose)
    story_anchors = anchors_of(story, exclude=excluded)
    story_content = _content(story, exclude=excluded)

    scored = [_overlap(s, story_anchors, story_content, excluded) for s in prose]
    candidates = [d for d in scored if d['covered']]

    # Never strip the stop bare: at most MAX_DROP_RATIO of it goes, worst first.
    cap = int(len(prose) * MAX_DROP_RATIO)
    if len(candidates) > cap:
        candidates.sort(key=lambda d: d['rank'], reverse=True)
        candidates = candidates[:cap]
        report['capped'] = True
    doomed = {id(d) for d in candidates}

    # ── If the story replaced the OPENING, the story becomes the opening ──
    #
    # Measured on the live run of 2026-08-24, and it is the defect this fix
    # introduced. A stop's first prose sentence is the one that introduces its
    # subject, so it is also the one most likely to duplicate a story mined from
    # it — and dropping it left all three stops opening on a reference to nobody:
    #
    #     "Broder published this limited edition book…"        (who is Broder?)
    #     "The project, originally conceived by L. Rosenberg…" (which project?)
    #     "Published by The Hogarth Press, Freud's theory…"    (which theory?)
    #
    # Moving the story to the front repairs every one of them without deleting a
    # word, because the story always introduces its own subjects in full: "Joan
    # Miró authored a surrealist poem and originally illustrated it in 1967 with a
    # suite of eighteen lithographs printed for publisher Louis Broder" — and then
    # "Broder published this limited edition book" has its antecedent.
    #
    # It is also the truer reading of "the story REPLACES the prose it overlaps":
    # replacement should happen where the prose was, not always at the end.
    story_first = bool(scored) and id(scored[0]) in doomed

    # Repair the anaphora the dedupe broke, when the prose still opens the stop.
    # Unnecessary when the story opens it — a following "This marked…" then points
    # at the story, which is a real antecedent — so this only runs in the other
    # case, and never deletes a sentence the reordering would have saved.
    orphans = []
    if not story_first:
        head = 0
        while (head < len(scored) and id(scored[head]) in doomed):
            head += 1
        while (head < len(scored) - 1 and len(orphans) < ORPHAN_BUDGET
               and head > 0
               and _is_orphaned_opener(scored[head]['sentence'])
               and sum(1 for d in scored if id(d) not in doomed) > 1):
            orphans.append(scored[head])
            doomed.add(id(scored[head]))
            head += 1
            while head < len(scored) and id(scored[head]) in doomed:
                head += 1

    kept_text = [d['sentence'] for d in scored if id(d) not in doomed]
    report['dropped'] = sorted(candidates, key=lambda d: d['rank'], reverse=True)
    report['orphans'] = [d['sentence'] for d in orphans]
    report['kept'] = kept_text
    report['n_dropped'] = len(candidates) + len(orphans)
    report['story_first'] = story_first

    ordered = [t.strip() for t in kept_text if t.strip()]
    ordered = ([story.strip()] + ordered) if story_first else (ordered + [story.strip()])
    merged = re.sub(r'\s+', ' ', ' '.join(ordered)).strip()

    if verbose and report['n_dropped']:
        for d in report['dropped']:
            print(f"      [D518] dropped (anchors {d['anchor_coverage']:.2f} "
                  f"{','.join(d['shared_anchors'][:5])} | content "
                  f"{d['content_coverage']:.2f}): \"{d['sentence'][:88]}\"")
        for s in report['orphans']:
            print(f"      [D518] dropped (orphaned opener): \"{s[:88]}\"")
    return merged, report
