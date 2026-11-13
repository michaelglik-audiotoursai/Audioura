#!/usr/bin/env python3
"""topic_library_build.py — LOCAL-907 (D772): build a region's topic segments ONCE.

    python3 topic_library_build.py --region <region_key> --max-segments 9 --dry-run
    python3 topic_library_build.py --region <region_key> --budget-usd 0.50
    python3 topic_library_build.py --region <region_key> --render-audio     # Kokoro (host)
    python3 topic_library_build.py --region <region_key> --language xx --from en

Pipeline per segment: plan -> fetch (Wikipedia, free, disk-cached, revision id kept) ->
write 1,500-2,200 spoken words (NARRATION_MODEL, gpt-4.1-mini) -> GROUND every sentence
against the fetched passages with the existing strict grounding gate (D771) -> keep the
survivors; fewer than 1,200 words => status 'rejected' -> append the credit line.

Money: every paid call is metered. ``--budget-usd`` stops the build; ``TASK_BUDGET_ID`` /
``TASK_BUDGET_USD`` (task_budget.py) are honoured too and the run's spend is appended to the
task ledger on exit. ``--dry-run`` plans and prices the build and spends $0.

Everything external (HTTP, LLM, grounding judge, translation engine, Kokoro, DB) is injected,
so the tests run fully offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import os
import re
import sys
import time
from typing import Any, Callable, Dict, List, Optional, Tuple

import topic_library as tl
import topic_relevance as tr
import wiki_client as wc

logger = logging.getLogger("topic_library")

NARRATION_MODEL = os.environ.get("NARRATION_MODEL", "gpt-4.1-mini")
TARGET_WORDS = 1900            # asked of the writer
MIN_WORDS_WRITTEN = 1500       # spec window
MAX_WORDS_WRITTEN = 2200
MIN_SURVIVOR_WORDS = 1200      # below this after grounding => rejected
MIN_SOURCE_WORDS = int(os.environ.get("TOPIC_MIN_SOURCE_WORDS", "500"))
MAX_OVERLAP = 0.30
GROUND_BATCH_SENTENCES = 20
CACHE_DIR = os.environ.get("TOPIC_SOURCE_CACHE", os.path.join(
    os.path.dirname(os.path.abspath(__file__)), "topic_source_cache"))
USER_AGENT = wc.USER_AGENT
MIN_LINKED_WORDS = int(os.environ.get("TOPIC_MIN_LINKED_WORDS", "800"))   # a linked stub cannot carry a segment
MAX_LINK_LOOKUPS = int(os.environ.get("TOPIC_MAX_LINK_LOOKUPS", "1500"))

# gpt-4.1-mini published rates, USD per 1M tokens (the live meter stays authoritative).
RATE_IN, RATE_OUT = 0.40, 1.60
# Calls reserved before they are made (budget pre-check).
GROUND_RESERVE_USD = 0.003


def llm_cost(in_tok: int, out_tok: int) -> float:
    return round(in_tok / 1e6 * RATE_IN + out_tok / 1e6 * RATE_OUT, 6)


# ═════════════════════════════════════════════════════════════════════════════
# metering
# ═════════════════════════════════════════════════════════════════════════════
class BudgetStop(Exception):
    """The build budget (--budget-usd or the task budget) would be crossed."""


class BuildMeter:
    """Accumulates the run's paid spend and refuses calls that would cross a budget."""

    def __init__(self, budget_usd: Optional[float], task_id: Optional[str] = None):
        self.budget_usd = budget_usd
        self.task_id = task_id if task_id is not None else _task_id()
        self.spent = 0.0
        self.calls = 0
        self.exhausted = False
        self.grounding_failures = 0     # judge calls that returned nothing usable

    def room_for(self, pending_usd: float) -> bool:
        if self.budget_usd is not None and self.spent + pending_usd > self.budget_usd + 1e-9:
            return False
        if self.task_id:
            try:
                import task_budget
                task_budget.check_task_budget(pending_usd=self.spent + pending_usd,
                                              task_id=self.task_id)
            except Exception as e:                       # BudgetExceeded
                if e.__class__.__name__ == "BudgetExceeded":
                    return False
                raise
        return True

    def require(self, pending_usd: float) -> None:
        if not self.room_for(pending_usd):
            self.exhausted = True
            raise BudgetStop(f"budget reached: spent ${self.spent:.4f}, next call ~${pending_usd:.4f}")

    def charge(self, usd: float) -> None:
        self.spent += max(0.0, float(usd))
        self.calls += 1

    def wrap_classify(self, classify_fn: Callable) -> Callable:
        """Wrap the grounding judge: budget-check before, charge after. When the budget is
        gone it returns (None, 0, 0) and sets ``exhausted`` (the caller aborts the segment —
        the gate itself would KEEP sentences it could not judge)."""
        def _fn(system, user, model, *a, **kw):
            if not self.room_for(GROUND_RESERVE_USD):
                self.exhausted = True
                return None, 0, 0
            parsed, in_tok, out_tok = classify_fn(system, user, model, *a, **kw)
            self.charge(llm_cost(in_tok, out_tok))
            if not isinstance(parsed, dict) or not parsed.get("verdicts"):
                self.grounding_failures += 1
            return parsed, in_tok, out_tok
        return _fn

    def finish(self, note: str = "topic_library_build") -> None:
        """Append this run to the task ledger (append-only; best effort)."""
        if self.task_id and self.spent > 0:
            try:
                import task_budget
                task_budget.record_run(self.task_id, self.spent, note=note,
                                       capped=self.exhausted)
            except Exception:
                pass


