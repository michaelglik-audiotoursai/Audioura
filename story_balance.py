#!/usr/bin/env python3
"""story_balance.py — LOCAL-620 (D634): a BALANCE policy, not a hard cap.

Michael's ruling (D634, 2026-10-07):
  "I would not dismiss outright museum and donor sentences in favour of the
   exhibit, and let some be used to determine the user preferences. I complained
   because these were the only stories in that museum and very little about the
   paintings themselves."

LOCAL-617 ``filter_stop_body_work_first`` enforced a HARD CAP: at most ONE
institutional sentence per stop, the own-acquisition one, and dropped every
other. That silenced real collector/museum STORIES — the only stories some
museums have about their holdings — and that is now too strict.

This module replaces the hard cap with a BALANCE policy on the delivered stop
body:

  • the WORK and its MEANING LEAD when the work's own evidence exists (work /
    artist / reception / emotion sentences are never dropped);
  • a REAL collector/museum STORY (``story_type_classes.is_real_collector_story``
    — a named person + a motive or consequence) is KEPT, up to ~25% of the stop's
    sentences, and MORE when the work's own evidence is thin (better a true
    collector story than nothing);
  • pure BOILERPLATE (renovation budgets, square metres, opening hours, a bare
    founding date, mission prose — ``is_boilerplate_institutional``) is still
    DROPPED; it is not a story and must never be a preference signal;
  • the stop is never emptied (D577): if trimming would leave nothing, the body
    is returned unchanged.

Across the tour, ``ensure_tour_class_coverage`` reports whether every preference
class (details / historic / social) appears in at least one stop when the
evidence allows, so a listener's preferences can be learned for all three. It
does not fabricate; it only measures and (optionally) protects a lone carrier of
a class from being trimmed below one.

Pure (no network, no LLM, no DB); deterministic; idempotent.
"""
from __future__ import annotations

import math
import re
from typing import Dict, List, Optional, Sequence, Tuple

import work_first_evidence as wfe
import story_type_classes as stc
from three_class_retrieval import CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL

__all__ = [
    "DEFAULT_INSTITUTIONAL_SHARE",
    "balance_stop_body",
    "balance_tour_text_work_first",
    "balance_snippets_work_first",
    "ensure_tour_class_coverage",
]

# The target ceiling for collector/museum ("institutional") sentences as a share
# of a stop's sentences when the work's own evidence is healthy (~25%). The cap
# RELAXES when the work's own evidence is thin (see ``_allowed_institutional``).
DEFAULT_INSTITUTIONAL_SHARE = 0.25

# A stop is "evidence-thin" when it has few work/artist/reception/emotion
# sentences to stand on. Below this many rich sentences, collector stories may
# take a larger share (better than nothing).
_THIN_RICH_THRESHOLD = 2

_STOP_HEADER_RE = re.compile(r"(?mi)^(Stop\s+\d+\s*[:\-][^\n]*)$")

# Opening-section markers (reuse the LOCAL-617 opening detector so the D611
# "About <museum>" section stays exempt — it is allowed to be institutional).
_is_opening_paragraph = wfe._is_opening_paragraph


def _allowed_institutional(n_rich: int, n_sentences: int,
                           share: float = DEFAULT_INSTITUTIONAL_SHARE) -> int:
    """How many collector/museum STORY sentences a stop may keep.

    Healthy evidence (>= _THIN_RICH_THRESHOLD rich sentences): about ``share`` of
    the stop's sentences, at least 1. Thin evidence: relax — allow up to half the
    stop, so a true collector story can carry a stop that has little of its own.
    """
    if n_sentences <= 0:
        return 0
    base = max(1, int(math.floor(share * n_sentences + 1e-9)))
    if n_rich < _THIN_RICH_THRESHOLD:
        # evidence thin → a collector story may take a larger share (up to half).
        relaxed = max(base, int(math.ceil(0.5 * n_sentences)))
        return relaxed
    return base


