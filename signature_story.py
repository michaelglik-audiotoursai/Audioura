"""signature_story.py — LOCAL-880: pick each stop's 1–2 signature stories.

Wave 38 (proof 547, LEAD 4.8/10) was CORRECT but forgettable: the gates removed
the errors and, with them, every stop's best moment. Wave 37 had carried the
Opera House's 1944 Allied bombing and its cameo in Graham Greene's *The Quiet
American*, and the Palace's 30 April 1975 tank through the gates. Wave 38 lost
both; the Palace became "a historic landmark and government-owned public hall".
Michael's bar: "the best is when the stories are interesting and true." A stop
without its signature story scores about 5 however correct it is.

So, BEFORE narration, for each landmark/user stop that has evidence, make ONE
cheap gpt-4.1-mini pass over that stop's own evidence and pick its 1–2 signature
stories. Each returned story MUST quote a source sentence that is present in the
evidence (so the claim gate can protect it, LOCAL-880 §5). A date or a dimension
alone is NOT a story — rank by human interest: an event, a person, a conflict, a
surprise, a famous book or film.

Contract:
  * ``select_signature_stories(title, evidence_text, *, location, narrate_fn,
    model, log)`` -> ``(stories, report)``.
  * ``stories`` is a list (len 0–2) of dicts ``{story, why_memorable,
    source_sentence}``. ``source_sentence`` is VERIFIED to be a (fuzzy) substring
    of the evidence; a story whose quote is not in the evidence is dropped
    (never invent a quote). An empty list means no memorable story was found —
    the narrator is not forced to manufacture one.
  * Cost cap: ≤ $0.003 per stop (one JSON call, small max_tokens). The LLM
    backend is injectable so the module is fully offline-testable; pure helpers
    never raise.
  * ``required_element_block(stories)`` renders the prompt block that tells the
    narrator to TELL these stories (append LAST, recency bias).
  * ``body_tells_story(body, story)`` is the post-narration check: True when the
    delivered body carries the story (distinctive-token overlap). The caller
    regenerates the stop ONCE when it is False.
"""
from __future__ import annotations

import json
import os
import re
from typing import Callable, Dict, List, Optional, Tuple

# ── cost guard ────────────────────────────────────────────────────────────────
# One gpt-4.1-mini JSON call. Priced well under the $0.003/stop cap: gpt-4.1-mini
# is ~$0.40/1M input and ~$1.60/1M output; with <=1500 input + <=320 output
# tokens the worst case is ~$0.0011. max_tokens is capped so the call cannot run
# away past the cap.
MODEL = os.environ.get("SIGNATURE_STORY_MODEL", "gpt-4.1-mini")
MAX_INPUT_CHARS = 6000          # evidence is truncated to this before the call
MAX_TOKENS = 360
TEMPERATURE = 0.2
COST_CAP_USD = float(os.environ.get("SIGNATURE_STORY_COST_CAP_USD", "0.003"))

_SYSTEM = (
    "You select the single most memorable true story a walking-tour guide could "
    "tell at one stop, using ONLY the evidence given. You never invent facts and "
    "you never quote a sentence that is not in the evidence."
)


def _fold(s: str) -> str:
    """ASCII-fold + lowercase + collapse whitespace, for robust matching."""
    try:
        import unicodedata
        s = unicodedata.normalize("NFKD", s)
        s = s.encode("ascii", "ignore").decode("ascii")
    except Exception:
        pass
    return re.sub(r"\s+", " ", (s or "").lower()).strip()


_STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "at", "by", "for",
    "with", "from", "as", "is", "was", "were", "are", "be", "been", "this",
    "that", "it", "its", "his", "her", "their", "you", "your", "here", "where",
    "which", "who", "when", "what", "now", "also", "but", "into", "over",
    "after", "before", "about", "between", "both", "one", "two",
}


def _content_tokens(s: str) -> set:
    return {w for w in re.findall(r"[a-z0-9]+", _fold(s)) if len(w) >= 3 and w not in _STOP}


def _sentences(text: str) -> List[str]:
    try:
        from sentence_split import split_sentences
        out = split_sentences(text)
        if out:
            return out
    except Exception:
        pass
    return re.findall(r"[^.!?]*[.!?]", text or "")


def _quote_in_evidence(quote: str, evidence: str, *, min_overlap: int = 4) -> bool:
    """True when ``quote`` is supported by the evidence: a folded-substring match,
    or a sentence in the evidence that shares >= ``min_overlap`` distinctive
    content tokens with the quote (handles minor paraphrase/whitespace)."""
    q = _fold(quote)
    if len(q) < 8:
        return False
    ev = _fold(evidence)
    if q in ev:
        return True
    qtok = _content_tokens(quote)
    if len(qtok) < min_overlap:
        # a short quote must match as a substring (handled above); do not accept
        # it on token overlap alone.
        return False
    for sent in _sentences(evidence):
        if len(qtok & _content_tokens(sent)) >= min_overlap:
            return True
    return False


# a story needs human interest: an event / person / conflict / surprise / a
# named book or film. A bare measurement or a lone date is explicitly NOT a
# story (Michael: "A date or a dimension is not a story").
_DIMENSION_ONLY_RE = re.compile(
    r"(?i)^\s*(it|the \w+)?\s*(is|was|measures|stands|rises|seats?|holds?)?\s*"
    r"[\d.,]+\s*(meters?|metres?|m|feet|ft|seats?|stories|storeys|tons?|"
    r"kilograms?|years? old)\b")


def _looks_like_story(story: str) -> bool:
    s = (story or "").strip()
    if len(s) < 20:
        return False
    if _DIMENSION_ONLY_RE.match(s) and len(_content_tokens(s)) <= 4:
        return False
    return True


