"""venue_identity_gate.py — LOCAL-828.

A VENUE-IDENTITY gate for every injected research passage on a MUSEUM tour.

THE BUG (GCloud_Storied wave 7, gen 00016-62s, cheap arm ON): a Rijksmuseum tour
(request 294) opened Stop 1 with a paragraph about **Museum Catharijneconvent,
Utrecht** — a DIFFERENT museum in a DIFFERENT city. Serper research for the
venue/opening section returned another museum's page, and nothing checked that the
passage was actually about the REQUESTED venue. LOCAL-802's relevance gate checks
stop/place/theme tokens, but "museum" and "Dutch art" are shared, so another
museum's passage sails through. LOCAL-668's foreign-museum snippet filter
(venue_anchored_research) catches a passage that NAMES a foreign institution, but
it is only wired for the area/collection stop snippets — NOT the opening/
about-museum section, the per-stop story leads, or the serper_research output —
and it keeps anything that shares a name token with the venue (so "Louvre Abu
Dhabi" slips past a Louvre tour).

WHAT THIS ADDS (per the ticket). For a museum tour, an injected research passage
is DROPPED when ANY of these holds:

  1. SUBJECT is ANOTHER venue — the passage names a museum/gallery/venue as its
     subject whose identity is NOT this venue. Identity is decided by the venue's
     QID / official domain / aliases, with a curated list of venues that SHARE a
     name yet are SEPARATE institutions (Louvre Abu Dhabi, Louvre-Lens and the Met
     Cloisters are distinct from the Louvre / the Met; Lower and Upper Belvedere
     are the SAME institution as the Belvedere and are kept).

  2. DOMAIN is ANOTHER venue's — the passage's source URL is on a domain that is a
     known OTHER venue's official domain (or simply not this venue's domain while
     naming another venue).

  3. CITY CONTRADICTS — the passage states a city that is not this venue's city
     (and names no reconciling signal for this venue).

Every drop is logged with the mandated line:

    [LOCAL-828] other-venue passage dropped <venue> <url>

HONESTY / SAFETY. The gate only ever REMOVES a passage that is about a DIFFERENT
venue. It never invents, rewrites, or reorders. When a passage names THIS venue,
names no competing venue, or cannot be judged, it is KEPT (a false drop costs a
real fact). The whole module is pure — no network, no LLM, no DB — so every rule
is deterministic and unit-testable; the venue identity is handed in by the caller
(built from the already-resolved VenueEntity + the request/preflight city).
"""
from __future__ import annotations

import contextvars
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse

# Reuse LOCAL-668's institution-name detection and venue token folding so the two
# gates agree on what "names a museum" means.
from venue_anchored_research import (
    _fold,
    venue_content_tokens,
    mentions_this_venue,
    names_foreign_museum,
)

__all__ = [
    "VenueIdentity",
    "build_identity",
    "domain_of",
    "same_venue_name",
    "passage_names_other_venue",
    "url_is_other_venue_domain",
    "passage_city_contradicts",
    "passage_is_other_venue",
    "other_venue_drop_log_line",
    "filter_research_passages",
    "filter_text_sentences",
    "set_tour_venue_identity",
    "reset_tour_venue_identity",
    "tour_venue_identity",
    "gate_active_for_museum",
    "scrub_research_result",
]


