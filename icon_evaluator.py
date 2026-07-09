"""
icon_evaluator.py — Per-stop informational-context scoring + classification.
=============================================================================
Hybrid evaluator: deterministic signals + GPT-4o-mini LLM pass.
Runs on the DELIVERED tour text (after QA corrective loop settles).

Calibration source: tours/Musee_National_Marc_Chagall__Nice__France_museum_tour_20260708_015040.txt
Michael's §2b scores (13 paragraphs, blind-scored 2026-07-08).

Produces: per-paragraph {i_con: 1|3|5, class_dist, flags[]}, stop and tour aggregates.
Persists to stop_metrics table. Advisory gates logged, never rejecting.
"""
import hashlib
import json
import logging
import os
import re
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

# --- Evaluator version + prompt hash for comparability across prompt changes ---
EVALUATOR_VERSION = "1.0.0"


# --- A. Deterministic Signals ---

# Signal 5: Content-outsourcing detector phrases (BANNED in content paragraphs)
_OUTSOURCING_PATTERNS = [
    r"(?i)\b(ask|inquire|engage)\b.{0,20}\b(staff|personnel|guide|curator)",
    r"(?i)\bfor\s+(additional|more|further|deeper)\s+(context|information|details|insight)",
    r"(?i)\b(museum|our)\s+staff\b.{0,30}\b(additional|context|information|guidance)",
    r"(?i)\bbe\s+sure\s+to\s+engage\b",
]

# Signal 6: Generic-filler lexicon (wallpaper phrases)
# Only the most egregious aesthetic-only phrases that contain ZERO information.
# "Invites contemplation" / "resonates with viewers" removed — they're weak but not zero.
_FILLER_PHRASES = [
    "vibrant hues dance",
    "symphony of colors",
    "let yourself be swept away",
    "explore the depths of",
    "seamlessly blend",
    "rich tapestry of",
    "envelop you in a world",
    "transports you to a realm",
    "ethereal grace",
    "exude a sense of wonder",
    "fluid lines",
    "harmoniously across",
    "drawn into a world where",
    "visual language that resonates",
]


def compute_deterministic_signals(paragraph: str, stop_index: int,
                                   prolog_text: str = "",
                                   all_paragraphs: List[str] = None,
                                   story_elements: List[Dict] = None) -> Dict[str, Any]:
    """Compute deterministic feature vector for a paragraph.
    
    Returns dict with signal results and flags.
    """
    flags = []
    
    # Signal 1: Date/proper-noun/number density
    years = re.findall(r'\b(1[4-9]\d{2}|20[0-2]\d)\b', paragraph)
    # Proper nouns: capitalized words NOT at sentence start, length >= 2
    # Excludes common modifiers that look like proper nouns but aren't specific people/places
    _COMMON_MODIFIERS = {
        'old', 'new', 'the', 'biblical', 'french', 'italian', 'german', 'spanish',
        'english', 'european', 'christian', 'jewish', 'catholic', 'protestant',
        'roman', 'greek', 'ancient', 'modern', 'contemporary', 'national',
        'testament', 'song', 'songs', 'solomon', 'genesis', 'exodus',
        'divine', 'holy', 'sacred', 'spiritual', 'celestial', 'eternal',
    }
    sentences = re.split(r'[.!?]\s+', paragraph)
    proper_nouns = []
    for sent in sentences:
        words = sent.split()
        for w in words[1:]:  # Skip first word (sentence start)
            if w and w[0].isupper() and len(w) >= 2 and w.lower() not in {'the', 'a', 'an', 'in', 'on', 'at', 'to', 'for', 'and', 'or', 'but', 'as', 'this', 'that', 'each', 'his', 'her'}:
                if w.lower() not in _COMMON_MODIFIERS:
                    proper_nouns.append(w)
    numbers = re.findall(r'\b\d+\b', paragraph)
    
    density_score = len(years) * 3 + len(proper_nouns) + len(numbers)
    
    # Signal 2: Claim-traces-to-story-element
    trace_count = 0
    traced_elements = []
    if story_elements:
        para_lower = paragraph.lower()
        for i, elem in enumerate(story_elements):
            elem_text = elem.get('text', '').lower()
            if not elem_text or len(elem_text) < 10:
                continue
            # Check if key phrases from element appear in paragraph
            key_words = [w for w in elem_text.split() if len(w) >= 5][:5]
            if key_words:
                matches = sum(1 for w in key_words if w in para_lower)
                if matches >= max(2, len(key_words) * 0.4):
                    trace_count += 1
                    traced_elements.append({"element_index": i, "type": elem.get('type', '')})
    
    # Signal 3: Thread/prolog overlap (shingled 4-gram)
    prolog_overlap = 0.0
    if prolog_text and stop_index > 0:
        prolog_overlap = _compute_shingle_overlap(paragraph, prolog_text)
        if prolog_overlap > 0.3:
            flags.append("prolog_repeat")
    
    # Signal 4: Unanswered-question detector
    questions = re.findall(r'[^.!?]*\?', paragraph)
    has_unanswered = False
    for q in questions:
        # Check if the text after the question contains a factual answer
        q_pos = paragraph.find(q) + len(q)
        after_q = paragraph[q_pos:q_pos + 200]
        # A "factual answer" contains a year, proper noun, or specific claim
        has_answer = bool(re.search(r'\b(1[4-9]\d{2}|20[0-2]\d)\b', after_q) or
                        re.search(r'\b[A-Z][a-z]{2,}\b', after_q))
        if not has_answer:
            has_unanswered = True
            flags.append("unanswered_question")
            break
    
    # Signal 5: Content-outsourcing detector
    is_outsourcing = False
    for pattern in _OUTSOURCING_PATTERNS:
        if re.search(pattern, paragraph):
            is_outsourcing = True
            flags.append("content_outsourcing")
            break
    
    # Signal 6: Generic-filler lexicon
    para_lower = paragraph.lower()
    filler_count = sum(1 for phrase in _FILLER_PHRASES if phrase in para_lower)
    if filler_count >= 3:
        flags.append("filler_cap")  # Will cap score at 1
    elif filler_count >= 1:
        flags.append("filler_present")  # Informs but doesn't cap
    
    return {
        "dates_count": len(years),
        "proper_nouns_count": len(proper_nouns),
        "numbers_count": len(numbers),
        "density_score": density_score,
        "trace_count": trace_count,
        "traced_elements": traced_elements,
        "prolog_overlap": prolog_overlap,
        "has_unanswered_question": has_unanswered,
        "is_outsourcing": is_outsourcing,
        "filler_count": filler_count,
        "flags": flags,
    }


