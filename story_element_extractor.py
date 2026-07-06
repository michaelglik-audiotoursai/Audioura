"""
story_element_extractor.py — Extract structured story elements from museum narrative text.
============================================================================================
Runs one cheap LLM pass PER PAGE of retrieved museum content, extracting documented
story elements with source snippets. De-duplicates across pages.

Output: list of story elements, each:
{
    "id": "se_001",
    "type": "origin|intention|turning_point|person|date|context_work|quote|superlative",
    "text": "brief element description",
    "source_url": "URL of the page this was extracted from",
    "snippet": "exact quote from the source text that supports this element",
    "author": "author/publisher if extractable, else null",
    "story_mode": "found"
}
"""
import json
import logging
import re
from typing import Dict, List, Optional

import requests

logger = logging.getLogger(__name__)


def extract_story_elements_from_pages(
    pages: List[Dict],
    venue_name: str,
    api_key: str,
    max_pages: int = 5,
) -> List[Dict]:
    """Extract story elements from multiple fetched pages.
    
    Args:
        pages: List of {url, text, title} dicts from story_miner
        venue_name: The museum/venue name
        api_key: OpenAI API key
        max_pages: Max pages to process (cap cost)
        
    Returns:
        De-duplicated list of story elements with source attribution.
    """
    all_elements = []
    
    # Filter to pages with substantial narrative content (>500 chars)
    narrative_pages = [p for p in pages if len(p.get('text', '')) > 500][:max_pages]
    
    if not narrative_pages:
        print(f"  [story_elements] No narrative pages to extract from")
        return []
    
    print(f"  [story_elements] Extracting from {len(narrative_pages)} pages...")
    
    for page in narrative_pages:
        page_text = page['text'][:8000]  # Cap per-page input to avoid token overflow
        page_url = page.get('url', '')
        
        elements = _extract_from_single_page(page_text, page_url, venue_name, api_key)
        if elements:
            all_elements.extend(elements)
            print(f"    {page.get('title', page_url)}: {len(elements)} elements")
    
    # De-duplicate by text similarity
    deduped = _deduplicate_elements(all_elements)
    
    # Assign sequential IDs
    for i, elem in enumerate(deduped):
        elem['id'] = f"se_{i+1:03d}"
    
    print(f"  [story_elements] Total: {len(deduped)} unique elements (from {len(all_elements)} raw)")
    return deduped