# ══════════════════════════════════════════════════════════════════════════════
# LOCAL-881 — TRUST ONLY THE STOP'S OWN SOURCE
#
# Wave 39 (proof 547, gen 00041-lkk, rolled back) shipped FALSE or off-site
# signature stories that the LOCAL-880 design then PROTECTED from the claim gate,
# so a wrong pick became worse than no story:
#   * Post Office: "designed by Gustave Eiffel" (a myth the evidence itself flags;
#     truth is Vildieu + Foulhoux, 1886-91);
#   * Book Street: the 1968 Loan/Lém execution "right here" (it was in Chợ Lớn);
#   * City Hall: the Gia Long Palace article (a different building ~600 m away);
#   * Palace: "months before … 31 October 1966" with a Nov 1963 event (3 years);
#   * Palace: the tank story that lost "30 April 1975".
#
# These all entered because the picker drew its source from the 873 thin-stop page
# facts (``poi['_lore']``), not the stop's OWN Wikipedia article. The helpers below
# are generic (D769 — no venue, city, date or name is hard-coded): a story is kept
# only when its source sentence comes from the stop's own source (own article, or a
# page that names the stop), does not carry a myth/contradiction marker about the
# stop, names the stop when it makes an on-this-spot location claim, and keeps a
# consistent relative-time phrasing. The full date is preserved for survival.
# ──────────────────────────────────────────────────────────────────────────────

# A sentence makes an "it happened HERE" location claim with one of these phrases.
# Generic deixis, no place name: "right here", "on this spot", "on this street",
# "in this building", "at this corner", "here, on a … street". Whitespace-tolerant.
_LOCATION_CLAIM_RE = re.compile(
    r"(?i)\b("
    r"right here"
    r"|here on (?:a|this|the)\b"
    r"|on this (?:spot|street|site|corner|square|avenue|boulevard|road|pavement|sidewalk)"
    r"|on these (?:steps|streets)"
    r"|at this (?:spot|street|site|corner|square|location|building|address)"
    r"|in this (?:building|house|hall|palace|room|very)"
    r"|outside this (?:building|house|hall)"
    r"|where you (?:are )?stand"
    r"|on the (?:spot|very spot) where"
    r"|at the (?:spot|very spot) where"
    r")\b")

# A sentence that CORRECTS or FLAGS a myth / misattribution about its subject.
# The marked (wrong) version may be told only as a myth correction (D760); it must
# never be picked as the stop's signature story nor protected at the gate.
_MYTH_MARKER_RE = re.compile(
    r"(?i)\b("
    r"often (?:wrongly |incorrectly |mistakenly |falsely )?(?:attributed|credited|said|claimed|believed|thought)"
    r"|wrongly attributed|incorrectly attributed|mistakenly attributed|falsely attributed"
    r"|commonly but incorrectly|popularly but"
    r"|contrary to (?:popular|common) (?:belief|opinion|myth)"
    r"|is a (?:myth|misconception|legend|popular myth|common myth)"
    r"|(?:a|the|this) (?:myth|misconception|legend|urban legend|folk tale|folklore)\b"
    r"|despite (?:the )?popular belief"
    r"|not (?:actually |in fact )?(?:designed|built|by)\b"
    r"|has no (?:actual |real )?(?:connection|link|involvement)"
    r"|no (?:evidence|record|proof) (?:that|of|for|supports)"
    r"|did not (?:design|build|create)"
    r"|was not (?:designed|built|created) by"
    r"|rumou?red|legend (?:has it|says)|it is said that"
    r")\b")

# A relative-time phrase relating two events: "months before X", "three years
# after Y", "weeks before …". We extract the unit and whether it is a "small"
# (days/weeks/months) or large (years/decades) gap, to contradict it against the
# actual gap between the two dates in the sentence/evidence.
_REL_TIME_RE = re.compile(
    r"(?i)\b(?:(?P<num>a|an|one|two|three|four|five|six|seven|eight|nine|ten|"
    r"eleven|twelve|several|a few|some|\d+)\s+)?"
    r"(?P<unit>day|days|week|weeks|month|months|year|years|decade|decades)\s+"
    r"(?P<dir>before|after|earlier than|later than|prior to)\b")

_MONTHS = ("january", "february", "march", "april", "may", "june", "july",
           "august", "september", "october", "november", "december")
_MONTH_IDX = {m: i + 1 for i, m in enumerate(_MONTHS)}
# common abbreviations
_MONTH_IDX.update({m[:3]: i + 1 for i, m in enumerate(_MONTHS)})
_MONTH_IDX["sept"] = 9

_YEAR_RE = re.compile(r"(?<!\d)(1[5-9]\d\d|20\d\d)(?!\d)")
# "30 April 1975" / "April 30, 1975" / "1 July 1962"
_FULL_DATE_RE = re.compile(
    r"(?i)\b(?:"
    r"(?P<d1>\d{1,2})\s+(?P<m1>january|february|march|april|may|june|july|august|"
    r"september|october|november|december)\s+(?P<y1>1[5-9]\d\d|20\d\d)"
    r"|(?P<m2>january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\s+(?P<d2>\d{1,2}),?\s+(?P<y2>1[5-9]\d\d|20\d\d)"
    r")\b")


def source_full_date(text: str) -> Optional[Dict[str, int]]:
    """The first full (day, month, year) date in ``text`` as {'day','month','year'},
    or None. Used so the survival check and the regeneration prompt keep a story's
    exact date (the wave-39 Palace lost '30 April 1975')."""
    m = _FULL_DATE_RE.search(text or "")
    if not m:
        return None
    if m.group("y1"):
        return {"day": int(m.group("d1")), "month": _MONTH_IDX[m.group("m1").lower()],
                "year": int(m.group("y1"))}
    return {"day": int(m.group("d2")), "month": _MONTH_IDX[m.group("m2").lower()],
            "year": int(m.group("y2"))}