# ─── curated venue-identity knowledge (offline, fact-only) ────────────────────
#
# Venues that SHARE a distinctive name token with another venue yet are SEPARATE
# institutions. A passage about one of these must be dropped from the OTHER's
# tour even though a bare token overlap ("louvre", "met") would otherwise mark it
# as "this venue". Each row names the SEPARATE institution and the set of PARENT
# tokens that identify the venue it must be distinguished FROM — the row only
# fires when this tour's venue carries one of those parent tokens (so the Louvre
# Abu Dhabi row fires on a Louvre tour, the Met Cloisters row on a Met tour). Seeded
# from the ticket; add only well-documented separate institutions, never a guess.
_DISTINCT_SHARED_NAME_VENUES: List[Dict] = [
    {"name": "louvre abu dhabi", "tokens": {"abu", "dhabi"},
     "parent": {"louvre"}, "city": "abu dhabi"},
    {"name": "louvre lens", "tokens": {"lens"},
     "parent": {"louvre"}, "city": "lens"},
    {"name": "the met cloisters", "tokens": {"cloisters"},
     "parent": {"met", "metropolitan"}, "city": "new york"},
    {"name": "met cloisters", "tokens": {"cloisters"},
     "parent": {"met", "metropolitan"}, "city": "new york"},
]

# Name fragments that mark a SUB-UNIT of the SAME institution (a wing / floor /
# part), NOT a separate venue. "Lower Belvedere" and "Upper Belvedere" are the
# SAME institution as the Belvedere; a passage about them on a Belvedere tour is
# KEPT. These are matched as leading/trailing qualifiers around the venue's own
# distinctive token(s).
_SAME_INSTITUTION_PART_WORDS = {
    "lower", "upper", "old", "new", "east", "west", "north", "south", "main",
    "orangery", "annex", "annexe", "wing", "pavilion", "palace", "garden",
    "gardens", "stables", "depot",
}


# ─── venue identity ───────────────────────────────────────────────────────────

@dataclass
class VenueIdentity:
    """The resolved identity of THIS tour's venue, used to judge a passage.

    All fields optional so the gate degrades gracefully: with no identity it keeps
    everything (never a blind drop). Built by ``build_identity`` from the resolved
    VenueEntity (qid / official_url) plus the request/preflight city.
    """
    name: str = ""
    qid: str = ""
    official_domain: str = ""
    city: str = ""
    aliases: Tuple[str, ...] = field(default_factory=tuple)

    # Derived, folded lookups (filled in __post_init__).
    _name_tokens: Set[str] = field(default_factory=set, repr=False)
    _alias_tokens: Set[str] = field(default_factory=set, repr=False)
    _city_fold: str = field(default="", repr=False)

    def __post_init__(self):
        self._name_tokens = venue_content_tokens(self.name)
        at: Set[str] = set()
        for a in self.aliases or ():
            at |= venue_content_tokens(a)
        self._alias_tokens = at
        self._city_fold = _fold(self.city or "").strip()

    @property
    def all_tokens(self) -> Set[str]:
        """Every distinctive token that identifies THIS venue (name + aliases)."""
        return self._name_tokens | self._alias_tokens


def domain_of(url: str) -> str:
    """Bare registrable-ish host of a URL, lower-case, 'www.' stripped. '' on junk."""
    if not url:
        return ""
    u = url if "://" in url else "https://" + url
    try:
        host = (urlparse(u).netloc or "").lower()
    except Exception:
        return ""
    if host.startswith("www."):
        host = host[4:]
    return host


def build_identity(venue_name: str = "", qid: str = "", official_url: str = "",
                   city: str = "", aliases: Optional[Sequence[str]] = None,
                   venue_entity=None, preflight: Optional[dict] = None) -> VenueIdentity:
    """Assemble a VenueIdentity from the resolved venue + request/preflight city.

    ``venue_entity`` (a venue_resolver.VenueEntity, or any object/dict carrying
    ``qid`` / ``name`` / ``official_url``) and ``preflight`` (the venue preflight
    dict, which may carry a resolved city/official site) are optional convenience
    inputs; explicit keyword args win over them. Nothing here hits the network.
    """
    def _get(obj, attr):
        if obj is None:
            return ""
        if isinstance(obj, dict):
            return obj.get(attr) or ""
        return getattr(obj, attr, "") or ""

    name = venue_name or _get(venue_entity, "name")
    qid = qid or _get(venue_entity, "qid")
    url = official_url or _get(venue_entity, "official_url") or _get(preflight, "official_site") \
        or _get(preflight, "official_url") or _get(preflight, "site")
    city = city or _get(preflight, "city") or _get(preflight, "locality")
    al = list(aliases or [])
    # A preflight may carry alternate names/aliases.
    for k in ("aliases", "also_known_as", "alt_names"):
        v = _get(preflight, k)
        if isinstance(v, (list, tuple)):
            al += [x for x in v if x]
        elif isinstance(v, str) and v:
            al.append(v)
    return VenueIdentity(
        name=name or "", qid=qid or "", official_domain=domain_of(url),
        city=city or "", aliases=tuple(dict.fromkeys(a for a in al if a)))