def _task_id() -> Optional[str]:
    try:
        import task_budget
        return task_budget.task_id_from_env()
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# fetch (Wikipedia / Wikivoyage action API: free, no key) + disk cache
# ═════════════════════════════════════════════════════════════════════════════
def _default_http_get(url: str, params: Dict[str, Any]) -> Dict[str, Any]:
    """Polite GET (User-Agent, serial >= 200 ms apart, maxlag=5, 429/503 backoff, 5 tries).
    Raises wiki_client.WikiFetchError when it still fails; callers skip that page."""
    return wc.default_client().get_json(url, params)


def _site_of(title: str) -> Tuple[str, str]:
    """'voyage:Foo' -> ('wikivoyage','Foo'); otherwise ('wikipedia', title)."""
    if title.lower().startswith("voyage:"):
        return "wikivoyage", title.split(":", 1)[1].strip()
    return "wikipedia", title.strip()


def _cache_path(cache_dir: str, lang: str, site: str, title: str) -> str:
    h = hashlib.sha1(f"{site}|{lang}|{title}".encode("utf-8")).hexdigest()[:16]
    safe = re.sub(r"[^A-Za-z0-9]+", "_", title)[:40]
    return os.path.join(cache_dir, f"{site}_{lang}_{safe}_{h}.json")


def fetch_article(lang: str, title: str, *, cache_dir: Optional[str] = None,
                  http_get: Optional[Callable] = None) -> Optional[Dict[str, Any]]:
    """One article: {lang, site, title, url, revision_id, licence, text, links}. None when the
    page does not exist. Cached on disk (never committed)."""
    cache_dir = cache_dir or CACHE_DIR
    site, name = _site_of(title)
    path = _cache_path(cache_dir, lang, site, name)
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            return json.load(fh) or None
    get = http_get or _default_http_get
    api = f"https://{lang}.{site}.org/w/api.php"
    data = get(api, {"action": "query", "format": "json", "formatversion": "2",
                     "prop": "extracts|revisions|info", "explaintext": "1",
                     "exsectionformat": "wiki", "rvprop": "ids", "inprop": "url",
                     "redirects": "1", "titles": name})
    pages = (data.get("query") or {}).get("pages") or []
    page = pages[0] if pages else {}
    if not page or page.get("missing") or not page.get("extract"):
        art = None
    else:
        links: List[str] = []
        params = {"action": "query", "format": "json", "formatversion": "2", "prop": "links",
                  "pllimit": "max", "plnamespace": "0", "titles": page.get("title", name)}
        for _ in range(4):                               # bounded paging
            ld = get(api, dict(params))
            for p in (ld.get("query") or {}).get("pages") or []:
                links += [l["title"] for l in p.get("links", []) if l.get("title")]
            cont = (ld.get("continue") or {}).get("plcontinue")
            if not cont:
                break
            params["plcontinue"] = cont
        revs = page.get("revisions") or [{}]
        art = {"lang": lang, "site": site, "title": page.get("title", name),
               "url": page.get("fullurl") or f"https://{lang}.{site}.org/wiki/{name.replace(' ', '_')}",
               "revision_id": revs[0].get("revid"), "licence": tl.LICENCE,
               "text": page["extract"], "links": links}
    os.makedirs(cache_dir, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(art, fh, ensure_ascii=False)
    return art


_HEADING_RE = re.compile(r"(?m)^(={2,6})\s*(.+?)\s*\1\s*$")
SKIP_HEADINGS = {"see also", "references", "external links", "further reading", "notes",
                 "bibliography", "sources", "gallery", "footnotes", "citations",
                 "notes and references", "references and sources", "in the news",
                 "sister cities", "twin towns", "notable people", "notable residents"}


def split_sections(text: str) -> Tuple[str, List[Dict[str, Any]]]:
    """(lead, top-level sections). A top-level (==) section carries its sub-sections' text."""
    ms = list(_HEADING_RE.finditer(text or ""))
    if not ms:
        return (text or "").strip(), []
    lead = text[:ms[0].start()].strip()
    sections: List[Dict[str, Any]] = []
    for i, m in enumerate(ms):
        body = text[m.end(): ms[i + 1].start() if i + 1 < len(ms) else len(text)]
        level, heading = len(m.group(1)), m.group(2).strip()
        if level == 2:
            sections.append({"heading": heading, "text": body.strip(), "subs": []})
        elif sections:
            sections[-1]["text"] += "\n\n" + heading + ".\n" + body.strip()
            sections[-1]["subs"].append(heading)
    for s in sections:
        s["text"] = s["text"].strip()
        s["words"] = tl.word_count(s["text"])
    return lead, [s for s in sections if s["heading"].lower() not in SKIP_HEADINGS]


# ═════════════════════════════════════════════════════════════════════════════
# plan
# ═════════════════════════════════════════════════════════════════════════════
_TOKEN_RE = re.compile(r"[^\W_]{3,}", re.UNICODE)
_TITLE_STOP = {"the", "and", "for", "from", "with", "county", "city", "province", "history"}


def _fold(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s.lower()) if not unicodedata.combining(c))


def title_tokens(title: str, region_tokens: frozenset = frozenset()) -> frozenset:
    toks = {_fold(t) for t in _TOKEN_RE.findall(title or "")}
    return frozenset(t for t in toks if t not in _TITLE_STOP and t not in region_tokens)


