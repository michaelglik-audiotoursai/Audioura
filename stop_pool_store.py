"""
Stop Pool Store (LOCAL-590 / LOCAL-495) — reuse the stops already written.
==========================================================================
The whole-tour cache (`tour_cache_layer1`) keys on (venue, type, stop BUCKET)
and reuses a tour ONLY when a later request falls in the same bucket; a bigger
request is a full regeneration and no stop is ever reused across sizes. Michael,
2026-09-23: *"if somebody asks to generate a tour of the same venue that we
already had generated, we should use the material we had."*

This module is the **stop POOL** that makes that reuse real. A stop is stored
once per (venue identity, tour_type, cache version) as an **audio-independent
unit** — title, narration body, the structured fields the renderer needs
(address, coordinates, type/specialty, examples, operational details), its
sources and story elements, and a per-stop `generated_at`. A later tour of the
same place is then a SELECTION from this pool plus only the genuinely new stops.

Why audio-independent (D581.1 / the design's hard part 1.1 & 1.3):
  * **Directions and Orientation are properties of a SEQUENCE, not of a stop.**
    They change every time the stop's neighbours change, so they are NOT stored
    with the pooled stop; they are recomputed per selection by the caller (the
    single-building and outdoor assembly paths in generate_tour_text).
  * **Audio is a rendering of the stop's TEXT in one voice/engine.** It is keyed
    per rendered stop text (polly_tts_service), not per tour, so the pool stores
    only the text; audio reuse is decided downstream by matching voice+engine
    against the identical narration (LOCAL-590 step 5).
  * **Freshness is per stop, not per tour.** Each row carries `generated_at`, so
    a single stale stop can age out without discarding the whole venue's pool.

Table discipline (declared, additive, never DELETE):
  * `stop_pool` is created IF NOT EXISTS and only ever INSERTed/UPSERTed into.
    Nothing in this module issues DELETE or DROP. A superseded stop is UPDATEd
    in place (same venue+type+title) with the newer narration and a refreshed
    `generated_at`; its identity row is never removed. Retiring a generation is
    done the same way the whole-tour cache does it (LOCAL-588): bump
    TOUR_CACHE_VERSION so older rows become unreachable and age out naturally.

Venue identity (the design's hard part 1.4 / Michael's QID-first rule):
  * Prefer the resolved Wikidata QID (`venue_resolver.resolve_venue`), which is
    stable across phrasings and languages. Fall back to the SAME string
    normalisation the whole-tour cache uses (`tour_cache_layer1._normalize_location`)
    so "Miró" and "Miro" share one pool even without a QID.

The caller (generate_tour_text) owns ordering, orientation, directions and the
conclusion. This module only persists and returns the reusable stop units and
reports what it holds.
"""
import json
import logging
import re
import unicodedata
from datetime import datetime, timezone
from typing import List, Dict, Optional

import psycopg2

logger = logging.getLogger(__name__)


# ── Pool version ─────────────────────────────────────────────────────────────
# Folded into the pool key exactly like tour_cache_layer1.TOUR_CACHE_VERSION, and
# kept in lock-step with it: a change that makes a cached WHOLE tour wrong makes a
# pooled STOP from the same code wrong too. We import the cache version so one
# bump retires both. If the import is unavailable (isolated unit test), fall back
# to a local constant with the same value.
try:
    from tour_cache_layer1 import TOUR_CACHE_VERSION as _POOL_VERSION
    from tour_cache_layer1 import _normalize_location as _normalize_location
except Exception:  # pragma: no cover - import shim for isolated tests
    _POOL_VERSION = 7

    _MEANINGLESS_PUNCT = re.compile(r"[,\.\u2019\u2018']")

    def _fold(s: str) -> str:
        if not s:
            return ""
        decomposed = unicodedata.normalize("NFKD", str(s).lower())
        stripped = "".join(c for c in decomposed if not unicodedata.combining(c))
        return re.sub(r"\s+", " ", stripped).strip()

    def _normalize_location(location: str) -> str:
        folded = _fold(location)
        depunct = _MEANINGLESS_PUNCT.sub(" ", folded)
        return re.sub(r"\s+", " ", depunct).strip()


POOL_VERSION = _POOL_VERSION


# ── Venue identity ───────────────────────────────────────────────────────────