def _date_tokens(d: Dict[str, int]) -> List[str]:
    """['30', 'april', '1975'] forms a body must carry to keep a full date."""
    month = _MONTHS[d["month"] - 1]
    return [str(d["day"]), month, str(d["year"])]


def body_keeps_date(body: str, d: Optional[Dict[str, int]]) -> bool:
    """When the story's source has a full date, the delivered body must carry its
    MONTH and YEAR (the day may be dropped). True when no full date to keep."""
    if not d:
        return True
    low = _fold(body)
    month = _MONTHS[d["month"] - 1]
    year = str(d["year"])
    return (year in low) and (month in low or month[:3] in low)


def _stop_name_tokens(stop_title: str, aliases: Optional[List[str]] = None) -> set:
    """Distinctive tokens that NAME this stop: its title + aliases, minus the
    generic venue vocabulary (so "Opera House" contributes nothing, but "Saigon",
    "Bạch Đằng", "Nguyễn Văn Bình" do). Used to test whether a source sentence
    names the stop as the place of an event."""
    toks: set = set()
    for s in [stop_title] + list(aliases or []):
        toks |= _content_tokens(s or "")
    return {t for t in toks if t not in _GENERIC_VENUE}


def _distinctive_name_phrases(stop_title: str,
                              aliases: Optional[List[str]] = None) -> List[str]:
    """The folded distinctive-name PHRASE of the stop and each alias: the title
    with generic venue words removed, kept in order ("nguyen van binh" from
    "Nguyễn Văn Bình Book Street", "bach dang" from "Bạch Đằng Pier"). Used so a
    coincidental single shared token (the common surname "Nguyễn" in "Nguyễn Văn
    Lém") does not count as naming the stop — the ordered name must appear."""
    out: List[str] = []
    for s in [stop_title] + list(aliases or []):
        toks = [t for t in re.findall(r"[a-z0-9]+", _fold(s or ""))
                if t not in _GENERIC_VENUE and t not in _STOP and len(t) >= 2]
        if toks:
            out.append(" ".join(toks))
    return out


def source_names_stop(source_sentence: str, stop_title: str,
                      aliases: Optional[List[str]] = None,
                      *, min_overlap: int = 1) -> bool:
    """True when the source sentence NAMES this stop as the place.

    A stop with a MULTI-token distinctive name ("Nguyễn Văn Bình", "Bạch Đằng")
    must appear as its ORDERED phrase — so the Loan/Lém fact ("Nguyễn Ngọc Loan …
    Nguyễn Văn Lém on a Saigon street"), which shares only the common tokens
    "nguyễn"/"văn", does NOT count as naming the Book Street. A stop whose
    distinctive name is a single token is matched on that token."""
    phrases = _distinctive_name_phrases(stop_title, aliases)
    if not phrases:
        return False
    folded_src = _fold(source_sentence)
    multi = [p for p in phrases if " " in p]
    if multi:
        return any(p in folded_src for p in multi) or any(
            " " not in p and p in _content_tokens(source_sentence) for p in phrases)
    # single-token distinctive names: a token match is enough.
    want = _stop_name_tokens(stop_title, aliases)
    have = _content_tokens(source_sentence)
    return len(want & have) >= min_overlap


def location_claim_ok(story: str, source_sentence: str, stop_title: str,
                      aliases: Optional[List[str]] = None) -> bool:
    """A location claim ("right here", "on this spot", "in this building") is only
    allowed when the SOURCE sentence names this stop as the place. A city-wide
    event pinned to the stop with deixis ("executed … right here on a Saigon
    street", on a stop the source does not name) fails and the story is dropped.

    A story with no such location claim passes trivially."""
    blob = f"{story} {source_sentence}"
    if not _LOCATION_CLAIM_RE.search(blob):
        return True
    return source_names_stop(source_sentence, stop_title, aliases)


def evidence_flags_myth(story: str, source_sentence: str,
                        own_evidence: str) -> bool:
    """True when the stop's OWN evidence flags a myth / misattribution that the
    story would repeat as fact. Two triggers, both generic:

      (a) the source sentence ITSELF carries a myth marker (so telling it straight
          launders a flagged myth — "designed by Eiffel" where the source reads
          "often attributed to Eiffel … actually by Foulhoux"); or
      (b) a DIFFERENT sentence in the evidence carries a myth marker that shares a
          distinctive subject token with the story (the evidence corrects the very
          claim the story makes).
    """
    if _MYTH_MARKER_RE.search(source_sentence or ""):
        return True
    story_tok = _content_tokens(story) | _content_tokens(source_sentence)
    story_tok = {t for t in story_tok if t not in _GENERIC_VENUE and not t.isdigit()}
    if not story_tok:
        return False
    for sent in _sentences(own_evidence or ""):
        if not _MYTH_MARKER_RE.search(sent):
            continue
        if len(story_tok & _content_tokens(sent)) >= 2:
            return True
    return False


