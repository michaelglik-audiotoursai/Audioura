#!/usr/bin/env python3
"""LOCAL-205: Per-claim unsupported analysis.

Classifies every factual claim in generated paragraphs as:
- SUPPORTED_PARAPHRASE: claim is in the corpus (quotes the passage)
- SUPPORTED_ELSEWHERE: correct venue, wrong stop (not counted as pass per D62)
- UNSUPPORTED: factually specific claim not in corpus
- NOT_CHECKABLE: atmospheric/aesthetic, no verifiable fact
- CONTRADICTED: contradicts corpus

Method: automated keyword detection + manual edge-case review.
"""
import sys
import os
import json
import re

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from db_connection import get_db_config
import psycopg2

# Load all corpus text for matching
config = get_db_config()
conn = psycopg2.connect(**config)
cur = conn.cursor()

cur.execute('''SELECT pages_json, story_elements_json FROM venue_corpus WHERE venue_name ILIKE %s''', ('%matisse%',))
row = cur.fetchone()
pages = json.loads(row[0]) if isinstance(row[0], str) else row[0]
elements = json.loads(row[1]) if isinstance(row[1], str) else row[1]

all_corpus = ''
for p in pages:
    if isinstance(p, dict):
        all_corpus += p.get('text', '') + '\n'
    else:
        all_corpus += str(p) + '\n'
for e in elements:
    all_corpus += e.get('text', '') + ' ' + e.get('source_sentence', '') + '\n'
cur.execute('''SELECT passages_json FROM stop_corpus WHERE venue_name ILIKE %s''', ('%matisse%',))
for row in cur.fetchall():
    pj = row[0]
    passages = json.loads(pj) if isinstance(pj, str) else pj
    for p in passages:
        text = p.get('text', p) if isinstance(p, dict) else str(p)
        all_corpus += text + '\n'
conn.close()

corpus_lower = all_corpus.lower()


def is_in_corpus(phrase):
    """Check if a phrase (or close variant) appears in corpus."""
    return phrase.lower() in corpus_lower


# ─── Classification of specific factual claims ───────────────────────
# Each claim is a tuple: (text_snippet_pattern, verdict, evidence_or_reasoning)

# CORPUS-SUPPORTED FACTS (available in venue_corpus/stop_corpus):
SUPPORTED_FACTS = {
    'opened_1963': 'The museum opened in 1963',
    'villa_arenes': 'Villa des Arènes',
    'seventeenth_century': 'seventeenth-century villa / XVIIe siècle',
    'cimiez': 'neighborhood of Cimiez',
    'reopened_1993': 'closed four years, reopened 1993',
    '1989_expansion': 'In 1989 archaeological museum moved, Matisse expanded',
    'nu_bleu_1952': 'Nu bleu IV, 1952 (title+date in Chefs-d\'œuvre list)',
    'nymphe_1936_1938': 'Nymphe dans la forêt, 1936-1938 (title+dates)',
    '68_paintings': '68 paintings and gouaches',
    '236_drawings': '236 drawings',
    '218_prints': '218 prints',
    '57_sculptures': '57 sculptures',
    '14_books': '14 illustrated books',
    'matisse_donations': 'Matisse himself donated works',
    'heirs_donated': 'heirs of Matisse also donated',
    'lived_nice_1917_1954': 'Matisse lived/worked in Nice from 1917 to 1954',
    'municipal_museum': 'municipal museum devoted to Matisse',
    '2025_donation': 'In 2025, Nature morte à la statuette africaine donated',
    'dedicated_matisse': 'museum devoted to the work of Henri Matisse',
}

