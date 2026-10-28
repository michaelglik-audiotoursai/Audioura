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


# [LEAD 2026-10-11] Spelling variants that name the same thing in translated titles:
# HCMC's highlights gloss said "Spring Garden of the Center, South, and North" while
# SPARQL said "North Central South Spring Garden" (tour 674 shipped both).
_CANON = {
    "central": "center", "centre": "center", "centered": "center",
    "northern": "north", "southern": "south", "eastern": "east", "western": "west",
    "colour": "color", "colours": "color", "grey": "gray",
}


def _canon(t: str) -> str:
    t = _CANON.get(t, t)
    # plural 's' only for longer words, so short names keep their spelling
    if len(t) > 4 and t.endswith("s") and not t.endswith("ss"):
        t = _CANON.get(t[:-1], t[:-1])
    return t


def _content_tokens(text: str) -> List[str]:
    """Tokens with glue words and 1-char tokens dropped, spelling variants canonicalised."""
    return [_canon(t) for t in _tokens(text) if t not in _GLUE and len(t) >= 2]


def _expand_bilingual(tokens: Iterable[str],
                      bilingual_map: Optional[Dict[str, str]]) -> Set[str]:
    """Expand a token set with its bilingual equivalents from the D1v2 map, so a
    local word and its English counterpart canonicalise to the SAME set. Both the
    original and the mapped form are kept (an equivalent may be multi-word)."""
    out: Set[str] = set(tokens)
    if not bilingual_map:
        return out
    # keys canonicalised the same way as the tokens (e.g. "central" -> "center")
    _ckeys = {_canon(_strip_accents_lower(k)): v for k, v in bilingual_map.items()}
    for t in list(out):
        equiv = bilingual_map.get(t) or _ckeys.get(t)
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


# ── LOCAL-669C: the FINAL identity gate ───────────────────────────────────────
# LOCAL-669B placed one identity-dedup pass inside the thin-museum selection
# branch. The 2026-10-10 side-by-side (tours 670/671) proved that is not enough:
#   * The dedup DID run on 670 but collapsed NOTHING — the English SPARQL work
#     "North Central South Spring Garden" (Q109406846) and the grounded-highlights
#     stop "Vườn xuân Trung Nam Bắc" are the SAME work, but the highlights stop
#     carried NO QID, and its English GLOSS was "…Center…" (US spelling) while the
#     SPARQL English label is "…Central…" — so the order-ignored token sets differ
#     by one word and the bilingual-title bridge missed. Two Spring Gardens shipped.
#   * The exhibition / checklist museum path (and any area-stop step that appends
#     AFTER the 669B pass) never reaches that dedup at all.
#
# This gate is the SINGLE choke point, called once right before narration on
# EVERY museum path. It does three things, in order:
#   1. STAMP QIDs by EXACT label. Each venue carries a QID→{label_local,label_en,
#      aliases} map (from SPARQL). A stop whose name/local/English title EXACTLY
#      matches one of a work's labels is that work — stamp its QID. This is the
#      language-agnostic bridge the token sets could not make: the highlights stop
#      is literally named "Vườn xuân Trung Nam Bắc", which IS Q109406846's
#      label_local, so it collapses by QID regardless of the Center/Central gloss.
#   2. DEDUP by identity (dedup_by_identity: QID, else bilingual order-ignored
#      title set + the D1v2 word map). Keep the best-sourced survivor.
#   3. REFILL every slot a collapse freed, from a reserve pool of still-unused
#      VERIFIED candidates — works first, area/building stops last — never by
#      repeating a work already present by identity.
#
# Pure function, no network, no LLM. Unit-tested in test_local669c_final_gate.py.

# Fields a stop may carry a QID→labels bridge under, mirroring the SPARQL
# evidence-log shape (sparql_labels) and the parsed-highlights shape.
_LABEL_LOCAL_FIELDS = ("label_local", "title_local", "local_title")
_LABEL_EN_FIELDS = ("label_en", "title_en", "english_title")