def relative_time_consistent(sentence: str, *, extra_dates: str = "") -> bool:
    """A phrase relating two dated events ("months/years before/after X") must
    agree with the actual gap between the dates in the sentence (plus any
    ``extra_dates`` from evidence/body). True when there is no relative-time
    phrase, or when the stated magnitude matches the real gap.

    Generic: it compares the phrase's unit (day/week/month vs. year/decade)
    against the number of years between the two earliest full-year dates found.
    The wave-39 "months before … 31 October 1966" with a Nov 1963 event (a
    three-year gap) is rejected."""
    m = _REL_TIME_RE.search(sentence or "")
    if not m:
        return True
    years = sorted({int(y) for y in _YEAR_RE.findall(
        f"{sentence} {extra_dates}")})
    if len(years) < 2:
        return True              # only one date present: nothing to contradict
    gap_years = max(years) - min(years)
    unit = m.group("unit").lower().rstrip("s")
    # "months/weeks/days" claim a gap under a year; "years/decades" a year or more.
    if unit in ("day", "week", "month"):
        return gap_years < 1
    if unit == "year":
        # "X years": if a number is given, it should be within 1 of the real gap;
        # a bare "years" just needs a multi-year gap.
        num = (m.group("num") or "").strip().lower()
        want = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
                "seven": 7, "eight": 8, "nine": 9, "ten": 10, "a": 1, "an": 1}.get(num)
        if want is None and num.isdigit():
            want = int(num)
        if want is None:
            return gap_years >= 1
        return abs(gap_years - want) <= 1
    if unit == "decade":
        return gap_years >= 8
    return True


def story_from_own_source(source_sentence: str, own_evidence: str,
                          page_facts: Optional[List[Dict]] = None,
                          stop_title: str = "",
                          aliases: Optional[List[str]] = None) -> bool:
    """True when the story's source sentence comes from the stop's OWN source:

      * it is supported by ``own_evidence`` (the stop's own Wikipedia article —
        name-matched + geo-gated upstream, LOCAL-878/881); OR
      * it is supported by one of ``page_facts`` (873 thin-stop pages) AND that
        page fact NAMES the stop. A 873 page may add detail, but it may only be
        the SIGNATURE source when its sentence names the stop (D881).
    """
    if _quote_in_evidence(source_sentence, own_evidence or ""):
        return True
    for f in (page_facts or []):
        txt = f.get("text", "") if isinstance(f, dict) else str(f)
        if not txt:
            continue
        if _quote_in_evidence(source_sentence, txt):
            # a 873 page fact is an acceptable signature source only if it names
            # the stop (so a city-wide fact pinned to this stop is rejected).
            return source_names_stop(source_sentence, stop_title, aliases) \
                or source_names_stop(txt, stop_title, aliases)
    return False


def _build_user_prompt(title: str, evidence_text: str, location: str) -> str:
    ev = (evidence_text or "")[:MAX_INPUT_CHARS]
    return (
        f"STOP: {title}\n"
        f"CITY/AREA: {location or '(unspecified)'}\n\n"
        "EVIDENCE (the only source you may use):\n"
        f"{ev}\n\n"
        "TASK: choose the 1 or 2 MOST MEMORABLE true stories a guide could tell "
        "here, ranked by human interest — an event, a person, a conflict, a "
        "surprise, a famous book or film. A date or a dimension on its own is "
        "NOT a story. If the evidence holds no memorable story, return an empty "
        "list; do not manufacture one.\n\n"
        "For EACH story return an object with exactly these keys:\n"
        '  "story": one or two sentences telling it (plain, concrete),\n'
        '  "why_memorable": a short phrase (event / person / conflict / '
        'surprise / book or film),\n'
        '  "source_sentence": a sentence COPIED VERBATIM from the evidence above '
        "that supports the story.\n\n"
        'Respond as JSON: {"stories": [ {…}, {…} ]} with at most 2 items.'
    )


def _price_call(in_tokens: int, out_tokens: int, model: str) -> float:
    # gpt-4.1-mini public rates (USD per 1M tokens): $0.40 in, $1.60 out.
    rate_in, rate_out = 0.40, 1.60
    if "gpt-4.1" in model and "mini" not in model:
        rate_in, rate_out = 2.00, 8.00
    return in_tokens / 1e6 * rate_in + out_tokens / 1e6 * rate_out


def _default_narrate(system: str, user: str, model: str, *,
                     temperature: float = TEMPERATURE,
                     timeout: int = 30, max_tokens: int = MAX_TOKENS
                     ) -> Tuple[Optional[dict], int, int]:
    """One JSON call. Returns (parsed|None, in_tokens, out_tokens). Billed by the
    project meter (plain requests.post the live meter intercepts). Never raises;
    returns (None, 0, 0) with no key or on any failure."""
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key:
        return None, 0, 0
    try:
        import requests
    except Exception:
        return None, 0, 0
    try:
        resp = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            data=json.dumps({
                "model": model,
                "messages": [{"role": "system", "content": system},
                             {"role": "user", "content": user}],
                "temperature": float(temperature), "max_tokens": int(max_tokens),
                "response_format": {"type": "json_object"},
            }),
            timeout=timeout,
        )
        if resp.status_code != 200:
            return None, 0, 0
        body = resp.json()
        usage = body.get("usage", {}) or {}
        content = body["choices"][0]["message"]["content"]
        return (json.loads(content),
                int(usage.get("prompt_tokens", 0)),
                int(usage.get("completion_tokens", 0)))
    except Exception:
        return None, 0, 0