def _compute_shingle_overlap(text_a: str, text_b: str, n: int = 4) -> float:
    """Compute 4-gram (word-level) Jaccard overlap between two texts."""
    words_a = text_a.lower().split()
    words_b = text_b.lower().split()
    if len(words_a) < n or len(words_b) < n:
        return 0.0
    shingles_a = set(tuple(words_a[i:i+n]) for i in range(len(words_a) - n + 1))
    shingles_b = set(tuple(words_b[i:i+n]) for i in range(len(words_b) - n + 1))
    if not shingles_a or not shingles_b:
        return 0.0
    intersection = shingles_a & shingles_b
    union = shingles_a | shingles_b
    return len(intersection) / len(union)


# --- B. LLM Pass ---

# The few-shot prompt uses VERBATIM paragraphs from the calibration tour
# Source: tours/Musee_National_Marc_Chagall__Nice__France_museum_tour_20260708_015040.txt
# Scores: Michael's §2b blind scores (2026-07-08)

_ICON_SYSTEM_PROMPT = """You are a tour-content quality evaluator. For each paragraph, provide:
1. i_con score (1, 3, or 5):
   - 1 = no information (aesthetic description the visitor sees unaided; rhetorical questions without answers; generic filler)
   - 3 = information with little emotional appeal (plaque-level facts; claims without explanation; repetition of earlier content)
   - 5 = interesting information (grounded specifics — dates, people, events traceable to sources — that advance a story or deliver documented narrative)

   Key rule: "Decoding function" (naming the depicted story; giving a framework for HOW to look at the artwork) rates ≥3 even when the subject is visually self-evident. Score 1 is reserved for aesthetic wallpaper with no decoding value.

   CRITICAL RULE: Naming or describing the depicted story with no dates, no named people beyond the artist, and no documented events is a 3, NEVER a 5. A 5 requires at least one specific, traceable fact (year, named person or place, documented event).

2. class_dist (three values summing to ~1.0):
   - details: dates, names, colors, subject descriptions, menus/prices, building specifics
   - historic: human history, epochs, biography, cultures
   - social: relationships, celebrities, atmosphere

3. evidence_sentence: quote the ONE sentence from the paragraph that most determines its score.

Output valid JSON array, one object per paragraph:
[{"i_con": 5, "class_dist": {"details": 0.4, "historic": 0.5, "social": 0.1}, "evidence_sentence": "..."}]"""