def region_tokens(region: Dict[str, Any], language: str) -> frozenset:
    """Tokens shared by the region's own name / seed titles — they say 'this region', not a
    topic, so they must not count as overlap between two topics."""
    names = [region.get("display_name", "")] + [_site_of(t)[1] for t in
                                                region.get("seed_articles", {}).get(language, [])]
    counts: Dict[str, int] = {}
    for n in names:
        for t in set(_TOKEN_RE.findall(_fold(n))):
            counts[t] = counts.get(t, 0) + 1
    toks = set(_TOKEN_RE.findall(_fold(region.get("display_name", ""))))
    toks |= {t for t, c in counts.items() if c >= 2}
    return frozenset(t for t in toks if t not in _TITLE_STOP)


def topic_tokens(text: str, rtoks: frozenset) -> frozenset:
    """Tokens that identify a topic. Falls back to the raw words when stripping the region and
    generic words leaves nothing (so two sections both called 'History' still overlap fully)."""
    t = title_tokens(text, rtoks)
    if t:
        return t
    return frozenset(_fold(x) for x in _TOKEN_RE.findall(text or "")) - rtoks


def overlap(a: frozenset, b: frozenset) -> float:
    """Shared title/section tokens over the smaller token set (0 when either is empty)."""
    if not a or not b:
        return 0.0
    return len(a & b) / float(min(len(a), len(b)))


def _topic_title(article_title: str, heading: Optional[str]) -> str:
    if not heading:
        return article_title
    if _fold(article_title) in _fold(heading):
        return heading
    return f"{article_title}: {heading}"


def _safe_fetch(fetch_fn: Callable, lang: str, title: str) -> Optional[Dict[str, Any]]:
    """A page that fails after the retries is skipped and logged, never a crash."""
    try:
        return fetch_fn(lang, title)
    except wc.WikiFetchError as e:
        logger.warning("[LOCAL-907B] fetch of '%s' skipped: %s", title, e)
        return None


def _hint_entries(region: Dict[str, Any], language: str) -> List[Dict[str, Optional[str]]]:
    """topic_hints[language]: a title string, or {"title":..., "theme":...} (an editorial
    theme for a curated hint; the article's own lead/categories are tried first)."""
    raw = (region.get("topic_hints") or {}).get(language) or []
    out = []
    for h in raw:
        if isinstance(h, str):
            out.append({"title": h, "theme": None})
        elif isinstance(h, dict) and h.get("title"):
            out.append({"title": h["title"], "theme": h.get("theme")})
    return out