def _norm_label(text: str) -> str:
    """Exact-match key for a label: lowercase, accents stripped, punctuation
    dropped, whitespace collapsed. Word ORDER is preserved here (this is an
    EXACT label match, not the order-ignored title-set match of norm_set)."""
    s = _strip_accents_lower(text or "")
    s = re.sub(r"[^\w\s]", " ", s)
    return " ".join(s.split())


def build_label_qid_index(
    qid_to_labels: Optional[Dict[str, Dict]] = None,
    evidence_log: Optional[Dict[str, Dict]] = None,
) -> Dict[str, str]:
    """Normalised label → QID, built from BOTH the venue's QID→labels map and the
    D1v2 evidence log's per-stop ``sparql_labels``. Every label_local, label_en
    and alias a known work carries becomes an exact-match key to that work's QID.
    Later entries never overwrite an earlier QID for the same label (first wins),
    so a stable mapping is produced regardless of iteration order."""
    index: Dict[str, str] = {}

    def _add(label: str, qid: str) -> None:
        q = _norm_qid(qid)
        key = _norm_label(label)
        if q and key and key not in index:
            index[key] = q

    for qid, labels in (qid_to_labels or {}).items():
        if not isinstance(labels, dict):
            continue
        _add(labels.get("label_local", ""), qid)
        _add(labels.get("label_en", ""), qid)
        for alias in (labels.get("aliases") or []):
            _add(alias, qid)

    for ev in (evidence_log or {}).values():
        if not isinstance(ev, dict):
            continue
        q = ev.get("qid", "")
        if not q:
            continue
        lbls = ev.get("sparql_labels") or {}
        if isinstance(lbls, dict):
            _add(lbls.get("label_local", ""), q)
            _add(lbls.get("label_en", ""), q)
            for alias in (lbls.get("aliases") or []):
                _add(alias, q)
        # The canonical title the evidence log recorded for this work is also an
        # exact bridge to its QID.
        _add(ev.get("canonical_title", ""), q)

    return index


def stamp_qids_by_label(
    pool: Sequence[Dict],
    label_qid_index: Dict[str, str],
) -> int:
    """Stamp a QID onto any candidate — IN PLACE — whose name or any carried
    title EXACTLY matches a known label in ``label_qid_index`` and that does not
    already carry a QID. Returns the number of candidates newly stamped. Never
    overwrites an existing (possibly conflicting) QID — a conflict is a real
    "distinct works" signal that dedup must still honour."""
    if not label_qid_index:
        return 0
    stamped = 0
    for cand in pool:
        if candidate_qid(cand):
            continue
        matched = ""
        for title in candidate_titles(cand):
            q = label_qid_index.get(_norm_label(title))
            if q:
                matched = q
                break
        if matched:
            cand["qid"] = matched
            stamped += 1
    return stamped


def _is_area_stop(cand: Dict) -> bool:
    """True for a LOCAL-667/668 building / collection-area fallback stop — these
    refill a tour only AFTER real works, so they sort last in the reserve."""
    return (cand.get("_stop_kind") in ("building", "collection_area")
            or bool(cand.get("_area_stop")))


# ── LOCAL-669C: bilingual stop titles (ticket point 3) ────────────────────────

def _qid_labels_lookup(
    qid_to_labels: Optional[Dict[str, Dict]] = None,
    evidence_log: Optional[Dict[str, Dict]] = None,
) -> Dict[str, Dict[str, str]]:
    """QID → {'local': …, 'en': …} from the venue map and the evidence log, so a
    stop that carries only ONE title can still be given its OTHER-language title
    for the bilingual header."""
    out: Dict[str, Dict[str, str]] = {}

    def _put(qid: str, local: str, en: str) -> None:
        q = _norm_qid(qid)
        if not q:
            return
        slot = out.setdefault(q, {"local": "", "en": ""})
        if local and not slot["local"]:
            slot["local"] = local.strip()
        if en and not slot["en"]:
            slot["en"] = en.strip()

    for qid, labels in (qid_to_labels or {}).items():
        if isinstance(labels, dict):
            _put(qid, labels.get("label_local", ""), labels.get("label_en", ""))
    for ev in (evidence_log or {}).values():
        if isinstance(ev, dict) and ev.get("qid"):
            lbls = ev.get("sparql_labels") or {}
            if isinstance(lbls, dict):
                _put(ev["qid"], lbls.get("label_local", ""), lbls.get("label_en", ""))
    return out


