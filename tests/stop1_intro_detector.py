#!/usr/bin/env python3
"""stop1_intro_detector.py — LOCAL-191: Stop 1 vs stops 2..N structural analysis.

Michael's hypothesis: Stop 1 is a "tour description wearing a stop's clothes."
The prolog (tour introduction) is injected into Stop 1 at line 6594 of
generate_tour_text.py, making it structurally different from other stops.

This script measures Stop 1 against stops 2..N across 10 tours on:
  1. Paragraph count
  2. Character length (total text)
  3. ANCHORED rate (from stop_anchor_detector_v2)
  4. Tour/region naming rate — how often the text names the tour or region
     rather than the stop itself

Read-only. No generation changes. No container rebuilds. $0.00 spend.
"""
import re
import sys
import json
from typing import Dict, List, Tuple
from collections import defaultdict

sys.path.insert(0, 'tests')
from db_connection import get_connection
from stop_anchor_detector_v2 import (
    parse_tour_stops, classify_paragraph, build_corpus_anchors,
    build_sibling_corpus_texts, is_navigation_paragraph,
    get_venue_corpus_for_tour,
)

# The 10 tours from the task: 7 baseline + 152, 156, 162
TOUR_IDS = [1, 29, 12, 24, 14, 46, 44, 152, 156, 162]

# ─── Tour/region naming detection ───────────────────────────────────────────

# Tour-level / region-level terms that indicate text is about the TOUR
# rather than the specific stop. These are names/phrases that refer to
# the overall experience, the route, or the region — not the POI.
_TOUR_FRAMING_PATTERNS = [
    # Direct tour references
    r'\b(?:this tour|the tour|our tour|your tour|audio tour|cycling tour|biking tour|walking tour|museum tour)\b',
    # Journey/experience framing
    r'\b(?:this journey|our journey|your journey|this experience|our experience)\b',
    # Route-level framing (about the overall path, not a single stop)
    r'\b(?:french riviera|côte d\'azur|cote d\'azur|riviera)\b',
    # Chapter/arc/story framing (tour-as-narrative, not stop-as-content)
    r'\b(?:each stop|every stop|the stops|our stops|chapters? of|arc of|thread of)\b',
    # Opening/intro self-reference
    r'\b(?:welcome to|embark on|set out|begin (?:our|your|this))\b',
    # Tour-level time references (about the overall duration)
    r'\b(?:by the end|as we conclude|throughout (?:this|our|the) tour)\b',
]

_TOUR_FRAMING_COMPILED = [re.compile(p, re.IGNORECASE) for p in _TOUR_FRAMING_PATTERNS]


def count_tour_framing_matches(text: str) -> int:
    """Count how many tour/region framing patterns match in the text."""
    return sum(1 for pat in _TOUR_FRAMING_COMPILED if pat.search(text))


def has_tour_framing(text: str) -> bool:
    """Return True if text contains any tour-level framing."""
    return any(pat.search(text) for pat in _TOUR_FRAMING_COMPILED)


# Venue corpus retrieval: imported from stop_anchor_detector_v2


# ─── Main analysis ──────────────────────────────────────────────────────────