# ─── name-identity comparison ─────────────────────────────────────────────────

def _identity_parent_tokens(identity: "VenueIdentity") -> Set[str]:
    """All folded word tokens of this venue's name + aliases (len>=2), used to
    match a curated row's ``parent`` set. Unlike ``venue_content_tokens`` this does
    NOT drop short/generic tokens, so a venue requested as "The Met Fifth Avenue"
    still exposes the parent token 'met'."""
    out: Set[str] = set()
    for src in (identity.name, *(identity.aliases or ())):
        for w in re.findall(r"[a-z\u00e0-\u00ff']+", _fold(src or "")):
            if len(w) >= 2:
                out.add(w)
    return out


def _distinct_shared_name_hit(cand_name: str, identity: VenueIdentity) -> Optional[dict]:
    """If ``cand_name`` is a CURATED separate institution of THIS venue (Louvre Abu
    Dhabi on a Louvre tour, the Met Cloisters on a Met tour), return its curated
    row, else None. The row fires only when THIS venue carries the row's PARENT
    token(s) and the candidate carries the row's distinguishing token(s)."""
    c = _fold(cand_name)
    if not c:
        return None
    ctok = venue_content_tokens(cand_name)
    parent_tokens = _identity_parent_tokens(identity)
    for row in _DISTINCT_SHARED_NAME_VENUES:
        rtok = set(row["tokens"])
        rparent = set(row.get("parent") or ())
        # This tour's venue must BE the parent (carry a parent token) and NOT itself
        # be the separate institution.
        if rparent and (rparent & parent_tokens) and not (rtok <= parent_tokens):
            if rtok and rtok <= ctok:
                return row
    return None


def _is_same_institution_part(cand_name: str, identity: VenueIdentity) -> bool:
    """True when ``cand_name`` is a SUB-UNIT of THIS institution (same venue): it
    carries this venue's distinctive token(s) plus only same-institution part words
    (Lower/Upper Belvedere for a Belvedere tour). Such a passage is KEPT."""
    ctok = venue_content_tokens(cand_name)
    if not ctok or not identity.all_tokens:
        return False
    shared = ctok & identity.all_tokens
    if not shared:
        return False
    # The curated distinct-venue list wins over this: Louvre Abu Dhabi carries
    # 'louvre' but is not a part of the Louvre.
    if _distinct_shared_name_hit(cand_name, identity):
        return False
    extra = ctok - identity.all_tokens
    # Every EXTRA distinctive token must be a same-institution part word, else it
    # is a genuinely different-named venue that merely happens to share a token.
    folded_parts = {_fold(w) for w in _SAME_INSTITUTION_PART_WORDS}
    return all(e in folded_parts for e in extra)


def same_venue_name(cand_name: str, identity: VenueIdentity) -> bool:
    """True when a named venue ``cand_name`` IS this venue (or a sub-unit of it).

    Shares a distinctive token AND is not a curated separate institution. A pure
    name test — the QID/domain checks are applied by the passage-level functions.
    """
    if not cand_name or not identity.all_tokens:
        return False
    if _distinct_shared_name_hit(cand_name, identity):
        return False
    ctok = venue_content_tokens(cand_name)
    if ctok & identity.all_tokens:
        return True
    return False


# ─── 1. subject is another venue ──────────────────────────────────────────────