def plan_topics(region: Dict[str, Any], language: str, max_segments: int, *,
                fetch_fn: Callable[[str, str], Optional[Dict[str, Any]]],
                meta_fn: Optional[Callable] = None) -> List[Dict[str, Any]]:
    """Choose up to ``max_segments`` topics across the region's themes. No two topics overlap
    by more than MAX_OVERLAP (title / section tokens). Fetches are free; no paid call.

    Order of preference: seed sections -> topic_hints -> linked articles that pass the
    relevance gate (LOCAL-907B). With ``meta_fn`` (lang, titles -> metadata) the hints are
    used and linked articles are gated, classified from their own lead + categories, and
    dropped when off-region. Without it (legacy / offline callers) linked articles are
    taken by link-title keyword as before."""
    seeds = region.get("seed_articles", {}).get(language) or []
    themes = region.get("default_themes") or tl.THEMES
    rtoks = region_tokens(region, language)
    # words that recur across the curated hint titles (a country / city / "people") say "this
    # region", not "this topic": they must not make two different topics look alike
    _hc: Dict[str, int] = {}
    for h in _hint_entries(region, language):
        for t in set(title_tokens(h["title"])):
            _hc[t] = _hc.get(t, 0) + 1
    rtoks = frozenset(rtoks | {t for t, c in _hc.items() if c >= 3} |
                      {_fold(x) for x in region.get("generic_tokens", [])})
    cands: Dict[str, List[Dict[str, Any]]] = {t: [] for t in themes}
    seen_titles = set()
    arts = []
    for seed in seeds:
        art = _safe_fetch(fetch_fn, language, seed)
        if art:
            arts.append(art)
    seed_names = {tr.fold(a["title"]) for a in arts} | {tr.fold(_site_of(x)[1]) for x in seeds}
    for art in arts:
        _lead, sections = split_sections(art["text"])
        if not any(x["words"] >= MIN_SOURCE_WORDS for x in sections) and \
                tl.word_count(art["text"]) >= MIN_SOURCE_WORDS:
            # a short / flat seed article: the article itself is the topic
            theme = tl.classify_theme(art["title"]) or "modern"
            if theme in cands:
                cands[theme].append({
                    "theme": theme, "title": art["title"], "tokens": topic_tokens(art["title"], rtoks),
                    "sources": [{"lang": language, "article": art["title"], "site": art["site"],
                                 "section": None}],
                    "source_words": tl.word_count(art["text"]), "score": 1200, "lazy": False,
                    "tier": 3, "reason": "seed", "url": art.get("url")})
        for s in sections:
            if s["words"] < MIN_SOURCE_WORDS:
                continue
            theme = tl.classify_theme(s["heading"]) or tl.classify_theme(art["title"])
            if theme not in cands:
                continue
            cands[theme].append({
                "theme": theme, "title": _topic_title(art["title"], s["heading"]),
                "tokens": topic_tokens(s["heading"], rtoks),
                "sources": [{"lang": language, "article": art["title"], "site": art["site"],
                             "section": s["heading"]}],
                "source_words": s["words"], "score": min(s["words"], 2500), "lazy": False,
                "tier": 3, "reason": "seed", "url": art.get("url")})
    n_dropped = 0
    if meta_fn is not None:
        hints = _hint_entries(region, language)
        hmeta = meta_fn(language, [h["title"] for h in hints]) if hints else {}
        for h in hints:
            m = hmeta.get(h["title"])
            if m is None:
                logger.warning("[LOCAL-907B] hint '%s' skipped: lookup failed", h["title"])
                continue
            if not m.get("exists"):
                logger.info("[LOCAL-907B] hint '%s' dropped: page does not exist", h["title"])
                continue
            title = m["title"]
            if tr.fold(title) in seen_titles or tr.fold(title) in seed_names:
                continue
            seen_titles.add(tr.fold(title))
            if tr.is_list_or_disambiguation(m):
                logger.info("[LOCAL-907B] hint '%s' dropped: list/disambiguation page", title)
                continue
            # a curated hint carries its editorial theme; otherwise the article's own lead
            # and categories decide (None -> dropped, never a guess)
            theme = h["theme"] or tr.classify_article(title, m.get("lead", ""), m.get("categories", []))
            if theme not in cands:
                logger.info("[LOCAL-907B] hint '%s' dropped: no clear theme", title)
                continue
            cands[theme].append({
                "theme": theme, "title": title, "tokens": topic_tokens(title, rtoks),
                "sources": [{"lang": language, "article": title, "site": "wikipedia", "section": None}],
                "source_words": 0, "score": 1500, "lazy": True, "tier": 2, "reason": "hint",
                "url": m.get("url")})
        links: List[str] = []
        for art in arts:
            for link in art.get("links", []):
                if link not in links and tr.fold(link) not in seen_titles \
                        and tr.fold(link) not in seed_names and not tr.title_excluded(link):
                    links.append(link)
        if len(links) > MAX_LINK_LOOKUPS:
            logger.info("[LOCAL-907B] %d linked titles; looking up the first %d",
                        len(links), MAX_LINK_LOOKUPS)
            links = links[:MAX_LINK_LOOKUPS]
        lmeta = meta_fn(language, links) if links else {}
        for link in links:
            m = lmeta.get(link)
            if not m or not m.get("exists"):
                continue
            title = m["title"]
            if tr.fold(title) in seen_titles or tr.fold(title) in seed_names:
                continue
            ok, reason, scores = tr.check_relevance(m, region)
            if not ok and reason != "mentions-pending":
                n_dropped += 1
                logger.info("[LOCAL-907B] topic '%s' dropped: %s (%s)",
                            title, "off-region" if reason == "off-region" else reason, scores)
                continue
            theme = tr.classify_article(title, m.get("lead", ""), m.get("categories", []))
            if theme not in cands:
                logger.info("[LOCAL-907B] topic '%s' dropped: no clear theme (uncategorised)", title)
                continue
            seen_titles.add(tr.fold(title))
            cands[theme].append({
                "theme": theme, "title": title, "tokens": topic_tokens(title, rtoks),
                "sources": [{"lang": language, "article": title, "site": "wikipedia", "section": None}],
                "source_words": 0, "lazy": True, "tier": 1, "reason": reason, "url": m.get("url"),
                "score": 900 + {"coord": 60, "category": 40, "mentions": 20}.get(reason, 0),
                "meta": m, "scores": scores})
    else:
        for art in arts:                                  # legacy: link-title keyword, no gate
            for link in art.get("links", []):
                theme = tl.classify_theme(link)
                if theme not in cands or link in seen_titles:
                    continue
                seen_titles.add(link)
                cands[theme].append({
                    "theme": theme, "title": link, "tokens": topic_tokens(link, rtoks),
                    "sources": [{"lang": language, "article": link, "site": "wikipedia",
                                 "section": None}],
                    "source_words": 0, "score": 900, "lazy": True, "tier": 1,
                    "reason": "linked (ungated)", "url": None})
    for t in cands:
        cands[t].sort(key=lambda c: (-c["tier"], -c["score"], c["title"]))
    chosen: List[Dict[str, Any]] = []

    def _ok(c: Dict[str, Any]) -> bool:
        return all(overlap(c["tokens"], x["tokens"]) <= MAX_OVERLAP for x in chosen) and \
            c["title"] not in {x["title"] for x in chosen}

    progressed = True
    while len(chosen) < max_segments and progressed:
        progressed = False
        for theme in themes:
            if len(chosen) >= max_segments:
                break
            pool = cands.get(theme, [])
            while pool:
                c = pool.pop(0)
                if not _ok(c):
                    continue
                if c["lazy"]:                             # fetch to learn the size, then vet it
                    a = _safe_fetch(fetch_fn, language, c["sources"][0]["article"])
                    if not a:
                        continue
                    if c.get("reason") == "mentions-pending":
                        ok, reason, scores = tr.check_relevance(c["meta"], region, full_text=a["text"])
                        if not ok:
                            logger.info("[LOCAL-907B] topic '%s' dropped: off-region (%s)",
                                        c["title"], scores)
                            continue
                        c["reason"] = reason
                    c["source_words"] = tl.word_count(a["text"])
                    c["url"] = c.get("url") or a.get("url")
                    if c["source_words"] < (MIN_LINKED_WORDS if c.get("tier") == 1 else MIN_SOURCE_WORDS):
                        continue
                    c["lazy"] = False
                chosen.append(c)
                progressed = True
                break
    for i, c in enumerate(chosen, 1):
        c["key"] = f"{region['region_key']}:{language}:{i}"
        c["est_cost_usd"] = estimate_segment_cost(c["source_words"])
    return chosen


