#!/usr/bin/env python3
"""LOCAL-206 — Test whether the CREATOR_ONLY gate actually prevents object description.

Generates narration for 2 MAMAC stops (Richard Long, She-Bam Pow POP Wizz),
both CREATOR_ONLY. 3 runs with gate on, 3 with gate off. Classifies each sentence.

Uses tests/db_connection.py for DB access.
Does NOT rebuild any container (D48).
Does NOT modify stop_corpus or corpus_coverage.py (D55/D73).
"""

import json
import os
import sys
import time
import requests
from datetime import datetime

sys.path.insert(0, os.path.dirname(__file__))
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from db_connection import get_connection

# ─── Config ───────────────────────────────────────────────────────────────────
OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]  # no hardcoded fallback — a literal key here is a leak
MODEL = os.environ.get("TOUR_LLM_MODEL", "gpt-3.5-turbo")
VENUE = "Musee d Art Moderne et d Art Contemporain, Nice, France"
LOCATION = "MAMAC Nice"
STOPS = [
    {"id": 18, "title": "Richard Long ou la sculpture en marchant"},
    {"id": 19, "title": "She-Bam Pow POP Wizz"},
]
RUNS_PER_ARM = 3
COST_CEILING = 0.35

HEADERS = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {OPENAI_API_KEY}",
}

# ─── Load corpus data from DB ────────────────────────────────────────────────
def load_stop_corpus():
    """Load passage data for both stops."""
    conn = get_connection()
    cur = conn.cursor()
    results = {}
    for stop in STOPS:
        cur.execute(
            "SELECT passages_json, passage_roles, source_pages FROM stop_corpus WHERE id = %s",
            (stop["id"],)
        )
        row = cur.fetchone()
        if row:
            passages = json.loads(row[0]) if isinstance(row[0], str) else row[0]
            roles = row[1] if row[1] else []
            sources = json.loads(row[2]) if isinstance(row[2], str) else (row[2] or [])
            results[stop["title"]] = {
                "passages": passages,
                "passage_roles": roles,
                "sources": sources,
            }
    conn.close()
    return results


def format_passages_block(stop_data, stop_name, include_role_annotation=True):
    """Reproduce the format_passages_for_prompt logic from stop_corpus_reader.py."""
    passages = stop_data["passages"]
    roles = stop_data.get("passage_roles", [])
    sources = stop_data.get("sources", [])
    max_chars = 2000

    passage_block = []
    passage_roles_for_prompt = []
    total_chars = 0
    for i, p in enumerate(passages):
        if total_chars + len(p) > max_chars:
            remaining = max_chars - total_chars
            if remaining > 100:
                passage_block.append(p[:remaining] + "…")
                passage_roles_for_prompt.append(roles[i] if i < len(roles) else None)
            break
        passage_block.append(p)
        passage_roles_for_prompt.append(roles[i] if i < len(roles) else None)
        total_chars += len(p)

    if not passage_block:
        return ""

    lines = [
        f'\nPER-STOP SOURCE MATERIAL for "{stop_name}" (from verified sources — use this as your primary factual basis):',
    ]
    for i, p in enumerate(passage_block):
        role_info = ""
        if include_role_annotation and i < len(passage_roles_for_prompt) and passage_roles_for_prompt[i]:
            r = passage_roles_for_prompt[i]
            role_val = r.get("role") if isinstance(r, dict) else r
            if role_val:
                role_info = f" [ROLE: {role_val}]"
        lines.append(f"  Passage {i+1}{role_info}: {p}")

    if sources:
        source_urls = []
        for s in sources:
            if isinstance(s, dict) and s.get("url"):
                source_urls.append(f"  [{s.get('title','')}] {s['url']} (tier {s.get('tier','?')})")
            elif isinstance(s, str):
                source_urls.append(f"  {s}")
        if source_urls:
            lines.append("  Sources:")
            lines.extend(source_urls)

    lines.append("")
    lines.append(
        "GROUNDING RULE (D50 — critical): Substantiate claims ONLY from the passages above. "
        "Do NOT supplement with facts from your own training data that are not in these passages. "
        "If the passages do not mention something, do not assert it as fact. "
        "You may describe what is physically visible at the stop and provide general orientation, "
        "but specific historical claims, dates, people, and events MUST come from the passages above. "
        "If a passage names a person or event, you may include it; if it does not, leave it out."
    )

    # Role note
    has_creator = any(
        (r.get("role") if isinstance(r, dict) else r) == "about_creator"
        for r in passage_roles_for_prompt if r
    )
    has_subject = any(
        (r.get("role") if isinstance(r, dict) else r) == "about_subject"
        for r in passage_roles_for_prompt if r
    )
    if has_creator and not has_subject:
        lines.append(
            "ROLE NOTE: All passages above are about the CREATOR/MAKER. You may discuss "
            "the maker's biography and significance, but do NOT describe the physical object "
            "at this stop — no appearance, materials, dimensions, or condition claims."
        )

    return "\n".join(lines) + "\n"