def venue_identity(location: str, qid: Optional[str] = None) -> str:
    """Return the stable pool identity for a venue.

    QID-first (Michael's rule): a resolved Wikidata QID is phrasing- and
    language-stable, so it is preferred when the caller already has one. Without
    a QID we fall back to the whole-tour cache's string normalisation so the two
    layers agree on what "the same venue" means (LOCAL-500).

    The returned string is the raw identity; `_pool_key` prefixes the version and
    tour_type. Kept separate so callers can log/compare identities directly.
    """
    if qid:
        q = str(qid).strip()
        if q:
            return f"qid:{q.upper()}"
    return f"loc:{_normalize_location(location)}"


def resolve_venue_identity(location: str, city: str = "") -> str:
    """Resolve `location` to a QID-based identity when possible, else normalise.

    Thin convenience wrapper that tries `venue_resolver.resolve_venue` and uses
    the QID if it comes back. Any failure (no network, unresolvable venue) falls
    back cleanly to the normalised-location identity — a resolver outage must not
    change which venue a stop is pooled under in a way that corrupts reuse, so a
    failed resolve is treated as "no QID", not an error.
    """
    try:
        from venue_resolver import resolve_venue
        entity = resolve_venue(location, city)
        if entity and getattr(entity, "qid", ""):
            return venue_identity(location, entity.qid)
    except Exception as e:
        logger.info(f"[POOL] venue resolve fell back to normalised location: {e}")
    return venue_identity(location)


def _pool_key(identity: str, tour_type: str) -> str:
    """Namespace a venue identity by pool version + tour_type.

    (version, identity, tour_type) is the pool's partition: all stops a venue has
    ever delivered for one tour_type under the current code live under one key.
    """
    return f"v{POOL_VERSION}|{identity}|{(tour_type or '').strip().lower()}"


# ── Delivered-tour parsing (audio-independent stop units) ────────────────────
#
# A pooled stop is extracted from the DELIVERED tour text, which is the single
# audio-independent artifact every path produces (the cache stores it too). We
# parse each "Stop N:" block into its title + the structured fields the renderer
# emits, and keep the narration BODY (the free prose) separately from the
# sequence-dependent lines (Orientation, Directions) which are NOT pooled.

_STOP_HEADER = re.compile(r'^Stop (\d+):\s*(.+?)\s*$', re.M)
# Structured field lines the renderer emits before/within a stop body.
_FIELD_LINES = {
    "address": re.compile(r'^Address:\s*(.+?)\s*$', re.M),
    "coordinates": re.compile(r'^Coordinates:\s*(.+?)\s*$', re.M),
    "type_specialty": re.compile(r'^Type/Specialty:\s*(.+?)\s*$', re.M),
    "specific_examples": re.compile(r'^Specific Examples:\s*(.+?)\s*$', re.M),
    "operational_details": re.compile(r'^(?:Operational Details|Museum Information):\s*(.+?)\s*$', re.M),
}
# Lines that are SEQUENCE-dependent and must NOT be pooled with the stop.
_SEQ_LINE = re.compile(r'^(?:Orientation|Directions):\s*.*$', re.M)
_SOURCES_LINE = re.compile(r'(?ms)^\s*Sources:\s.*\Z')
# The closing recap opener (LOCAL-280).
_RECAP_FROM_TO = re.compile(r'\bFrom\s+.+?\s+to\s+.+?,\s+you have followed the thread\b')