def estimate_segment_cost(source_words: int) -> float:
    """Write call + ceil(sentences/20) grounding calls (conservative: full evidence window)."""
    ev_tok = int(min(source_words, 7000) * 1.4)
    write = llm_cost(ev_tok + 450, int(TARGET_WORDS * 1.4))
    batches = max(1, -(-int(TARGET_WORDS / 17) // GROUND_BATCH_SENTENCES))
    ground = batches * llm_cost(1500 + GROUND_BATCH_SENTENCES * 35 + 600, 500)
    return round(write + ground, 4)


def theme_counts(topics: List[Dict[str, Any]], themes: Optional[List[str]] = None) -> Dict[str, int]:
    out = {t: 0 for t in (themes or tl.THEMES)}
    for t in topics:
        out[t["theme"]] = out.get(t["theme"], 0) + 1
    return out


def format_plan(region: Dict[str, Any], language: str, topics: List[Dict[str, Any]]) -> str:
    themes = region.get("default_themes") or tl.THEMES
    counts = theme_counts(topics, themes)
    lines = [f"Plan for {region['region_key']} ({language}): {len(topics)} topics, "
             f"{len({t['theme'] for t in topics})} themes"]
    for i, t in enumerate(topics, 1):
        lines.append(f"  {i:>2}. [{t['theme']:<16}] {t['title']}  "
                     f"(why: {t.get('reason', '?')}; source {t['source_words']} words; "
                     f"est ${t['est_cost_usd']:.4f})")
        if t.get("url"):
            lines.append(f"        {t['url']}")
    lines.append("Themes: " + ", ".join(f"{k}={v}" for k, v in counts.items()))
    thin = [k for k, v in counts.items() if v < 2]
    covered = sum(1 for v in counts.values() if v >= 2)
    lines.append(f"Themes with >= 2 topics: {covered}/{len(counts)}"
                 + (f"  |  thin: {', '.join(thin)}" if thin else ""))
    total = sum(t["est_cost_usd"] for t in topics)
    lines.append(f"Estimated paid cost: ${total:.4f}  |  spent by this plan: $0.0000 (dry run)")
    return "\n".join(lines)


# ═════════════════════════════════════════════════════════════════════════════
# write
# ═════════════════════════════════════════════════════════════════════════════
WRITER_SYSTEM = (
    "You write one segment of a spoken audio guide, to be heard while travelling between "
    "stops. Use ONLY the facts in the SOURCE passages the user gives you; add nothing from "
    "memory. Write about %d words of plain spoken English prose (never fewer than %d, never "
    "more than %d), in this order:\n"
    "1. First line: a single-sentence hook that makes the listener curious.\n"
    "2. Then flowing paragraphs separated by blank lines.\n"
    "Spoken register: short sentences, one idea each. NO citations, NO footnote marks, NO "
    "parentheses, NO brackets, NO tables, NO lists, NO headings, NO markdown. Write years as "
    "digits (for example 1975), because the voice reads them naturally. Spell out symbols "
    "and abbreviations a voice would stumble on. Never mention 'the source', 'the article' "
    "or 'Wikipedia'. Do not write a closing credit; it is added separately."
    % (TARGET_WORDS, MIN_WORDS_WRITTEN, MAX_WORDS_WRITTEN))


def default_llm(system: str, user: str, model: str, max_tokens: int) -> Tuple[str, int, int]:
    """ONE chat-completion call (billed by the project meter, which intercepts requests.post).
    Returns (text, in_tokens, out_tokens); raises on failure."""
    import requests
    key = os.environ.get("OPENAI_API_KEY", "")
    if not key:
        raise RuntimeError("OPENAI_API_KEY not set")
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
        data=json.dumps({"model": model, "temperature": 0.4, "max_tokens": max_tokens,
                         "messages": [{"role": "system", "content": system},
                                      {"role": "user", "content": user}]}),
        timeout=120)
    resp.raise_for_status()
    body = resp.json()
    usage = body.get("usage") or {}
    return (body["choices"][0]["message"]["content"],
            int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))


_CITE_RE = re.compile(r"\[[^\]]*\]")
_PAREN_RE = re.compile(r"\s*\([^()]*\)")


def clean_spoken(text: str) -> str:
    """Strip what a voice must not read: citations, parentheses, markdown, table rows."""
    out = []
    for line in (text or "").replace("\r", "").split("\n"):
        s = line.strip()
        if "|" in s or re.match(r"^[-=_*#]{3,}$", s):
            continue
        s = re.sub(r"^(#{1,6}\s*|[-*•]\s+|\d+\.\s+)", "", s)
        s = _PAREN_RE.sub("", _CITE_RE.sub("", s)).replace("**", "").replace("__", "")
        s = re.sub(r"[ \t]+", " ", s).strip()
        out.append(s)
    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def gather_evidence(topic: Dict[str, Any], fetch_fn: Callable) -> Tuple[str, List[Dict[str, Any]]]:
    """(evidence text, sources[]) for a topic: its section(s) / article plus the article lead."""
    parts, sources, seen = [], [], set()
    for src in topic["sources"]:
        art = fetch_fn(src["lang"], src["article"] if src.get("site") != "wikivoyage"
                       else "voyage:" + src["article"])
        if not art:
            continue
        lead, sections = split_sections(art["text"])
        if src.get("section"):
            body = next((s["text"] for s in sections if s["heading"] == src["section"]), "")
            parts.append(f"{art['title']} — {src['section']}\n{body}")
            if lead:
                parts.append(f"{art['title']} — overview\n{' '.join(lead.split()[:700])}")
        else:
            parts.append(f"{art['title']}\n{' '.join(art['text'].split()[:5000])}")
        if art["url"] not in seen:
            seen.add(art["url"])
            sources.append({"url": art["url"], "title": art["title"], "lang": art["lang"],
                            "site": art["site"], "revision_id": art["revision_id"],
                            "licence": art.get("licence", tl.LICENCE),
                            "licence_url": tl.LICENCE_URL, "section": src.get("section")})
    return "\n\n".join(parts), sources