def balance_stop_body(body: str,
                      venue_tokens: Optional[Sequence[str]] = None,
                      work_subject: str = "",
                      is_opening_section: bool = False,
                      share: float = DEFAULT_INSTITUTIONAL_SHARE
                      ) -> Tuple[str, Dict]:
    """[LOCAL-620] Balance a delivered stop body instead of hard-capping it.

    Keeps all work/artist/reception/emotion sentences; keeps REAL collector/
    museum stories up to ~``share`` of the stop (more when evidence is thin);
    drops pure boilerplate and bare transfers of title. Never empties a stop.

    Returns (new_body, report) with keys:
      institutional_total   — collector/museum sentences seen;
      story_kept            — real collector STORY sentences kept;
      boilerplate_dropped   — pure boilerplate sentences dropped;
      transfer_dropped      — bare-transfer institutional sentences dropped;
      rich                  — work/artist/reception/emotion sentences;
      thin                  — True when the stop's own evidence was thin;
      changed               — True when any sentence was dropped.
    """
    report = {
        "institutional_total": 0,
        "story_kept": 0,
        "boilerplate_dropped": 0,
        "transfer_dropped": 0,
        "rich": 0,
        "thin": False,
        "exempt_opening": bool(is_opening_section),
        "changed": False,
    }
    if is_opening_section or not body or not body.strip():
        return body, report

    sents = wfe.split_sentences(body)
    if len(sents) <= 1:
        return body, report

    # Classify each sentence into {rich, story, boilerplate, transfer, other}.
    kinds: List[str] = []
    for s in sents:
        stype = wfe.classify_sentence(s, venue_tokens=venue_tokens,
                                      work_subject=work_subject)
        if stype in ("work", "artist", "reception", "emotion"):
            kinds.append("rich")
        elif stype == "institutional":
            if stc.is_boilerplate_institutional(s):
                kinds.append("boilerplate")
            elif stc.is_real_collector_story(s, work_subject=work_subject):
                kinds.append("story")
            else:
                kinds.append("transfer")  # bare transfer of title — not a story
        elif stc.is_real_collector_story(s, work_subject=work_subject):
            # A real collector/museum STORY the LOCAL-617 lexicon labelled
            # 'other' (e.g. "The banker Reiset, in memory of his wife, gave …")
            # is still a collector story and must obey the same ~25% budget.
            kinds.append("story")
        else:
            kinds.append("other")

    n_rich = kinds.count("rich")
    n_story = kinds.count("story")
    n_inst = n_story + kinds.count("transfer") + kinds.count("boilerplate")
    report["rich"] = n_rich
    report["institutional_total"] = n_inst
    thin = n_rich < _THIN_RICH_THRESHOLD
    report["thin"] = thin

    # Nothing rich to stand on → leave the stop untouched (never empty a stop,
    # D577). The collector stories ARE the stop's content in that case.
    if n_rich == 0:
        return body, report

    allowed_story = _allowed_institutional(n_rich, len(sents), share=share)

    kept_sents: List[str] = []
    story_kept = 0
    boiler_dropped = 0
    transfer_dropped = 0
    for s, kind in zip(sents, kinds):
        if kind == "rich" or kind == "other":
            kept_sents.append(s)
            continue
        if kind == "boilerplate":
            boiler_dropped += 1
            continue
        if kind == "transfer":
            # a bare transfer of title is dropped UNLESS the stop is thin and we
            # still have story budget (then it is better than nothing).
            if thin and story_kept < allowed_story:
                kept_sents.append(s)
                story_kept += 1
            else:
                transfer_dropped += 1
            continue
        # kind == 'story' — a REAL collector/museum story.
        if story_kept < allowed_story:
            kept_sents.append(s)
            story_kept += 1
        else:
            transfer_dropped += 1  # trimmed to respect the ~25% balance

    report["story_kept"] = story_kept
    report["boilerplate_dropped"] = boiler_dropped
    report["transfer_dropped"] = transfer_dropped
    report["changed"] = (boiler_dropped + transfer_dropped) > 0

    new_body = " ".join(kept_sents).strip()
    if not new_body:
        return body, report
    return new_body, report


def balance_tour_text_work_first(tour_text: str,
                                 venue_tokens: Optional[Sequence[str]] = None,
                                 stop_subjects: Optional[Dict[int, str]] = None,
                                 share: float = DEFAULT_INSTITUTIONAL_SHARE
                                 ) -> Tuple[str, Dict]:
    """[LOCAL-620] Apply ``balance_stop_body`` across a whole delivered tour.

    Mirrors ``work_first_evidence.filter_tour_text_work_first`` (same splitting
    and opening-section exemption) but uses the BALANCE policy instead of the
    hard cap. Pure string→string. Returns (new_text, report).
    """
    report = {"stops": 0, "boilerplate_dropped": 0, "transfer_dropped": 0,
              "story_kept": 0, "changed": False}
    if not tour_text or not tour_text.strip():
        return tour_text, report

    parts = _STOP_HEADER_RE.split(tour_text)
    if len(parts) < 3:
        return tour_text, report

    out = [parts[0]]
    i = 1
    stop_index = 0
    total_boiler = 0
    total_transfer = 0
    total_story = 0
    while i < len(parts):
        header = parts[i]
        body = parts[i + 1] if i + 1 < len(parts) else ""
        stop_index += 1
        report["stops"] += 1
        subject = (stop_subjects or {}).get(stop_index, "")

        paras = re.split(r"(\n\s*\n)", body)
        new_paras: List[str] = []
        for seg in paras:
            if seg.strip() == "" or re.fullmatch(r"\n\s*\n", seg):
                new_paras.append(seg)
                continue
            if stop_index == 1 and _is_opening_paragraph(seg):
                new_paras.append(seg)  # exempt opening section (D611)
                continue
            balanced, prep = balance_stop_body(
                seg, venue_tokens=venue_tokens, work_subject=subject,
                is_opening_section=False, share=share)
            total_boiler += prep.get("boilerplate_dropped", 0)
            total_transfer += prep.get("transfer_dropped", 0)
            total_story += prep.get("story_kept", 0)
            new_paras.append(balanced)
        out.append(header)
        out.append("".join(new_paras))
        i += 2

    report["boilerplate_dropped"] = total_boiler
    report["transfer_dropped"] = total_transfer
    report["story_kept"] = total_story
    report["changed"] = (total_boiler + total_transfer) > 0
    return "".join(out), report