def select_signature_stories(
        title: str, evidence_text: str, *, location: str = "",
        narrate_fn: Optional[Callable] = None, model: str = MODEL,
        max_stories: int = 2, log: Optional[Callable] = None,
        own_evidence_text: Optional[str] = None,
        page_facts: Optional[List[Dict]] = None,
        aliases: Optional[List[str]] = None,
        ) -> Tuple[List[Dict[str, str]], Dict]:
    """Pick 1–2 signature stories for one stop from its own evidence.

    Returns ``(stories, report)``. ``stories`` is a list of validated dicts
    ``{story, why_memorable, source_sentence}`` (0–2 items). A story is kept ONLY
    when its ``source_sentence`` is supported by the evidence and the story reads
    like a story (not a lone dimension). ``report`` carries ``cost_usd`` and
    counts. Never raises.

    LOCAL-881 — the story must come from the stop's OWN source, and must not be a
    myth, an off-site event, or a mis-dated claim:
      * ``own_evidence_text`` is the stop's OWN article (name-matched + geo-gated
        upstream). When given, the source sentence must come from it, OR from a
        ``page_facts`` (873 thin-stop page) entry that NAMES the stop. The 873
        page facts may add detail but may not be the signature source on their own.
        When ``own_evidence_text`` is None, ``evidence_text`` is treated as the
        own evidence (backward-compatible).
      * a story whose own evidence FLAGS a myth / misattribution about it is
        rejected (it may be told only as a myth correction, D760);
      * a location claim ("right here", "on this spot") is dropped unless the
        source sentence NAMES this stop as the place;
      * a relative-time phrase ("months before X") that disagrees with the dates
        is rejected;
      * each kept story carries ``source_date`` (day/month/year) when its source
        has a full date, so the survival check and regeneration keep it.
    """
    rep = {"title": title, "cost_usd": 0.0, "returned": 0, "kept": 0,
           "dropped_unsourced": 0, "dropped_off_source": 0, "dropped_myth": 0,
           "dropped_location": 0, "dropped_rel_time": 0}
    if not (title and (evidence_text or "").strip()):
        return [], rep
    own_ev = own_evidence_text if own_evidence_text is not None else evidence_text
    fn = narrate_fn or _default_narrate
    user = _build_user_prompt(title, evidence_text, location)
    try:
        parsed, in_tok, out_tok = fn(_SYSTEM, user, model,
                                     max_tokens=MAX_TOKENS)
    except TypeError:
        # an injected narrate_fn with the (system, user, model) signature only
        parsed, in_tok, out_tok = fn(_SYSTEM, user, model)
    except Exception:
        parsed, in_tok, out_tok = None, 0, 0
    rep["cost_usd"] = _price_call(in_tok or 0, out_tok or 0, model)
    if not isinstance(parsed, dict):
        return [], rep
    raw = parsed.get("stories") or parsed.get("signature_stories") or []
    if isinstance(raw, dict):
        raw = [raw]
    kept: List[Dict[str, str]] = []
    for item in (raw or [])[:max_stories]:
        if not isinstance(item, dict):
            continue
        rep["returned"] += 1
        story = str(item.get("story") or "").strip()
        why = str(item.get("why_memorable") or "").strip()
        src = str(item.get("source_sentence") or "").strip()
        if not (story and src):
            continue
        if not _looks_like_story(story):
            continue
        if not _quote_in_evidence(src, evidence_text):
            rep["dropped_unsourced"] += 1
            if log:
                log(f"  [LOCAL-880] signature story for {title}: DROPPED "
                    f"(source_sentence not in evidence): {story[:60]}")
            continue
        # [LOCAL-881 §1] The story's source must be the stop's OWN source: its own
        # article, or a 873 page fact that NAMES the stop. A 873 page fact that
        # does not name the stop is detail only, never the signature source.
        if not story_from_own_source(src, own_ev, page_facts, title, aliases):
            rep["dropped_off_source"] += 1
            if log:
                log(f"  [LOCAL-881] signature story for {title}: DROPPED "
                    f"(not from the stop's own source): {story[:60]}")
            continue
        # [LOCAL-881 §3] The evidence must not flag this as a myth / misattribution.
        if evidence_flags_myth(story, src, own_ev):
            rep["dropped_myth"] += 1
            if log:
                log(f"  [LOCAL-881] signature story for {title}: DROPPED "
                    f"(evidence flags a myth / misattribution): {story[:60]}")
            continue
        # [LOCAL-881 §2] A location claim needs a source that names the stop.
        if not location_claim_ok(story, src, title, aliases):
            rep["dropped_location"] += 1
            if log:
                log(f"  [LOCAL-881] signature story for {title}: DROPPED "
                    f"(location claim not named in source): {story[:60]}")
            continue
        # [LOCAL-881 §5] A relative-time phrase must agree with the dates.
        if not (relative_time_consistent(story, extra_dates=src)
                and relative_time_consistent(src, extra_dates=own_ev)):
            rep["dropped_rel_time"] += 1
            if log:
                log(f"  [LOCAL-881] signature story for {title}: DROPPED "
                    f"(relative-time phrase contradicts the dates): {story[:60]}")
            continue
        entry = {"story": story, "why_memorable": why, "source_sentence": src}
        # [LOCAL-881 §6] keep the story's exact date so survival/regen preserve it.
        _d = source_full_date(src) or source_full_date(story)
        if _d:
            entry["source_date"] = _d
        kept.append(entry)
    rep["kept"] = len(kept)
    if log:
        for k in kept:
            log(f"  [LOCAL-880] signature story for {title}: {k['story'][:60]}")
        if not kept:
            log(f"  [LOCAL-880] signature story for {title}: none "
                f"(no memorable sourced story in evidence)")
    return kept, rep