# Few-shots built from ACTUAL calibration paragraphs (verbatim quotes)
_ICON_FEW_SHOT_USER = """Score these paragraphs from a museum tour about Marc Chagall (Nice):

¶1: "In the early 1950s, Chagall's return to France reignited his passion for biblical stories, culminating in the creation of his renowned Biblical Message cycle. The Creation of Man, a pivotal piece in this series, showcases Chagall's deep connection to his Jewish heritage and his exploration of spiritual themes."

¶2: "As you gaze upon the canvas, you are drawn into a world where vibrant hues dance harmoniously across the composition. Chagall's unique blend of symbolism and emotion transports you to a realm where the divine and the human intersect. The figures in the painting, rendered with fluid lines and ethereal grace, exude a sense of wonder and reverence."

¶3: "The contrasting colors - from celestial blues to earthy tones - symbolize the duality of heaven and earth, of the sacred and the mundane. Each element in the painting, from the swirling clouds to the figures reaching towards the heavens, conveys a profound sense of creation and divine intervention."

¶4: "The dynamic composition and Chagall's masterful use of color create a visual symphony that resonates with viewers of all backgrounds. The artist's creative process, steeped in tradition yet infused with modern sensibilities, invites contemplation and introspection."

¶5: "As you ponder The Creation of Man, consider the sacrifices Chagall made to bring his Biblical Message to life. This masterpiece stands as a testament to his vision and enduring legacy, inviting you to delve deeper into the rich tapestry of art and spirituality woven by this master artist."
"""

_ICON_FEW_SHOT_ASSISTANT = """[{"i_con": 5, "class_dist": {"details": 0.30, "historic": 0.50, "social": 0.20}, "evidence_sentence": "In the early 1950s, Chagall's return to France reignited his passion for biblical stories, culminating in the creation of his renowned Biblical Message cycle."},
{"i_con": 1, "class_dist": {"details": 0.80, "historic": 0.10, "social": 0.10}, "evidence_sentence": "As you gaze upon the canvas, you are drawn into a world where vibrant hues dance harmoniously across the composition."},
{"i_con": 3, "class_dist": {"details": 0.60, "historic": 0.20, "social": 0.20}, "evidence_sentence": "The contrasting colors - from celestial blues to earthy tones - symbolize the duality of heaven and earth, of the sacred and the mundane."},
{"i_con": 3, "class_dist": {"details": 0.50, "historic": 0.30, "social": 0.20}, "evidence_sentence": "The artist's creative process, steeped in tradition yet infused with modern sensibilities, invites contemplation and introspection."},
{"i_con": 3, "class_dist": {"details": 0.20, "historic": 0.40, "social": 0.40}, "evidence_sentence": "As you ponder The Creation of Man, consider the sacrifices Chagall made to bring his Biblical Message to life."}]"""

# Second few-shot: Stop 2 (scores: 5,3,3,1) — ONLY Stop 2, Stop 3 is held out for testing
_ICON_FEW_SHOT_USER_2 = """Score these paragraphs (same museum tour, Stop 2):

¶1: "In this poignant work by Marc Chagall, The Sacrifice of Isaac, the viewer is drawn into a moment of profound tension and emotional turmoil. The painting depicts the biblical story from the Book of Genesis where Abraham, tormented yet faithful, prepares to sacrifice his beloved son Isaac as a test of his devotion to God. The scene is charged with a sense of urgency and sacrifice, conveyed through Chagall's masterful use of color and composition."

¶2: "Chagall, known for his ethereal and symbolic style, infuses this piece with layers of meaning and personal reflection. The artist's own sacrifices and struggles are subtly echoed in the narrative, adding a poignant depth to the work. The painting stands as a testament to Chagall's commitment to sharing his vision with the world, a transformation of his original plans for a chapel into the museum that now houses his works."

¶3: "As you gaze upon The Sacrifice of Isaac, take note of the expressive brushwork and emotive colors that bring the scene to life. The figures of Abraham and Isaac are rendered with a haunting intensity, capturing the anguish and faith intertwined in this pivotal moment. This work not only showcases Chagall's artistic prowess but also invites contemplation on themes of sacrifice, devotion, and the complexities of faith."

¶4: "After experiencing this powerful painting, consider how Chagall's legacy has shaped the museum's collection and artistic direction. How did the museum evolve after his passing, and what new insights and influences emerged in the wake of his vision?"
"""