def passage_names_other_venue(text: str, identity: VenueIdentity) -> Optional[str]:
    """Return the name of ANOTHER venue the passage is about, or None.

    Two sources of a "name":
      * the curated separate institutions that share a token with this venue
        (Louvre Abu Dhabi / Louvre-Lens / the Met Cloisters) — these are NOT caught
        by the LOCAL-668 foreign test because they share a token with this venue;
      * any museum/gallery/institution LOCAL-668's ``names_foreign_museum``
        detects whose identity is not this venue.

    A passage that names THIS venue (or a same-institution sub-unit) is NOT other —
    even if it also mentions another venue for comparison, naming us keeps it.
    """
    if not text:
        return None

    # Curated shared-name separate institutions (the Louvre Abu Dhabi / Louvre-Lens
    # / Met Cloisters cases) are checked FIRST: they share this venue's token, so
    # ``mentions_this_venue`` would otherwise (wrongly) treat them as "about us".
    hit = _scan_curated_other_venue(text, identity)
    if hit:
        return hit

    # If the passage clearly names THIS venue (by its name OR any alias), keep it.
    if _mentions_identity(text, identity):
        return None

    # The LOCAL-668 foreign-institution detector for everything else. It is run
    # against this venue's NAME and every ALIAS, so "the Metropolitan Museum of
    # Art" is recognised as THIS venue on a "The Met Fifth Avenue" tour (the alias
    # carries the distinctive tokens the bare request name lacks).
    foreign = names_foreign_museum(text, identity.name)
    if foreign:
        # Not foreign if it is a same-institution sub-unit, IS this venue under an
        # alias, or shares a distinctive token with this venue's name/aliases.
        if _is_same_institution_part(foreign, identity):
            return None
        if same_venue_name(foreign, identity):
            return None
        ftok = venue_content_tokens(foreign)
        if ftok and (ftok & identity.all_tokens):
            return None
        return foreign
    return None


def _mentions_identity(text: str, identity: "VenueIdentity") -> bool:
    """True when ``text`` names THIS venue by its name OR any alias (reusing the
    LOCAL-668 distinctive-token test, which requires ALL of a name's distinctive
    tokens to be present)."""
    for nm in ([identity.name] + list(identity.aliases or ())):
        if nm and mentions_this_venue(text, nm):
            return True
    return False


_CURATED_NAME_RES = None


def _curated_name_patterns():
    """Compiled regexes matching each curated distinct venue's full name."""
    global _CURATED_NAME_RES
    if _CURATED_NAME_RES is None:
        pats = []
        for row in _DISTINCT_SHARED_NAME_VENUES:
            # Build a loose regex from the folded name words, allowing hyphen/space
            # between tokens ("louvre-lens" / "louvre lens").
            words = row["name"].split()
            if not words:
                continue
            rx = r"\b" + r"[\s\-]+".join(re.escape(w) for w in words) + r"\b"
            pats.append((re.compile(rx, re.IGNORECASE), row))
        _CURATED_NAME_RES = pats
    return _CURATED_NAME_RES


def _scan_curated_other_venue(text: str, identity: VenueIdentity) -> Optional[str]:
    """If the passage names a curated separate institution of this venue (and is
    not this venue), return that institution's display name."""
    folded = _fold(text)
    parent_tokens = _identity_parent_tokens(identity)
    for rx, row in _curated_name_patterns():
        if rx.search(folded):
            rtok = set(row["tokens"])
            rparent = set(row.get("parent") or ())
            # Fires only when THIS tour's venue is the parent and the named venue
            # is the SEPARATE institution (carries the distinguishing tokens).
            if rparent and (rparent & parent_tokens) and not (rtok <= parent_tokens):
                return row["name"]
    return None


# ─── 2. domain is another venue's ─────────────────────────────────────────────

