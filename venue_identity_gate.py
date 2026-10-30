"""venue_identity_gate.py — LOCAL-828 / LOCAL-828B (precision-first rework).

A VENUE-IDENTITY gate for injected research passages on a MUSEUM tour.

THE BUG (GCloud_Storied wave 7, cheap arm ON): a Rijksmuseum tour opened Stop 1
with a paragraph about **Museum Catharijneconvent, Utrecht** — a DIFFERENT museum
in a DIFFERENT city. Serper research for the venue/opening section returned
another museum's page, and nothing checked the passage was actually about the
REQUESTED venue.

WHY 828 (A) WAS BOUNCED (LEAD, 2026-10-30). The first cut over-dropped the
venue's OWN material:
  * the Rijksmuseum's own ``rijksmuseum.nl/en/stories/...`` page and the
    artsandculture "the-night-watch-rijksmuseum" story were dropped;
  * Met passages "…print is part of the Metropolitan Museum", "The Harvesters has
    been at The Metropolitan Museum…" were dropped — the venue's OWN works, named
    under the venue's full name, because the bound identity carried no alias and
    the foreign-museum detector returned ragged fragments ("with the others
    displayed in museums", "print is part of the Metropolitan Museum");
  * Wikipedia pages ABOUT THE WORKS (Washington Crossing the Delaware, The
    Harvesters) were dropped by a CITY rule that fired on any "in <City>" phrase —
    an art-work painted in Düsseldorf, a crossing at Trenton — which would gut the
    history on every museum tour.

THE 828B PRINCIPLE: PRECISION FIRST. Only ever drop a passage whose SUBJECT is
ANOTHER venue/institution. A work that merely mentions where it was made, depicts
or now hangs is NEVER a reason to drop. Concretely, a passage is dropped only
when ONE of these precise conditions holds and the passage does not name THIS
venue:

  1. SUBJECT — the passage is ABOUT a concretely, fully-named OTHER institution
     (a proper venue name + an institution head word, or a curated famous name),
     whose identity is not this venue. Ragged fragments, bare head words
     ("the museum", "museums"), and works-that-mention-a-museum do NOT qualify.
     The curated shared-name separate institutions (Louvre Abu Dhabi, Louvre-Lens,
     the Met Cloisters) are dropped; same-institution sub-units (Lower/Upper
     Belvedere) and this venue's own name/aliases are KEPT.

  2. DOMAIN — the source URL is the OFFICIAL domain of a KNOWN OTHER venue
     (resolved via a curated famous-venue domain map, or the official domain the
     passage's named other-venue carries). NEVER for wikipedia / wikidata /
     artsandculture / britannica / a Google redirect / news / or THIS venue's own
     domain (and its subdomains/paths). A Google ``/goto?url=`` redirect is an
     UNKNOWN host, not a foreign one.

  3. CITY — only as a property of an OTHER venue already named as the subject
     (e.g. "The Catharijneconvent in Utrecht houses…" — Utrecht is where that
     OTHER venue sits). There is NO standalone city rule: a city that is where a
     work was made, depicts or happened is never, on its own, a drop.

Every drop is logged with the mandated line:

    [LOCAL-828] other-venue passage dropped <venue> <url>

HONESTY / SAFETY. The gate only ever REMOVES a passage whose subject is a
different venue. It never invents, rewrites, or reorders. When a passage names
THIS venue, names no competing venue as its subject, or cannot be judged, it is
KEPT (a false drop costs a real fact). The module is pure — no network, no LLM,
no DB — so every rule is deterministic and unit-testable; the venue identity is
handed in by the caller (built from the resolved VenueEntity + request/preflight
city, enriched with a curated famous-venue alias/domain table).
"""
from __future__ import annotations