_ICON_FEW_SHOT_ASSISTANT_2 = """[{"i_con": 5, "class_dist": {"details": 0.15, "historic": 0.50, "social": 0.35}, "evidence_sentence": "The painting depicts the biblical story from the Book of Genesis where Abraham, tormented yet faithful, prepares to sacrifice his beloved son Isaac as a test of his devotion to God."},
{"i_con": 3, "class_dist": {"details": 0.20, "historic": 0.45, "social": 0.35}, "evidence_sentence": "The painting stands as a testament to Chagall's commitment to sharing his vision with the world, a transformation of his original plans for a chapel into the museum that now houses his works."},
{"i_con": 3, "class_dist": {"details": 0.50, "historic": 0.20, "social": 0.30}, "evidence_sentence": "The figures of Abraham and Isaac are rendered with a haunting intensity, capturing the anguish and faith intertwined in this pivotal moment."},
{"i_con": 1, "class_dist": {"details": 0.10, "historic": 0.40, "social": 0.50}, "evidence_sentence": "How did the museum evolve after his passing, and what new insights and influences emerged in the wake of his vision?"}]"""


def _get_prompt_hash() -> str:
    """Hash the prompt + few-shots for version tracking."""
    content = _ICON_SYSTEM_PROMPT + _ICON_FEW_SHOT_USER + _ICON_FEW_SHOT_ASSISTANT + _ICON_FEW_SHOT_USER_2 + _ICON_FEW_SHOT_ASSISTANT_2
    return hashlib.md5(content.encode()).hexdigest()[:12]


def evaluate_paragraphs_llm(paragraphs: List[str]) -> List[Dict]:
    """Score paragraphs using GPT-4o-mini (temperature=0 for determinism).
    
    Returns list of {i_con, class_dist, evidence_sentence} per paragraph.
    Compatible with openai 0.27.x (legacy API).
    """
    import openai
    
    # Build the user message with numbered paragraphs
    user_parts = ["Score these paragraphs:\n"]
    for i, p in enumerate(paragraphs, 1):
        user_parts.append(f'¶{i}: "{p}"\n')
    user_message = "\n".join(user_parts)
    
    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o-mini",
            temperature=0,
            messages=[
                {"role": "system", "content": _ICON_SYSTEM_PROMPT},
                {"role": "user", "content": _ICON_FEW_SHOT_USER},
                {"role": "assistant", "content": _ICON_FEW_SHOT_ASSISTANT},
                {"role": "user", "content": _ICON_FEW_SHOT_USER_2},
                {"role": "assistant", "content": _ICON_FEW_SHOT_ASSISTANT_2},
                {"role": "user", "content": user_message},
            ],
        )
        
        content = response.choices[0].message.content
        
        # Parse JSON from response (may be wrapped in ```json...``` or bare)
        content = content.strip()
        if content.startswith("```"):
            content = re.sub(r'^```\w*\n?', '', content)
            content = re.sub(r'\n?```$', '', content)
        
        result = json.loads(content)
        
        # Handle both {"results": [...]} and bare [...] formats
        if isinstance(result, dict) and "results" in result:
            result = result["results"]
        elif isinstance(result, dict) and "paragraphs" in result:
            result = result["paragraphs"]
        
        if not isinstance(result, list):
            logger.warning(f"Unexpected LLM response format: {type(result)}")
            return [{"i_con": 3, "class_dist": {"details": 0.33, "historic": 0.34, "social": 0.33}, "evidence_sentence": ""} for _ in paragraphs]
        
        # Validate and normalize
        scored = []
        for i, item in enumerate(result[:len(paragraphs)]):
            icon = item.get("i_con", 3)
            if icon not in (1, 3, 5):
                icon = 3  # Default to middle
            class_dist = item.get("class_dist", {"details": 0.33, "historic": 0.34, "social": 0.33})
            evidence = item.get("evidence_sentence", "")
            scored.append({"i_con": icon, "class_dist": class_dist, "evidence_sentence": evidence})
        
        # Pad if LLM returned fewer than expected
        while len(scored) < len(paragraphs):
            scored.append({"i_con": 3, "class_dist": {"details": 0.33, "historic": 0.34, "social": 0.33}, "evidence_sentence": ""})
        
        return scored
        
    except Exception as e:
        logger.error(f"I-CON LLM evaluation failed: {e}")
        print(f"  [I-CON] LLM error: {e}")
        # Fail gracefully: return neutral scores
        return [{"i_con": 3, "class_dist": {"details": 0.33, "historic": 0.34, "social": 0.33}, "evidence_sentence": ""} for _ in paragraphs]