# ═════════════════════════════════════════════════════════════════════════════
# ground
# ═════════════════════════════════════════════════════════════════════════════
def _norm(s: str) -> str:
    return " ".join((s or "").split())


def ground_text(title: str, text: str, evidence: str, classify_fn: Callable,
                *, batch_sentences: int = GROUND_BATCH_SENTENCES) -> Tuple[str, Dict[str, int]]:
    """Run the strict grounding gate (strict_grounding_gate.apply_grounding_gate) over the text
    in batches of whole paragraphs. Unsupported / contradicted sentences are dropped; paragraph
    structure is kept. Returns (kept text, {"before","kept","dropped"})."""
    import strict_grounding_gate as sgg
    from sentence_split import split_sentences
    paras = [p for p in re.split(r"\n\s*\n", text.strip()) if p.strip()]
    batches: List[List[str]] = []
    cur: List[str] = []
    n = 0
    for p in paras:
        cur.append(p)
        n += len(split_sentences(p))
        if n >= batch_sentences:
            batches.append(cur)
            cur, n = [], 0
    if cur:
        batches.append(cur)
    kept_paras: List[str] = []
    before = kept = 0
    for batch in batches:
        body = "\n\n".join(batch)
        new_prose, _rep = sgg.apply_grounding_gate(title, body, evidence, classify_fn=classify_fn,
                                                   deny_check=False)
        survivors = [_norm(s) for s in split_sentences(new_prose)]
        ptr = 0
        for p in batch:
            keep = []
            for s in split_sentences(p):
                before += 1
                ns = _norm(s)
                if ptr < len(survivors) and survivors[ptr] == ns:
                    keep.append(s.strip())
                    ptr += 1
                    kept += 1
                elif ns in survivors[ptr:ptr + 3]:       # tolerate a gate-internal drop of a short fragment
                    ptr = survivors.index(ns, ptr) + 1
                    keep.append(s.strip())
                    kept += 1
            if keep:
                kept_paras.append(" ".join(keep))
    return "\n\n".join(kept_paras), {"before": before, "kept": kept, "dropped": before - kept}


# ═════════════════════════════════════════════════════════════════════════════
# build one segment / a region
# ═════════════════════════════════════════════════════════════════════════════
def build_segment(topic: Dict[str, Any], region: Dict[str, Any], language: str, *,
                  fetch_fn: Callable, llm_fn: Callable, classify_fn: Callable,
                  meter: BuildMeter, model: str = NARRATION_MODEL) -> Dict[str, Any]:
    """Write + ground one segment. Returns a topic_segments row (status ready / rejected).
    Raises BudgetStop (nothing paid is lost silently: spend so far stays in the meter)."""
    start_spent = meter.spent
    evidence, sources = gather_evidence(topic, fetch_fn)
    row: Dict[str, Any] = {
        "region_key": region["region_key"], "theme": topic["theme"], "title": topic["title"],
        "language": language, "text": "", "word_count": 0, "est_minutes": 0,
        "sources": sources, "credit_line": tl.CREDIT_LINE,
        "centroid_lat": region["centre"]["lat"], "centroid_lng": region["centre"]["lng"],
        "radius_km": region["radius_km"], "audio_path": None, "source_segment_id": None,
        "status": "rejected", "cost_usd": 0.0}
    if tl.word_count(evidence) < MIN_SOURCE_WORDS:
        row["reject_reason"] = "insufficient_source"
        return row
    meter.require(estimate_segment_cost(tl.word_count(evidence)) * 0.4)   # the write call
    user = (f"TOPIC: {topic['title']}\nTHEME: {topic['theme']}\nREGION: {region['display_name']}\n\n"
            f"SOURCE passages:\n{evidence}\n\nWrite the segment now.")
    written, in_tok, out_tok = llm_fn(WRITER_SYSTEM, user, model, int(MAX_WORDS_WRITTEN * 2.2))
    meter.charge(llm_cost(in_tok, out_tok))
    text = clean_spoken(written)
    fails_before, exhausted_before = meter.grounding_failures, meter.exhausted
    kept_text, stats = ground_text(topic["title"], text, evidence, meter.wrap_classify(classify_fn))
    if meter.exhausted and not exhausted_before:
        raise BudgetStop("budget reached while grounding; segment discarded")
    row["cost_usd"] = round(meter.spent - start_spent, 6)
    row["ground_stats"] = stats
    if meter.grounding_failures > fails_before:
        row["reject_reason"] = "grounding_unavailable"   # an unjudged sentence is never trusted
        return row
    words = tl.word_count(kept_text)
    row["survivor_words"] = words
    full = (kept_text + "\n\n" + tl.CREDIT_LINE).strip()
    row.update(text=full, word_count=tl.word_count(full), est_minutes=tl.est_minutes(tl.word_count(full)))
    if words >= MIN_SURVIVOR_WORDS:
        row["status"] = "ready"
    else:
        row["reject_reason"] = f"only {words} grounded words (< {MIN_SURVIVOR_WORDS})"
    return row