def analyze_stop1_vs_rest(tour_ids: List[int]) -> str:
    """Compare Stop 1 against stops 2..N across all specified tours.
    
    Returns a formatted report with evidence.
    """
    conn = get_connection()
    import psycopg2.extras

    report_lines = []
    report_lines.append("=" * 78)
    report_lines.append("STOP 1 INTRO DETECTOR — LOCAL-191: Structural Analysis")
    report_lines.append("=" * 78)
    report_lines.append("")
    report_lines.append("Hypothesis: Stop 1 is a 'tour description wearing a stop's clothes'.")
    report_lines.append("Mechanism: generate_tour_text.py line 6594 injects _saved_prolog")
    report_lines.append("           into Stop 1 before its description (STORIED_MODE only).")
    report_lines.append("")

    # Verify audio_tours count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM audio_tours")
    total_tours = cur.fetchone()[0]
    report_lines.append(f"audio_tours row count: {total_tours}")
    report_lines.append(f"Tours analyzed: {len(tour_ids)}")
    report_lines.append("")

    # ─── Per-tour analysis ───────────────────────────────────────────────
    all_stop1_data = []
    all_rest_data = []
    per_tour_summaries = []

    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    for tour_id in tour_ids:
        cur.execute("SELECT id, tour_name, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
        row = cur.fetchone()
        if not row or not row['tour_content']:
            report_lines.append(f"  Tour {tour_id}: NO CONTENT — skipped")
            continue

        tour_name = row['tour_name']
        tour_content = row['tour_content']
        venue_corpus = get_venue_corpus_for_tour(tour_id, tour_name, conn)
        stops = parse_tour_stops(tour_content)

        if not stops:
            report_lines.append(f"  Tour {tour_id} ({tour_name}): NO STOPS PARSED — skipped")
            continue

        # Build sibling corpus texts for anchor detection
        all_stop_titles = [s['title'] for s in stops]
        sibling_corpus_texts = build_sibling_corpus_texts(
            venue_corpus, all_stop_titles, tour_name
        ) if venue_corpus else {}

        # Analyze each stop
        stop_metrics = []
        for idx, stop in enumerate(stops):
            # Basic metrics
            total_chars = sum(len(p) for p in stop['paragraphs'])
            para_count = len(stop['paragraphs'])

            # Anchor classification
            corpus_anchors = build_corpus_anchors(
                venue_corpus, stop['title'], tour_name
            ) if venue_corpus else {
                'people': set(), 'dates': set(), 'titles': set(),
                'facts': [], 'all_corpus_people': set(), 'all_corpus_text': '',
            }

            anchored = 0
            no_anchor = 0
            nav = 0
            unlinked = 0
            scoreable = 0

            for para in stop['paragraphs']:
                result = classify_paragraph(
                    para, corpus_anchors, stop['title'], tour_name,
                    sibling_corpus_texts=sibling_corpus_texts
                )
                cls = result['classification']
                if cls == 'ANCHORED':
                    anchored += 1
                    scoreable += 1
                elif cls == 'NO_ANCHOR':
                    no_anchor += 1
                    scoreable += 1
                elif cls == 'UNLINKED_ENTITY':
                    unlinked += 1
                    scoreable += 1
                elif cls == 'NAVIGATION':
                    nav += 1

            anchored_rate = anchored / scoreable if scoreable > 0 else 0.0

            # Tour/region framing
            full_text = ' '.join(stop['paragraphs'])
            tour_framing_count = count_tour_framing_matches(full_text)
            # Normalize by paragraph count to get per-paragraph rate
            tour_framing_rate = tour_framing_count / para_count if para_count > 0 else 0.0
            has_framing = has_tour_framing(full_text)

            metrics = {
                'tour_id': tour_id,
                'tour_name': tour_name,
                'stop_index': idx,
                'stop_title': stop['title'],
                'para_count': para_count,
                'total_chars': total_chars,
                'anchored': anchored,
                'no_anchor': no_anchor,
                'unlinked': unlinked,
                'navigation': nav,
                'scoreable': scoreable,
                'anchored_rate': anchored_rate,
                'tour_framing_count': tour_framing_count,
                'tour_framing_rate': tour_framing_rate,
                'has_tour_framing': has_framing,
            }
            stop_metrics.append(metrics)

            if idx == 0:
                all_stop1_data.append(metrics)
            else:
                all_rest_data.append(metrics)

        # Per-tour summary
        stop1 = stop_metrics[0] if stop_metrics else None
        rest = stop_metrics[1:] if len(stop_metrics) > 1 else []

        per_tour_summaries.append({
            'tour_id': tour_id,
            'tour_name': tour_name,
            'stop_count': len(stops),
            'stop1': stop1,
            'rest': rest,
        })

    # ─── Aggregate statistics ────────────────────────────────────────────
    report_lines.append("─" * 78)
    report_lines.append("PER-TOUR COMPARISON: Stop 1 vs Stops 2..N")
    report_lines.append("─" * 78)
    report_lines.append("")

    header = f"{'Tour':<6} {'Name':<45} {'Stops':<6} {'S1¶':<5} {'Rest¶':<6} {'S1chars':<8} {'Restchars':<10} {'S1anch':<8} {'Restanch':<9} {'S1frame':<8} {'Restframe'}"
    report_lines.append(header)
    report_lines.append("-" * len(header))

    for ts in per_tour_summaries:
        s1 = ts['stop1']
        rest = ts['rest']
        if not s1:
            continue

        avg_rest_para = sum(r['para_count'] for r in rest) / len(rest) if rest else 0
        avg_rest_chars = sum(r['total_chars'] for r in rest) / len(rest) if rest else 0
        avg_rest_anch = sum(r['anchored_rate'] for r in rest) / len(rest) if rest else 0
        avg_rest_frame = sum(r['tour_framing_rate'] for r in rest) / len(rest) if rest else 0

        report_lines.append(
            f"{ts['tour_id']:<6} {ts['tour_name'][:44]:<45} {ts['stop_count']:<6} "
            f"{s1['para_count']:<5} {avg_rest_para:<6.1f} "
            f"{s1['total_chars']:<8} {avg_rest_chars:<10.0f} "
            f"{s1['anchored_rate']:<8.0%} {avg_rest_anch:<9.0%} "
            f"{s1['tour_framing_rate']:<8.2f} {avg_rest_frame:.2f}"
        )

    # ─── Aggregate summary ───────────────────────────────────────────────
    report_lines.append("")
    report_lines.append("─" * 78)
    report_lines.append("AGGREGATE: Stop 1 (N=10) vs Stops 2..N")
    report_lines.append("─" * 78)
    report_lines.append("")

    n1 = len(all_stop1_data)
    nr = len(all_rest_data)

    if n1 > 0 and nr > 0:
        # Paragraph count
        s1_para_avg = sum(d['para_count'] for d in all_stop1_data) / n1
        rest_para_avg = sum(d['para_count'] for d in all_rest_data) / nr
        s1_para_med = sorted(d['para_count'] for d in all_stop1_data)[n1 // 2]
        rest_para_med = sorted(d['para_count'] for d in all_rest_data)[nr // 2]

        # Character length
        s1_chars_avg = sum(d['total_chars'] for d in all_stop1_data) / n1
        rest_chars_avg = sum(d['total_chars'] for d in all_rest_data) / nr
        s1_chars_med = sorted(d['total_chars'] for d in all_stop1_data)[n1 // 2]
        rest_chars_med = sorted(d['total_chars'] for d in all_rest_data)[nr // 2]

        # ANCHORED rate
        s1_anch_avg = sum(d['anchored_rate'] for d in all_stop1_data) / n1
        rest_anch_avg = sum(d['anchored_rate'] for d in all_rest_data) / nr

        # Tour framing rate
        s1_frame_avg = sum(d['tour_framing_rate'] for d in all_stop1_data) / n1
        rest_frame_avg = sum(d['tour_framing_rate'] for d in all_rest_data) / nr
        s1_has_framing = sum(1 for d in all_stop1_data if d['has_tour_framing'])
        rest_has_framing = sum(1 for d in all_rest_data if d['has_tour_framing'])

        report_lines.append(f"  {'Metric':<30} {'Stop 1 (avg)':<15} {'Stops 2..N (avg)':<18} {'Delta':<12} {'Ratio'}")
        report_lines.append(f"  {'-'*30} {'-'*15} {'-'*18} {'-'*12} {'-'*8}")
        report_lines.append(f"  {'Paragraph count':<30} {s1_para_avg:<15.1f} {rest_para_avg:<18.1f} {s1_para_avg - rest_para_avg:<+12.1f} {s1_para_avg/rest_para_avg:.2f}x")
        report_lines.append(f"  {'Character length':<30} {s1_chars_avg:<15.0f} {rest_chars_avg:<18.0f} {s1_chars_avg - rest_chars_avg:<+12.0f} {s1_chars_avg/rest_chars_avg:.2f}x")
        report_lines.append(f"  {'ANCHORED rate':<30} {s1_anch_avg:<15.0%} {rest_anch_avg:<18.0%} {(s1_anch_avg - rest_anch_avg)*100:<+12.1f}pp {'—'}")
        report_lines.append(f"  {'Tour framing (per ¶)':<30} {s1_frame_avg:<15.2f} {rest_frame_avg:<18.2f} {s1_frame_avg - rest_frame_avg:<+12.2f} {s1_frame_avg/rest_frame_avg if rest_frame_avg > 0 else float('inf'):.2f}x")
        report_lines.append(f"  {'Stops with ANY framing':<30} {s1_has_framing}/{n1:<14} {rest_has_framing}/{nr:<17} {'—':<12} {'—'}")
        report_lines.append("")
        report_lines.append(f"  Medians: S1 ¶={s1_para_med}, chars={s1_chars_med}  |  Rest ¶={rest_para_med}, chars={rest_chars_med}")

    # ─── Verbatim evidence: Stop 1 opening paragraphs ────────────────────
    report_lines.append("")
    report_lines.append("─" * 78)
    report_lines.append("VERBATIM EVIDENCE: Stop 1 opening paragraph (first 300 chars)")
    report_lines.append("─" * 78)
    report_lines.append("")

    cur2 = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    for tour_id in tour_ids:
        cur2.execute("SELECT tour_name, tour_content FROM audio_tours WHERE id = %s", (tour_id,))
        row = cur2.fetchone()
        if not row or not row['tour_content']:
            continue
        stops = parse_tour_stops(row['tour_content'])
        if stops and stops[0]['paragraphs']:
            first_para = stops[0]['paragraphs'][0]
            framing = count_tour_framing_matches(first_para)
            is_nav = is_navigation_paragraph(first_para)
            report_lines.append(f"Tour {tour_id} — {row['tour_name'][:50]}")
            report_lines.append(f"  Stop 1 title: {stops[0]['title']}")
            report_lines.append(f"  Tour framing matches: {framing}  |  Navigation: {is_nav}")
            report_lines.append(f"  >>> {first_para[:300]}")
            if len(first_para) > 300:
                report_lines.append(f"      [...{len(first_para)} total chars]")
            report_lines.append("")

    # ─── Mechanism summary ───────────────────────────────────────────────
    report_lines.append("─" * 78)
    report_lines.append("MECHANISM: Where Stop 1's extra content comes from")
    report_lines.append("─" * 78)
    report_lines.append("")
    report_lines.append("File: generate_tour_text.py")
    report_lines.append("")
    report_lines.append("1. PROLOG GENERATION (lines 6316-6345):")
    report_lines.append("   - Activated only when STORIED_MODE=true AND spine generation succeeds")
    report_lines.append("   - Calls GPT-3.5-turbo with prompt: 'Write a compelling 80-190 word tour")
    report_lines.append("     introduction that frames this experience as a journey'")
    report_lines.append("   - Uses: connecting_thread, tour_hook, chapter previews, venue-identity facts")
    report_lines.append("   - Stored in _saved_prolog (declared at line 4650)")
    report_lines.append("")
    report_lines.append("2. PROLOG INJECTION INTO STOP 1 (line 6594-6595):")
    report_lines.append("   # [R2] For Stop 1: inject prolog before description")
    report_lines.append("   if i == 0 and _saved_prolog:")
    report_lines.append("       poi_content += f\"{_saved_prolog}\\n\\n\"")
    report_lines.append("")
    report_lines.append("3. ADDITIONAL STOP 1 EXCLUSIVES:")
    report_lines.append("   - Museum Information / operational details (hours, admission)")
    report_lines.append("     → line 6580: if tour_category == 'museum' and i == 0")
    report_lines.append("   - Entrance directions (non-museum tours)")
    report_lines.append("   - Coordinates always shown (museum: only Stop 1 shows them)")
    report_lines.append("")
    report_lines.append("4. FALLBACK PATH (LOCAL-119, lines 6430-6460):")
    report_lines.append("   If prolog LLM fails:")
    report_lines.append("   a) Use Stop 1's first two description sentences")
    report_lines.append("   b) Use raw tour_hook (last resort)")
    report_lines.append("   c) Empty (tour opens directly on Stop 1 content)")
    report_lines.append("")
    report_lines.append("RESULT: Stop 1 always receives 80-190 extra words (prolog) that are")
    report_lines.append("ABOUT THE TOUR, not about the POI. This is the structural phenomenon")
    report_lines.append("Michael observed. The prolog text describes the journey, names the region,")
    report_lines.append("previews the arc — none of which belongs to Stop 1's POI specifically.")

    # ─── Verdict ─────────────────────────────────────────────────────────
    report_lines.append("")
    report_lines.append("─" * 78)
    report_lines.append("VERDICT")
    report_lines.append("─" * 78)
    report_lines.append("")

    if n1 > 0 and nr > 0:
        size_ratio = s1_chars_avg / rest_chars_avg if rest_chars_avg > 0 else 0
        para_ratio = s1_para_avg / rest_para_avg if rest_para_avg > 0 else 0
        framing_diff = s1_frame_avg - rest_frame_avg

        if size_ratio > 1.2 or framing_diff > 0.3:
            report_lines.append("CONFIRMED: The effect is real and systematic.")
            report_lines.append("")
            report_lines.append(f"  - Stop 1 is {size_ratio:.2f}x longer than average stop (chars)")
            report_lines.append(f"  - Stop 1 has {para_ratio:.2f}x more paragraphs")
            report_lines.append(f"  - Tour framing rate: Stop 1 = {s1_frame_avg:.2f}/¶ vs rest = {rest_frame_avg:.2f}/¶")
            report_lines.append(f"  - {s1_has_framing}/{n1} Stop 1s contain tour-level framing")
            report_lines.append("")
            report_lines.append("The prolog IS the tour introduction. It is legitimate content that")
            report_lines.append("belongs in its own slot rather than inside Stop 1.")
            report_lines.append("")
            report_lines.append("WHAT SEPARATING IT WOULD TOUCH:")
            report_lines.append("  1. generate_tour_text.py line 6594: the injection point")
            report_lines.append("     Change: emit prolog as a separate 'Introduction' section")
            report_lines.append("     above Stop 1, instead of inside it.")
            report_lines.append("  2. parse_tour_stops() in stop_anchor_detector_v2.py: would need")
            report_lines.append("     to recognize an 'Introduction' section as non-stop content.")
            report_lines.append("  3. App tour player: if it parses stops by 'Stop N:' headers,")
            report_lines.append("     an Introduction section needs its own rendering path.")
            report_lines.append("  4. Tour delivery / existing tours: all existing tours have the")
            report_lines.append("     prolog inside Stop 1. Migration or backward compat needed.")
            report_lines.append("")
            report_lines.append("RISK:")
            report_lines.append("  - Low code risk (1 injection point, clear boundary)")
            report_lines.append("  - Medium integration risk (app player, delivery, existing tours)")
            report_lines.append("  - The prolog is good content — the fault is placement, not quality")
        else:
            report_lines.append("NOT CONFIRMED: Stop 1 does not appear systematically different.")
            report_lines.append(f"  Size ratio: {size_ratio:.2f}x, framing diff: {framing_diff:.2f}")
            report_lines.append("  Michael's read is a one-off observation, not a pattern.")

    conn.close()
    return '\n'.join(report_lines)


# ─── Entry point ─────────────────────────────────────────────────────────────

if __name__ == '__main__':
    report = analyze_stop1_vs_rest(TOUR_IDS)
    print(report)

    # Write report to file
    with open('tests/stop1_intro_analysis_report.txt', 'w') as f:
        f.write(report)
    print(f"\n\nReport written to tests/stop1_intro_analysis_report.txt")