import contextvars
import json
import os
import re
import threading
import unicodedata
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Set, Tuple
from urllib.parse import urlparse, parse_qs

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
# Abu Dhabi row fires on a Louvre tour, the Met Cloisters row on a Met tour).
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
# KEPT. Matched as leading/trailing qualifiers around the venue's own token(s).
_SAME_INSTITUTION_PART_WORDS = {
    "lower", "upper", "old", "new", "east", "west", "north", "south", "main",
    "orangery", "annex", "annexe", "wing", "pavilion", "palace", "garden",
    "gardens", "stables", "depot",
}

# Curated famous venues: their canonical display name, the ALIASES a passage may
# use to name them (for the own-venue keep AND the other-venue subject match), the
# OFFICIAL domain(s), the home city, and the distinctive tokens that identify the
# venue even when the bound identity is thin (the live resolver may hand us only a
# bare request name with no aliases/domain — e.g. "The Met Fifth Avenue" with
# domain='-'). Fact-only, seeded from the two bounce logs + the ticket; add only a
# well-documented venue, never a guess.
_FAMOUS_VENUES: List[Dict] = [
    {"canonical": "The Metropolitan Museum of Art",
     "tokens": {"metropolitan"},
     "aliases": ["The Metropolitan Museum of Art", "Metropolitan Museum of Art",
                 "The Met", "The Met Fifth Avenue", "Met Fifth Avenue",
                 "Metropolitan Museum"],
     "domains": ["metmuseum.org"], "city": "new york"},
    {"canonical": "Rijksmuseum",
     "tokens": {"rijksmuseum"},
     "aliases": ["Rijksmuseum", "the Rijksmuseum", "Rijks"],
     "domains": ["rijksmuseum.nl"], "city": "amsterdam"},
    {"canonical": "Musee d'Orsay",
     "tokens": {"orsay"},
     "aliases": ["Musee d'Orsay", "Musée d'Orsay", "Orsay Museum",
                 "the Orsay", "Orsay"],
     "domains": ["musee-orsay.fr"], "city": "paris"},
    {"canonical": "Louvre",
     "tokens": {"louvre"},
     "aliases": ["Louvre", "the Louvre", "Musee du Louvre", "Musée du Louvre"],
     "domains": ["louvre.fr"], "city": "paris"},
    {"canonical": "Museum Catharijneconvent",
     "tokens": {"catharijneconvent"},
     "aliases": ["Museum Catharijneconvent", "Catharijneconvent"],
     "domains": ["catharijneconvent.nl"], "city": "utrecht"},
    {"canonical": "Art Institute of Chicago",
     "tokens": {"chicago"},
     "aliases": ["Art Institute of Chicago", "the Art Institute of Chicago"],
     "domains": ["artic.edu"], "city": "chicago"},
    {"canonical": "Philadelphia Museum of Art",
     "tokens": {"philadelphia"},
     "aliases": ["Philadelphia Museum of Art"],
     "domains": ["philamuseum.org"], "city": "philadelphia"},
    {"canonical": "Albertina",
     "tokens": {"albertina"},
     "aliases": ["Albertina", "Albertina Museum"],
     "domains": ["albertina.at"], "city": "vienna"},
    {"canonical": "Belvedere",
     "tokens": {"belvedere"},
     "aliases": ["Belvedere", "the Belvedere"],
     "domains": ["belvedere.at"], "city": "vienna"},
]

# Reference / aggregator / redirect hosts that carry NO single-venue identity.
# A URL on one of these is NEVER "another venue's domain".
_REFERENCE_HOSTS = (
    "wikipedia.org", "wikidata.org", "wikimedia.org", "commons.wikimedia.org",
    "britannica.com", "artsandculture.google.com", "google.com", "google.",
    "bing.com", "duckduckgo.com", "tripadvisor.", "wikivoyage.org",
    "dbpedia.org", "getty.edu", "jstor.org", "khanacademy.org", "smarthistory.org",
)


def _is_reference_host(host: str) -> bool:
    h = (host or "").lower()
    return any(ref in h for ref in _REFERENCE_HOSTS)