def url_is_other_venue_domain(url: str, identity: VenueIdentity,
                              passage_text: str = "") -> bool:
    """True when the passage's SOURCE URL is on a DIFFERENT venue's domain.

    * If this venue's official domain is known and the URL is on it → not other.
    * If the URL host shares no token with this venue AND the passage names another
      venue → other (the page is that other venue's site).
    * Wikipedia / Wikidata / reference domains are never "another venue's domain".
    """
    host = domain_of(url)
    if not host:
        return False
    od = (identity.official_domain or "").lower()
    if od and (host == od or host.endswith("." + od) or od.endswith("." + host)):
        return False  # this venue's own site
    # Reference/aggregator domains carry no single-venue identity.
    _REFERENCE_HOSTS = (
        "wikipedia.org", "wikidata.org", "wikimedia.org", "britannica.com",
        "google.com", "tripadvisor.", "wikivoyage.org", "dbpedia.org",
    )
    if any(h in host for h in _REFERENCE_HOSTS):
        return False
    # A host that itself carries this venue's distinctive token is this venue's
    # (e.g. "rijksmuseum.nl" for the Rijksmuseum).
    host_tokens = {t for t in re.split(r"[.\-]", host) if len(t) >= 3}
    if identity.all_tokens & host_tokens:
        return False
    # Otherwise: the URL is on some other site. Only call it "another venue's
    # domain" when the passage itself names another venue (so a generic blog about
    # the venue is not dropped merely for being off-domain).
    if passage_text and passage_names_other_venue(passage_text, identity):
        return True
    return False


# ─── 3. city contradiction ────────────────────────────────────────────────────

_CITY_IN_RE = re.compile(r"(?i)\bin\s+([A-Z][\wÀ-ÿ'’.-]+(?:\s+[A-Z][\wÀ-ÿ'’.-]+){0,2})")


def passage_city_contradicts(text: str, identity: VenueIdentity) -> bool:
    """True when the passage states a city that is NOT this venue's city.

    Conservative: only fires when (a) this venue's city is known, (b) the passage
    names a DIFFERENT city via an explicit "in <City>" subject cue, and (c) the
    passage does NOT also name this venue's own city or this venue by name. This is
    the Catharijneconvent-in-Utrecht signal (Rijksmuseum's city is Amsterdam)."""
    if not identity._city_fold or not text:
        return False
    folded = _fold(text)
    own_city = identity._city_fold.split(",")[0].strip()
    if not own_city:
        return False
    if own_city in folded:
        return False  # names our city — not a contradiction
    if _mentions_identity(text, identity):
        return False  # names us (by name or alias) — keep
    # Look for an explicit "in <OtherCity>" subject cue on the ORIGINAL (cased) text
    # so we only pick up proper-noun cities.
    for m in _CITY_IN_RE.finditer(text or ""):
        cand = _fold(m.group(1)).strip()
        if not cand:
            continue
        cand_head = cand.split()[0]
        if cand_head == own_city or cand_head in own_city or own_city in cand:
            return False
    # A different city is named and ours is absent → contradiction only if the
    # passage actually names some city via the cue.
    return bool(_CITY_IN_RE.search(text or ""))


# ─── combined decision + logging ──────────────────────────────────────────────

def passage_is_other_venue(text: str, identity: VenueIdentity,
                           url: str = "") -> Tuple[bool, str, str]:
    """Decide whether an injected passage is about ANOTHER venue.

    Returns ``(is_other, reason, detail)`` where reason is one of
    'subject' / 'domain' / 'city' / '' and detail is the other venue name / host /
    '' for logging. Order: subject → domain → city. A passage that names THIS venue
    is never other.
    """
    if not identity or not (identity.all_tokens or identity.official_domain
                            or identity._city_fold):
        return (False, "", "")  # no identity to judge against — keep
    # A curated separate institution that shares our name token (Louvre Abu Dhabi
    # on a Louvre tour, the Met Cloisters on a Met tour) is OTHER even though it
    # carries our token — so this is decided before the "names this venue" keep.
    curated = _scan_curated_other_venue(text or "", identity)
    if curated:
        return (True, "subject", curated)
    # Naming this venue (by name or alias) keeps the passage outright.
    if _mentions_identity(text or "", identity):
        return (False, "", "")

    other = passage_names_other_venue(text or "", identity)
    if other:
        return (True, "subject", other)

    if url and url_is_other_venue_domain(url, identity, passage_text=text or ""):
        return (True, "domain", domain_of(url))

    if passage_city_contradicts(text or "", identity):
        return (True, "city", "")

    return (False, "", "")