def _is_mostly_ascii(s: str) -> bool:
    letters = [c for c in (s or "") if c.isalpha()]
    if not letters:
        return False
    return sum(1 for c in letters if ord(c) < 128) / len(letters) >= 0.8


def bilingual_display_title(
    cand: Dict,
    qid_labels: Optional[Dict[str, Dict[str, str]]] = None,
) -> str:
    """The listener-facing header for one stop: the LOCAL title first, with the
    ENGLISH title in parentheses — "Vườn xuân Trung Nam Bắc (North Central South
    Spring Garden)". Sourced from the candidate's own local/English pair
    (highlights parse) or, failing that, the work's SPARQL labels looked up by
    QID. Never fabricates: when only one title is known, or the two are the same
    work-word-set, the single title is returned unchanged — so a stop never gets
    two different headers and a mono-lingual work is left alone.

    The result is a DISPLAY string; the candidate's ``name`` (the matching key)
    is left untouched by this function (the gate stores the result separately).
    """
    local = ""
    en = ""
    for f in _LABEL_LOCAL_FIELDS:
        v = cand.get(f)
        if isinstance(v, str) and v.strip():
            local = v.strip()
            break
    for f in _LABEL_EN_FIELDS:
        v = cand.get(f)
        if isinstance(v, str) and v.strip():
            en = v.strip()
            break
    # Fall back to the work's SPARQL labels (by QID) for the missing side.
    q = candidate_qid(cand)
    if q and qid_labels and q in qid_labels:
        local = local or qid_labels[q].get("local", "")
        en = en or qid_labels[q].get("en", "")
    name = (cand.get("name") or "").strip()
    # Decide which is the local (non-ASCII / native) title. If we only have a
    # bare name, there is nothing bilingual to show.
    if not local and not en:
        return name
    if local and not en:
        # Only a local title — if the name adds an English gloss, keep the name.
        return name or local
    if en and not local:
        return name or en
    # Both present. If they normalise to the SAME work-word-set, they are the
    # same string in two spellings — show just one (the local).
    if norm_set(local) and norm_set(local) == norm_set(en):
        return local
    # Local first, English in parens. If 'local' is actually the ASCII one and
    # 'en' the native one (mislabelled), swap so the native title leads.
    if _is_mostly_ascii(local) and not _is_mostly_ascii(en):
        local, en = en, local
    return f"{local} ({en})"


@dataclass
class GateResult:
    poi_list: List[Dict]
    collapses: List[Collapse]
    refilled: List[str]            # display titles added to replace freed slots
    stamped_qids: int
    decision_log: List[str]        # human-readable lines for the run log