def ensure_tour_class_coverage(stop_bodies: Sequence[str],
                               venue_tokens: Optional[Sequence[str]] = None,
                               stop_subjects: Optional[Dict[int, str]] = None
                               ) -> Dict:
    """[LOCAL-620] Report class coverage across a tour's delivered stop bodies.

    Across the tour, every class (details / historic / social) should appear in
    at least one stop when the evidence allows, so a listener's preferences can
    be learned for all three. This computes, per stop, the class distribution of
    its signal sentences, and reports:

      per_stop_classes : [set(classes present)] per stop;
      classes_present  : the union across all stops;
      missing          : classes that appear in NO stop (coverage gap);
      covered          : True when all three classes appear somewhere.

    It MEASURES (and the caller can act); it never fabricates a class a stop's
    evidence does not contain.
    """
    per_stop: List[set] = []
    present: set = set()
    for idx, body in enumerate(stop_bodies, 1):
        subject = (stop_subjects or {}).get(idx, "")
        dist = stc.paragraph_class_distribution(
            body, venue_tokens=venue_tokens, work_subject=subject)
        counts = dist.get("_counts", {})
        classes = {c for c in (CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL)
                   if counts.get(c, 0) > 0}
        per_stop.append(classes)
        present |= classes
    all_classes = {CLASS_DETAILS, CLASS_HISTORIC, CLASS_SOCIAL}
    missing = sorted(all_classes - present)
    return {
        "per_stop_classes": [sorted(s) for s in per_stop],
        "classes_present": sorted(present),
        "missing": missing,
        "covered": not missing,
    }


def _snippet_text(snip: Dict) -> str:
    return f"{snip.get('title', '')}. {snip.get('snippet', '')}".strip()


def balance_snippets_work_first(snippets: List[Dict],
                                work_subject: str = "",
                                venue_tokens: Optional[Sequence[str]] = None,
                                share: float = DEFAULT_INSTITUTIONAL_SHARE
                                ) -> Tuple[List[Dict], Dict]:
    """[LOCAL-620] Keep work-first evidence AND real collector/museum stories.

    Supersedes ``work_first_evidence.filter_snippets_work_first`` (which kept at
    most ONE own-acquisition institutional snippet and dropped every other). Under
    the balance policy:

      • a snippet with ANY work/artist/reception/emotion sentence is KEPT;
      • a purely-institutional snippet is KEPT when it is a REAL collector/museum
        STORY (named person + motive/consequence) OR this work's own acquisition
        story — up to ~``share`` of the kept snippets (more when rich evidence is
        thin);
      • a purely-boilerplate snippet (budgets, square metres, hours, bare
        founding, mission) is DROPPED.

    Order is preserved. Returns (kept_snippets, report).
    """
    report = {
        "input": len(snippets),
        "kept_rich": 0,
        "kept_story": 0,
        "dropped_boilerplate": 0,
        "dropped_excess": 0,
        "output": 0,
    }
    # First pass: classify each snippet.
    classified = []
    n_rich = 0
    for snip in snippets:
        text = _snippet_text(snip)
        sents = wfe.split_sentences(text) or [text]
        labels = [wfe.classify_sentence(s, venue_tokens=venue_tokens,
                                        work_subject=work_subject) for s in sents]
        rich = any(l in ("work", "artist", "reception", "emotion") for l in labels)
        if rich:
            classified.append((snip, "rich"))
            n_rich += 1
            continue
        # purely institutional snippet
        is_story = any(stc.is_real_collector_story(s, work_subject=work_subject)
                       for s in sents)
        is_own = any(wfe.is_own_acquisition(s, work_subject) for s in sents)
        is_boiler = all(stc.is_boilerplate_institutional(s) for s in sents)
        if is_boiler and not (is_story or is_own):
            classified.append((snip, "boilerplate"))
        elif is_story or is_own:
            classified.append((snip, "story"))
        else:
            classified.append((snip, "transfer"))

    total = len(classified)
    thin = n_rich < _THIN_RICH_THRESHOLD
    allowed_story = _allowed_institutional(n_rich, total, share=share) if total else 0

    kept: List[Dict] = []
    story_kept = 0
    for snip, kind in classified:
        if kind == "rich":
            kept.append(snip)
            report["kept_rich"] += 1
        elif kind == "story":
            if story_kept < allowed_story:
                kept.append(snip)
                story_kept += 1
            else:
                report["dropped_excess"] += 1
        elif kind == "transfer":
            if thin and story_kept < allowed_story:
                kept.append(snip)
                story_kept += 1
            else:
                report["dropped_excess"] += 1
        else:  # boilerplate
            report["dropped_boilerplate"] += 1

    report["kept_story"] = story_kept
    report["output"] = len(kept)
    return kept, report

