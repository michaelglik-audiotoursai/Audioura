"""customer_voice.py — LOCAL-800: "What customers say" for a business/place stop.

WHY THIS EXISTS
---------------
Michael on tour 469 (Russian, massage & spa near Ben Thanh Market): a day spa
"acceptable with stories; not really interesting" — a spa rarely has history or a
famous visitor, so the usual story-first narration has nothing true to say. What
IS interesting and useful about a business is **what its customers say**: the
Google rating and how many people left it, roughly what it costs, how long it has
been open, the treatments or dishes reviewers keep mentioning, the single thing
most praised, and the single recurring complaint.

This module is the ACQUISITION + COMPOSITION half for that paragraph. It is used
only for PLACE-TYPE stops (dining and business/activity — the LOCAL-788B places
path). A landmark/museum stop never reaches it.

THE SOURCES (and the hard rule)
-------------------------------
1. THE SERPER PLACES RECORD already fetched for the stop (LOCAL-783). It carries,
   with NO extra call, the Google rating (`_serper_rating`), review count
   (`_serper_rating_count`), price band (`_serper_price_level`) and the venue's
   own website (`_serper_website`). These are reused verbatim.
2. AT MOST ONE extra Serper call per stop (~$0.001), a plain organic search
   "<name> <scope> reviews", from whose SNIPPETS we read — never invent — the
   signature items/treatments that recur, the single most common praise, the
   single most common complaint, and a "since <year>" if the snippets state one.

THE HARD RULE (ticket): never invent a number, a name or a quote. Every item in
the paragraph must trace to one of the two sources above; an item with no source
is OMITTED. A COMPLAINT is surfaced only when at least TWO snippets agree on it
(one grumble is not "what customers say"). No rating AND no review count → no
paragraph at all (there is nothing attributable to say). Translations keep the
numbers (they are facts, not prose).

COST
----
At most one extra Serper call per stop, through the guaranteed-metered door
(`serper_meter.serper_post`). `fetch_review_signals` can be told to skip the call
(`allow_search=False`) — then the paragraph is built from the Places record alone.

LOG
---
One line per stop that gets a paragraph:
    [LOCAL-800] customer-voice <title> rating=<r> n=<count> items=<a; b; c>
"""
import os
import re
import unicodedata
from collections import Counter
from typing import Dict, List, Optional, Tuple

_SERPER_SEARCH_ENDPOINT = "https://google.serper.dev/search"


# ──────────────────────────── small helpers ─────────────────────────────────
def _as_float(v) -> Optional[float]:
    """Parse a Serper rating-ish value into a float, or None. Accepts 4.8, "4.8",
    "4,8" (comma decimal). Rejects nonsense and out-of-range (0–5) ratings."""
    if v is None or v == "":
        return None
    try:
        f = float(str(v).strip().replace(",", "."))
    except (TypeError, ValueError):
        return None
    if not (0.0 <= f <= 5.0):
        return None
    return f


def _as_int_count(v) -> Optional[int]:
    """Parse a review count. Accepts 2300, "2300", "2,300", "2.3k"-style is NOT
    accepted (we only trust an exact integer Serper gave). None when unusable."""
    if v is None or v == "":
        return None
    s = str(v).strip().replace(",", "").replace(" ", "")
    if not re.fullmatch(r"\d+", s):
        return None
    try:
        n = int(s)
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _round_count(n: int) -> str:
    """Speak a review count the way the ticket's example does ("about 2,300"):
    exact under 100, else rounded to a human figure with a thousands separator."""
    if n < 100:
        return str(n)
    if n < 1000:
        return f"about {int(round(n / 10.0) * 10):,}"
    if n < 10000:
        return f"about {int(round(n / 100.0) * 100):,}"
    return f"about {int(round(n / 1000.0) * 1000):,}"


