"""
language_guard.py — [LOCAL-616 item 3]
======================================
A site-scraped sentence must be in the tour language. Tour 414 (Musée Fabre, an
ENGLISH tour) shipped an untranslated French fragment lifted verbatim from the
museum's own French pages:

    "de Cherbourg, le musée Fabre expose une œuvre de jeunesse du peintre
     Jacques-Louis David"

This module adds a deterministic language check for scraped prose. Any scraped
sentence that is NOT in the tour language is either translated with a cheap LLM
(gpt-4o-mini, when OPENAI_API_KEY is set) or DROPPED (never shipped verbatim).

The check is intentionally conservative: it only flags a sentence as foreign when
the foreign-language signal clearly dominates and the English signal is weak, so a
normal English sentence that merely contains a loanword or a proper noun with an
accent (e.g. "Musée Fabre", "Cézanne") is never dropped. Silence on a dropped
sentence is correct — never ship text the listener cannot understand.
"""
from __future__ import annotations

import os
import re
from typing import List, Optional, Tuple

try:  # module-level logger, non-fatal if logging unconfigured
    import logging
    _logger = logging.getLogger(__name__)
except Exception:  # pragma: no cover
    _logger = None


# ── deterministic language detection ────────────────────────────────────────
#
# We detect "is this sentence in English?" with a stopword-ratio heuristic. English
# function words are extremely frequent in any genuine English sentence; the
# Romance-language function words below (fr/es/it/pt) are just as frequent in those
# languages and almost never form runs in English. We flag FOREIGN only when the
# foreign function-word hits clearly outnumber the English ones.

_EN_STOPWORDS = {
    "the", "a", "an", "and", "or", "but", "of", "to", "in", "on", "at", "by",
    "for", "with", "from", "as", "is", "are", "was", "were", "be", "been", "being",
    "it", "its", "this", "that", "these", "those", "he", "she", "they", "we", "you",
    "his", "her", "their", "our", "which", "who", "whom", "whose", "has", "have",
    "had", "will", "would", "can", "could", "about", "into", "over", "after",
    "before", "between", "through", "during", "where", "when", "while", "than",
    "then", "there", "here", "also", "known", "built", "founded", "opened",
    "houses", "holds", "collection", "museum", "gallery",
}

# Romance / common European function words (fr, es, it, pt, de) that do NOT occur
# in English. A short, high-precision list — only words that are unambiguous.
_FOREIGN_STOPWORDS = {
    # French
    "le", "la", "les", "un", "une", "des", "du", "de", "au", "aux", "et", "ou",
    "est", "sont", "sur", "dans", "avec", "pour", "par", "qui", "que", "ce",
    "cette", "ces", "son", "sa", "ses", "leur", "leurs", "musee", "peintre",
    "oeuvre", "jeunesse", "expose", "siecle", "ans", "ville", "eglise",
    # Spanish / Italian / Portuguese overlaps
    "el", "los", "las", "y", "en", "con", "por", "para", "del", "una",
    "e", "di", "il", "lo", "gli", "nel", "della", "museo",
    # German
    "und", "der", "die", "das", "den", "dem", "ein", "eine", "mit", "von",
    "im", "zum", "zur",
}

_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)

# Strip combining accents so "musée"→"musee", "siècle"→"siecle" match the ASCII
# keys above regardless of how the scrape encoded them.
def _deaccent(s: str) -> str:
    import unicodedata
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


def _tokens(text: str) -> List[str]:
    return [_deaccent(t.lower()) for t in _WORD_RE.findall(text or "")]


def is_in_tour_language(sentence: str, tour_language: str = "en") -> bool:
    """Return True when ``sentence`` is (plausibly) in the tour language.

    Only ``en`` (English) tours are actively guarded here — that is the shipping
    default and the tour-414 defect. For any other tour language we return True
    (no-op) so this guard never silently drops correct content in a non-English
    tour (that path has no reported defect and no reference signal to key on).

    English detection: compare English vs foreign function-word hits. We flag the
    sentence as NOT English only when foreign function words clearly dominate
    (``foreign >= en + 2`` and at least two foreign hits). Very short strings and
    strings with no alphabetic tokens are treated as in-language (nothing to drop).
    """
    if (tour_language or "en").split("-")[0].lower() != "en":
        return True
    raw = _WORD_RE.findall(sentence or "")
    toks = [_deaccent(t.lower()) for t in raw]
    if len(toks) < 4:
        # Too short to judge — a title fragment or label; leave it to other guards.
        return True
    en_hits = sum(1 for t in toks if t in _EN_STOPWORDS)
    # [LOCAL-616] Count a FOREIGN function word as evidence ONLY when its original
    # token is lowercase. A French article inside a Title-Cased work name
    # ("La Mort de la Vierge", "La Vierge au chanoine Van der Paele") is a proper
    # noun, not foreign prose — if counted, a normal English sentence that merely
    # names a French-titled painting ("Your first stop is La Mort de la Vierge")
    # would be wrongly flagged. Genuine foreign prose (the tour-414 fragment
    # "de Cherbourg, le musée Fabre expose une œuvre…") carries its function words
    # in lowercase, between lowercase content words, so it is still caught.
    fr_hits = sum(1 for orig, t in zip(raw, toks)
                  if t in _FOREIGN_STOPWORDS and orig[:1].islower())
    # Clear foreign dominance → not English.
    if fr_hits >= 2 and fr_hits >= en_hits + 2:
        return False
    return True