def final_identity_gate(
    poi_list: Sequence[Dict],
    *,
    needed_stops: Optional[int] = None,
    bilingual_map: Optional[Dict[str, str]] = None,
    qid_to_labels: Optional[Dict[str, Dict]] = None,
    evidence_log: Optional[Dict[str, Dict]] = None,
    reserve_pool: Sequence[Dict] = (),
    set_bilingual_titles: bool = False,
) -> GateResult:
    """The single final identity gate, run once right before narration on EVERY
    museum path.

    Steps:
      1. Stamp QIDs by exact label (QID→labels map + evidence-log sparql_labels),
         so a cross-language duplicate the token sets missed collapses by QID.
      2. Collapse same-work stops by identity (dedup_by_identity), keeping the
         best-sourced survivor.
      3. Refill each freed slot from ``reserve_pool`` — VERIFIED works first, area
         stops last — skipping anything already present by identity. Never repeats.

    Args:
        poi_list: the final stop list about to go to narration.
        needed_stops: how many stops the tour should ship (the requested count,
            possibly capped earlier for an honest shortfall). When None, no refill
            is attempted — the gate only dedups.
        bilingual_map: the D1v2 per-venue word map (story_miner._BILINGUAL_MAP).
        qid_to_labels: QID → {label_local, label_en, aliases} for this venue.
        evidence_log: the D1v2 evidence log (per-stop qid + sparql_labels).
        reserve_pool: still-unused verified candidates to refill freed slots from.

    Returns a GateResult. Pure; mutates copies, never the inputs' list identity
    (individual dicts may gain a stamped 'qid', which is intended hardening).
    """
    work = [dict(p) for p in poi_list]
    decision: List[str] = []

    # 1. Stamp QIDs by exact label across the WHOLE list.
    index = build_label_qid_index(qid_to_labels, evidence_log)
    stamped = stamp_qids_by_label(work, index)
    if stamped:
        decision.append(
            f"[LOCAL-669C] final gate: stamped {stamped} QID(s) by exact label")

    # 2. Dedup by identity.
    pre = len(work)
    deduped, collapses = dedup_by_identity(work, bilingual_map)
    for c in collapses:
        decision.append(
            f"[LOCAL-669C] identity collapse ({c.reason}): kept '{c.kept_title}', "
            f"dropped {c.dropped_titles}")
    if pre != len(deduped):
        decision.append(
            f"[LOCAL-669C] final gate: {pre} → {len(deduped)} stop(s) "
            f"(one identity → one stop)")
    else:
        decision.append(
            f"[LOCAL-669C] final gate: no duplicates ({pre} stop(s))")

    # 3. Refill freed slots from the reserve pool (works first, area stops last),
    # never repeating a work already present by identity.
    refilled: List[str] = []
    if needed_stops is not None and len(deduped) < needed_stops and reserve_pool:
        present = [identity_of(c, bilingual_map) for c in deduped]
        # Stamp reserve candidates too, so a reserve work that is the same as a
        # present one (by QID) is correctly rejected rather than re-added.
        reserve = [dict(r) for r in reserve_pool]
        stamp_qids_by_label(reserve, index)
        # Works before area stops; stable within each class.
        ordered = ([r for r in reserve if not _is_area_stop(r)]
                   + [r for r in reserve if _is_area_stop(r)])
        for cand in ordered:
            if len(deduped) >= needed_stops:
                break
            cid = identity_of(cand, bilingual_map)
            if any(cid.shares_with(p) for p in present):
                continue
            deduped.append(cand)
            present.append(cid)
            title = _best_title(cand)
            refilled.append(title)
            decision.append(
                f"[LOCAL-669C] refilled freed slot with "
                f"{'area stop' if _is_area_stop(cand) else 'work'} '{title}'")

    # 4. [ticket point 3] Bilingual stop titles. Give each surviving stop a
    # ``display_title`` = "<local> (<English>)" when both titles are known (the
    # stop's own pair or the work's SPARQL labels by QID). Local leads, English
    # in parens, word order from the source. ``name`` (the matching key) is left
    # untouched. One header per work — never two.
    if set_bilingual_titles:
        _qlab = _qid_labels_lookup(qid_to_labels, evidence_log)
        _retitled = 0
        for cand in deduped:
            disp = bilingual_display_title(cand, _qlab)
            if disp and disp != (cand.get("name") or "").strip():
                cand["display_title"] = disp
                _retitled += 1
            else:
                # Keep an explicit display_title so renderers can rely on it.
                cand.setdefault("display_title", (cand.get("name") or "").strip())
        if _retitled:
            decision.append(
                f"[LOCAL-669C] bilingual titles: set {_retitled} '<local> "
                f"(<English>)' header(s)")

    return GateResult(poi_list=deduped, collapses=collapses, refilled=refilled,
                      stamped_qids=stamped, decision_log=decision)


# ── LOCAL-790: dedupe a PLACE/WALKING candidate pool by location or QID ───────
# The museum final_identity_gate above collapses by QID / bilingual title, but it
# runs ONLY on the museum path. A walking/place tour's pool is deduped by TITLE
# only (stop_title_dedup), and a title compare cannot see that "Ngoc Hoang Pagoda"
# (the Vietnamese name) and "Jade Emperor Pagoda" (its English name) are the SAME
# place — they share no tokens — so both shipped in the HCMC field run. Two places
# are the same when they carry the same Wikidata QID, OR when their geocoded points
# are within ~60 m of each other (one building cannot be two stops). This is the
# place-tour analogue of the museum QID/bilingual collapse, keyed on geography.