def _strip_accents(s: str) -> str:
    if not s:
        return ""
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _clean_price_band(raw: str) -> str:
    """A Serper `priceLevel` is a compact band like "$40–50" or "$$". Speak it as
    given; only trim stray whitespace. Never derive a price from anything else."""
    return (raw or "").strip()


# ─────────────── signature items / praise / complaint extraction ─────────────
# A snippet mentions a "signature item" when a known dish/treatment noun recurs.
# These are GENERIC nouns, matched case-insensitively against review snippets, so
# the extraction never invents an item — a word is surfaced only if reviewers used
# it. Grouped by the two place families the ticket names (dining, spa/wellness),
# plus shop/café staples. A word here is a candidate; it is kept only when it
# appears in >= 2 snippets (``_MIN_ITEM_SNIPPETS``), so a one-off mention is not
# spoken as "many mention …".
_ITEM_VOCAB = (
    # spa / massage / wellness
    "hot stone", "hot-stone", "deep tissue", "deep-tissue", "aromatherapy",
    "foot massage", "foot reflexology", "reflexology", "thai massage",
    "swedish massage", "facial", "facials", "body scrub", "body wrap", "sauna",
    "steam room", "jacuzzi", "manicure", "pedicure", "mani-pedi", "waxing",
    "massage", "spa package", "couples massage", "shiatsu", "acupressure",
    # café / coffee / bakery
    "latte", "cappuccino", "espresso", "cold brew", "flat white", "cortado",
    "pour over", "pour-over", "croissant", "pastry", "pastries", "scone",
    "muffin", "bagel", "avocado toast", "matcha", "chai", "mocha", "drip coffee",
    "iced coffee", "oat milk", "breakfast sandwich", "donut", "doughnut",
    # restaurant / dining
    "pho", "banh mi", "spring rolls", "dumplings", "pad thai", "ramen", "sushi",
    "pizza", "pasta", "tacos", "burger", "falafel", "shawarma", "hummus",
    "kebab", "biryani", "curry", "dim sum", "steak", "seafood", "brunch",
    "tasting menu", "wine list", "cocktails", "dessert", "tiramisu",
    # shop / general (a notable product line reviewers name)
    "selection", "produce", "cheese", "flowers", "books", "wine",
)

# Praise adjectives/nouns — the thing reviewers most often compliment. Only words
# reviewers actually used are surfaced (matched against snippets).
_PRAISE_VOCAB = (
    "friendly", "welcoming", "relaxing", "clean", "professional", "attentive",
    "cozy", "cosy", "authentic", "delicious", "fresh", "fast", "excellent",
    "great value", "reasonable", "spacious", "quiet", "knowledgeable", "helpful",
    "generous", "comfortable", "beautiful", "charming", "peaceful",
)

# Complaint words — the recurring negative. Surfaced ONLY when >= 2 snippets agree
# (``_MIN_COMPLAINT_SNIPPETS``), so one bad review never becomes "customers say".
_COMPLAINT_VOCAB = (
    "expensive", "overpriced", "pricey", "slow", "rude", "crowded", "noisy",
    "small portions", "long wait", "cramped", "dirty", "pushy", "cold",
    "understaffed", "parking", "wait time", "inconsistent", "touristy",
)

_MIN_ITEM_SNIPPETS = 2      # "many mention X" needs >= 2 snippets naming X
_MIN_PRAISE_SNIPPETS = 2    # a top praise needs >= 2 snippets
_MIN_COMPLAINT_SNIPPETS = 2  # ticket: complaint only with >= 2 agreeing snippets


def _count_vocab_hits(snippets: List[str], vocab) -> "Counter":
    """Count, per vocab phrase, the NUMBER OF SNIPPETS it appears in (not the raw
    occurrence count) — so "appears in >= 2 snippets" is a true agreement test, not
    one snippet repeating a word. Accent-folded, case-insensitive, word-ish match."""
    folded = [_strip_accents(s or "").lower() for s in (snippets or [])]
    hits: "Counter" = Counter()
    for phrase in vocab:
        p = _strip_accents(phrase).lower()
        n = sum(1 for s in folded if p in s)
        if n:
            hits[phrase] = n
    return hits