# --- C. Scoring Aggregation ---

def evaluate_tour_icon(tour_text: str, story_elements: List[Dict] = None) -> Dict:
    """Evaluate a complete tour's informational context.
    
    Args:
        tour_text: The DELIVERED tour text (after QA corrections)
        story_elements: Optional story_elements for trace checking
        
    Returns:
        {
            "tour_avg": float,
            "tour_min": float,
            "stops": [{stop_title, i_con, class_dist, paragraphs: [...]}],
            "prompt_hash": str,
        }
    """
    # Parse tour into stops
    stops = _parse_tour_stops(tour_text)
    
    if not stops:
        return {"tour_avg": 0.0, "tour_min": 0.0, "stops": [], "prompt_hash": _get_prompt_hash()}
    
    # Get prolog text (Stop 1's Orientation paragraph)
    prolog_text = stops[0].get("orientation", "") if stops else ""
    
    # Collect all scoreable paragraphs across all stops
    all_paragraphs_flat = []
    paragraph_map = []  # (stop_idx, para_idx) for each flat entry
    
    for stop_idx, stop in enumerate(stops):
        for para_idx, para in enumerate(stop.get("paragraphs", [])):
            all_paragraphs_flat.append(para)
            paragraph_map.append((stop_idx, para_idx))
    
    if not all_paragraphs_flat:
        return {"tour_avg": 0.0, "tour_min": 0.0, "stops": [], "prompt_hash": _get_prompt_hash()}
    
    # Run LLM pass on all paragraphs at once (cost-efficient)
    llm_scores = evaluate_paragraphs_llm(all_paragraphs_flat)
    
    # Compute deterministic signals and apply caps
    stop_results = []
    for stop_idx, stop in enumerate(stops):
        stop_paragraphs = []
        for para_idx, para in enumerate(stop.get("paragraphs", [])):
            # Find this paragraph's LLM score
            flat_idx = next(i for i, (si, pi) in enumerate(paragraph_map) if si == stop_idx and pi == para_idx)
            llm_result = llm_scores[flat_idx]
            
            # Compute deterministic signals
            det_signals = compute_deterministic_signals(
                para, stop_idx, prolog_text, all_paragraphs_flat, story_elements
            )
            
            # Apply caps (Section C rules)
            final_icon = llm_result["i_con"]
            
            # Cap: content-outsourcing → 1
            if det_signals["is_outsourcing"]:
                final_icon = 1
            
            # Cap: ≥3 filler phrases → 1
            if det_signals["filler_count"] >= 3:
                final_icon = 1
            
            # Demotion cap: LLM says 5 but paragraph has ZERO traceable specifics → 3
            # A "5" without a traceable specific is definitionally impossible per the matrix
            if final_icon == 5 and det_signals["dates_count"] == 0 and det_signals["trace_count"] == 0:
                # Check for proper nouns beyond the artist name (at least 2 required for 5)
                if det_signals["proper_nouns_count"] < 2:
                    final_icon = 3
                    det_signals["flags"].append("demotion_5to3_no_specifics")
            
            # Single filler match: informs only, never caps (LEAD fix 4a)
            
            stop_paragraphs.append({
                "text": para[:200],  # Truncate for storage
                "i_con": final_icon,
                "class_dist": llm_result["class_dist"],
                "evidence_sentence": llm_result["evidence_sentence"],
                "flags": det_signals["flags"],
            })
        
        # Stop-level aggregation
        if stop_paragraphs:
            stop_icon = sum(p["i_con"] for p in stop_paragraphs) / len(stop_paragraphs)
            
            # Class dist: i-con-weighted average (wallpaper doesn't dominate classification)
            total_weight = sum(p["i_con"] for p in stop_paragraphs) or 1
            stop_class = {"details": 0.0, "historic": 0.0, "social": 0.0}
            for p in stop_paragraphs:
                w = p["i_con"] / total_weight
                for k in stop_class:
                    stop_class[k] += p["class_dist"].get(k, 0.0) * w
        else:
            stop_icon = 0.0
            stop_class = {"details": 0.33, "historic": 0.34, "social": 0.33}
        
        stop_results.append({
            "stop_title": stop.get("title", f"Stop {stop_idx + 1}"),
            "stop_index": stop_idx,
            "i_con": round(stop_icon, 2),
            "class_dist": {k: round(v, 3) for k, v in stop_class.items()},
            "paragraphs": stop_paragraphs,
        })
    
    # Tour-level aggregation
    stop_icons = [s["i_con"] for s in stop_results if s["i_con"] > 0]
    tour_avg = sum(stop_icons) / len(stop_icons) if stop_icons else 0.0
    tour_min = min(stop_icons) if stop_icons else 0.0
    
    return {
        "tour_avg": round(tour_avg, 2),
        "tour_min": round(tour_min, 2),
        "stops": stop_results,
        "prompt_hash": _get_prompt_hash(),
        "evaluator_version": EVALUATOR_VERSION,
    }