def _extract_from_single_page(
    page_text: str,
    source_url: str,
    venue_name: str,
    api_key: str,
) -> List[Dict]:
    """Extract story elements from a single page's text content.
    
    Uses GPT-3.5-turbo at temperature 0.1 for deterministic extraction.
    """
    if not page_text or len(page_text) < 100:
        return []
    
    prompt = f"""You are a museum researcher. Extract documented story elements from this text about '{venue_name}'.

--- TEXT ---
{page_text}
--- END TEXT ---

Extract ONLY facts that are explicitly stated in the text above. Return a JSON array of elements:
[
  {{
    "type": "origin|intention|turning_point|person|date|context_work|quote|superlative",
    "text": "brief description of the element",
    "snippet": "exact short quote (max 30 words) from the text that supports this",
    "author": "author/curator name if mentioned, else null"
  }}
]

Element types:
- origin: how/why the collection/work was created
- intention: original purpose or plan (even if changed later)
- turning_point: a key moment that changed the project's direction
- person: a named person who played a role (curator, patron, minister)
- date: a specific date or date range with what happened
- context_work: another artist/work that provides context (e.g. Matisse's chapel)
- quote: a direct quote from a named person
- superlative: a "first", "only", "largest" etc. claim

Rules:
- ONLY extract facts stated in the text — never invent or infer
- snippet must be an EXACT quote from the text (max 30 words)
- If the text is mostly navigation/boilerplate with no narrative, return []
- Prefer elements that tell a STORY (origin, intention, turning points) over bare dates"""

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
                    {"role": "system", "content": "You return ONLY valid JSON arrays. No markdown fences, no commentary."},
                    {"role": "user", "content": prompt},
                ],
                "temperature": 0.1,
                "max_tokens": 1500,
            },
            timeout=30,
        )
        
        if response.status_code != 200:
            logger.warning(f"story_element extraction API error: {response.status_code}")
            return []
        
        result = response.json()
        text_response = result["choices"][0]["message"]["content"].strip()
        
        # Log cost
        tokens = result.get("usage", {}).get("total_tokens", 0)
        cost = tokens / 1000 * 0.002
        logger.info(f"  story_element extraction: {tokens} tokens, ${cost:.4f}")
        
        # Parse JSON (handle markdown fences)
        clean = text_response
        m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", clean, re.DOTALL)
        if m:
            clean = m.group(1)
        
        elements = json.loads(clean)
        if not isinstance(elements, list):
            return []
        
        # Add source_url and story_mode to each element
        valid_elements = []
        for elem in elements:
            if not isinstance(elem, dict):
                continue
            if not elem.get('type') or not elem.get('text'):
                continue
            elem['source_url'] = source_url
            elem['story_mode'] = 'found'
            # Validate snippet exists in source (exact or fuzzy)
            snippet = elem.get('snippet', '')
            if snippet and len(snippet) > 10:
                # Check snippet is roughly in the source text
                snippet_words = snippet.lower().split()[:5]
                source_lower = text_response.lower() if not page_text else page_text.lower()
                if not any(w in source_lower for w in snippet_words if len(w) > 4):
                    elem['snippet'] = ''  # Clear unverifiable snippet
            valid_elements.append(elem)
        
        return valid_elements
        
    except json.JSONDecodeError as e:
        logger.warning(f"story_element JSON parse error: {e}")
        return []
    except Exception as e:
        logger.warning(f"story_element extraction error: {e}")
        return []


def _deduplicate_elements(elements: List[Dict]) -> List[Dict]:
    """De-duplicate elements by text similarity (>80% word overlap = duplicate)."""
    if not elements:
        return []
    
    unique = []
    seen_texts = []
    
    for elem in elements:
        text = elem.get('text', '').lower()
        text_words = set(text.split())
        
        is_dup = False
        for seen in seen_texts:
            seen_words = set(seen.split())
            if not text_words or not seen_words:
                continue
            overlap = len(text_words & seen_words) / max(len(text_words), len(seen_words))
            if overlap > 0.8:
                is_dup = True
                break
        
        if not is_dup:
            unique.append(elem)
            seen_texts.append(text)
    
    return unique


def persist_story_elements(
    elements: List[Dict],
    output_path: str,
) -> None:
    """Save story elements to JSON file."""
    try:
        with open(output_path, 'w', encoding='utf-8') as f:
            json.dump(elements, f, indent=2, ensure_ascii=False)
        print(f"  [story_elements] Persisted {len(elements)} elements to {output_path}")
    except Exception as e:
        logger.error(f"Failed to persist story elements: {e}")


def get_elements_for_work(
    elements: List[Dict],
    work_name: str,
) -> List[Dict]:
    """Get story elements relevant to a specific work."""
    if not elements or not work_name:
        return []
    
    work_lower = work_name.lower()
    work_words = [w for w in work_lower.split() if len(w) >= 4]
    
    relevant = []
    for elem in elements:
        elem_text = (elem.get('text', '') + ' ' + elem.get('snippet', '')).lower()
        # Check if any significant word from the work name appears in this element
        if any(w in elem_text for w in work_words):
            relevant.append(elem)
        # Also include venue-level story elements (origin, turning_point, superlative)
        # for the first stop's prolog
        elif elem.get('type') in ('origin', 'intention', 'turning_point', 'superlative'):
            relevant.append(elem)
    
    return relevant


def get_prolog_elements(elements: List[Dict]) -> List[Dict]:
    """Get story elements suitable for the tour prolog/introduction.
    
    These are venue-level story elements (origin, intention, turning points)
    that frame the entire tour, not individual works.
    """
    prolog_types = ('origin', 'intention', 'turning_point', 'superlative', 'person', 'context_work')
    return [e for e in elements if e.get('type') in prolog_types]