# ─── venue identity ───────────────────────────────────────────────────────────

@dataclass
class VenueIdentity:
    """The resolved identity of THIS tour's venue, used to judge a passage.

    All fields optional so the gate degrades gracefully: with no identity it keeps
    everything (never a blind drop). Built by ``build_identity`` from the resolved
    VenueEntity (qid / official_url) plus the request/preflight city, enriched from
    the curated famous-venue table so a thin resolver result still carries the
    venue's real aliases + official domain.
    """
    name: str = ""
    qid: str = ""
    official_domain: str = ""
    city: str = ""
    aliases: Tuple[str, ...] = field(default_factory=tuple)
    # Every official domain for THIS venue (curated + resolved), used so a passage
    # on any of them is kept.
    domains: Tuple[str, ...] = field(default_factory=tuple)

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

    @property
    def all_domains(self) -> Tuple[str, ...]:
        out = []
        for d in (self.official_domain, *(self.domains or ())):
            d = (d or "").lower()
            if d and d not in out:
                out.append(d)
        return tuple(out)


def domain_of(url: str) -> str:
    """Bare registrable-ish host of a URL, lower-case, 'www.' stripped. '' on junk.

    A Google ``/goto?url=`` (or ``/url?q=``) redirect is treated as an UNKNOWN host
    (returns ''), never as google.com — the ticket says a Google redirect URL is
    unknown, not foreign. (The encoded target is opaque, so we do not resolve it.)
    """
    if not url:
        return ""
    u = url if "://" in url else "https://" + url
    try:
        parsed = urlparse(u)
    except Exception:
        return ""
    host = (parsed.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    # Google redirect: opaque target → unknown host, not google.com.
    if host.endswith("google.com") or host.endswith("google."):
        path = (parsed.path or "")
        if path.startswith("/goto") or path.startswith("/url") or path.startswith("/aclk"):
            # If a plain target is present we could use it, but /goto encodes it
            # opaquely — treat the whole thing as unknown.
            q = parse_qs(parsed.query or "")
            tgt = (q.get("url") or q.get("q") or [""])[0]
            if tgt and "://" in tgt:
                return domain_of(tgt)
            return ""
    return host


def _lookup_famous(name: str = "", tokens: Optional[Set[str]] = None,
                   domain: str = "") -> Optional[Dict]:
    """Find the curated famous-venue row this venue IS, by token/domain/alias.
    Used to enrich a thin identity. Returns the row or None."""
    toks = set(tokens or set())
    dom = (domain or "").lower()
    nfold = _fold(name or "")
    for row in _FAMOUS_VENUES:
        if row["tokens"] & toks:
            return row
        if dom and any(dom == d or dom.endswith("." + d) for d in row["domains"]):
            return row
        for a in row["aliases"]:
            if _fold(a) and _fold(a) in nfold:
                return row
    return None


def build_identity(venue_name: str = "", qid: str = "", official_url: str = "",
                   city: str = "", aliases: Optional[Sequence[str]] = None,
                   venue_entity=None, preflight: Optional[dict] = None) -> VenueIdentity:
    """Assemble a VenueIdentity from the resolved venue + request/preflight city.

    ``venue_entity`` (a venue_resolver.VenueEntity, or any object/dict carrying
    ``qid`` / ``name`` / ``official_url``) and ``preflight`` (the venue preflight
    dict) are optional convenience inputs; explicit keyword args win over them.

    LOCAL-828B: the identity is ENRICHED from the curated famous-venue table when
    the venue is recognised (by name token / official domain / alias). The live
    resolver can hand us a bare request name ("The Met Fifth Avenue") with no
    aliases and no official domain; without enrichment the gate would not know
    "the Metropolitan Museum of Art" is the same venue and would over-drop the
    venue's own works. Nothing here hits the network.
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
    for k in ("aliases", "also_known_as", "alt_names"):
        v = _get(preflight, k)
        if isinstance(v, (list, tuple)):
            al += [x for x in v if x]
        elif isinstance(v, str) and v:
            al.append(v)
        ev = _get(venue_entity, k)
        if isinstance(ev, (list, tuple)):
            al += [x for x in ev if x]
        elif isinstance(ev, str) and ev:
            al.append(ev)

    official_domain = domain_of(url)
    domains: List[str] = [official_domain] if official_domain else []

    # Enrich from the curated famous-venue table.
    famous = _lookup_famous(
        name=" ".join([name] + al), tokens=venue_content_tokens(name),
        domain=official_domain)
    if famous:
        al = list(al) + [a for a in famous["aliases"] if a not in al]
        for d in famous["domains"]:
            if d not in domains:
                domains.append(d)
        if not official_domain and famous["domains"]:
            official_domain = famous["domains"][0]
        if not city and famous.get("city"):
            city = famous["city"]

    return VenueIdentity(
        name=name or "", qid=qid or "", official_domain=official_domain,
        city=city or "", aliases=tuple(dict.fromkeys(a for a in al if a)),
        domains=tuple(dict.fromkeys(domains)))


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
    row, else None."""
    c = _fold(cand_name)
    if not c:
        return None
    ctok = venue_content_tokens(cand_name)
    parent_tokens = _identity_parent_tokens(identity)
    for row in _DISTINCT_SHARED_NAME_VENUES:
        rtok = set(row["tokens"])
        rparent = set(row.get("parent") or ())
        if rparent and (rparent & parent_tokens) and not (rtok <= parent_tokens):
            if rtok and rtok <= ctok:
                return row
    return None


def _is_same_institution_part(cand_name: str, identity: VenueIdentity) -> bool:
    """True when ``cand_name`` is a SUB-UNIT of THIS institution (Lower/Upper
    Belvedere for a Belvedere tour). Such a passage is KEPT."""
    ctok = venue_content_tokens(cand_name)
    if not ctok or not identity.all_tokens:
        return False
    shared = ctok & identity.all_tokens
    if not shared:
        return False
    if _distinct_shared_name_hit(cand_name, identity):
        return False
    extra = ctok - identity.all_tokens
    folded_parts = {_fold(w) for w in _SAME_INSTITUTION_PART_WORDS}
    return all(e in folded_parts for e in extra)


def same_venue_name(cand_name: str, identity: VenueIdentity) -> bool:
    """True when a named venue ``cand_name`` IS this venue (or a sub-unit of it)."""
    if not cand_name or not identity.all_tokens:
        return False
    if _distinct_shared_name_hit(cand_name, identity):
        return False
    ctok = venue_content_tokens(cand_name)
    if ctok & identity.all_tokens:
        return True
    return False


def _mentions_identity(text: str, identity: "VenueIdentity") -> bool:
    """True when ``text`` names THIS venue by its name OR any alias (reusing the
    LOCAL-668 distinctive-token test, which requires ALL of a name's distinctive
    tokens to be present)."""
    for nm in ([identity.name] + list(identity.aliases or ())):
        if nm and mentions_this_venue(text, nm):
            return True
    return False


# ─── named-other-venue detection (precision-first) ────────────────────────────
#
# The 828(A) over-drops came from LOCAL-668's ``names_foreign_museum`` returning
# ragged fragments ("with the others displayed in museums", "print is part of the
# Metropolitan Museum") that were then treated as other-venue names. 828B accepts
# a detected foreign name ONLY when it is a CLEAN, properly-cased venue name: it
# begins with a Capitalised word (a proper noun, not a mid-sentence verb/particle),
# contains no generic lead-in verbs/prepositions, and is not merely a bare
# institution head word. This is what distinguishes "the subject IS another venue"
# from "a work that mentions a museum".

# Words that, when they LEAD a detected name, mark it as a ragged mid-sentence
# fragment rather than a venue's proper name.
_FRAGMENT_LEAD_WORDS = {
    "the", "a", "an", "of", "in", "on", "at", "to", "for", "with", "by", "from",
    "and", "or", "is", "are", "was", "were", "been", "being", "be", "has", "have",
    "had", "part", "displayed", "held", "housed", "located", "shown", "exhibited",
    "now", "other", "others", "surviving", "this", "that", "these", "those",
    "its", "his", "her", "their", "which", "where", "while", "when",
}

# Words that must NEVER appear ANYWHERE inside a detected venue name: they mark the
# detector having swept a verb/clause fragment into the "name" (the live
# "Kennedy's donation changed the museum" false drop). A real venue name is a noun
# phrase — it has none of these verbs/connectives in the middle.
_FRAGMENT_INTERIOR_WORDS = {
    "is", "are", "was", "were", "been", "being", "be", "has", "have", "had",
    "displayed", "held", "housed", "located", "shown", "exhibited", "changed",
    "donation", "donated", "bequeathed", "acquired", "gave", "gifted", "added",
    "became", "opened", "moved", "part", "now", "which", "where", "while", "when",
    "that", "this", "these", "those", "its", "his", "her", "their", "surviving",
    "collection", "holdings",
}

# Bare institution head words — a detected "name" that is ONLY these is not a venue.
_BARE_HEAD_WORDS = {
    "museum", "museums", "gallery", "galleries", "collection", "collections",
    "art museum", "art gallery", "the museum", "the gallery", "metropolitan museum",
    "art institute", "the art institute",
}

# Geographic / institution anchor tokens that make a "<Proper> museum/gallery"
# a real venue name rather than a person-possessive fragment. A detected name that
# ends in a bare head word is accepted only when SOME word before the head is a
# plausible place/institution proper noun (not merely a person's possessive).
_INSTITUTION_HEAD_TOKENS = {
    "museum", "museums", "gallery", "galleries", "institute", "collection",
    "foundation", "pinacoteca", "kunstmuseum", "rijksmuseum", "academy",
}


def _looks_like_proper_venue_name(name: str) -> bool:
    """True when ``name`` reads as a venue's OWN proper name (precision guard).

    Rejects the ragged fragments the LOCAL-668 detector can return: a name that
    leads with a lowercase/verb word, carries a possessive ("Kennedy's …"), has a
    verb/clause word anywhere inside ("… donation changed the museum"), or is a
    bare head word. A real venue name is a short, clean noun phrase led by a
    Capitalised proper noun ("Louvre Abu Dhabi", "Art Institute of Chicago",
    "Albertina Museum", "the Met Cloisters")."""
    raw = (name or "").strip()
    if not raw:
        return False
    words = raw.split()
    if not words:
        return False
    # A venue name is short; a long run is a swept-in clause.
    if len(words) > 6:
        return False
    # No possessive — a venue is not named "X's …".
    if "'s" in _fold(raw) or "\u2019s" in raw.lower():
        return False
    first = words[0]
    if first.lower() in _FRAGMENT_LEAD_WORDS:
        return False
    _LONE = {"louvre", "rijksmuseum", "hermitage", "uffizi", "prado", "guggenheim",
             "tate", "getty", "smithsonian", "pompidou", "orsay", "moma",
             "albertina", "belvedere"}
    if first[0].islower() and first.lower() not in _LONE:
        return False
    if _fold(raw) in _BARE_HEAD_WORDS:
        return False
    # No verb/clause word anywhere inside — those mark a fragment, not a name.
    fwords = {_fold(w).strip(".,;:'\u2019") for w in words}
    if fwords & _FRAGMENT_INTERIOR_WORDS:
        return False
    toks = venue_content_tokens(raw)
    if not toks:
        # No distinctive token at all (e.g. "Art Museum") — cannot be judged a
        # specific OTHER venue.
        return False
    # If the name ends in a bare institution head word, require a distinctive
    # proper token OTHER than the head itself (a place/institution name), so a
    # bare "<person> museum" swept fragment is rejected. The curated/famous path
    # handles the real named venues; this is the open-ended detector's backstop.
    last = _fold(words[-1]).strip(".,;:")
    if last in _INSTITUTION_HEAD_TOKENS:
        non_head = {t for t in toks if t not in _INSTITUTION_HEAD_TOKENS}
        if not non_head:
            return False
    return True


def _scan_famous_other_venue(text: str, identity: VenueIdentity) -> Optional[str]:
    """If the passage names a CURATED famous OTHER venue (by a full alias, not a
    bare token), return that venue's canonical name, else None. The venue must not
    be THIS one and must not share this venue's token (a shared token is handled by
    the curated distinct-institution list, not here)."""
    folded = _fold(text)
    if not folded:
        return None
    my_tokens = identity.all_tokens | _identity_parent_tokens(identity)
    for row in _FAMOUS_VENUES:
        if row["tokens"] & my_tokens:
            continue  # this is (or shares a token with) OUR venue
        for alias in row["aliases"]:
            af = _fold(alias)
            # Require a MULTI-WORD or distinctive alias so a bare token like "met"
            # cannot match; the alias must appear as a whole phrase.
            if len(af.split()) < 2 and af not in row["tokens"]:
                continue
            if re.search(r"\b" + re.escape(af) + r"\b", folded):
                return row["canonical"]
    return None


_CURATED_NAME_RES = None


def _curated_name_patterns():
    global _CURATED_NAME_RES
    if _CURATED_NAME_RES is None:
        pats = []
        for row in _DISTINCT_SHARED_NAME_VENUES:
            words = row["name"].split()
            if not words:
                continue
            rx = r"\b" + r"[\s\-]+".join(re.escape(w) for w in words) + r"\b"
            pats.append((re.compile(rx, re.IGNORECASE), row))
        _CURATED_NAME_RES = pats
    return _CURATED_NAME_RES


def _scan_curated_other_venue(text: str, identity: VenueIdentity) -> Optional[str]:
    """If the passage names a curated SHARED-NAME separate institution of this
    venue (Louvre Abu Dhabi / Louvre-Lens / the Met Cloisters), return its name."""
    folded = _fold(text)
    parent_tokens = _identity_parent_tokens(identity)
    for rx, row in _curated_name_patterns():
        if rx.search(folded):
            rtok = set(row["tokens"])
            rparent = set(row.get("parent") or ())
            if rparent and (rparent & parent_tokens) and not (rtok <= parent_tokens):
                return row["name"]
    return None


def passage_names_other_venue(text: str, identity: VenueIdentity) -> Optional[str]:
    """Return the name of ANOTHER venue the passage is ABOUT, or None.

    PRECISION-FIRST (828B). Sources of a "name", in order:
      1. a curated SHARED-NAME separate institution (Louvre Abu Dhabi etc.);
      2. a curated FAMOUS other venue named by a full alias (the Met on an Orsay
         tour, the Philadelphia Museum of Art on a Met tour);
      3. the LOCAL-668 foreign-institution detector — but ONLY when it returns a
         CLEAN, proper venue name (``_looks_like_proper_venue_name``), so ragged
         fragments and works-that-mention-a-museum are never treated as a venue.

    A passage that names THIS venue (or a same-institution sub-unit) is NOT other —
    naming us keeps it even if it also mentions another venue for comparison.
    """
    if not text:
        return None

    # 1. Curated shared-name separate institutions first (they share our token).
    hit = _scan_curated_other_venue(text, identity)
    if hit:
        return hit

    # If the passage clearly names THIS venue, keep it.
    if _mentions_identity(text, identity):
        return None

    # 2. Curated famous OTHER venue named by a full alias.
    famous = _scan_famous_other_venue(text, identity)
    if famous:
        return famous

    # 3. The LOCAL-668 foreign-institution detector, gated by the proper-name test.
    foreign = names_foreign_museum(text, identity.name)
    if foreign:
        if _is_same_institution_part(foreign, identity):
            return None
        if same_venue_name(foreign, identity):
            return None
        ftok = venue_content_tokens(foreign)
        if ftok and (ftok & identity.all_tokens):
            return None
        # PRECISION GUARD: accept only a clean, properly-named venue — never a
        # ragged fragment ("print is part of the Metropolitan Museum") or a
        # bare head word.
        if not _looks_like_proper_venue_name(foreign):
            return None
        # If the fragment names a famous venue alias that is actually US (e.g.
        # "the Metropolitan Museum of Art" on a Met tour whose identity was
        # enriched), the earlier _mentions_identity would have kept it; a famous
        # row whose tokens are ours is never returned here.
        myrow = _lookup_famous(tokens=identity.all_tokens | _identity_parent_tokens(identity))
        if myrow:
            frow = _lookup_famous(name=foreign, tokens=ftok)
            if frow is myrow:
                return None
        return foreign
    return None


# ─── domain is another venue's ────────────────────────────────────────────────

def url_is_other_venue_domain(url: str, identity: VenueIdentity,
                              passage_text: str = "") -> bool:
    """True when the passage's SOURCE URL is the OFFICIAL domain of a KNOWN OTHER
    venue (828B precision).

    * THIS venue's own domain(s) (and subdomains) → never.
    * Reference / aggregator / Google-redirect hosts → never.
    * A host that itself carries this venue's distinctive token → never.
    * A host that is a curated famous OTHER venue's official domain → OTHER.
    * Otherwise → NOT other (an unknown host is unknown, not foreign). A generic
      blog about the venue, or a Google ``/goto`` redirect, is NOT dropped on
      domain grounds.
    """
    host = domain_of(url)
    if not host:
        return False
    for od in identity.all_domains:
        if host == od or host.endswith("." + od) or od.endswith("." + host):
            return False  # this venue's own site
    if _is_reference_host(host):
        return False
    host_tokens = {t for t in re.split(r"[.\-]", host) if len(t) >= 3}
    if identity.all_tokens & host_tokens:
        return False
    my_tokens = identity.all_tokens | _identity_parent_tokens(identity)
    for row in _FAMOUS_VENUES:
        if row["tokens"] & my_tokens:
            continue  # our own row
        for d in row["domains"]:
            if host == d or host.endswith("." + d):
                return True  # a known OTHER venue's official domain
    return False


# ─── combined decision + logging ──────────────────────────────────────────────

def passage_is_other_venue(text: str, identity: VenueIdentity,
                           url: str = "") -> Tuple[bool, str, str]:
    """Decide whether an injected passage is ABOUT ANOTHER venue (828B).

    Returns ``(is_other, reason, detail)`` where reason is one of
    'subject' / 'domain' / '' and detail is the other venue name / host / '' for
    logging. Order: subject → domain. There is NO standalone 'city' reason — a city
    is only ever a property of an other-venue already named as the subject. A
    passage that names THIS venue is never other.
    """
    if not identity or not (identity.all_tokens or identity.all_domains):
        return (False, "", "")  # no identity to judge against — keep
    # A curated shared-name separate institution (Louvre Abu Dhabi on a Louvre
    # tour, the Met Cloisters on a Met tour) is OTHER even though it carries our
    # token — decided before the "names this venue" keep.
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


# ─── optional capture of every evaluated passage (fixtures) ───────────────────
#
# LOCAL-828B: set LOCAL828_CAPTURE=<path> to append one JSON line per passage the
# gate evaluates ({venue, text, url, is_other, reason, detail}). Used ONCE to turn
# a real live run into the test fixtures; a strict no-op when the env var is unset.
_capture_lock = threading.Lock()


def _capture(identity: VenueIdentity, text: str, url: str,
             is_other: bool, reason: str, detail: str) -> None:
    path = os.environ.get("LOCAL828_CAPTURE")
    if not path:
        return
    try:
        rec = {
            "venue": getattr(identity, "name", "") or "",
            "text": text or "", "url": url or "",
            "is_other": bool(is_other), "reason": reason or "",
            "detail": detail or "",
        }
        with _capture_lock:
            with open(path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _decide(text: str, identity: VenueIdentity, url: str = "") -> Tuple[bool, str, str]:
    """passage_is_other_venue + optional fixture capture."""
    is_other, reason, detail = passage_is_other_venue(text, identity, url=url)
    _capture(identity, text, url, is_other, reason, detail)
    return is_other, reason, detail


def filter_research_passages(
    passages: Sequence,
    identity: VenueIdentity,
    log=None,
) -> Tuple[List, List[Dict]]:
    """Drop every injected passage that is ABOUT ANOTHER venue; keep the rest.

    ``passages`` may be dicts ({'text'|'snippet'|'passage', 'url'}) or strings.
    Returns ``(kept, dropped_log)``. ``log`` is called once per drop with the
    mandated line. Order preserved. Pure. Empty identity keeps everything.
    """
    kept: List = []
    dropped: List[Dict] = []
    if identity is None:
        return (list(passages or []), [])
    for p in passages or []:
        text = _passage_text(p)
        url = _passage_url(p)
        is_other, reason, detail = _decide(text, identity, url=url)
        if is_other:
            other_name = detail if reason == "subject" else (detail or identity.name)
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
    about-museum opening section). Drops each sentence whose SUBJECT is ANOTHER
    venue, re-joins the rest.

    Returns ``(scrubbed_text, dropped_sentences)``. Never empties the text: if
    EVERY sentence would be dropped the original is returned unchanged (the caller
    can inspect ``dropped_sentences`` and regenerate). Pure. Logs each drop.

    828B: a sentence is judged by its SUBJECT only, so a sentence about a work that
    mentions another city (a painting made in Arles) is KEPT; only a sentence whose
    subject is a different, concretely-named venue is dropped.
    """
    if not text or not text.strip() or identity is None:
        return (text, [])
    sentences = [s for s in re.split(r"(?<=[.!?])\s+", text.strip()) if s.strip()]
    if not sentences:
        return (text, [])
    kept, dropped = [], []
    for s in sentences:
        is_other, reason, detail = _decide(s, identity, url=source_url)
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
    (via the cheap_arm contextvar)."""
    ident = _tour_identity.get()
    if ident is None:
        return False
    try:
        import cheap_arm as _ca
        cat = _ca.tour_category()
    except Exception:
        cat = ""
    return (not cat) or cat == "museum"


def scrub_research_result(result: Dict, identity: Optional[VenueIdentity] = None,
                          log=None) -> Dict:
    """[LOCAL-828] Drop other-venue content from a research result in the shape
    gemini_with_sources / serper_research return
    ({text, sources, supports, queries, error}).

    Each per-sentence ``support`` whose SUBJECT is another venue (keyed on its own
    source URL when present) is dropped; the top-level ``text`` is then recomposed
    from the surviving supports (falling back to a sentence-level scrub of the
    original text when there are no supports). Sources that no surviving support
    cites are pruned. Pure; a missing identity or non-museum context returns the
    result unchanged. Never raises.
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
                is_other, reason, detail = _decide(stext, ident, url=url0)
                if is_other:
                    if log:
                        other = detail if reason == "subject" else (detail or ident.name)
                        log(other_venue_drop_log_line(other, url0))
                    continue
                kept_sup.append(sup)
            if len(kept_sup) != len(supports):
                result = dict(result)
                result["supports"] = kept_sup
                result["text"] = " ".join(
                    (s.get("text") or "").strip() for s in kept_sup).strip()
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