def other_venue_drop_log_line(venue: str, url: str) -> str:
    """The exact mandated log line for a dropped other-venue passage:
    ``[LOCAL-828] other-venue passage dropped <venue> <url>``."""
    return (f"[LOCAL-828] other-venue passage dropped "
            f"{(venue or '?').strip()} {(url or '').strip()}").rstrip()


def _passage_text(p) -> str:
    if isinstance(p, dict):
        return (p.get("text") or p.get("snippet") or p.get("passage")
                or p.get("title") or "")
    return str(p or "")


def _passage_url(p) -> str:
    if isinstance(p, dict):
        return p.get("url") or p.get("link") or p.get("source") or ""
    return ""


def filter_research_passages(
    passages: Sequence,
    identity: VenueIdentity,
    log=None,
) -> Tuple[List, List[Dict]]:
    """Drop every injected passage that is about ANOTHER venue; keep the rest.

    ``passages`` may be dicts ({'text'|'snippet'|'passage', 'url'}) or strings.
    Returns ``(kept, dropped_log)`` where dropped_log is a list of
    {venue, url, reason}. ``log`` is called once per drop with the mandated line.
    Order preserved. Pure (no network). A missing/empty identity keeps everything.
    """
    kept: List = []
    dropped: List[Dict] = []
    if identity is None:
        return (list(passages or []), [])
    for p in passages or []:
        text = _passage_text(p)
        url = _passage_url(p)
        is_other, reason, detail = passage_is_other_venue(text, identity, url=url)
        if is_other:
            other_name = detail if reason in ("subject",) else (detail or identity.name)
            line = other_venue_drop_log_line(other_name, url)
            dropped.append({"venue": other_name, "url": url, "reason": reason})
            if log:
                log(line)
            continue
        kept.append(p)
    return kept, dropped


def filter_text_sentences(
    text: str,
    identity: VenueIdentity,
    source_url: str = "",
    log=None,
) -> Tuple[str, List[str]]:
    """Sentence-level gate for an already-composed block of research prose (the
    about-museum opening section, a stop narration lifted from another venue's
    page). Drops each sentence that is about ANOTHER venue, re-joins the rest.

    Returns ``(scrubbed_text, dropped_sentences)``. Never empties the text: if
    EVERY sentence would be dropped the original is returned unchanged (the caller
    can inspect ``dropped_sentences`` and regenerate). Pure. Logs each drop.
    """
    if not text or not text.strip() or identity is None:
        return (text, [])
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return (text, [])
    kept, dropped = [], []
    for s in sentences:
        is_other, reason, detail = passage_is_other_venue(s, identity, url=source_url)
        if is_other:
            dropped.append(s)
            if log:
                other_name = detail if reason == "subject" else (detail or identity.name)
                log(other_venue_drop_log_line(other_name, source_url))
        else:
            kept.append(s)
    if not kept:
        return (text, dropped)
    if not dropped:
        return (text, [])
    return (" ".join(kept).strip(), dropped)


# ─── per-tour venue-identity context (concurrency-safe) ───────────────────────
#
# The gate runs inside story_leads.research_with_sources, which fans out across
# ThreadPoolExecutor workers in the per-stop loop. The tour's venue identity is
# held in a ContextVar set ONCE on the tour thread when the venue resolves — the
# same pattern cheap_arm uses for the tour category, and propagated into pool
# workers by cost_accumulator.install_executor_context_propagation. Default None:
# with no identity bound (non-museum tours, or an unresolved venue) the gate is a
# no-op and research is byte-for-byte unchanged.
_tour_identity: "contextvars.ContextVar[Optional[VenueIdentity]]" = \
    contextvars.ContextVar("venue_identity_gate::identity", default=None)