def required_element_block(stories: List[Dict[str, str]]) -> str:
    """Prompt block telling the narrator to TELL each signature story. Appended
    LAST to the description prompt (recency bias). Empty string when no story."""
    if not stories:
        return ""
    lines = [
        "",
        "━━━ SIGNATURE STORY — TELL THIS (LOCAL-880, the most memorable true "
        "moment at this stop) ━━━",
        "Your narration MUST tell the following story (or both, if two are "
        "given), in the guide's voice, as the emotional centre of the stop. "
        "Each is drawn from the evidence above and is TRUE — use the source "
        "sentence as your fact, not as a quote to read aloud:",
    ]
    for i, s in enumerate(stories, 1):
        lines.append(f"  {i}. {s['story']}")
        if s.get("why_memorable"):
            lines.append(f"     (why it lands: {s['why_memorable']})")
        if s.get("source_sentence"):
            lines.append(f"     (source: {s['source_sentence']})")
        # [LOCAL-881 §6] name the exact date so the narrator keeps it in full.
        _d = s.get("source_date") if isinstance(s, dict) else None
        if _d:
            lines.append(
                f"     (state this date in full: {_d['day']} "
                f"{_MONTHS[_d['month'] - 1].capitalize()} {_d['year']})")
    lines.append(
        "Do not reduce the story to a bare date or dimension. Do not drop it for "
        "a generic description. Tell it.")
    lines.append("━━━ END SIGNATURE STORY ━━━")
    lines.append("")
    return "\n".join(lines)


# Generic venue vocabulary: shared by a stop's name and any description, so it
# does NOT prove the story was told. "The opera house is elegant" must not count
# as telling "Allied bombing in 1944". Distinctive tokens (1944, allied, bombing,
# Greene, quiet, american) do.
#
# D769: this set names NO proof tour's city, country or demonym. Place words are
# generic only *relative to the tour* — "saigon"/"vietnam"/"vietnamese" for a
# Saigon tour, "paris"/"france"/"french" for a Paris tour — so they are derived
# at run time from the tour's location and the stop title (see
# ``derive_generic_tokens``) and unioned in by the caller, never hard-coded here.
_GENERIC_VENUE = {
    "opera", "house", "building", "theatre", "theater", "cathedral", "basilica",
    "church", "palace", "hall", "museum", "street", "pier", "wharf", "quay",
    "bar", "cafe", "apartment", "apartments", "office", "post", "city", "town",
    "square", "centre", "center", "station", "market", "park", "river", "bridge",
    "tower", "towers", "gate", "gates", "monument", "landmark", "place", "site",
    "venue", "visitors", "visitor", "today", "stands", "located", "stop",
    "guide", "tour", "walk", "walking", "street", "road", "boulevard", "avenue",
    "colonial",
}


# Country/major-city -> demonym, for deriving a tour's own place words. Small and
# additive: an unlisted place simply contributes its own name (and a suffix-based
# demonym guess), never another tour's. D769: nothing here is specific to one
# proof tour — it is a general gazetteer fragment.
_DEMONYMS = {
    "vietnam": "vietnamese", "france": "french", "italy": "italian",
    "spain": "spanish", "germany": "german", "china": "chinese",
    "japan": "japanese", "thailand": "thai", "cambodia": "cambodian",
    "england": "english", "britain": "british", "scotland": "scottish",
    "ireland": "irish", "portugal": "portuguese", "greece": "greek",
    "turkey": "turkish", "russia": "russian", "poland": "polish",
    "sweden": "swedish", "norway": "norwegian", "denmark": "danish",
    "netherlands": "dutch", "belgium": "belgian", "austria": "austrian",
    "switzerland": "swiss", "mexico": "mexican", "brazil": "brazilian",
    "argentina": "argentine", "australia": "australian", "india": "indian",
    "korea": "korean", "egypt": "egyptian", "morocco": "moroccan",
    "america": "american", "canada": "canadian", "usa": "american",
    "paris": "parisian", "rome": "roman", "london": "londoner",
    "vienna": "viennese", "naples": "neapolitan", "venice": "venetian",
}


def _location_words(location: str) -> List[str]:
    """Split a location string ('Ho Chi Minh City, Vietnam') into folded word
    tokens, dropping generic geography words ('city', 'province')."""
    skip = {"city", "province", "region", "district", "state", "county",
            "area", "centre", "center", "greater", "metropolitan"}
    words = re.findall(r"[a-z]+", _fold(location))
    return [w for w in words if len(w) >= 3 and w not in skip]


def derive_generic_tokens(location: str = "", title: str = "") -> set:
    """The place words that are generic *for this tour*: the folded tokens of the
    tour's location and the stop title, plus any demonym of a location token
    (vietnam -> vietnamese, france -> french). These are generic only relative to
    the tour, so they are derived at run time and never stored in _GENERIC_VENUE
    (D769). A Paris tour yields {paris, france, french, parisian, …}; a Saigon
    tour {ho, chi, minh, saigon, vietnam, vietnamese, …}."""
    toks: set = set()
    loc_words = _location_words(location)
    for w in loc_words:
        toks.add(w)
        dem = _DEMONYMS.get(w)
        if dem:
            toks.add(dem)
    # the stop title's own words are generic (they name the venue, which cannot
    # prove its story was told).
    for w in re.findall(r"[a-z]+", _fold(title)):
        if len(w) >= 3:
            toks.add(w)
    return toks


def story_key_tokens(story: Dict[str, str], *,
                     generic_extra: Optional[set] = None) -> set:
    """The DISTINCTIVE tokens that identify the story in a delivered body: the
    union of the story and its source sentence, minus stopwords, minus generic
    venue vocabulary AND minus the tour's own derived place words
    (``generic_extra``). A 4-digit year always counts as distinctive."""
    toks = _content_tokens(story.get("story", ""))
    toks |= _content_tokens(story.get("source_sentence", ""))
    years = {t for t in toks if re.fullmatch(r"(1[5-9]|20)\d\d", t)}
    generic = _GENERIC_VENUE | (generic_extra or set())
    distinctive = {t for t in toks if t not in generic and not t.isdigit()}
    return distinctive | years


