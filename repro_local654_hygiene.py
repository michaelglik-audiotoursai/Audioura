#!/usr/bin/env python3
"""repro_local654_hygiene.py — run the welded mini-model text through the REAL
D523 clean_spoken_text then LOCAL-618 grammar_splice_lint, printing per-sentence
flags, to pinpoint the pass and sentence that produces the collision."""
import re
import spoken_text_hygiene as H

AIC_S1 = (
    "Stop 1: The Great Wave of Kanagawa\n\n"
    "When Hokusai produced this work, he was in the later decades of his life. "
    "Years of personal upheaval and artistic reinvention had brought him to this "
    "point\u2014seeking to capture not only the outward appearance of nature, but "
    "its overwhelming power and the vulnerability of those who venture into its "
    "depths.Thousands of copies of The Great Wave were originally produced and "
    "sold inexpensively, making it accessible to many during a period when "
    "Japanese trade was strictly controlled.\n"
)

UFFIZI_S2 = (
    "Stop 2: Adorazione dei Magi\n\n"
    "In 1481, the monks of San Donato a Scopeto commissioned Leonardo da Vinci "
    "to paint the Adoration of the Magi, giving him two years to complete it."
    "Leonardo prepared extensively, creating multiple preparatory studies for "
    "both the figures and the background. "
    "However, when he departed for Milan in the summer of 1482, he left the "
    "painting unfinished.\n"
)


def trace(label, text):
    print("=" * 72)
    print(label)
    print("=" * 72)
    out, rep = H.clean_spoken_text(text, verbose=True)
    print(f"\n[D523] report: missing_spaces={rep['missing_spaces']} seams={rep['seams']}")
    print("\n--- after D523 ---")
    print(out)
    # Now split exactly as grammar_splice_lint does and show flags.
    print("\n--- grammar_splice_lint per-sentence flags ---")
    for para in out.split("\n\n"):
        body = para
        m = re.match(r'^([A-Z][a-z]+:\s*)', para)
        if m:
            body = para[m.end():]
        for sent in re.split(r'(?<=[.!?])\s+', body):
            if sent.strip():
                codes = H.flag_sentence(sent)
                print(f"  flags={codes or '[]'}  {sent!r}")
    out2, rep2 = H.grammar_splice_lint(out, rewrite_fn=None, verbose=True)
    print("\n--- after LOCAL-618 (no rewrite_fn -> drop) ---")
    print(out2)
    hits = re.findall(r"[a-z]{3,}\s+[A-Z][a-z]{2,}", out2)
    print(f"\ncollision-shape hits: {hits}")


if __name__ == "__main__":
    trace("AIC 599 Stop 1", AIC_S1)
    print()
    trace("Uffizi 597 Stop 2", UFFIZI_S2)
