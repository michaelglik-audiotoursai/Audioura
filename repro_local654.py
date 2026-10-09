#!/usr/bin/env python3
"""repro_local654.py — isolate the pass that produces the ON-mode mid-clause
collisions ("…venture into Thousands of…", "…to complete Leonardo prepared…").

Runs reconstructed stop bodies — shaped like the gpt-4.1-mini output, i.e. with a
MISSING SPACE after a sentence-ending period — through the SAME splitter and the
SAME guard passes the generator applies, in order, printing before/after for each.

No network, no DB. Pure functions only.
"""
import re


def collisions(text):
    """Return mid-clause joins of the '…into Thousands…' shape: a lowercase word,
    a single space, then a Capitalised word, with no punctuation between them."""
    hits = []
    for m in re.finditer(r"([a-z]{3,})\s+([A-Z][a-z]{2,})", text):
        start = max(0, m.start() - 40)
        ctx = text[start:m.end() + 40]
        hits.append((m.group(1), m.group(2), ctx.strip()))
    return hits


def show(label, text):
    print(f"\n----- {label} -----")
    print(text)


# Reconstructed Stop-1 body of AIC 599 as the model emits it: a missing space
# after "depths." welds the two sentences.
AIC_S1 = (
    "When Hokusai produced this work, he was in the later decades of his life. "
    "Years of personal upheaval and artistic reinvention had brought him to this "
    "point\u2014seeking to capture not only the outward appearance of nature, but "
    "its overwhelming power and the vulnerability of those who venture into its "
    "depths.Thousands of copies of The Great Wave were originally produced and "
    "sold inexpensively, making it accessible to many during a period when "
    "Japanese trade was strictly controlled. "
    "The Great Wave of Kanagawa was painted between 1830 and 1833. "
    "Katsushika Hokusai lived from 1760 to 1849, creating it during his lifetime."
)

UFFIZI_S2 = (
    "In 1481, the monks of San Donato a Scopeto commissioned Leonardo da Vinci "
    "to paint the Adoration of the Magi, giving him two years to complete it."
    "Leonardo prepared extensively, creating multiple preparatory studies for "
    "both the figures and the background. "
    "However, when he departed for Milan in the summer of 1482, he left the "
    "painting unfinished."
)


def run_passes(body, title="", artist="", material="", period=""):
    import sentence_split
    print("\n### split_sentences on the raw body ###")
    for i, s in enumerate(sentence_split.split_sentences(body)):
        print(f"  [{i}] {s!r}")

    wrapped = f"Stop 1: {title or 'X'}\n\n{body}\n"

    import story_balance as sbal
    out, rep = sbal.balance_tour_text_work_first(
        wrapped, venue_tokens=[], stop_subjects={1: title})
    print(f"\n[LOCAL-620] changed={rep.get('changed')}")
    if rep.get("changed"):
        show("after LOCAL-620 story_balance", out)

    import same_title_bleed_guard as stbg
    out2, rep2 = stbg.filter_tour_text_same_title(
        out, stop_titles={1: title}, stop_artists={1: artist})
    print(f"[LOCAL-623 same_title] changed={rep2.get('changed')}")
    if rep2.get("changed"):
        show("after LOCAL-623 same_title", out2)
    out = out2

    out3, rep3 = stbg.filter_tour_text_object_type(
        out, stop_titles={1: title}, stop_materials={1: material})
    print(f"[LOCAL-626 object_type] changed={rep3.get('changed')}")
    if rep3.get("changed"):
        show("after LOCAL-626 object_type", out3)
    out = out3

    import date_consistency_guard as dcg
    out4, rep4 = dcg.filter_tour_text_date_consistency(
        out, stop_corpus_dates={1: period})
    print(f"[LOCAL-626 date_consistency] changed={rep4.get('changed')}")
    if rep4.get("changed"):
        show("after LOCAL-626 date_consistency", out4)
    out = out4

    import museum_motif_guard as mmg
    out5, rep5 = mmg.filter_tour_text_museum_motif(out)
    print(f"[LOCAL-623 museum_motif] changed={rep5.get('changed')}")
    if rep5.get("changed"):
        show("after LOCAL-623 museum_motif", out5)
    out = out5

    show("FINAL", out)
    hs = collisions(out)
    print("\n### collisions in FINAL ###")
    for lw, cap, ctx in hs:
        print(f"  '{lw} {cap}'  …{ctx}…")
    return out


if __name__ == "__main__":
    print("=" * 70)
    print("AIC 599 Stop 1 (Great Wave) — missing space after 'depths.'")
    print("=" * 70)
    run_passes(AIC_S1, title="The Great Wave of Kanagawa",
               artist="Katsushika Hokusai", material="woodblock print",
               period="1830-1833")

    print("\n" + "=" * 70)
    print("Uffizi 597 Stop 2 (Adorazione) — missing space after 'complete it.'")
    print("=" * 70)
    run_passes(UFFIZI_S2, title="Adorazione dei Magi",
               artist="Leonardo da Vinci", material="tempera on wood",
               period="1481-1482")