def body_tells_story(body: str, story: Dict[str, str], *,
                     min_overlap: int = 2,
                     generic_extra: Optional[set] = None) -> bool:
    """Post-narration check: does the delivered body actually tell the story?

    True when the body shares at least ``min_overlap`` DISTINCTIVE tokens with the
    story (names, places, events, years) — generic venue vocabulary and the tour's
    own derived place words (``generic_extra``) do not count. Deliberately lenient
    on wording (the narrator rephrases) but strict on the story's distinctive
    nouns/years being present.

    [LOCAL-881 §6] When the story carries a full ``source_date`` (day/month/year),
    the body must ALSO keep its MONTH and YEAR — the wave-39 Palace kept "a tank
    broke through the gates" but lost "30 April 1975", so it would have passed the
    token check yet failed the date. The date is re-required here.
    """
    _d = story.get("source_date") if isinstance(story, dict) else None
    if _d and not body_keeps_date(body, _d):
        return False
    want = story_key_tokens(story, generic_extra=generic_extra)
    if len(want) < min_overlap:
        # a tiny story: require its source quote to be (fuzzily) present
        return _quote_in_evidence(story.get("source_sentence", ""), body,
                                  min_overlap=max(2, len(want)))
    btok = _content_tokens(body)
    return len(want & btok) >= min_overlap


# ── block grammar (shared with the 855B/873B scrubs) ────────────────────────────
_STOP_HEADER_RE = re.compile(r"(?mi)^Stop\s+(\d+):\s*(.+)$")
_FIELD_RE = re.compile(
    r"(?i)^(Coordinates|Type/Specialty|Specific Examples|Directions|Address|"
    r"Museum Information|Operational Details|Sources|Orientation):")


def _split_blocks(text: str):
    """Yield (stop_num, title, full_block_text) for each 'Stop N:' block."""
    titles = _STOP_HEADER_RE.findall(text or "")
    parts = re.split(r"(?mi)^Stop\s+\d+:\s*.+$", text or "")
    out = []
    for (n, t), body in zip(titles, parts[1:]):
        out.append((int(n), t.strip(), body))
    return out


def _block_body_prose(block_text: str) -> str:
    """The narration prose of a block: field lines and the Orientation label
    removed, Directions dropped."""
    out = []
    for line in block_text.split("\n"):
        s = line.strip()
        if not s:
            continue
        m = re.match(r"(?i)^orientation:\s*(.*)$", s)
        if m:
            if m.group(1).strip():
                out.append(m.group(1).strip())
            continue
        if _FIELD_RE.match(s):
            continue
        out.append(s)
    return " ".join(out)


def regenerate_body_with_story(
        title: str, current_body_prose: str, stories: List[Dict[str, str]],
        facts: Optional[List[str]] = None, *, location: str = "",
        narrate_fn: Optional[Callable] = None, model: str = MODEL,
        min_sentences: int = 5, max_sentences: int = 8,
        log: Optional[Callable] = None,
        ) -> Tuple[Optional[List[str]], Dict]:
    """ONE gpt-4.1-mini call that rewrites a stop's body so it TELLS the signature
    story, keeping the correct material already present. Constrained to the given
    facts + the story's source sentences (never invent). Returns
    ``(sentences|None, report)``; None when the call fails or the result still
    does not tell the story — the caller then leaves the original body untouched.
    Billed by the project meter; <= one extra call per missing-story stop."""
    rep = {"title": title, "cost_usd": 0.0, "regenerated": False}
    if not (title and stories):
        return None, rep
    fn = narrate_fn or _default_narrate
    fact_lines = list(facts or [])
    for s in stories:
        if s.get("source_sentence"):
            fact_lines.append(s["source_sentence"])
    story_lines = "\n".join(f"- {s['story']}" for s in stories)
    facts_blob = "\n".join(f"- {f}" for f in fact_lines if f and f.strip())
    system = (
        "You rewrite one walking-tour stop as spoken narration (second person, "
        "present tense). You use ONLY the facts given, never invent, and you make "
        "the required signature story the emotional centre of the stop."
    )
    # [LOCAL-881 §6] Pass the story's EXACT full date so the rewrite keeps it. The
    # wave-39 Palace regeneration dropped "30 April 1975"; naming the date as a
    # required element makes the survival check (which now re-requires the month
    # and year) pass.
    _date_lines = []
    for s in stories:
        _d = s.get("source_date") if isinstance(s, dict) else None
        if _d:
            _date_lines.append(
                f"- {_d['day']} {_MONTHS[_d['month'] - 1].capitalize()} {_d['year']}")
    _date_block = ("\nYou MUST state this exact date, in full (day, month and "
                   "year):\n" + "\n".join(dict.fromkeys(_date_lines)) + "\n"
                   ) if _date_lines else ""
    user = (
        f"STOP: {title}\nCITY/AREA: {location or '(unspecified)'}\n\n"
        f"REQUIRED SIGNATURE STORY (must be told):\n{story_lines}\n"
        f"{_date_block}\n"
        f"FACTS YOU MAY USE (the only source):\n{facts_blob}\n\n"
        f"EXISTING BODY (keep the correct, on-topic parts):\n{current_body_prose}\n\n"
        f"TASK: write {min_sentences}-{max_sentences} spoken sentences for this "
        "stop. The signature story MUST be told clearly. Keep accurate existing "
        "material; drop filler. Do not invent facts, dates, or quotations.\n"
        'Respond as JSON: {"sentences": ["…", "…"]}'
    )
    try:
        parsed, in_tok, out_tok = fn(system, user, model, max_tokens=700)
    except TypeError:
        parsed, in_tok, out_tok = fn(system, user, model)
    except Exception:
        parsed, in_tok, out_tok = None, 0, 0
    rep["cost_usd"] = _price_call(in_tok or 0, out_tok or 0, model)
    if not isinstance(parsed, dict):
        return None, rep
    sents = parsed.get("sentences") or parsed.get("body") or []
    if isinstance(sents, str):
        sents = _sentences(sents)
    sents = [str(x).strip() for x in sents if str(x).strip()]
    if len(sents) < min_sentences:
        return None, rep
    joined = " ".join(sents)
    # the rewrite must actually tell EVERY required story, else reject it. Place
    # words of this tour (from the location + stop title) are generic, not story
    # evidence, so they are excluded from the match (D769, derived at run time).
    _gx = derive_generic_tokens(location, title)
    if not all(body_tells_story(joined, s, generic_extra=_gx) for s in stories):
        if log:
            log(f"  [LOCAL-880] regen for {title}: result still missing the "
                f"signature story — keeping original body")
        return None, rep
    rep["regenerated"] = True
    return sents, rep