def _canonical_item(phrase: str) -> str:
    """Normalise a matched item phrase for display ("hot-stone" → "hot stone")."""
    return phrase.replace("-", " ").strip()


_SINCE_RE = re.compile(
    r"\b(?:since|established|est\.?|founded|opened(?:\s+in)?|serving\s+since|"
    r"family[- ]owned\s+since)\s+(\d{4})\b", re.IGNORECASE)


def _extract_since_year(snippets: List[str]) -> Optional[int]:
    """Pull a "since <year>" / "established <year>" if the SNIPPETS state one.
    Returns the earliest plausible year (1700..current+0) found in >= 1 snippet.
    A year with no founding/opening word around it is NOT taken (a street number
    or a price is not a founding date)."""
    import datetime
    this_year = datetime.date.today().year
    years = []
    for s in (snippets or []):
        for m in _SINCE_RE.finditer(s or ""):
            try:
                y = int(m.group(1))
            except (TypeError, ValueError):
                continue
            if 1700 <= y <= this_year:
                years.append(y)
    if not years:
        return None
    return min(years)


# ──────────────────────────── the single search ─────────────────────────────
def _serper_review_snippets(name: str, scope: str,
                            api_key: Optional[str] = None,
                            timeout: int = 12) -> List[str]:
    """ONE metered Serper organic search for review snippets about this place.

    Returns a list of snippet strings (possibly empty). Never raises — a failure
    returns []. This is the AT-MOST-ONE extra call per stop the ticket allows; the
    cost (~$0.001) is recorded by serper_meter.serper_post. The caller decides
    whether to make it (``fetch_review_signals(allow_search=...)``)."""
    key = (api_key or os.environ.get("SERP_API_KEY")
           or os.environ.get("SERPER_API_KEY"))
    if not key or not name:
        return []
    place = (scope or "").split(",")[0].strip()
    query = f"{name} {place} reviews".strip()
    try:
        from serper_meter import serper_post
    except Exception:
        return []
    try:
        import json as _json
        status, body = serper_post(_SERPER_SEARCH_ENDPOINT,
                                   {"q": query, "num": 10},
                                   api_key=key, timeout=timeout)
        if status != 200 or not body:
            return []
        data = _json.loads(body.decode("utf-8", "ignore"))
    except Exception:
        return []
    out: List[str] = []
    for r in (data.get("organic") or []):
        sn = (r.get("snippet") or "").strip()
        if sn:
            out.append(sn)
    # The answer box / knowledge graph sometimes carries a one-line description.
    kg = data.get("knowledgeGraph") or {}
    desc = (kg.get("description") or "").strip()
    if desc:
        out.append(desc)
    return out


def _serper_places_lookup(name: str, scope: str) -> Optional[Dict]:
    """Look up ONE place by name on Serper Places and return its normalised record
    (the dict ``places_search._normalize_serper_place`` produces, carrying
    `_serper_rating`, `_serper_rating_count`, `_serper_price_level`,
    `_serper_website`). Returns None when nothing matched or Serper is off.

    Reuse is cheap: ``places_search.places_search`` caches identical (query, ll)
    for 24 h, so when the stop was already verified on the map during generation
    this is a CACHE HIT and bills nothing. When it is not cached it is the ONE
    extra Serper call the ticket allows. Never raises."""
    try:
        import places_search as _ps
    except Exception:
        return None
    if not _ps.serper_places_enabled() or not name:
        return None
    try:
        scope_center = None
        try:
            from stop_existence_gate import _geocode_scope_center as _gsc
            scope_center = _gsc(scope)
        except Exception:
            scope_center = None
        recs = _ps.places_search(name, scope, limit=1, scope_center=scope_center)
    except Exception:
        return None
    if not recs:
        return None
    return recs[0]