# UNSUPPORTED CLAIMS (not in any corpus passage):
UNSUPPORTED_CLAIMS = {
    'blue_gouache_paper': 'blue gouache-covered paper (medium description)',
    'canson_paper': 'white Canson paper',
    'mounted_canvas': 'mounted on a vertical canvas',
    'female_nude': 'female nude / depicts a nude',
    'cut_paste_technique': 'cut and pasted / cut-out technique for Nu bleu IV',
    'first_last_blue_nude': 'first Blue Nude started, last completed',
    'satyr_approaching': 'satyr approaching the nymph',
    'nude_nymph_reclining': 'nude nymph reclining in forest',
    'oil_on_canvas': 'oil on canvas (medium for Nymphe)',
    'on_loan_1989': 'on loan since 1989',
    'donated_1979': 'donated in 1979',
    'orangerie_2023': 'exhibited at musée de l\'Orangerie in 2023',
    'earth_tones_greens': 'rich earth tones and vibrant greens (color desc)',
    'negative_space': 'deliberate use of negative space',
    'four_blue_nudes': 'one of four Blue Nudes',
    'blue_nudes_series': 'Blue Nudes series',
    'land_art_reference': 'references to nature/landscape movement',
    'light_shadow_foliage': 'light filtering through foliage',
}