def run_build(region_key: str, language: str = "en", *, max_segments: int = 9,
              budget_usd: Optional[float] = None, dry_run: bool = False,
              store=None, fetch_fn: Optional[Callable] = None, llm_fn: Optional[Callable] = None,
              classify_fn: Optional[Callable] = None, regions_path: Optional[str] = None,
              meta_fn: Optional[Callable] = None,
              log: Callable[[str], None] = print) -> Dict[str, Any]:
    region = tl.get_region(region_key, regions_path)
    meta_fn = meta_fn
    if fetch_fn is None:
        fetch_fn = lambda lang, title: fetch_article(lang, title)       # noqa: E731
        if meta_fn is None:
            meta_fn = tr.WikiMeta()                      # real runs use the relevance gate
    topics = plan_topics(region, language, max_segments, fetch_fn=fetch_fn, meta_fn=meta_fn)
    summary: Dict[str, Any] = {"region": region_key, "language": language, "topics": topics,
                               "estimated_cost_usd": round(sum(t["est_cost_usd"] for t in topics), 4),
                               "spent_usd": 0.0, "built": [], "stopped_on_budget": False}
    if dry_run:
        summary["plan_text"] = format_plan(region, language, topics)
        log(summary["plan_text"])
        return summary
    if store is None:
        raise ValueError("a segment store is required for a real build")
    meter = BuildMeter(budget_usd)
    if budget_usd is None and not meter.task_id:
        raise ValueError("refusing to spend without a limit: pass --budget-usd or set "
                         "TASK_BUDGET_ID/TASK_BUDGET_USD")
    llm_fn = llm_fn or default_llm
    if classify_fn is None:
        import strict_grounding_gate as sgg
        classify_fn = sgg._default_classify
    existing = {s["title"] for s in store.list_segments(region_key, language)}
    last_cost = 0.0
    try:
        for topic in topics:
            if topic["title"] in existing:
                log(f"skip (already built): {topic['title']}")
                continue
            try:
                # reserve the larger of the estimate and what the last segment really cost
                meter.require(max(topic["est_cost_usd"], last_cost))
                row = build_segment(topic, region, language, fetch_fn=fetch_fn, llm_fn=llm_fn,
                                    classify_fn=classify_fn, meter=meter)
            except BudgetStop as e:
                summary["stopped_on_budget"] = True
                log(f"BUDGET STOP: {e}")
                break
            last_cost = row["cost_usd"]
            extra = {k: row.pop(k) for k in ("reject_reason", "ground_stats", "survivor_words") if k in row}
            sid = store.insert_segment(row)
            summary["built"].append({"id": sid, "title": row["title"], "status": row["status"],
                                     "words": row["word_count"], "cost_usd": row["cost_usd"], **extra})
            log(f"{row['status']:>8}  {row['title']}  ({row['word_count']} words, ${row['cost_usd']:.4f})"
                + (f"  [{extra.get('reject_reason')}]" if row["status"] == "rejected" else ""))
    finally:
        summary["spent_usd"] = round(meter.spent, 6)
        meter.finish(f"topic_library_build {region_key} {language}")
    return summary


# ═════════════════════════════════════════════════════════════════════════════
# translations (LLM engine only; never re-grounded)
# ═════════════════════════════════════════════════════════════════════════════
class TranslationEngineError(RuntimeError):
    pass


def make_llm_translate_fn(service=None) -> Callable[[str, str], Tuple[str, float]]:
    """translate_fn(text, lang) -> (translated, cost_usd) on translation_service's LLM engine.
    AWS Translate is NEVER used: the service is forced to engine 'llm' and its AWS fallback is
    replaced by an error, so a failing LLM call fails the segment instead of silently
    switching engine."""
    if service is None:
        service = _load_translation_service()
    service.translation_engine = "llm"

    def _no_aws(*_a, **_k):
        raise TranslationEngineError("LLM translation failed; AWS Translate is not allowed here")
    service._translate_text_aws = _no_aws

    def _fn(text: str, lang: str) -> Tuple[str, float]:
        before = float(getattr(service, "_llm_cost_total", 0.0) or 0.0)
        out = service.translate_text(text, lang)
        return out, max(0.0, float(getattr(service, "_llm_cost_total", 0.0) or 0.0) - before)
    return _fn


