"""
Fact Extractor — generates structured fact sheets from RAG context + GPT.
==========================================================================
Produces verified facts, uncertain claims, and surprising details for each POI.
Used by the spine generator to ground narrative in reality.
"""
import json
import logging
import re
from typing import Optional

import requests

logger = logging.getLogger(__name__)


def generate_fact_sheet(
    poi_name: str, rag_context: dict, api_key: str,
    venue_corpus_excerpt: str = "",
) -> Optional[dict]:
    """Generate a structured fact sheet for a POI using RAG context.

    Args:
        poi_name: Name of the point of interest.
        rag_context: dict with 'artist_context' and 'period_context' from rag_retriever.
        api_key: OpenAI API key.
        venue_corpus_excerpt: Pre-fetched venue corpus text relevant to this POI.
            When provided, used as PRIMARY context (higher priority than Wikipedia lookups).

    Returns:
        dict with keys: confirmed_facts, uncertain_facts, date_created, medium, surprising_detail.
        None on failure.
    """
    artist_ctx = rag_context.get("artist_context", "")
    period_ctx = rag_context.get("period_context", "")

    # [LOCAL-12 Fix A] Venue corpus is primary context when available
    has_corpus = bool(venue_corpus_excerpt and venue_corpus_excerpt.strip())

    if not artist_ctx and not period_ctx and not has_corpus:
        logger.warning(f"No RAG context for {poi_name} — cannot generate fact sheet")
        return None

    # Build context block: venue corpus first (primary), then Wikipedia (supplementary)
    context_parts = []
    if has_corpus:
        context_parts.append(f"VENUE COLLECTION SOURCES (primary — these come from the museum's own documentation):\n{venue_corpus_excerpt[:1200]}")
    if artist_ctx:
        context_parts.append(f"Artist/Creator (supplementary): {artist_ctx[:800]}")
    if period_ctx:
        context_parts.append(f"Venue/Period (supplementary): {period_ctx[:800]}")
    context_block = "\n\n".join(context_parts)

    prompt = (
        f"You are a meticulous museum researcher. Given the following context "
        f"about an exhibit/room called '{poi_name}', extract verified facts.\n\n"
        f"--- CONTEXT ---\n"
        f"{context_block}\n"
        f"--- END CONTEXT ---\n\n"
        f"Return ONLY valid JSON with this schema:\n"
        f'{{\n'
        f'  "confirmed_facts": ["fact 1", "fact 2", ...],\n'
        f'  "uncertain_facts": ["unverified claim 1", ...],\n'
        f'  "date_created": "year or date range if known, else null",\n'
        f'  "medium": "materials/medium used if applicable, else null",\n'
        f'  "surprising_detail": "one non-obvious detail that would intrigue a visitor"\n'
        f'}}\n\n'
        f"Rules:\n"
        f"- confirmed_facts: ONLY facts directly supported by the context above.\n"
        f"- uncertain_facts: claims you believe but cannot confirm from the context.\n"
        f"- surprising_detail: must be genuinely unexpected, not a generic statement.\n"
        f"- If you cannot find information, use empty arrays and null values."
    )

    try:
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "model": "gpt-3.5-turbo",
                "messages": [
                    {"role": "system", "content": "You return ONLY valid JSON. No markdown, no commentary."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 500,
            },
            timeout=15,
        )

        if response.status_code != 200:
            logger.error(f"Fact sheet API error: {response.status_code}")
            return None

        result = response.json()
        text = result["choices"][0]["message"]["content"].strip()

        # Cost logging
        tokens = result.get("usage", {}).get("total_tokens", 0)
        cost = tokens / 1000 * 0.002
        logger.info(f"Fact sheet: {poi_name} | {tokens} tokens | ${cost:.4f}")

        # Parse JSON (handle markdown fences)
        clean = text
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", clean, re.DOTALL)
        if m:
            clean = m.group(1)

        fact_sheet = json.loads(clean)

        # Validate structure
        required = ["confirmed_facts", "uncertain_facts", "surprising_detail"]
        for field in required:
            if field not in fact_sheet:
                fact_sheet[field] = [] if "facts" in field else None

        # Ensure lists are lists
        if not isinstance(fact_sheet.get("confirmed_facts"), list):
            fact_sheet["confirmed_facts"] = []
        if not isinstance(fact_sheet.get("uncertain_facts"), list):
            fact_sheet["uncertain_facts"] = []

        return fact_sheet

    except json.JSONDecodeError as e:
        logger.error(f"Fact sheet JSON error for {poi_name}: {e}")
        return None
    except Exception as e:
        logger.error(f"Fact sheet error for {poi_name}: {e}")
        return None