# ───────────────────────────── public: collect ──────────────────────────────
def collect_facts(place_record: Optional[Dict], name: str, scope: str,
                  *, allow_search: bool = True,
                  api_key: Optional[str] = None,
                  review_snippets: Optional[List[str]] = None) -> Dict:
    """Collect the customer-voice facts for ONE place stop, from the Serper Places
    record already in hand plus AT MOST ONE extra Serper call.

    Args:
        place_record: the stop's Serper-sourced dict. Read for `_serper_rating`,
            `_serper_rating_count`, `_serper_price_level`, `_serper_website`,
            `_serper_category`. May be None/partial — missing fields are omitted.
        name: the stop's spoken name (for the search query and the log).
        scope: the tour scope ("Ben Thanh Market, Ho Chi Minh City") — the locality
            part is used in the review search.
        allow_search: when False, NO extra Serper call is made; the facts come from
            the Places record alone (used by tests and by a cost-exhausted run).
        api_key: Serper key override (tests pass a fake; prod reads the env).
        review_snippets: pre-supplied snippets (tests inject recorded ones). When
            given, NO live search is made regardless of allow_search.

    Returns a facts dict (all keys always present; empty when unsourced):
        {name, rating, rating_count, price_band, website, category,
         since_year, items[], top_praise, top_complaint, snippets_used,
         sources[], searched(bool), usable(bool)}
    usable is True only when there is a rating OR a review count — the ticket's
    "no paragraph when rating/count missing" rule.
    """
    rec = place_record or {}
    rating = _as_float(rec.get("_serper_rating"))
    rating_count = _as_int_count(rec.get("_serper_rating_count"))
    price_band = _clean_price_band(rec.get("_serper_price_level") or "")
    website = (rec.get("_serper_website") or "").strip()
    category = (rec.get("_serper_category") or "").strip()
    cid = rec.get("_serper_cid")

    # [LOCAL-800] THE ONE CALL, part 1 — when the stop carries NO rating and NO
    # count (it was verified on the map by name, or came from the LLM list), look
    # the place up on Serper Places to GET the rating / count / price band. This is
    # the single allowed extra call; it is a 24 h CACHE HIT (free) when the place
    # was already fetched during generation. Skipped when snippets are injected
    # (tests) or the caller forbade searching. Reuse-first: if a rating is already
    # present we do NOT make this call.
    _did_places_call = False
    if (rating is None and rating_count is None
            and review_snippets is None and allow_search):
        _looked = _serper_places_lookup(name, scope)
        if _looked:
            _did_places_call = True
            rec = {**_looked, **{k: v for k, v in rec.items() if v is not None}} \
                if isinstance(rec, dict) else _looked
            rating = _as_float(_looked.get("_serper_rating")) if rating is None else rating
            rating_count = (_as_int_count(_looked.get("_serper_rating_count"))
                            if rating_count is None else rating_count)
            if not price_band:
                price_band = _clean_price_band(_looked.get("_serper_price_level") or "")
            if not website:
                website = (_looked.get("_serper_website") or "").strip()
            if not category:
                category = (_looked.get("_serper_category") or "").strip()
            if not cid:
                cid = _looked.get("_serper_cid")

    facts: Dict = {
        "name": name or (rec.get("name") or ""),
        "rating": rating,
        "rating_count": rating_count,
        "price_band": price_band,
        "website": website,
        "category": category,
        "since_year": None,
        "items": [],
        "top_praise": "",
        "top_complaint": "",
        "snippets_used": 0,
        "sources": [],
        "searched": False,
        "usable": bool(rating is not None or rating_count is not None),
    }

    # Provenance for the Places-sourced numbers (the stop carries the cid).
    if cid:
        facts["sources"].append(f"serper_places:cid={cid}")
    if website:
        facts["sources"].append(website)
    if _did_places_call:
        facts["searched"] = True
        facts["sources"].append(f"serper_places:{name} (lookup)")

    # [LOCAL-800] THE ONE CALL, part 2 — review snippets for the signature items /
    # praise / complaint / since-year. This runs ONLY when we did NOT already spend
    # the single allowed call on the Places lookup above, so at most ONE extra
    # Serper network call is ever made per stop. Injected snippets (tests) feed it
    # directly and cost nothing.
    snippets: List[str] = []
    if review_snippets is not None:
        snippets = [s for s in review_snippets if s]
    elif allow_search and not _did_places_call:
        snippets = _serper_review_snippets(name, scope, api_key=api_key)
        facts["searched"] = True
        if snippets:
            facts["sources"].append(f"serper_search:{name} reviews")

    if snippets:
        facts["snippets_used"] = len(snippets)
        item_hits = _count_vocab_hits(snippets, _ITEM_VOCAB)
        # Collapse "hot-stone"/"hot stone" style variants onto one display form and
        # sum their snippet agreement, then keep the items reviewers agree on.
        canon: "Counter" = Counter()
        for phrase, n in item_hits.items():
            canon[_canonical_item(phrase)] += n
        facts["items"] = [it for it, n in canon.most_common()
                          if n >= _MIN_ITEM_SNIPPETS][:3]

        praise_hits = _count_vocab_hits(snippets, _PRAISE_VOCAB)
        top_praise = [w for w, n in praise_hits.most_common()
                      if n >= _MIN_PRAISE_SNIPPETS]
        facts["top_praise"] = top_praise[0] if top_praise else ""

        complaint_hits = _count_vocab_hits(snippets, _COMPLAINT_VOCAB)
        # Ticket: a complaint is surfaced ONLY when >= 2 snippets agree on it.
        top_complaint = [w for w, n in complaint_hits.most_common()
                         if n >= _MIN_COMPLAINT_SNIPPETS]
        facts["top_complaint"] = top_complaint[0] if top_complaint else ""

        facts["since_year"] = _extract_since_year(snippets)

    return facts