def _load_translation_service():
    import importlib.util
    os.environ["TRANSLATION_ENGINE"] = "llm"
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "translation-service", "translation_service.py")
    sys.path.insert(0, os.path.dirname(path))
    spec = importlib.util.spec_from_file_location("translation_service_llm", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.TranslationService()


def run_translate(region_key: str, language: str, from_language: str, *, store,
                  translate_fn: Callable[[str, str], Tuple[str, float]],
                  budget_usd: Optional[float] = None, max_segments: Optional[int] = None,
                  log: Callable[[str], None] = print) -> Dict[str, Any]:
    """Translate READY segments of ``from_language`` into ``language``. Keeps
    source_segment_id; the translation is not re-grounded (the source already was)."""
    meter = BuildMeter(budget_usd)
    if budget_usd is None and not meter.task_id:
        raise ValueError("refusing to spend without a limit: pass --budget-usd or set "
                         "TASK_BUDGET_ID/TASK_BUDGET_USD")
    done = {s["source_segment_id"] for s in store.list_segments(region_key, language)
            if s.get("source_segment_id")}
    out = {"region": region_key, "language": language, "translated": [], "stopped_on_budget": False}
    try:
        for src in store.list_segments(region_key, from_language, "ready"):
            if src["id"] in done:
                continue
            if max_segments is not None and len(out["translated"]) >= max_segments:
                break
            est = llm_cost(int(src["word_count"] * 1.5) + 300, int(src["word_count"] * 2.2))
            try:
                meter.require(est)
            except BudgetStop as e:
                out["stopped_on_budget"] = True
                log(f"BUDGET STOP: {e}")
                break
            text, c1 = translate_fn(src["text"], language)
            title, c2 = translate_fn(src["title"], language)
            credit, c3 = translate_fn(src["credit_line"], language)
            meter.charge(c1 + c2 + c3)
            row = {k: src[k] for k in ("region_key", "theme", "sources", "centroid_lat",
                                       "centroid_lng", "radius_km", "est_minutes")}
            row.update(title=title.strip(), language=language, text=text, credit_line=credit.strip(),
                       word_count=tl.word_count(text), audio_path=None,
                       source_segment_id=src["id"], status="ready", cost_usd=round(c1 + c2 + c3, 6))
            sid = store.insert_segment(row)
            out["translated"].append({"id": sid, "source_segment_id": src["id"], "title": row["title"]})
            log(f"translated #{src['id']} -> #{sid} ({language})")
    finally:
        out["spent_usd"] = round(meter.spent, 6)
        meter.finish(f"topic_library_build translate {region_key} {from_language}->{language}")
    return out


# ═════════════════════════════════════════════════════════════════════════════
# English audio (host Kokoro service)
# ═════════════════════════════════════════════════════════════════════════════
def default_render(text: str, voice: str) -> bytes:
    """POST {text, voice} to the host Kokoro service (KOKORO_URL) -> MP3 bytes."""
    import requests
    url = os.environ.get("KOKORO_URL", "http://localhost:5181/render").strip()
    if not url:
        raise RuntimeError("KOKORO_URL is empty; run this on the Mac with the host service up")
    r = requests.post(url, json={"text": text, "voice": voice}, timeout=600)
    r.raise_for_status()
    if not r.content:
        raise RuntimeError("Kokoro returned no audio")
    return r.content


def _chunks_for_tts(text: str, max_chars: int = 2500) -> List[str]:
    chunks, cur = [], ""
    for p in re.split(r"\n\s*\n", text):
        if cur and len(cur) + len(p) + 2 > max_chars:
            chunks.append(cur)
            cur = ""
        cur = (cur + "\n\n" + p).strip() if cur else p
    if cur:
        chunks.append(cur)
    return chunks


def run_render_audio(region_key: str, *, store, out_dir: str, render_fn: Callable = default_render,
                     voice: Optional[str] = None, language: str = "en",
                     log: Callable[[str], None] = print) -> List[int]:
    """Render ready English segments that have no audio. The stored audio_path is relative to
    ``out_dir`` (TOPIC_AUDIO_DIR). Kokoro runs on the host: no paid call."""
    voice = voice or os.environ.get("TOPIC_VOICE", "Joanna")
    rendered = []
    for seg in store.list_segments(region_key, language, "ready"):
        if seg.get("audio_path"):
            continue
        mp3 = b"".join(render_fn(c, voice) for c in _chunks_for_tts(seg["text"]))
        rel = os.path.join(region_key, language, f"segment_{seg['id']}.mp3")
        full = os.path.join(out_dir, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as fh:
            fh.write(mp3)
        store.set_audio_path(seg["id"], rel)
        rendered.append(seg["id"])
        log(f"audio #{seg['id']} -> {rel} ({len(mp3)} bytes)")
    return rendered


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════
def _parse(argv: Optional[List[str]]) -> argparse.Namespace:
    ap = argparse.ArgumentParser(description="Build a region's reusable topic segments (LOCAL-907).")
    ap.add_argument("--region", required=True)
    ap.add_argument("--language", default="en")
    ap.add_argument("--from", dest="from_language", default=None,
                    help="translate READY segments of this language (e.g. en) into --language")
    ap.add_argument("--max-segments", type=int, default=9)
    ap.add_argument("--budget-usd", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true", help="print the plan + estimated cost; spend $0")
    ap.add_argument("--render-audio", action="store_true", help="render English audio via KOKORO_URL")
    ap.add_argument("-v", "--verbose", action="store_true",
                    help="log every dropped / skipped topic ([LOCAL-907B] lines) to stderr")
    ap.add_argument("--audio-dir", default=os.environ.get("TOPIC_AUDIO_DIR", "topic_audio"))
    return ap.parse_args(argv)


def _open_store():
    import psycopg2
    return tl.PgSegmentStore(psycopg2.connect(os.environ["DATABASE_URL"]))


def main(argv: Optional[List[str]] = None) -> int:
    a = _parse(argv)
    logging.basicConfig(level=logging.INFO if a.verbose else logging.WARNING,
                        format="%(message)s", stream=sys.stderr)
    if a.dry_run:
        run_build(a.region, a.language, max_segments=a.max_segments, dry_run=True)
        return 0
    store = _open_store()
    if a.from_language:
        run_translate(a.region, a.language, a.from_language, store=store,
                      translate_fn=make_llm_translate_fn(), budget_usd=a.budget_usd,
                      max_segments=a.max_segments)
    elif a.language != "en":
        print("non-English segments are translations: pass --from en", file=sys.stderr)
        return 2
    elif a.budget_usd is not None or not a.render_audio:
        # build (existing titles are skipped); --render-audio alone, with no budget, only renders
        run_build(a.region, a.language, max_segments=a.max_segments, budget_usd=a.budget_usd, store=store)
    if a.render_audio:
        run_render_audio(a.region, store=store, out_dir=a.audio_dir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