def generate_fact_sheets_parallel(
    poi_list: list,
    venue_name: str,
    tour_category: str,
    api_key: str,
    max_workers: int = 5,
    venue_corpus: str = "",
    per_work_contexts: dict = None,
) -> list:
    """Generate fact sheets for all POIs in parallel.

    Uses ThreadPoolExecutor to fetch RAG context and generate a fact sheet
    per POI concurrently. Returns results in original order.
    Gracefully handles individual POI failures (None per failed stop).

    Args:
        poi_list: List of POI dicts (each with 'name') or strings.
        venue_name: The venue/location name.
        tour_category: 'museum', 'walking', 'restaurant', or 'book'.
        api_key: OpenAI API key.
        max_workers: Max concurrent threads (default 5).
        venue_corpus: Already-fetched combined venue corpus text (from story_miner).
            When provided, used as primary context for fact extraction — avoids
            relying solely on standalone Wikipedia lookups per exhibit.
        per_work_contexts: Dict {title: [sentences]} — per-work contextual sentences
            extracted from the venue corpus. Used to provide targeted context per POI.

    Returns:
        List of fact_sheet dicts (or None for failed POIs), in original order.
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from rag_retriever import fetch_poi_rag_context

    if per_work_contexts is None:
        per_work_contexts = {}

    def _extract_corpus_for_poi(poi_name: str) -> str:
        """[LOCAL-12 Fix A] Extract relevant corpus excerpt for a specific POI.

        Priority: per_work_contexts match > keyword search in venue_corpus.
        Returns the best available corpus excerpt for this POI.
        """
        excerpts = []

        # 1. Check per_work_contexts for a title match (fuzzy prefix)
        poi_lower = poi_name.lower().strip()
        for title, sentences in per_work_contexts.items():
            title_lower = title.lower().strip()
            # Match if either is a prefix of the other (first 8 chars), same as §4 logic
            if (poi_lower[:8] in title_lower or title_lower[:8] in poi_lower):
                excerpts.extend(s[:200] for s in sentences[:5])
                break
            # [LOCAL-14] Also match if significant words overlap (for titles like
            # "La geste de Bouddha" where the prefix "la geste" might not be in the
            # per_work_contexts key if it was stored as "geste de Bouddha" etc.)
            _poi_sig = set(w for w in poi_lower.split() if len(w) >= 4)
            _title_sig = set(w for w in title_lower.split() if len(w) >= 4)
            if _poi_sig and _title_sig and len(_poi_sig & _title_sig) >= max(1, min(len(_poi_sig), len(_title_sig)) // 2):
                excerpts.extend(s[:200] for s in sentences[:5])
                break

        # 2. Keyword search in venue_corpus (same approach as C5-1 in description prompt)
        if venue_corpus and not excerpts:
            key_words = [w for w in poi_lower.split() if len(w) >= 4 and w not in ('the', 'and', 'for', 'with')]
            if key_words:
                corpus_sentences = [
                    s.strip() for s in venue_corpus.split('.')
                    if any(kw in s.lower() for kw in key_words)
                ]
                excerpts.extend(s[:200] for s in corpus_sentences[:8])

        return '. '.join(excerpts) if excerpts else ""

    def _process_one(idx_poi):
        idx, poi = idx_poi
        poi_name = poi.get("name", str(poi)) if isinstance(poi, dict) else str(poi)
        try:
            # [LOCAL-12 Fix A] Get venue corpus excerpt for this POI
            corpus_excerpt = _extract_corpus_for_poi(poi_name)

            rag_ctx = fetch_poi_rag_context(poi_name, venue_name, tour_category)
            fact_sheet = generate_fact_sheet(
                poi_name, rag_ctx, api_key,
                venue_corpus_excerpt=corpus_excerpt,
            )
            # [BLOCKER 2] Pass attribution_confident from RAG to the fact sheet
            if fact_sheet and isinstance(fact_sheet, dict):
                fact_sheet['attribution_confident'] = rag_ctx.get('attribution_confident', False)
                # [LOCAL-12] Mark whether corpus context was available
                fact_sheet['had_corpus_context'] = bool(corpus_excerpt)
            return idx, fact_sheet
        except Exception as e:
            logger.error(f"Fact sheet failed for POI #{idx} ({poi_name}): {e}")
            return idx, None

    # Submit all in parallel
    results = [None] * len(poi_list)
    with ThreadPoolExecutor(max_workers=min(max_workers, len(poi_list))) as executor:
        futures = {
            executor.submit(_process_one, (i, poi)): i
            for i, poi in enumerate(poi_list)
        }
        for future in as_completed(futures):
            idx, fact_sheet = future.result()
            results[idx] = fact_sheet

    success_count = sum(1 for r in results if r is not None)
    corpus_count = sum(1 for r in results if r and r.get('had_corpus_context'))
    logger.info(f"Fact sheets: {success_count}/{len(poi_list)} successful for {venue_name} ({corpus_count} with corpus context)")
    return results