# ───────────────────────────── public: compose ──────────────────────────────
def build_paragraph(facts: Optional[Dict]) -> str:
    """Compose the "What people say" paragraph from ONLY the sourced facts.

    Returns "" when there is nothing attributable to say (no rating AND no review
    count) — the ticket's "no paragraph when rating/count missing" rule. Every
    clause is built from a present, sourced field; an absent field contributes no
    clause (no invented numbers, names or quotes). Attribution is explicit
    ("Visitors on Google give it …")."""
    if not facts or not facts.get("usable"):
        return ""
    rating = facts.get("rating")
    count = facts.get("rating_count")
    # The paragraph needs at least a rating or a count to open with attribution.
    if rating is None and count is None:
        return ""

    bits: List[str] = []

    # 1) The headline: rating + count, attributed to Google.
    if rating is not None and count is not None:
        bits.append(f"Visitors on Google give it {rating:g} "
                    f"from {_round_count(count)} reviews")
    elif rating is not None:
        bits.append(f"Visitors on Google give it {rating:g}")
    else:  # count only
        bits.append(f"It has {_round_count(count)} Google reviews")

    # 2) Signature items reviewers keep mentioning.
    items = [i for i in (facts.get("items") or []) if i]
    if items:
        if len(items) == 1:
            bits.append(f"many mention the {items[0]}")
        else:
            head = ", ".join(items[:-1])
            bits.append(f"many mention the {head} and {items[-1]}")

    # 3) The single most common praise.
    praise = (facts.get("top_praise") or "").strip()
    if praise:
        bits.append(f"reviewers often call it {praise}")

    # 4) How long it has been open ("since <year>").
    since = facts.get("since_year")
    if since:
        bits.append(f"it has been open since {since}")

    # 5) Price band (sourced from Serper Places), stated plainly.
    price = (facts.get("price_band") or "").strip()
    if price:
        bits.append(f"expect prices around {price}")

    # 6) The recurring complaint — only ever here because >= 2 snippets agreed.
    complaint = (facts.get("top_complaint") or "").strip()
    if complaint:
        bits.append(f"though some find it {complaint}")

    if not bits:
        return ""

    # Join into one short paragraph. Capitalise the first clause; the "though …"
    # complaint reads naturally after a semicolon.
    sentence = bits[0]
    rest = bits[1:]
    if rest:
        # Separate the complaint (it starts with "though") with a semicolon.
        lead = [b for b in rest if not b.startswith("though")]
        tail = [b for b in rest if b.startswith("though")]
        if lead:
            sentence = sentence + "; " + "; ".join(lead)
        for t in tail:
            sentence = sentence + "; " + t
    sentence = sentence.strip()
    if not sentence.endswith("."):
        sentence += "."
    return sentence