def ensure_signature_in_tour(
        tour_text: str, stories_by_title: Dict[str, List[Dict[str, str]]],
        facts_by_title: Optional[Dict[str, List[str]]] = None, *,
        location: str = "", narrate_fn: Optional[Callable] = None,
        model: str = MODEL, max_regens: int = 10, log: Optional[Callable] = None,
        ) -> Tuple[str, Dict]:
    """Post-narration: for each stop that has a signature story but whose
    delivered body does NOT tell it, regenerate that stop ONCE. Returns
    ``(new_tour_text, report)``. Deterministic block edit; the only cost is the
    at-most-one regen call per missing-story stop. Never raises."""
    rep = {"checked": 0, "missing": 0, "regenerated": 0, "cost_usd": 0.0,
           "regenerated_stops": []}
    if not (tour_text and stories_by_title):
        return tour_text, rep
    facts_by_title = facts_by_title or {}

    def _norm(s):
        return _fold(s)

    # map normalised title -> stories (stop titles in the text may differ in case
    # / diacritics from the sink key)
    norm_stories = {_norm(k): v for k, v in stories_by_title.items() if v}
    norm_facts = {_norm(k): v for k, v in facts_by_title.items()}

    blocks = _split_blocks(tour_text)
    regens = 0
    new_text = tour_text
    for stop_num, title, block in blocks:
        key = _norm(title)
        stories = norm_stories.get(key)
        if not stories:
            # also try a looser containment match
            for nk, v in norm_stories.items():
                if nk and (nk in key or key in nk):
                    stories = v
                    break
        if not stories:
            continue
        rep["checked"] += 1
        body_prose = _block_body_prose(block)
        # place words of this tour (location + this stop's title) are generic and
        # must not count as telling the story (D769, derived at run time).
        _gx = derive_generic_tokens(location, title)
        if all(body_tells_story(body_prose, s, generic_extra=_gx) for s in stories):
            continue
        rep["missing"] += 1
        if regens >= max_regens:
            continue
        facts = norm_facts.get(key) or []
        if not facts:
            for nk, v in norm_facts.items():
                if nk and (nk in key or key in nk):
                    facts = v
                    break
        sents, r = regenerate_body_with_story(
            title, body_prose, stories, facts, location=location,
            narrate_fn=narrate_fn, model=model, log=log)
        rep["cost_usd"] += r.get("cost_usd", 0.0)
        regens += 1
        if not sents:
            continue
        new_text = _replace_block_body(new_text, stop_num, title, sents)
        rep["regenerated"] += 1
        rep["regenerated_stops"].append(title)
        if log:
            log(f"  [LOCAL-880] regenerated Stop {stop_num} '{title[:40]}' to tell "
                f"its signature story")
    return new_text, rep


def _replace_block_body(tour_text: str, stop_num: int, title: str,
                        new_sentences: List[str]) -> str:
    """Replace the narration body of one 'Stop N:' block with new_sentences,
    preserving the header, Coordinates/Type/Specific Examples/Orientation lines
    and the trailing Directions line. Deterministic; returns the original text on
    any parse miss."""
    lines = tour_text.split("\n")
    # find the header line for this stop
    hdr_idx = None
    for i, ln in enumerate(lines):
        m = re.match(r"(?i)^Stop\s+(\d+):\s*(.+)$", ln.strip())
        if m and int(m.group(1)) == stop_num:
            hdr_idx = i
            break
    if hdr_idx is None:
        return tour_text
    # the block runs until the next Stop header or EOF
    end_idx = len(lines)
    for j in range(hdr_idx + 1, len(lines)):
        if re.match(r"(?i)^Stop\s+\d+:", lines[j].strip()):
            end_idx = j
            break
    head_keep = []     # header + field lines + Orientation (through its blank line)
    directions = []    # trailing Directions line(s)
    k = hdr_idx
    head_keep.append(lines[k])
    k += 1
    # keep leading field lines and the Orientation line + its paragraph
    while k < end_idx:
        s = lines[k].strip()
        if _FIELD_RE.match(s) or not s:
            head_keep.append(lines[k])
            k += 1
            # after an Orientation: label, keep its (possibly multi-line) paragraph
            if re.match(r"(?i)^orientation:", s):
                while k < end_idx and lines[k].strip():
                    head_keep.append(lines[k])
                    k += 1
        else:
            break
    # collect Directions line(s) from the tail of the block
    for j in range(end_idx - 1, k - 1, -1):
        if re.match(r"(?i)^Directions:", lines[j].strip()):
            directions = lines[j:end_idx]
            break
    new_block = list(head_keep)
    if new_block and new_block[-1].strip():
        new_block.append("")
    new_block.append(" ".join(new_sentences))
    if directions:
        new_block.append("")
        new_block.extend(d for d in directions if d.strip())
    return "\n".join(lines[:hdr_idx] + new_block + lines[end_idx:])