# ── cheap-LLM translation (optional) ─────────────────────────────────────────

def translate_to_english(sentence: str, model: str = "gpt-4o-mini",
                          timeout: int = 20) -> Optional[str]:
    """Translate ``sentence`` to English with a cheap LLM. Returns the English
    text, or None when no API key is set or the call fails (caller then DROPS).

    Deterministic in tests: with no OPENAI_API_KEY the function returns None
    immediately (no network), so the filter below drops foreign sentences offline.
    """
    api_key = os.environ.get("OPENAI_API_KEY", "")
    if not api_key or not (sentence or "").strip():
        return None
    try:
        import json
        import urllib.request
        prompt = (
            "Translate the following sentence into natural, spoken English for an "
            "audio tour. Preserve proper nouns (names of people, works, places). "
            "Respond with ONLY the English translation, no quotes, no explanation.\n\n"
            f"{sentence.strip()}"
        )
        data = json.dumps({
            "model": model,
            "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 160,
            "temperature": 0.2,
        }).encode()
        req = urllib.request.Request(
            "https://api.openai.com/v1/chat/completions",
            data=data,
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode())
            reply = (body["choices"][0]["message"]["content"] or "").strip()
        reply = reply.strip().strip('"').strip()
        if not reply:
            return None
        # Guard against the model echoing the still-foreign text back.
        if not is_in_tour_language(reply, "en"):
            return None
        return reply
    except Exception as _e:  # pragma: no cover - network/parse failures
        if _logger:
            _logger.info(f"[LOCAL-616] translate_to_english skipped ({_e})")
        return None


def filter_scraped_sentences(sentences: List[str], tour_language: str = "en",
                             translate: bool = True) -> List[str]:
    """Return ``sentences`` with every non-tour-language sentence translated (cheap
    LLM) or dropped. Order preserved. Never ships a verbatim foreign sentence.

    ``translate=False`` forces drop-only (deterministic, no network) — used by the
    pure-code path and tests.
    """
    out: List[str] = []
    for s in sentences or []:
        if not s or not s.strip():
            continue
        if is_in_tour_language(s, tour_language):
            out.append(s)
            continue
        # Foreign sentence: translate or drop.
        rendered = translate_to_english(s) if translate else None
        if rendered:
            if _logger:
                _logger.info("[LOCAL-616] translated scraped foreign sentence")
            out.append(rendered)
        else:
            if _logger:
                _logger.info(
                    f"[LOCAL-616] dropped non-{tour_language} scraped sentence: {s[:60]!r}")
    return out


# Structural one-liners in a delivered tour that must never be language-judged.
_STRUCT_LINE_RE = re.compile(
    r"(?i)^(Stop\s+\d+:|Address:|Coordinates:|Directions:|Sources?:|"
    r"Tour-Category:|Type/?Specialty:|Specific Examples?:|Operational Details:|"
    r"Museum Information:|Orientation:|Step-by-Step)")


def filter_foreign_sentences_in_text(text: str, tour_language: str = "en",
                                     translate: bool = False) -> Tuple[str, List[str]]:
    """[LOCAL-616 item 3] Sweep a DELIVERED tour's spoken text and drop (or
    translate) any genuinely-foreign sentence, wherever in the pipeline it entered
    (story corpus, closing recap, …). Returns (new_text, dropped).

    Operates paragraph-by-paragraph, sentence-by-sentence. Structural one-liners
    (Stop/Address/Coordinates/Directions/Sources/…) are passed through untouched —
    they are never judged. Prose paragraphs keep their English sentences and drop
    foreign ones. Conservative: uses the hardened detector, so an English sentence
    naming a French-titled work is kept; only true foreign prose is removed. The
    optional ``Orientation: `` prefix on a paragraph is preserved.
    """
    if not text:
        return text, []
    dropped: List[str] = []
    out_blocks: List[str] = []
    # Split on blank-line boundaries, keeping separators to rebuild spacing.
    parts = re.split(r"(\n\s*\n)", text)
    for part in parts:
        if re.fullmatch(r"\n\s*\n", part or ""):
            out_blocks.append(part)
            continue
        stripped = (part or "").strip()
        if not stripped or _STRUCT_LINE_RE.match(stripped.split("\n", 1)[0].strip()):
            out_blocks.append(part)
            continue
        # Preserve a leading "Orientation:" label on the block, judge the rest.
        prefix = ""
        body = stripped
        m = re.match(r"(?i)^(Orientation:\s*)(.*)$", stripped, re.DOTALL)
        if m:
            prefix, body = m.group(1), m.group(2)
        sentences = re.split(r"(?<=[.!?])\s+", body)
        kept = []
        for sent in sentences:
            if not sent.strip():
                continue
            if is_in_tour_language(sent, tour_language):
                kept.append(sent)
                continue
            rendered = translate_to_english(sent) if translate else None
            if rendered:
                kept.append(rendered)
            else:
                dropped.append(sent.strip())
                if _logger:
                    _logger.info(
                        f"[LOCAL-616] dropped foreign spoken sentence: {sent[:60]!r}")
        new_body = " ".join(kept).strip()
        out_blocks.append((prefix + new_body) if new_body else prefix.strip())
    new_text = "".join(b for b in out_blocks)
    # Collapse any blank-line runs we may have opened by emptying a block.
    new_text = re.sub(r"\n{3,}", "\n\n", new_text)
    return new_text, dropped