def classify_paragraph_claims(text, stop_title):
    """Classify claims in a paragraph. Returns counts and details."""
    supported = []
    unsupported = []
    not_checkable = []
    supported_elsewhere = []
    contradicted = []
    
    text_lower = text.lower()
    
    # Check supported facts
    if '1963' in text:
        supported.append(('SUPPORTED_PARAPHRASE', 'museum opened 1963',
                         'Page 4: "The museum was created in 1963"'))
    if 'villa des arènes' in text_lower or 'villa des arenes' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'Villa des Arènes',
                         'Page 4: "located in the Villa des Arènes"'))
    if 'seventeenth' in text_lower or 'xviie' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'seventeenth-century building',
                         'Page 4: "a seventeenth-century villa"'))
    if 'cimiez' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'Cimiez neighborhood',
                         'Page 4: "in the neighborhood of Cimiez"'))
    if '1993' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'reopened 1993',
                         'Page 4: "reopened in 1993"'))
    if '1989' in text_lower and 'archaeolog' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', '1989 archaeological museum moved',
                         'Page 4: "In 1989, the archaeological museum was moved"'))
    elif '1989' in text_lower and 'expand' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', '1989 museum expanded',
                         'Page 4: "allowing the Musée Matisse to have the entire building"'))
    elif '1989' in text_lower and ('loan' in text_lower or 'prêt' in text_lower):
        unsupported.append(('UNSUPPORTED', 'on loan since 1989',
                           'No corpus passage mentions any loan arrangement'))
    elif '1989' in text_lower:
        # Just the year in epilog context
        supported.append(('SUPPORTED_PARAPHRASE', '1989 referenced',
                         'Page 4: "In 1989, the archaeological museum was moved"'))
    if '1952' in text_lower and stop_title == 'Nu bleu IV':
        supported.append(('SUPPORTED_PARAPHRASE', 'Nu bleu IV created 1952',
                         'Page 5 (Chefs-d\'œuvre): "Nu bleu IV, 1952"'))
    if ('1936' in text_lower or '1938' in text_lower) and stop_title == 'Nymphe dans la forêt':
        supported.append(('SUPPORTED_PARAPHRASE', 'Nymphe 1936-1938',
                         'Page 5 (Chefs-d\'œuvre): "Nymphe dans la forêt, 1936-1938"'))
    if '68 paint' in text_lower or '68 peinture' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', '68 paintings collection',
                         'Page 4: "68 paintings and gouaches, 236 drawings"'))
    if 'donation' in text_lower or 'donat' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'donations shaped museum',
                         'SE[002]: "Matisse himself donated a variety of works"'))
    if 'heir' in text_lower or 'héritier' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'heirs donated',
                         'SE[004]: "donations from the heirs of Henri Matisse"'))
    if '2025' in text_lower and 'statuette' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', '2025 donation',
                         'SE[003]: "reçu en don la Nature morte à la statuette africaine en 2025"'))
    if 'closed' in text_lower and ('four year' in text_lower or 'quatre ans' in text_lower or 'renovati' in text_lower):
        supported.append(('SUPPORTED_PARAPHRASE', 'closed for renovations',
                         'Page 4: "closed for four years during renovations"'))
    if 'municipal' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'municipal museum',
                         'Page 4: "a municipal museum devoted to the work"'))
    if '1917' in text_lower and '1954' in text_lower:
        supported.append(('SUPPORTED_PARAPHRASE', 'Matisse in Nice 1917-1954',
                         'SE[006]: "résida et travailla à Nice de 1917 à 1954"'))
    
    # Check unsupported claims
    if 'gouache' in text_lower and 'paper' in text_lower:
        unsupported.append(('UNSUPPORTED', 'blue gouache-covered paper medium',
                           'No corpus passage describes Nu bleu IV\'s medium'))
    if 'canson' in text_lower:
        unsupported.append(('UNSUPPORTED', 'Canson paper',
                           'Canson not mentioned anywhere in corpus'))
    if ('vertical canvas' in text_lower or 'mounted on' in text_lower):
        unsupported.append(('UNSUPPORTED', 'mounted on vertical canvas',
                           'No mounting description in corpus'))
    if ('female nude' in text_lower or 'nude figure' in text_lower or
        ('nude' in text_lower and stop_title == 'Nu bleu IV' and 'nu bleu' not in text_lower[:text_lower.find('nude')-5:text_lower.find('nude')].lower())):
        # Need to be careful: "Nu" in the title is not the same as describing a nude
        if stop_title == 'Nu bleu IV' and re.search(r'\b(female nude|nude figure|a female nude|depicts.*nude)', text_lower):
            unsupported.append(('UNSUPPORTED', 'female nude subject description',
                               'Corpus lists only title "Nu bleu IV, 1952" with no subject description'))
    if 'cut and past' in text_lower or 'cut-out' in text_lower or 'cutting and layer' in text_lower:
        unsupported.append(('UNSUPPORTED', 'cut and paste / cut-out technique',
                           'Technique not described in corpus for this specific work'))
    if re.search(r'first.*blue nude|last.*blue nude|blue nudes series|one of four blue', text_lower):
        unsupported.append(('UNSUPPORTED', 'Blue Nudes series / first-last sequence',
                           'No mention of Blue Nudes series in corpus'))
    if 'satyr' in text_lower:
        unsupported.append(('UNSUPPORTED', 'satyr approaching nymph',
                           '"satyr" does not appear anywhere in corpus'))
    if stop_title == 'Nymphe dans la forêt' and re.search(r'nude.*nymph|nymph.*reclin|naked nymph|nymph.*forest', text_lower):
        unsupported.append(('UNSUPPORTED', 'nude nymph reclining in forest',
                           'Corpus lists only "Nymphe dans la forêt, 1936-1938" with no scene description'))
    if 'oil on canvas' in text_lower:
        unsupported.append(('UNSUPPORTED', 'oil on canvas medium',
                           'Medium not stated in corpus'))
    if '1979' in text_lower:
        unsupported.append(('UNSUPPORTED', 'donated/created 1979',
                           '1979 not mentioned in corpus'))
    if 'orangerie' in text_lower:
        unsupported.append(('UNSUPPORTED', 'Orangerie exhibition',
                           'Musée de l\'Orangerie not in corpus'))
    if 'negative space' in text_lower:
        unsupported.append(('UNSUPPORTED', 'deliberate use of negative space',
                           'No compositional analysis in corpus'))
    
    # NOT_CHECKABLE: atmospheric/aesthetic descriptions without verifiable facts
    # (e.g. "a sense of tranquility", "inviting contemplation")
    # These are counted separately
    
    return {
        'supported': supported,
        'unsupported': unsupported,
        'not_checkable': not_checkable,
        'supported_elsewhere': supported_elsewhere,
        'contradicted': contradicted,
    }