def set_tour_venue_identity(identity: Optional[VenueIdentity]) -> "contextvars.Token":
    """Bind the current tour's venue identity for this context. Returns the Token
    so the caller may reset it; the tour path sets it once at generation start."""
    return _tour_identity.set(identity)


def reset_tour_venue_identity(token: "contextvars.Token") -> None:
    try:
        _tour_identity.reset(token)
    except (ValueError, LookupError):  # pragma: no cover
        pass


def tour_venue_identity() -> Optional[VenueIdentity]:
    """The current tour's bound venue identity, or None when none is set."""
    return _tour_identity.get()


def gate_active_for_museum() -> bool:
    """True when a venue identity is bound AND this tour's category is 'museum'
    (via the cheap_arm contextvar). The gate applies to museum tours only — a
    non-museum tour never scopes its research to a single venue identity."""
    ident = _tour_identity.get()
    if ident is None:
        return False
    try:
        import cheap_arm as _ca
        cat = _ca.tour_category()
    except Exception:
        cat = ""
    # When the category is unknown ('') but an identity was deliberately bound,
    # honour it (a museum live run / harness binds it on purpose).
    return (not cat) or cat == "museum"


def scrub_research_result(result: Dict, identity: Optional[VenueIdentity] = None,
                          log=None) -> Dict:
    """[LOCAL-828] Drop other-venue content from a research result in the shape
    gemini_with_sources / serper_research return
    ({text, sources, supports, queries, error}).

    Each per-sentence ``support`` whose text is about another venue (keyed on its
    own source URL when present) is dropped; the top-level ``text`` is then
    recomposed from the surviving supports (falling back to a sentence-level scrub
    of the original text when there are no supports). Sources that no surviving
    support cites are pruned. Pure; a missing identity or non-museum context
    returns the result unchanged. Never raises.
    """
    if not isinstance(result, dict):
        return result
    ident = identity if identity is not None else tour_venue_identity()
    if ident is None:
        return result
    try:
        supports = result.get("supports") or []
        if supports:
            kept_sup: List[Dict] = []
            for sup in supports:
                stext = (sup or {}).get("text") or ""
                surls = [s.get("url", "") for s in (sup or {}).get("sources") or []]
                url0 = surls[0] if surls else ""
                is_other, reason, detail = passage_is_other_venue(stext, ident, url=url0)
                if is_other:
                    if log:
                        other = detail if reason == "subject" else (detail or ident.name)
                        log(other_venue_drop_log_line(other, url0))
                    continue
                kept_sup.append(sup)
            if len(kept_sup) != len(supports):
                result = dict(result)
                result["supports"] = kept_sup
                # Recompose the top-level text from surviving supports.
                result["text"] = " ".join(
                    (s.get("text") or "").strip() for s in kept_sup).strip()
                # Prune sources no surviving support cites.
                kept_urls = {s.get("url", "")
                             for sup in kept_sup for s in (sup.get("sources") or [])}
                if kept_urls:
                    result["sources"] = [
                        s for s in (result.get("sources") or [])
                        if s.get("url", "") in kept_urls]
            return result
        # No per-sentence supports — scrub the flat text, keyed on the first source.
        text = result.get("text") or ""
        src0 = ""
        srcs = result.get("sources") or []
        if srcs and isinstance(srcs[0], dict):
            src0 = srcs[0].get("url", "")
        scrubbed, dropped = filter_text_sentences(text, ident, source_url=src0, log=log)
        if dropped:
            result = dict(result)
            result["text"] = scrubbed
        return result
    except Exception:
        return result