def build_description_prompt(stop_title, stop_data, gate_on):
    """Build the full description prompt for a MAMAC stop."""
    # Base museum prompt (simplified version of the full generate_tour_text.py prompt)
    prompt = f"""Create a detailed audio description for {stop_title} at {LOCATION}, focusing on museum.

IMPORTANT: The listener is ALREADY inside this museum and has been walking for several stops. Do NOT re-introduce the museum or its city. Do NOT say 'As you step into [museum name]' or 'Welcome to'. Begin directly with this specific exhibit.

Start with a brief orientation that names "{stop_title}" specifically (not "the exhibit" or "this piece") and tells the listener WHERE to stand or look AND WHY — what becomes visible, legible, or striking from that position that they would miss otherwise.

Then provide a detailed description of the exhibit. Include:
- What the work physically depicts or consists of — what the visitor sees
- One specific technique, material choice, or compositional decision and WHY it matters
- One piece of historical or cultural context that changes how the visitor understands it
- If relevant: how this piece connects to the broader collection or museum

EXPLAIN-WHAT-YOU-NAME RULE (critical):
Every concept, motif, symbol, technique, cultural reference, or person you mention
MUST get at least one clause of explanation.

AUDIO RULES (this will be heard, not read):
- NEVER end with a rhetorical question.
- NEVER list more than three items in a row.
- Write for the EAR: short-to-medium sentences, concrete language.

NO PREACHING — NEVER INSTRUCT THE LISTENER (critical):
- NEVER end a stop by telling the listener what to feel, notice, consider, reflect on, or carry away.
- End on a FACT or an OBSERVATION, not an instruction.
"""

    # Gate injection
    if gate_on:
        prompt += f"""
CORPUS GATE: CREATOR_ONLY (D75 enforcement — LOCAL-203):
The corpus for this stop contains information about the MAKER/ARTIST of "{stop_title}",
but does NOT contain verified information about the specific object/artwork itself.

YOU MAY:
- Discuss the artist's or maker's biography, career, and significance
- Mention their techniques, style, and historical context — IF stated in the passages
- Note that this maker created the work at this stop

YOU MUST NOT:
- Describe the object's appearance, dimensions, materials, or condition
- Claim what the visitor will see at this specific stop
- Invent details about the physical work from your training data
- State facts about the object that are not in the provided passages

Ground all claims about the maker in the passages provided. Do not describe the object.
"""

    # Passages
    prompt += format_passages_block(stop_data, stop_title, include_role_annotation=True)

    return prompt


def call_llm(prompt, temperature=0.7):
    """Call OpenAI chat API. Returns (text, tokens, cost)."""
    data = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": "You are a knowledgeable museum guide with expertise in art, architecture, and history."},
            {"role": "user", "content": prompt},
        ],
        "temperature": temperature,
        "max_tokens": 1000,
    }
    resp = requests.post(
        "https://api.openai.com/v1/chat/completions",
        headers=HEADERS,
        data=json.dumps(data),
    )
    resp.raise_for_status()
    result = resp.json()
    text = result["choices"][0]["message"]["content"]
    usage = result.get("usage", {})
    tokens = usage.get("total_tokens", 0)
    # gpt-3.5-turbo pricing: $0.0015/1K input, $0.002/1K output
    prompt_tokens = usage.get("prompt_tokens", 0)
    completion_tokens = usage.get("completion_tokens", 0)
    cost = (prompt_tokens * 0.0015 + completion_tokens * 0.002) / 1000.0
    return text, tokens, cost


def run_experiment():
    """Run 3 gate-on + 3 gate-off generations for both stops."""
    print("=" * 70)
    print("LOCAL-206: CREATOR_ONLY Gate Effectiveness Test")
    print(f"Model: {MODEL}  |  Venue: {LOCATION}  |  Runs: {RUNS_PER_ARM}")
    print("=" * 70)

    corpus = load_stop_corpus()
    print(f"\nLoaded corpus for {len(corpus)} stops:")
    for name, data in corpus.items():
        print(f"  {name}: {len(data['passages'])} passages")

    total_cost = 0.0
    results = {}  # {(stop_title, gate_on, run_idx): text}

    for stop in STOPS:
        title = stop["title"]
        stop_data = corpus.get(title)
        if not stop_data:
            print(f"\n⚠️ No corpus data for {title} — skipping")
            continue

        for gate_on in [True, False]:
            gate_label = "GATE_ON" if gate_on else "GATE_OFF"
            for run_idx in range(RUNS_PER_ARM):
                if total_cost >= COST_CEILING:
                    print(f"\n⚠️ Cost ceiling ${COST_CEILING} reached (spent ${total_cost:.4f}). Stopping.")
                    return results, total_cost

                prompt = build_description_prompt(title, stop_data, gate_on)
                print(f"\n{'─'*60}")
                print(f"  {title} | {gate_label} | Run {run_idx+1}/{RUNS_PER_ARM}")
                print(f"  Prompt length: {len(prompt)} chars")

                text, tokens, cost = call_llm(prompt)
                total_cost += cost
                results[(title, gate_on, run_idx)] = text

                print(f"  Response: {len(text)} chars, {tokens} tokens, ${cost:.4f}")
                print(f"  Cumulative cost: ${total_cost:.4f}")
                time.sleep(0.5)  # rate limiting

    print(f"\n{'='*70}")
    print(f"Total cost: ${total_cost:.4f} (ceiling: ${COST_CEILING})")
    return results, total_cost


def save_results(results, total_cost):
    """Save all generated paragraphs to a file."""
    output_dir = os.path.dirname(os.path.dirname(__file__))
    output_path = os.path.join(output_dir, "tests", "local206_gate_test_output.json")

    output = {
        "timestamp": datetime.now().isoformat(),
        "model": MODEL,
        "venue": VENUE,
        "total_cost": total_cost,
        "runs_per_arm": RUNS_PER_ARM,
        "generations": {},
    }

    for (title, gate_on, run_idx), text in results.items():
        key = f"{title}|{'gate_on' if gate_on else 'gate_off'}|run{run_idx+1}"
        output["generations"][key] = text

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print(f"\nSaved to: {output_path}")
    return output_path


if __name__ == "__main__":
    results, total_cost = run_experiment()
    if results:
        save_results(results, total_cost)
        print(f"\n✓ {len(results)} generations completed. Total cost: ${total_cost:.4f}")
    else:
        print("\n✗ No results generated.")
        sys.exit(1)