# ── Epilog stripping (LOCAL-607 defect 1) ────────────────────────────────────
#
# A tour's EPILOG — the closing recap, the stop-count line, the "this journey
# comes to a close" sign-off and the restaurant offer — is a property of the
# WHOLE tour, not of any one stop. It must never ride inside a pooled stop's
# narration. The last stop of an EARLIER tour was stored with that tour's full
# epilog attached (Ideal Portrait, tour 399), so when it is reused mid-tour the
# listener hears "That's 7 stops … If you would like to eat nearby …" in the
# MIDDLE of the new tour (Michael's defect 1).
#
# Unlike `_RECAP_FROM_TO`/`_SOURCES_LINE`, which are applied only to the LAST
# block's trailing tail at parse time, these patterns are swept out of EVERY
# stored narration (and out of existing pooled rows via the migration below),
# because a pooled stop may have been the last stop of some prior tour and so
# carries the epilog embedded in its own body. Each pattern matches from its
# opener to the end of that sentence/line so only the epilog is removed and the
# stop's real last sentence is preserved.
#
# The openers mirror the generator's own epilog wording (generate_tour_text
# `_build_closing_recap` / `_build_closing_offer`, theme_thread_discoverer,
# icon_evaluator, content_qa_runner):
#   * "From X to Y, you have followed the thread …"   (closing recap)
#   * "That's N stops …"                               (scale line; may trail a recap)
#   * "As this journey comes to a close …"             (sign-off)
#   * "If you would like to eat nearby …"              (restaurant offer)
_EPILOG_PATTERNS = (
    # Recap: "From X to Y, you have followed the thread …" through the sentence end.
    re.compile(r'\bFrom\s+.+?\s+to\s+.+?,\s+you have followed the thread\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    # Scale line: "That's 7 stops" and anything that trails it on the same
    # sentence (e.g. "— Dura-Europos …, Ideal Portrait …, and Grace Hoops ….").
    re.compile(r"\bThat['\u2019]s\s+\d+\s+stops?\b.*?(?:\.|$)",
               re.IGNORECASE | re.DOTALL),
    # Sign-off opener used by other closing builders.
    re.compile(r'\bAs this journey comes to a close\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
    # Restaurant offer (the exact house wording and small variants).
    re.compile(r'\bIf you would like to eat nearby\b.*?(?:\.|$)',
               re.IGNORECASE | re.DOTALL),
)


def strip_epilog(text: str) -> str:
    """Remove any tour EPILOG that leaked into a stop narration body.

    Deterministic, idempotent and conservative: it only deletes spans that begin
    with a known epilog opener and runs each to the end of its sentence, so a
    stop's own last real sentence is kept. Collapses the whitespace the removal
    leaves behind. Safe to call on text that has no epilog (returns it unchanged
    apart from whitespace normalisation).
    """
    if not text:
        return text
    out = text
    for pat in _EPILOG_PATTERNS:
        out = pat.sub("", out)
    # Collapse the gaps the removals leave: trailing spaces before newlines, and
    # runs of 3+ blank lines down to a paragraph break.
    out = re.sub(r'[ \t]+\n', '\n', out)
    out = re.sub(r'\n{3,}', '\n\n', out)
    return out.strip()


# ── Opening-section stripping (LOCAL-607 defect 5 / LOCAL-592) ───────────────
#
# The OPENING SECTION of Stop 1 — the museum's About prolog ("Before we look at
# anything on the walls, here is the story of … what it is known for.") and the
# practical-facts line (real hours, or the "Check opening hours and admission on
# <site> before you go." fallback) — is a SEQUENCE-level opener, regenerated per
# tour by about_museum_stop.build_opening_section and prepended fresh by the
# orchestrator. It must NOT also live inside the pooled Stop-1 narration: tour
# 399 was stored before that separation was enforced, so its Stop-1 narration
# still carries the About prolog AND a STALE "Check … on bc.edu before you go."
# (Michael's defect 5 — LOCAL-603's preflight now supplies real hours). Left in,
# the reused tour would duplicate the About and speak the stale pointer.
#
# These openers are deterministic (about_museum_stop composes them verbatim), so
# the whole About-prolog paragraph and the practical-fallback paragraph are
# removed from a narration. Only paragraphs that MATCH an opener are dropped, so a
# work narration is never touched.
_ABOUT_PROLOG_RE = re.compile(
    r'(?is)Before we look at anything on the walls,\s*here is the story of\b')
_PRACTICAL_FALLBACK_RE = re.compile(
    r'(?i)Check opening hours and admission on\b.*?before you go\.?')
_PRACTICAL_LEAD_RE = re.compile(r'(?i)Before you go in, a few practical notes\.?')


def strip_opening_section(text: str) -> str:
    """Remove the regenerated-per-tour opening section from a pooled narration.

    Drops the About-prolog paragraph (the museum's own story, which is rebuilt
    fresh for the delivered tour) and the practical-facts fallback / lead lines
    (real hours are supplied fresh by the opening section). Operates on whole
    paragraphs so a work's narration is never partially cut. Idempotent and safe
    on text that has no opening section.
    """
    if not text:
        return text
    paras = re.split(r'\n{2,}', text)
    kept = []
    for p in paras:
        ps = p.strip()
        if not ps:
            continue
        if _ABOUT_PROLOG_RE.search(ps):
            continue  # the whole About prolog paragraph — regenerated per tour
        # Strip the practical fallback / lead lines wherever they appear.
        ps2 = _PRACTICAL_FALLBACK_RE.sub("", ps)
        ps2 = _PRACTICAL_LEAD_RE.sub("", ps2).strip()
        if not ps2:
            continue
        kept.append(ps2)
    return "\n\n".join(kept).strip()


# ── Orientation / preview stripping (LOCAL-614 item 2) ───────────────────────
#
# A tour-OPENING orientation and the "what you'll see next" preview belong to
# Stop 1's opening only. The kiro-cli critique of tour 399 found a full opening
# orientation misfiled mid-tour (critique Stop 6): "You are about to explore …
# Prepare to encounter seven distinct works … In the upcoming stops, you will see
# 'Meal at the House of Simon' … Your first stop is Dura-Europos …". That block
# was stored with the stop and reused. LOCAL-607 already strips a leaked epilog
# and the opening About section at store/read; this extends the SAME layer to the
# opening / preview orientation.
#
# Deterministic PATTERN SET — a sentence is an opening/preview leftover when it
# OPENS with one of these cues. Matching only at a sentence start (not anywhere
# in the sentence) keeps a normal narration sentence that happens to use a word
# like "stop" or "explore" ("The painting stops the eye", "visitors explore the
# gallery") untouched.
_ORIENTATION_PREVIEW_CUES = (
    r"Prepare to (?:encounter|see|explore|discover|view)",
    r"In the upcoming stops?",
    r"In the (?:next|following) stops?",
    r"You are about to (?:explore|encounter|see|discover|begin)",
    r"Your first stop is\b",
    r"On this tour,? you will\b",
    r"Over the (?:next|following|course of)\b.*?\byou(?:'ll| will)\b",
    r"Throughout (?:this|the) tour,? you will\b",
    r"We will (?:begin|start) (?:our|the|this) (?:tour|journey)\b",
    r"Before we begin,? (?:our|the|this)\b",
    r"This tour will take you\b",
    r"Get ready to (?:encounter|explore|see|discover)",
    r"As you (?:move|continue) (?:through|on) (?:the|this) tour\b",
)
# A sentence that STARTS (after optional opening quote/paren) with a cue.
_ORIENTATION_PREVIEW_RE = re.compile(
    r'(?i)^[\s"“\'(]*(?:' + "|".join(_ORIENTATION_PREVIEW_CUES) + r')')


def strip_orientation_preview(text: str) -> str:
    """Remove tour-OPENING orientation / preview sentences from a narration body.

    [LOCAL-614 item 2] Splits the text into sentences with the ONE shared
    splitter and drops every sentence that OPENS with a deterministic orientation
    / preview cue (``_ORIENTATION_PREVIEW_CUES``) — "Prepare to encounter …",
    "In the upcoming stops …", "You are about to explore …", "Your first stop is
    …", etc. A sentence that merely CONTAINS such a word elsewhere ("The painting
    stops the eye") is kept, because the cue must be at the sentence start.

    Operates paragraph by paragraph so paragraph structure is preserved. Pure,
    deterministic and idempotent; safe on text that has no preview block.
    """
    if not text:
        return text
    try:
        from sentence_split import split_sentences as _shared
    except Exception:  # pragma: no cover
        _shared = lambda t: [s.strip() for s in re.split(r'(?<=[.!?])\s+', t or "")
                             if s.strip()]
    paras = re.split(r'\n{2,}', text)
    out_paras = []
    for para in paras:
        ps = para.strip()
        if not ps:
            continue
        sentences = _shared(ps)
        kept = [s for s in sentences if not _ORIENTATION_PREVIEW_RE.search(s)]
        if kept:
            out_paras.append(" ".join(kept))
    return "\n\n".join(out_paras).strip()


def _strip_title_decorations(raw_title: str) -> str:
    """Return the bare stop title from a 'Stop N:' header value.

    The header may carry ' by {artist}' and ', {year}' decorations
    (generate_tour_text render loop). The pool keys on the bare title so the same
    artwork is one pooled stop regardless of how the decoration rendered; the
    artist/year are preserved separately in the stored unit.
    """
    title = raw_title
    # Strip a trailing ", 1888"-style year.
    m_year = re.search(r',\s*(\d{3,4})\s*$', title)
    year = m_year.group(1) if m_year else ""
    if m_year:
        title = title[:m_year.start()].rstrip()
    # Strip a trailing " by {artist}".
    artist = ""
    m_artist = re.search(r'\s+by\s+(.+?)\s*$', title)
    if m_artist:
        artist = m_artist.group(1).strip()
        title = title[:m_artist.start()].rstrip()
    return title, artist, year


def parse_delivered_stops(tour_content: str) -> List[Dict]:
    """Parse a delivered tour into a list of audio-independent stop units.

    Each returned dict carries:
        title                bare stop title (no artist/year decoration)
        artist, year         decoration recovered from the header (may be "")
        address, coordinates, type_specialty, specific_examples,
        operational_details  structured renderer fields (strings; "" if absent)
        narration            the free-prose BODY of the stop, with the
                             sequence-dependent Orientation/Directions lines and
                             the structured field lines removed — this is the
                             reusable, audio-independent text.
        raw_block            the full original block (kept for exact-reuse audio
                             matching when a stop is served unchanged).

    The closing recap and the trailing Sources block belong to the tour as a
    whole, not to a stop, so they are excluded from every unit.
    """
    text = tour_content or ""
    headers = list(_STOP_HEADER.finditer(text))
    if not headers:
        return []

    # The region that holds stop bodies ends at the recap or Sources, whichever
    # comes first after the last stop header.
    tail_cut = len(text)
    m_recap = _RECAP_FROM_TO.search(text, headers[-1].end())
    if m_recap:
        tail_cut = m_recap.start()
    m_src = _SOURCES_LINE.search(text)
    if m_src and m_src.start() < tail_cut:
        tail_cut = m_src.start()

    units = []
    for idx, hdr in enumerate(headers):
        start = hdr.end()
        end = headers[idx + 1].start() if idx + 1 < len(headers) else tail_cut
        block = text[hdr.start():end].strip()
        body_region = text[start:end]

        title, artist, year = _strip_title_decorations(hdr.group(2).strip())

        unit = {
            "title": title,
            "artist": artist,
            "year": year,
            "raw_block": block,
        }
        # Pull structured fields.
        for field_name, pat in _FIELD_LINES.items():
            m = pat.search(body_region)
            unit[field_name] = m.group(1).strip() if m else ""

        # Narration = body with structured field lines AND sequence lines removed.
        narration = body_region
        for pat in _FIELD_LINES.values():
            narration = pat.sub("", narration)
        narration = _SEQ_LINE.sub("", narration)
        # Drop any trailing recap/sources that leaked into the last block.
        narration = _RECAP_FROM_TO.split(narration)[0]
        narration = _SOURCES_LINE.sub("", narration)
        # [LOCAL-607 defect 1] Strip any tour EPILOG that leaked into the body.
        # The recap/sources cut above only trims the LAST block's trailing tail;
        # a stop that was the LAST stop of an EARLIER tour carries that tour's
        # full epilog ("That's 7 stops … If you would like to eat nearby …")
        # embedded mid-body, so it is swept out of EVERY stop here. The stop ends
        # at the stop.
        narration = strip_epilog(narration)
        # [LOCAL-607 defect 5] Strip the OPENING SECTION (About prolog + practical
        # fallback) — it is a sequence-level opener regenerated per tour, not a
        # stop's own narration. Keeping it would duplicate the About and speak a
        # stale "Check … bc.edu" pointer when real hours are now supplied.
        narration = strip_opening_section(narration)
        # [LOCAL-614 item 2] Strip any tour-OPENING orientation / preview block
        # that leaked into the body ("Prepare to encounter … In the upcoming
        # stops … Your first stop is …") — it belongs to Stop 1's opening only.
        narration = strip_orientation_preview(narration)
        unit["narration"] = re.sub(r'\n{3,}', '\n\n', narration).strip()

        units.append(unit)
    return units


# ── Schema (additive; never DELETE) ──────────────────────────────────────────

def _ensure_table(conn) -> None:
    """Create the additive `stop_pool` table if absent (idempotent).

    Declared here (LOCAL-590 deliverable 1). Primary key is
    (pool_key, title_norm) so the same artwork/subject under one
    (version, venue, tour_type) is exactly one pooled row. Nothing in this module
    ever DELETEs or DROPs; a superseded stop is UPDATEd in place.
    """
    with conn.cursor() as cur:
        cur.execute("""
            CREATE TABLE IF NOT EXISTS stop_pool (
                pool_key TEXT NOT NULL,
                title_norm TEXT NOT NULL,
                venue_identity TEXT NOT NULL,
                tour_type TEXT NOT NULL,
                pool_version INTEGER NOT NULL,
                title TEXT NOT NULL,
                artist TEXT DEFAULT '',
                year TEXT DEFAULT '',
                narration TEXT NOT NULL,
                raw_block TEXT,
                address TEXT DEFAULT '',
                coordinates TEXT DEFAULT '',
                type_specialty TEXT DEFAULT '',
                specific_examples TEXT DEFAULT '',
                operational_details TEXT DEFAULT '',
                sources_json TEXT,
                story_elements_json TEXT,
                generated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                hit_count INTEGER DEFAULT 0,
                order_seq INTEGER DEFAULT 0,
                research_cost_usd NUMERIC(12, 6) DEFAULT 0,
                PRIMARY KEY (pool_key, title_norm)
            )
        """)
        # Migration path for a table created before order_seq existed.
        cur.execute("""
            ALTER TABLE stop_pool ADD COLUMN IF NOT EXISTS order_seq INTEGER DEFAULT 0
        """)
        # [LOCAL-609] Additive migration: per-stop research cost, stored when a
        # stop is first pooled. Lets a pool/cache delivery report
        # `research_cost_reused` (the sum over the reused stops) so a listener's
        # price can be shown as "this delivery" plus "share of research". Additive
        # only — never DELETE/DROP (ticket LOCAL-609).
        cur.execute("""
            ALTER TABLE stop_pool ADD COLUMN IF NOT EXISTS research_cost_usd NUMERIC(12, 6) DEFAULT 0
        """)
        cur.execute("""
            CREATE INDEX IF NOT EXISTS idx_stop_pool_key
            ON stop_pool (pool_key)
        """)
    conn.commit()


def _title_norm(title: str) -> str:
    """Normalise a stop title for pool identity (accent-fold + collapse)."""
    return _normalize_location(title)


# ── Store ────────────────────────────────────────────────────────────────────

def store_delivered_tour(
    location: str,
    tour_type: str,
    tour_content: str,
    db_url: str,
    qid: Optional[str] = None,
    sources: Optional[List[str]] = None,
    story_elements_by_title: Optional[Dict[str, dict]] = None,
    research_cost_usd_per_stop: float = 0.0,
) -> int:
    """Parse a delivered tour and UPSERT each stop into the pool.

    Returns the number of stop units written (new or refreshed). Additive only:
    an existing title is UPDATEd in place with the newer narration + a refreshed
    `generated_at`; no row is ever removed. `sources` (tour-level source URLs)
    are stored on each stop as a reasonable default; `story_elements_by_title`
    (keyed by bare title) overrides per stop when the caller has them.

    [LOCAL-609] `research_cost_usd_per_stop` is the one-time research cost
    attributed to EACH stop of this delivery (the caller divides the tour's
    non-TTS generation cost across its stops). It is written only when a stop is
    FIRST pooled — on a conflict the earlier (original) value is kept (COALESCE to
    the greater of 0 so a later $0 re-pool never erases a real original cost). A
    later pool/cache delivery reports `research_cost_reused` by summing this
    column over the stops it reuses.
    """
    identity = venue_identity(location, qid)
    pool_key = _pool_key(identity, tour_type)
    units = parse_delivered_stops(tour_content)
    if not units:
        logger.info(f"[POOL] no parseable stops in delivered tour for {identity}")
        return 0

    sources_json_default = json.dumps(sources) if sources else None
    written = 0
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            # Base offset so NEW stops in this delivery append after everything
            # already pooled for this venue, while stops already present keep
            # their earlier (MIN) position — the venue's original order is stable.
            cur.execute(
                "SELECT COALESCE(MAX(order_seq), -1) FROM stop_pool WHERE pool_key = %s",
                (pool_key,),
            )
            base_seq = (cur.fetchone() or [-1])[0] + 1
            for seq_i, u in enumerate(units):
                tnorm = _title_norm(u["title"])
                if not tnorm:
                    continue
                se = (story_elements_by_title or {}).get(u["title"])
                se_json = json.dumps(se) if se else None
                cur.execute(
                    """
                    INSERT INTO stop_pool (
                        pool_key, title_norm, venue_identity, tour_type, pool_version,
                        title, artist, year, narration, raw_block,
                        address, coordinates, type_specialty, specific_examples,
                        operational_details, sources_json, story_elements_json,
                        order_seq, research_cost_usd, generated_at
                    ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW())
                    ON CONFLICT (pool_key, title_norm) DO UPDATE SET
                        title = EXCLUDED.title,
                        artist = EXCLUDED.artist,
                        year = EXCLUDED.year,
                        narration = EXCLUDED.narration,
                        raw_block = EXCLUDED.raw_block,
                        address = EXCLUDED.address,
                        coordinates = EXCLUDED.coordinates,
                        type_specialty = EXCLUDED.type_specialty,
                        specific_examples = EXCLUDED.specific_examples,
                        operational_details = EXCLUDED.operational_details,
                        sources_json = COALESCE(EXCLUDED.sources_json, stop_pool.sources_json),
                        story_elements_json = COALESCE(EXCLUDED.story_elements_json, stop_pool.story_elements_json),
                        order_seq = LEAST(stop_pool.order_seq, EXCLUDED.order_seq),
                        -- [LOCAL-609] Keep the ORIGINAL research cost on re-pool
                        -- (first-pooled semantics): only adopt the new value when
                        -- the stored one is 0/NULL (never seen a real cost yet).
                        research_cost_usd = CASE
                            WHEN COALESCE(stop_pool.research_cost_usd, 0) > 0
                            THEN stop_pool.research_cost_usd
                            ELSE EXCLUDED.research_cost_usd END,
                        generated_at = NOW()
                    """,
                    (
                        pool_key, tnorm, identity, (tour_type or "").strip().lower(),
                        POOL_VERSION, u["title"], u["artist"], u["year"],
                        u["narration"], u["raw_block"],
                        u["address"], u["coordinates"], u["type_specialty"],
                        u["specific_examples"], u["operational_details"],
                        sources_json_default, se_json, base_seq + seq_i,
                        float(research_cost_usd_per_stop or 0.0),
                    ),
                )
                written += 1
        conn.commit()
        conn.close()
        logger.info(f"[POOL] stored {written} stop(s) under {pool_key}")
        return written
    except Exception as e:
        logger.error(f"[POOL] store error: {e}")
        return 0


# ── Retrieve ─────────────────────────────────────────────────────────────────

def get_pool_stops(
    location: str,
    tour_type: str,
    db_url: str,
    qid: Optional[str] = None,
) -> List[Dict]:
    """Return every pooled stop for this venue (both QID and location identity).

    Ordered by stable delivery sequence (order_seq ASC) so a caller taking "the
    best N from the pool" gets the venue's original stop order — the core stops
    first, new stops appended after — not an alphabetical or write-time accident.

    Venue-identity robustness (D582 class): resolving a Wikidata QID is a network
    call that can succeed on one generation and fail on the next, which would
    silently split one venue's pool between a `qid:...` key and a `loc:...` key —
    a stored stop then never found on reuse. To defend against that, this reads
    BOTH the QID-based pool key (when a QID is supplied) AND the normalised-
    location key, and UNIONs them (dedup by normalised title, earliest order_seq
    wins). So however the resolver behaved when a stop was stored, it is found.

    Each dict mirrors the stored unit plus `generated_at` (ISO) and `hit_count`.
    Returns [] on any error or empty pool — an empty pool is a legitimate
    "nothing reusable yet", distinct from an exception which is logged.
    """
    keys = []
    if qid:
        keys.append(_pool_key(venue_identity(location, qid), tour_type))
    loc_key = _pool_key(venue_identity(location), tour_type)
    if loc_key not in keys:
        keys.append(loc_key)
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT title, artist, year, narration, raw_block,
                       address, coordinates, type_specialty, specific_examples,
                       operational_details, sources_json, story_elements_json,
                       generated_at, hit_count, title_norm, research_cost_usd
                FROM stop_pool
                WHERE pool_key = ANY(%s)
                ORDER BY order_seq ASC, generated_at ASC, title_norm ASC
                """,
                (keys,),
            )
            rows = cur.fetchall()
        conn.close()
    except Exception as e:
        logger.error(f"[POOL] read error: {e}")
        return []

    stops = []
    _seen_titles = set()
    for r in rows:
        tnorm = r[14]
        if tnorm in _seen_titles:
            continue  # same stop under both keys — keep the first (earliest order_seq)
        _seen_titles.add(tnorm)
        stops.append({
            "title": r[0],
            "artist": r[1] or "",
            "year": r[2] or "",
            # [LOCAL-607 defect 1] Strip any epilog on READ too: existing rows were
            # stored before this fix and may still carry an earlier tour's epilog
            # inside their narration. The migration below cleans them in place, but
            # stripping on read guarantees a clean body even if the migration has
            # not run against this database yet. Idempotent on already-clean rows.
            # [LOCAL-607 defect 5] Also strip the opening section (About prolog +
            # stale "Check … bc.edu" fallback), regenerated fresh per tour.
            "narration": strip_opening_section(strip_epilog(r[3])),
            "raw_block": r[4] or "",
            "address": r[5] or "",
            "coordinates": r[6] or "",
            "type_specialty": r[7] or "",
            "specific_examples": r[8] or "",
            "operational_details": r[9] or "",
            "sources": json.loads(r[10]) if r[10] else [],
            "story_elements": json.loads(r[11]) if r[11] else None,
            "generated_at": r[12].isoformat() if r[12] else None,
            "hit_count": r[13] or 0,
            # [LOCAL-609] the one-time research cost stored when this stop was
            # first pooled; summed into research_cost_reused on reuse.
            "research_cost_usd": float(r[15]) if r[15] is not None else 0.0,
        })
    logger.info(f"[POOL] {len(stops)} pooled stop(s) across keys {keys}")
    return stops


def pool_titles(
    location: str,
    tour_type: str,
    db_url: str,
    qid: Optional[str] = None,
) -> List[str]:
    """Return the bare titles currently in the pool (for selection exclusion).

    A new-stop selection must EXCLUDE pooled titles so a bigger tour adds genuinely
    new subjects rather than regenerating ones it already has (LOCAL-590 step 2).
    """
    return [s["title"] for s in get_pool_stops(location, tour_type, db_url, qid=qid)]


def bump_hit_counts(
    location: str,
    tour_type: str,
    titles: List[str],
    db_url: str,
    qid: Optional[str] = None,
) -> None:
    """Increment hit_count for the pooled stops actually reused in a delivery.

    Pure accounting (how often a pooled stop has been served); never changes
    narration or removes rows.
    """
    if not titles:
        return
    identity = venue_identity(location, qid)
    pool_key = _pool_key(identity, tour_type)
    norms = [_title_norm(t) for t in titles if _title_norm(t)]
    if not norms:
        return
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE stop_pool SET hit_count = hit_count + 1 "
                "WHERE pool_key = %s AND title_norm = ANY(%s)",
                (pool_key, norms),
            )
        conn.commit()
        conn.close()
    except Exception as e:
        logger.warning(f"[POOL] hit-count update error: {e}")


# ── Epilog-strip migration (LOCAL-607 defect 1; in-place UPDATE only) ─────────

def migrate_strip_epilog_in_pool(db_url: str) -> Dict[str, int]:
    """Clean existing pooled rows in place: strip any tour epilog + opening section.

    Old rows (stored before LOCAL-607) may carry an earlier tour's epilog inside
    their narration — the Ideal Portrait / tour-399 defect — and the Stop-1
    About-prolog + stale "Check … bc.edu" opening section (defect 5). This walks
    every `stop_pool` row, applies `strip_epilog` then `strip_opening_section`,
    and issues an in-place UPDATE for each row whose narration actually changes.
    It never DELETEs or DROPs anything (the task's "no DELETE; UPDATE of the
    narration only" rule): a row's identity, order_seq, sources and story elements
    are untouched; only the narration text is rewritten, and only when it still
    contains an epilog or opening section.

    Returns a counts dict for the before/after report:
        {"scanned": N, "with_epilog": M, "updated": M}
    where `with_epilog` is how many rows carried an epilog before the run and
    `updated` is how many were rewritten (equal to `with_epilog` on success).
    Idempotent: a second run finds `with_epilog == 0` and updates nothing.
    """
    counts = {"scanned": 0, "with_epilog": 0, "updated": 0}
    try:
        conn = psycopg2.connect(db_url)
        _ensure_table(conn)
        with conn.cursor() as cur:
            cur.execute("SELECT pool_key, title_norm, narration FROM stop_pool")
            rows = cur.fetchall()
            counts["scanned"] = len(rows)
            to_update = []
            for pool_key, title_norm, narration in rows:
                cleaned = strip_opening_section(strip_epilog(narration or ""))
                if cleaned != (narration or "").strip():
                    to_update.append((cleaned, pool_key, title_norm))
            counts["with_epilog"] = len(to_update)
            for cleaned, pool_key, title_norm in to_update:
                cur.execute(
                    "UPDATE stop_pool SET narration = %s "
                    "WHERE pool_key = %s AND title_norm = %s",
                    (cleaned, pool_key, title_norm),
                )
                counts["updated"] += 1
        conn.commit()
        conn.close()
        logger.info(
            f"[POOL] epilog-strip migration: scanned={counts['scanned']} "
            f"with_epilog={counts['with_epilog']} updated={counts['updated']}"
        )
        return counts
    except Exception as e:
        logger.error(f"[POOL] epilog-strip migration error: {e}")
        return counts
