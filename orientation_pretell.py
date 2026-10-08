"""
orientation_pretell.py — [LOCAL-618 #1] Keep the Stop-1 orientation from
pre-telling the whole tour.

The critic's Sevilla review named this blocker: the Stop-1 orientation
concatenates per-stop facts (the Part-4 forward-connection builder), so the
listener hears every stop's dated events and proper nouns a minute before they
reach them. The orientation should be 2–3 sentences: where you are, what thread
connects the stops, and where Stop 1 is — with NO facts that belong to a later
stop.

This module is pure and deterministic (no network / LLM / DB), so every rule is
unit-tested and cannot drift at runtime. The generator wires `strip_later_stop_facts`
onto the DELIVERED Stop-1 orientation text, after Part 4 has been folded in.
"""
import re
from typing import Dict, List, Tuple

__all__ = [
    "extract_later_stop_terms",
    "sentence_delivers_later_stop_fact",
    "strip_later_stop_facts",
    "build_forward_connection_prompt",
]

# Words that look like proper nouns but are too generic to count as a "later-stop
# fact" (they appear everywhere and would over-trigger the strip).
_GENERIC_PROPER = {
    "the", "a", "an", "this", "that", "stop", "stops", "tour", "museum", "gallery",
    "collection", "work", "works", "artist", "painting", "paintings", "room",
    "first", "second", "third", "next", "final", "last", "you", "your",
    "orientation", "it", "its", "here", "there", "where", "what", "who",
    "january", "february", "march", "april", "may", "june", "july", "august",
    "september", "october", "november", "december",
}


def _proper_nouns(text: str) -> List[str]:
    """Capitalised multi/word tokens that are not sentence-initial generic words."""
    out = []
    for m in re.finditer(r"\b([A-Z][a-zà-ÿ]+(?:\s+[A-Z][a-zà-ÿ]+)*)\b", text):
        phrase = m.group(1).strip()
        # Reject phrases whose words are ALL generic (e.g. "The Museum").
        words = [w for w in phrase.split() if w.lower() not in _GENERIC_PROPER]
        if words:
            out.append(phrase)
    return out


def _significant_words(phrase: str) -> List[str]:
    return [w for w in re.split(r"\s+", phrase) if len(w) > 3 and w.lower() not in _GENERIC_PROPER]


def extract_later_stop_terms(later_stop_names: List[str],
                             later_stop_texts: List[str]) -> Dict[str, set]:
    """Collect the proper nouns and 3–4 digit years that belong to stops ≥2.

    Returns {"proper": set[str lower], "years": set[str]}. Stop *names* of later
    stops are included (naming a later stop in Stop 1 is itself a pre-tell).
    """
    proper: set = set()
    years: set = set()
    for name in later_stop_names:
        for w in _significant_words(name):
            proper.add(w.lower())
    for text in later_stop_texts:
        for ph in _proper_nouns(text):
            for w in _significant_words(ph):
                proper.add(w.lower())
        for y in re.findall(r"\b(1\d{3}|20\d{2})\b", text):
            years.add(y)
    return {"proper": proper, "years": years}


def sentence_delivers_later_stop_fact(sentence: str, terms: Dict[str, set],
                                      stop1_terms: Dict[str, set] = None) -> bool:
    """True if the sentence carries a proper noun or year that belongs to a later
    stop and NOT to Stop 1 (so we never strip a fact the orientation legitimately
    shares with its own stop)."""
    stop1_terms = stop1_terms or {"proper": set(), "years": set()}
    s_proper = {w.lower() for ph in _proper_nouns(sentence) for w in _significant_words(ph)}
    s_years = set(re.findall(r"\b(1\d{3}|20\d{2})\b", sentence))

    later_proper = (s_proper & terms.get("proper", set())) - stop1_terms.get("proper", set())
    later_years = (s_years & terms.get("years", set())) - stop1_terms.get("years", set())
    return bool(later_proper or later_years)


def strip_later_stop_facts(orientation: str,
                           later_stop_names: List[str],
                           later_stop_texts: List[str],
                           stop1_name: str = "",
                           stop1_text: str = "") -> Tuple[str, int]:
    """Drop orientation sentences that deliver a later-stop fact.

    Returns (cleaned_orientation, dropped_count). Never returns empty: if every
    sentence would be dropped (pathological), the first sentence is kept so the
    listener still gets an opening. The "Orientation:" label and any
    "Your first stop is X." pointer sentence are always preserved.
    """
    if not orientation or not orientation.strip():
        return orientation, 0

    # Preserve a leading "Orientation:" label if present.
    label = ""
    body = orientation
    m = re.match(r"^(orientation:\s*)", orientation, flags=re.IGNORECASE)
    if m:
        label = orientation[: m.end()]
        body = orientation[m.end():]

    terms = extract_later_stop_terms(later_stop_names, later_stop_texts)
    stop1_terms = extract_later_stop_terms([stop1_name] if stop1_name else [],
                                           [stop1_text] if stop1_text else [])
    stop1_name_l = stop1_name.strip().lower()

    sentences = re.split(r"(?<=[.!?])\s+", body.strip())
    kept: List[str] = []
    dropped = 0
    for sent in sentences:
        if not sent.strip():
            continue
        # Always keep the "your first stop is <stop1>" pointer sentence.
        if "first stop is" in sent.lower() or (stop1_name_l and stop1_name_l in sent.lower()
                                               and "first stop" in sent.lower()):
            kept.append(sent)
            continue
        if sentence_delivers_later_stop_fact(sent, terms, stop1_terms):
            dropped += 1
            continue
        kept.append(sent)

    if not kept:
        # Never empty the orientation — keep the first sentence.
        kept = [sentences[0]] if sentences else []
        dropped = max(0, len(sentences) - 1)

    cleaned = label + " ".join(s.strip() for s in kept).strip()
    return cleaned, dropped


def build_forward_connection_prompt(stop1_name: str, connecting_thread: str,
                                    total_stops: int) -> str:
    """[LOCAL-618 #1] Replacement Part-4 prompt: a THREAD-only forward connection.

    The old Part-4 prompt asked the model to name one fact from each of ≥2 stops,
    which is exactly the pre-tell. This asks for a single sentence that states the
    connecting thread and points to Stop 1 — no dated events, no later-stop proper
    nouns.
    """
    thread_clause = (
        f'The works are connected by: {connecting_thread}. '
        if connecting_thread and connecting_thread.strip() else ""
    )
    return (
        "Write ONE sentence (max 30 words) that connects this tour's introduction "
        "to its first stop. State the THREAD that unites the stops and point the "
        f"listener to the first stop, \"{stop1_name}\". {thread_clause}"
        "Do NOT name any dates, events, people, or works that belong to the later "
        "stops — each stop tells its own story when the listener arrives. "
        "Second-person present tense. Return ONLY the sentence."
    )
