"""identity_dedup.py — LOCAL-669B.

LOCAL-669's live HCMC run put ONE National Treasure into the tour THREE times:
  * "North Central South Spring Garden"       (R4, from the English Wikidata label)
  * "Central South and North Spring Garden"   (R4, from the English altLabel)
  * "Vườn xuân Trung Nam Bắc"                  (grounded highlights, the Vietnamese)
They are the same work (Wikidata Q109406846). LOCAL-667's collapse guard is
TOKEN-based: it folds English word-order permutations into one, but it cannot
bridge the Vietnamese title to the English one (they share no tokens), so two of
the three survived into the delivered tour.

This module collapses candidates by IDENTITY, not by token overlap:

  (a) WIKIDATA QID — when two candidates carry the same QID (on either side),
      they are the same work, full stop. This is the strongest signal and it is
      language-agnostic.

  (b) BILINGUAL TITLE MATCH — a candidate may carry BOTH a local-language title
      and an English title (the grounded highlights call is asked for both, and
      SPARQL works carry label_local + label_en). Two candidates are the same
      work when ANY of one candidate's titles matches ANY of the other's under an
      ORDER-IGNORED normalisation:
          lowercase → strip accents → drop punctuation → drop glue words
          (the/of/and + common EN/FR/DE/ES/IT articles) → SORTED token set.
      Word order is ignored (a sorted set), so "North Central South Spring Garden"
      and "Central South and North Spring Garden" collapse. Because each candidate
      contributes BOTH its titles, the Vietnamese title of one side matches the
      Vietnamese title the other side also carries, OR the English title of one
      matches the English title of the other — the cross-language bridge is the
      pairing (local↔English) each candidate already carries, topped up by the

  (c) D1v2 BILINGUAL WORD MAP — the per-venue map built from SPARQL label pairs
      (story_miner.build_bilingual_map_from_sparql). Each title's tokens are
      expanded through it, so a lone local title can still match a lone English
      title when the venue's own SPARQL labels pair their words.

When a group collapses to one, we keep the BEST-SOURCED title (a stop that was
verified against the museum's own domain or two independent sources outranks a
bare R4 guess; a QID-bearing SPARQL/canonical title outranks a free-text one).

Pure functions, no network, no LLM. Unit-tested in
test_local669b_identity_dedup.py. The bilingual map is injected (a dict), so the
module is testable offline and does not import story_miner's global state.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

# Glue words carrying no distinguishing identity. The ticket names "the/of/and";
# we keep a small multilingual set so a French/German/Spanish/Italian title is
# normalised the same way (consistent with candidate_collapse_guard._GLUE).
_GLUE = {
    "the", "of", "and", "a", "an", "to", "in", "on", "with", "for", "at", "by",
    "de", "del", "della", "dei", "la", "le", "les", "el", "il", "lo", "los", "las",
    "und", "der", "die", "das", "von", "den", "dem", "ein", "eine",
}

# A QID is a Wikidata entity id like Q109406846.
_QID_RE = re.compile(r"^[Qq]\d+$")


def _strip_accents_lower(text: str) -> str:
    nfkd = unicodedata.normalize("NFKD", str(text or "").lower())
    return "".join(c for c in nfkd if not unicodedata.combining(c))


def _tokens(text: str) -> List[str]:
    """lowercase → strip accents → drop punctuation → word tokens."""
    s = _strip_accents_lower(text)
    s = re.sub(r"[^\w\s]", " ", s)
    return s.split()


def _content_tokens(text: str) -> List[str]:
    """Tokens with glue words and 1-char tokens dropped."""
    return [t for t in _tokens(text) if t not in _GLUE and len(t) >= 2]


def _expand_bilingual(tokens: Iterable[str],
                      bilingual_map: Optional[Dict[str, str]]) -> Set[str]:
    """Expand a token set with its bilingual equivalents from the D1v2 map, so a
    local word and its English counterpart canonicalise to the SAME set. Both the
    original and the mapped form are kept (an equivalent may be multi-word)."""
    out: Set[str] = set(tokens)
    if not bilingual_map:
        return out
    for t in list(out):
        equiv = bilingual_map.get(t)
        if equiv:
            for w in _content_tokens(equiv):
                out.add(w)
    return out


def norm_set(title: str, bilingual_map: Optional[Dict[str, str]] = None) -> str:
    """The ORDER-IGNORED identity string for a single title: sorted set of its
    content tokens (glue dropped, accents stripped, punctuation dropped), each
    token bilingual-expanded through the D1v2 map. Returns "" for an empty/
    glue-only title (which then never matches anything by title)."""
    content = _content_tokens(title)
    if not content:
        return ""
    expanded = _expand_bilingual(content, bilingual_map)
    return " ".join(sorted(expanded))


def _norm_qid(qid: str) -> str:
    q = (qid or "").strip()
    return q.upper() if _QID_RE.match(q) else ""


# ── identity of a candidate ───────────────────────────────────────────────────

# The field names a candidate may carry a title under. Both the grounded
# highlights parse (name / title_local / title_en) and the SPARQL/D1v2 world
# (label_local / label_en) are covered, plus the generic 'name'.
_TITLE_FIELDS = ("name", "title", "title_local", "title_en",
                 "label_local", "label_en", "local_title", "english_title")
_QID_FIELDS = ("qid", "QID", "wikidata_qid", "work_qid")


def candidate_titles(cand: Dict) -> List[str]:
    """Every non-empty title a candidate carries (local + English + name)."""
    out: List[str] = []
    seen: Set[str] = set()
    for f in _TITLE_FIELDS:
        v = cand.get(f)
        if isinstance(v, str) and v.strip():
            key = _strip_accents_lower(v.strip())
            if key not in seen:
                seen.add(key)
                out.append(v.strip())
    return out


def candidate_qid(cand: Dict) -> str:
    for f in _QID_FIELDS:
        q = _norm_qid(str(cand.get(f) or ""))
        if q:
            return q
    return ""


@dataclass
class _Identity:
    qid: str
    title_sets: Set[str] = field(default_factory=set)  # norm_set per title

    def shares_with(self, other: "_Identity") -> bool:
        if self.qid and other.qid:
            return self.qid == other.qid
        # No conflicting QIDs → fall back to a shared normalised title set. A
        # candidate that carries a QID can still title-match one that does not
        # (the QID side simply had no QID conflict to settle it).
        if self.qid and other.qid and self.qid != other.qid:
            return False
        inter = self.title_sets & other.title_sets
        return any(s for s in inter)  # non-empty normalised set in common


def identity_of(cand: Dict, bilingual_map: Optional[Dict[str, str]] = None
                ) -> _Identity:
    qid = candidate_qid(cand)
    sets = {norm_set(t, bilingual_map) for t in candidate_titles(cand)}
    sets.discard("")
    return _Identity(qid=qid, title_sets=sets)


# ── best-sourced title selection ──────────────────────────────────────────────

def _source_rank(cand: Dict) -> Tuple[int, int, int, int]:
    """Rank a candidate so the BEST-SOURCED survivor is chosen on a collapse.
    Higher tuple sorts first. Components, in priority order:
      1. carries a Wikidata QID (a canonical identity)           → strongest
      2. own-domain OR >=1 highlight/thin source                 → verified
      3. number of distinct cited source domains
      4. verified flag truthy
    """
    qid = 1 if candidate_qid(cand) else 0
    srcs = (cand.get("highlight_sources") or cand.get("thin_sources") or [])
    own = 1 if any((s.get("detail") == "own_domain" or s.get("origin") == "__own__")
                   for s in srcs if isinstance(s, dict)) else 0
    n_src = len({s.get("origin") for s in srcs if isinstance(s, dict) and s.get("origin")})
    verified = 1 if cand.get("verified", False) else 0
    return (qid, own + (1 if n_src else 0), n_src, verified)


def _best_title(cand: Dict) -> str:
    """The display title to keep for a candidate: prefer an explicit English
    title when present (listeners read English), else the primary name/title."""
    for f in ("name", "title", "title_en", "label_en", "english_title",
              "title_local", "label_local"):
        v = cand.get(f)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return ""


# ── the dedup pass ────────────────────────────────────────────────────────────

@dataclass
class Collapse:
    kept_title: str
    dropped_titles: List[str]
    reason: str   # 'qid' | 'bilingual_title'


def dedup_by_identity(
    pool: Sequence[Dict],
    bilingual_map: Optional[Dict[str, str]] = None,
) -> Tuple[List[Dict], List[Collapse]]:
    """Collapse candidates that are the SAME work by identity (QID, or a shared
    order-ignored bilingual-normalised title set).

    Order-stable: each surviving group is represented at the position of its
    FIRST member, but the KEPT candidate is the best-sourced member of the group
    (its fields win); the first member's position is retained so tour ordering is
    not reshuffled. Returns (deduped_pool, collapses).

    Never merges two candidates whose QIDs are present and DIFFERENT — a QID
    conflict is a hard "distinct works" signal (so "Thanh niên Thành đồng" with
    its own QID is never folded into the Spring Garden work).
    """
    cands = [dict(p) for p in pool]
    identities = [identity_of(c, bilingual_map) for c in cands]

    # Union-find over candidates that share an identity.
    parent = list(range(len(cands)))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    def union(i: int, j: int) -> None:
        ri, rj = find(i), find(j)
        if ri != rj:
            parent[max(ri, rj)] = min(ri, rj)

    for i in range(len(cands)):
        for j in range(i + 1, len(cands)):
            a, b = identities[i], identities[j]
            # Hard distinct: both have QIDs and they differ.
            if a.qid and b.qid and a.qid != b.qid:
                continue
            same = False
            reason = ""
            if a.qid and b.qid and a.qid == b.qid:
                same, reason = True, "qid"
            else:
                shared = {s for s in (a.title_sets & b.title_sets) if s}
                if shared:
                    same, reason = True, "bilingual_title"
            if same:
                union(i, j)

    # Group by root, preserving first-seen order of roots.
    groups: Dict[int, List[int]] = {}
    order: List[int] = []
    for idx in range(len(cands)):
        r = find(idx)
        if r not in groups:
            groups[r] = []
            order.append(r)
        groups[r].append(idx)

    out: List[Dict] = []
    collapses: List[Collapse] = []
    for r in order:
        members = groups[r]
        if len(members) == 1:
            out.append(cands[members[0]])
            continue
        # Choose the best-sourced member to KEEP; retain first position.
        best = max(members, key=lambda i: (_source_rank(cands[i]), -i))
        kept = dict(cands[best])
        # Carry a QID onto the survivor if any member had one (identity hardening
        # for any later pass), without overwriting an existing one.
        if not candidate_qid(kept):
            for i in members:
                q = candidate_qid(cands[i])
                if q:
                    kept["qid"] = q
                    break
        dropped_titles = [_best_title(cands[i]) for i in members if i != best]
        # QID reason wins the label when any pair in the group matched on QID.
        reason = "bilingual_title"
        qids = {candidate_qid(cands[i]) for i in members if candidate_qid(cands[i])}
        if len(qids) == 1 and qids != {""} and sum(
                1 for i in members if candidate_qid(cands[i])) >= 2:
            reason = "qid"
        collapses.append(Collapse(kept_title=_best_title(kept),
                                   dropped_titles=dropped_titles, reason=reason))
        out.append(kept)
    return out, collapses