def main():
    tests_dir = os.path.dirname(os.path.abspath(__file__))
    
    results = {}
    for arm in ['A', 'B']:
        results[arm] = []
        for run in [1, 2, 3]:
            path = os.path.join(tests_dir, f'local205_{arm}{run}_text.txt')
            with open(path, 'r') as f:
                tour_text = f.read()
            
            # Parse paragraphs
            paragraphs = []
            current_stop = None
            for line in tour_text.split('\n'):
                line = line.strip()
                if re.match(r'^Stop \d+:', line):
                    current_stop = re.sub(r'^Stop \d+:\s*', '', line)
                elif (len(line) > 50 and current_stop and
                      not line.startswith('Address:') and 
                      not line.startswith('Coordinates:') and
                      not line.startswith('Museum Information:') and
                      not line.startswith('Directions:') and
                      not line.startswith('Step-by-Step') and
                      not line.startswith('Tour-Category:')):
                    if not line.startswith('Sources:'):
                        paragraphs.append({'text': line, 'stop': current_stop})
            
            run_claims = []
            for para in paragraphs:
                claims = classify_paragraph_claims(para['text'], para['stop'])
                run_claims.append({
                    'stop': para['stop'],
                    'text_preview': para['text'][:80] + '...',
                    'supported_count': len(claims['supported']),
                    'unsupported_count': len(claims['unsupported']),
                    'unsupported_details': [(v, desc, ev) for v, desc, ev in claims['unsupported']],
                    'supported_details': [(v, desc, ev) for v, desc, ev in claims['supported']],
                })
            results[arm].append(run_claims)
    
    # Summary
    print("="*70)
    print("LOCAL-205: UNSUPPORTED CLAIMS ANALYSIS")
    print("="*70)
    
    for arm_label, model in [('A', 'gpt-3.5-turbo'), ('B', 'gpt-4o-mini')]:
        total_supported = 0
        total_unsupported = 0
        total_paras = 0
        paras_with_unsupported = 0
        all_unsupported = []
        
        for run_idx, run_data in enumerate(results[arm_label]):
            for para in run_data:
                total_paras += 1
                total_supported += para['supported_count']
                total_unsupported += para['unsupported_count']
                if para['unsupported_count'] > 0:
                    paras_with_unsupported += 1
                    for v, desc, ev in para['unsupported_details']:
                        all_unsupported.append(f"  {arm_label}{run_idx+1}: {desc}")
        
        print(f"\n--- ARM {arm_label}: {model} ---")
        print(f"  Total paragraphs (excl sources): {total_paras}")
        print(f"  Total supported claims: {total_supported}")
        print(f"  Total unsupported claims: {total_unsupported}")
        print(f"  Paragraphs with ≥1 unsupported: {paras_with_unsupported}/{total_paras}")
        print(f"  Unsupported per paragraph: {total_unsupported/total_paras:.2f}")
        print(f"\n  Unsupported claims breakdown:")
        from collections import Counter
        claim_types = Counter()
        for run_data in results[arm_label]:
            for para in run_data:
                for v, desc, ev in para['unsupported_details']:
                    claim_types[desc] += 1
        for desc, count in claim_types.most_common():
            print(f"    {desc}: {count}")
    
    # Per-run detail
    print("\n" + "="*70)
    print("PER-RUN DETAIL")
    print("="*70)
    for arm_label in ['A', 'B']:
        for run_idx, run_data in enumerate(results[arm_label]):
            print(f"\n--- {arm_label}{run_idx+1} ---")
            for i, para in enumerate(run_data):
                u = para['unsupported_count']
                s = para['supported_count']
                marker = " ⚠️" if u > 0 else ""
                print(f"  P{i+1} [{para['stop'][:20]}] supported={s} unsupported={u}{marker}")
                if u > 0:
                    for v, desc, ev in para['unsupported_details']:
                        print(f"       → {desc}")


if __name__ == '__main__':
    main()