def _parse_tour_stops(tour_text: str) -> List[Dict]:
    """Parse tour text into stops with title, orientation, paragraphs, directions."""
    stops = []
    
    # Split by "Stop N:" pattern
    stop_blocks = re.split(r'\nStop\s+\d+:', tour_text)
    
    for block in stop_blocks[1:]:  # Skip text before first stop
        lines = block.strip().split('\n')
        
        title = lines[0].strip() if lines else ""
        
        # Find the content paragraphs (after metadata, before Directions)
        content_lines = []
        orientation = ""
        in_content = False
        
        for line in lines:
            stripped = line.strip()
            
            # Skip metadata lines
            if stripped.startswith(('Address:', 'Coordinates:', 'Type/', 'Specific Examples:', 'Museum Information:')):
                continue
            
            # Orientation paragraph
            if stripped.startswith('Orientation:'):
                orientation = stripped[len('Orientation:'):].strip()
                in_content = True
                continue
            
            # Directions: marks end of content
            if stripped.startswith('Directions:'):
                break
            
            # Epilog markers — stop collecting content
            if any(marker in stripped.lower() for marker in [
                "as this journey comes to a close",
                "you've experienced",
                "if you'd like to explore more",
                "sources: this tour draws",
            ]):
                break
            
            # Content paragraphs (non-empty lines after orientation)
            if in_content and stripped and len(stripped) > 30:
                content_lines.append(stripped)
        
        # Exclude Stop 1 prolog from scoring (the Orientation of Stop 1 is prolog)
        # But include Orientation for Stop 2+ (LEAD: "Orientation paragraphs score as content everywhere except Stop 1's tour prolog")
        paragraphs = content_lines
        
        stops.append({
            "title": title,
            "orientation": orientation,
            "paragraphs": paragraphs,
        })
    
    # For Stop 1: exclude the Orientation (it's the tour prolog)
    # For Stop 2+: include the Orientation as a scored paragraph
    for i, stop in enumerate(stops):
        if i > 0 and stop["orientation"]:
            stop["paragraphs"] = [stop["orientation"]] + stop["paragraphs"]
    
    return stops


# --- D. Advisory Gate Reporting ---

def report_icon_gate(icon_result: Dict) -> str:
    """Report advisory PASS/FAIL on proposed thresholds.
    
    Thresholds (advisory only, never rejecting):
    - Tour avg >= 3.5
    - No stop avg < 3
    - <= 1 paragraph scoring 1 per stop
    """
    tour_avg = icon_result.get("tour_avg", 0)
    tour_min = icon_result.get("tour_min", 0)
    
    gate_pass = True
    issues = []
    
    if tour_avg < 3.5:
        gate_pass = False
        issues.append(f"tour avg {tour_avg:.2f} < 3.5")
    
    for stop in icon_result.get("stops", []):
        if stop["i_con"] < 3.0:
            gate_pass = False
            issues.append(f"stop '{stop['stop_title']}' avg {stop['i_con']:.2f} < 3")
        
        ones_count = sum(1 for p in stop["paragraphs"] if p["i_con"] == 1)
        if ones_count > 1:
            gate_pass = False
            issues.append(f"stop '{stop['stop_title']}' has {ones_count} wallpaper ¶s (max 1)")
    
    status = "ADVISORY PASS" if gate_pass else "ADVISORY FAIL"
    report = f"[I-CON] {status} — tour avg: {tour_avg:.2f}, min stop: {tour_min:.2f}"
    if issues:
        report += f" | Issues: {'; '.join(issues)}"
    
    print(report)
    return report