def _coords_of(cand: Dict) -> Optional[Tuple[float, float]]:
    """Best-effort (lat, lng) for a candidate: explicit lat/lng, else a
    "lat,lng" coordinates string. None when no usable point is present."""
    if not isinstance(cand, dict):
        return None
    lat = cand.get("latitude")
    lng = cand.get("longitude")
    try:
        if lat is not None and lng is not None:
            return (float(lat), float(lng))
    except (TypeError, ValueError):
        pass
    coord = cand.get("coordinates") or cand.get("coords")
    if isinstance(coord, str) and "," in coord:
        try:
            a, b = coord.split(",", 1)
            return (float(a.strip()), float(b.strip()))
        except (TypeError, ValueError):
            return None
    if isinstance(coord, (list, tuple)) and len(coord) == 2:
        try:
            return (float(coord[0]), float(coord[1]))
        except (TypeError, ValueError):
            return None
    return None


def _haversine_m(a: Tuple[float, float], b: Tuple[float, float]) -> float:
    """Great-circle distance in METRES between two (lat, lng) points."""
    import math
    lat1, lon1 = a
    lat2, lon2 = b
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = (math.sin(dp / 2) ** 2
         + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2)
    return 2 * r * math.asin(min(1.0, math.sqrt(h)))


def dedupe_by_location_or_qid(
    poi_list: Sequence[Dict],
    radius_m: float = 60.0,
) -> Tuple[List[Dict], List[Tuple[str, str]]]:
    """[LOCAL-790] Collapse a place/walking candidate pool by identity:

      (a) same Wikidata QID (on either side) → same place, OR
      (b) geocoded points within ``radius_m`` metres of each other → same place
          (a single building cannot be two stops), OR
      (c) same normalised TITLE (the stop_title_dedup fallback, so a plain repeat
          still collapses even without coordinates or a QID).

    Keeps the FIRST occurrence of each place in order. Returns
    ``(deduped_list, dropped)`` where ``dropped`` is ``[(dup_name, kept_name), …]``
    in pool order. Pure — no network, no mutation of the inputs. A candidate with
    neither a QID nor coordinates falls back to title identity, so this never
    merges two genuinely different places that happen to lack coordinates.
    """
    kept: List[Dict] = []
    kept_meta: List[Dict] = []  # parallel: {'qid','coords','norm'}
    dropped: List[Tuple[str, str]] = []

    for cand in poi_list or []:
        if not isinstance(cand, dict):
            kept.append(cand)
            kept_meta.append({"qid": "", "coords": None, "norm": ""})
            continue
        qid = _norm_qid(cand.get("qid", "") or cand.get("wikidata_qid", ""))
        coords = _coords_of(cand)
        name = (cand.get("name") or cand.get("title") or "").strip()
        norm = " ".join(sorted(_tokens(name))) if name else ""

        match_idx = None
        for i, meta in enumerate(kept_meta):
            # (a) QID — strongest, language-agnostic.
            if qid and meta["qid"] and qid == meta["qid"]:
                match_idx = i
                break
            # (b) proximity — one building is one stop.
            if coords and meta["coords"]:
                if _haversine_m(coords, meta["coords"]) <= radius_m:
                    match_idx = i
                    break
            # (c) title fallback (only when neither side had a QID/coords match).
            if norm and meta["norm"] and norm == meta["norm"]:
                match_idx = i
                break

        if match_idx is not None:
            kept_name = (kept[match_idx].get("name")
                         or kept[match_idx].get("title") or "").strip()
            dropped.append((name, kept_name))
            # Enrich the keeper with a QID/coords the duplicate carried but it did
            # not (so the surviving stop lands on the map / keeps its identity).
            _km = kept_meta[match_idx]
            if qid and not _km["qid"]:
                _km["qid"] = qid
                kept[match_idx].setdefault("qid", qid)
            if coords and not _km["coords"]:
                _km["coords"] = coords
            continue

        kept.append(cand)
        kept_meta.append({"qid": qid, "coords": coords, "norm": norm})

    return kept, dropped