# ───────────────────────── public: prompt block ─────────────────────────────
def customer_voice_prompt_block(facts: Optional[Dict]) -> str:
    """The "What people say" paragraph shaped for the stop prompt, with the
    disclosure rule attached (mirrors restaurant_practicals.practicals_prompt_block).

    Returns "" when there is no sourced paragraph. The block hands the narrator the
    ALREADY-COMPOSED, fully-sourced paragraph and forbids adding to it — the model
    must not invent a number, a name or a quote beyond what is listed."""
    paragraph = build_paragraph(facts)
    if not paragraph:
        return ""
    return (
        "\nWHAT PEOPLE SAY — CUSTOMER VOICE, SOURCED FROM GOOGLE/SERPER. These are "
        "facts about how this place's own customers rate and describe it.\n"
        f"  {paragraph}\n"
        "WEAVE THIS INTO THE STOP in the narrator's own voice as a short 'what "
        "visitors say' moment — this is the most interesting, useful thing about a "
        "business that has little history of its own.\n"
        "Use ONLY the numbers, items and words in the paragraph above. Do NOT invent "
        "a rating, a review count, a price, a signature dish/treatment, a founding "
        "year or a quote that is not listed. Keep the numbers exactly as written "
        "(they are sourced); in a translated tour the numbers stay the same.\n"
    )


# ───────────────────────── public: the log line ─────────────────────────────
def log_line(facts: Optional[Dict]) -> str:
    """The ticket's required log line for a stop that got a customer-voice paragraph:
        [LOCAL-800] customer-voice <title> rating=<r> n=<count> items=<a; b; c>
    Returns "" when there is no usable paragraph (nothing to log)."""
    if not build_paragraph(facts):
        return ""
    name = (facts.get("name") or "").strip() or "(unnamed)"
    rating = facts.get("rating")
    count = facts.get("rating_count")
    items = "; ".join(facts.get("items") or []) or "-"
    r = f"{rating:g}" if rating is not None else "-"
    n = str(count) if count is not None else "-"
    return f"[LOCAL-800] customer-voice {name} rating={r} n={n} items={items}"


def facts_for_sources(facts: Optional[Dict]) -> Dict:
    """A compact, JSON-serialisable record of the customer-voice facts to store
    with the stop's sources (evidence/provenance). Empty dict when not usable."""
    if not facts or not facts.get("usable"):
        return {}
    return {
        "customer_voice": {
            "rating": facts.get("rating"),
            "rating_count": facts.get("rating_count"),
            "price_band": facts.get("price_band") or "",
            "website": facts.get("website") or "",
            "since_year": facts.get("since_year"),
            "items": list(facts.get("items") or []),
            "top_praise": facts.get("top_praise") or "",
            "top_complaint": facts.get("top_complaint") or "",
            "snippets_used": facts.get("snippets_used") or 0,
            "sources": list(facts.get("sources") or []),
            "paragraph": build_paragraph(facts),
        }
    }
