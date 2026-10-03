#!/usr/bin/env python3
"""LOCAL-571 step 3 — build the blind pack from whatever cells succeeded.

For each request where BOTH arms (A=gpt-4o, B=gpt-4.1) produced a tour text, this
writes the two texts as <name>_P.txt and <name>_Q.txt with the P/Q assignment
chosen at random per request (so the reader cannot infer the model from the
letter), and records the mapping in KEY.md after 60 blank lines. No model names
appear inside any tour text (verified: the generator does not stamp the model).

Honesty guard (D-style): a blind A/B comparison REQUIRES both arms for a request.
This run was blocked by OpenAI credit exhaustion after a single cell (Palais_A,
gpt-4o) completed; the gpt-4.1 arm never produced a text. Where an arm is missing
the request cannot be a blind pair, so its single available text is written as
<name>_SINGLE_<letter>.txt and KEY.md states which arm is missing and why. The
pack is honest about n: it does not fabricate the absent arm.

Run: python3 build_local571_blind_pack.py
"""
import json
import os
import random

HERE = os.path.dirname(os.path.abspath(__file__))
MEAS = os.path.join(HERE, "LOCAL571_measure")
SUMMARY = os.path.join(MEAS, "summary.json")
DEST = os.path.expanduser("~/Desktop/Audioura_model_blind")

REQUESTS = ["Palais", "MFA", "BosRest", "OldNice"]
# fixed seed so re-runs reproduce the same (still-random-looking) assignment
random.seed(571)


def _read_text(cell_id):
    p = os.path.join(MEAS, f"{cell_id}.txt")
    if os.path.exists(p) and os.path.getsize(p) > 0:
        return open(p, encoding="utf-8").read()
    return None


def main():
    os.makedirs(DEST, exist_ok=True)
    summary = json.load(open(SUMMARY))
    cells = summary.get("cells", {})

    key_lines = []
    key_lines.append("# LOCAL-571 Blind Pack — KEY")
    key_lines.append("")
    key_lines.append("Arm A = writer model gpt-4o (ship default).")
    key_lines.append("Arm B = writer model gpt-4.1 (candidate).")
    key_lines.append("Gates run gpt-4o-mini in both arms. 3 stops, Gemini off, "
                     "LOCAL-569 flags OFF.")
    key_lines.append("")
    key_lines.append("Per-request P/Q assignment (random per request):")
    key_lines.append("")

    manifest = []
    for rkey in REQUESTS:
        a_ok = cells.get(f"{rkey}_A", {}).get("ok")
        b_ok = cells.get(f"{rkey}_B", {}).get("ok")
        a_txt = _read_text(f"{rkey}_A") if a_ok else None
        b_txt = _read_text(f"{rkey}_B") if b_ok else None

        if a_txt and b_txt:
            # genuine blind pair — randomise which arm is P
            if random.random() < 0.5:
                p_arm, p_txt, q_arm, q_txt = "A", a_txt, "B", b_txt
            else:
                p_arm, p_txt, q_arm, q_txt = "B", b_txt, "A", a_txt
            with open(os.path.join(DEST, f"{rkey}_P.txt"), "w", encoding="utf-8") as fh:
                fh.write(p_txt)
            with open(os.path.join(DEST, f"{rkey}_Q.txt"), "w", encoding="utf-8") as fh:
                fh.write(q_txt)
            key_lines.append(f"- {rkey}: P = arm {p_arm} "
                            f"({'gpt-4o' if p_arm=='A' else 'gpt-4.1'}), "
                            f"Q = arm {q_arm} "
                            f"({'gpt-4o' if q_arm=='A' else 'gpt-4.1'})")
            manifest.append(f"{rkey}_P.txt / {rkey}_Q.txt (blind pair)")
        elif a_txt or b_txt:
            # only one arm available — NOT a blind pair; label it honestly
            arm = "A" if a_txt else "B"
            txt = a_txt or b_txt
            model = "gpt-4o" if arm == "A" else "gpt-4.1"
            fn = f"{rkey}_SINGLE_{arm}.txt"
            with open(os.path.join(DEST, fn), "w", encoding="utf-8") as fh:
                fh.write(txt)
            missing = "B (gpt-4.1)" if arm == "A" else "A (gpt-4o)"
            key_lines.append(f"- {rkey}: NOT A BLIND PAIR. Only arm {arm} "
                            f"({model}) produced a text; arm {missing} is missing "
                            f"(OpenAI credit exhaustion). File: {fn}")
            manifest.append(f"{fn} (single arm — no blind pair)")
        else:
            key_lines.append(f"- {rkey}: no text in either arm "
                            f"(OpenAI credit exhaustion). No file.")
            manifest.append(f"{rkey}: no file (both arms empty)")

    # README (visible, no key)
    with open(os.path.join(DEST, "README.md"), "w", encoding="utf-8") as fh:
        fh.write("# Audioura model blind pack (LOCAL-571)\n\n")
        fh.write("Each `<name>_P.txt` / `<name>_Q.txt` pair is the same tour "
                "request written by two different writer models; which letter is "
                "which model is random per request and recorded only in `KEY.md` "
                "(after 60 blank lines, so you can read the tours first without "
                "spoiling the key). No model names appear inside the tour texts.\n\n")
        fh.write("Files:\n\n")
        for m in manifest:
            fh.write(f"- {m}\n")
        fh.write("\nNOTE: this run was blocked by OpenAI credit exhaustion after "
                "one cell completed, so most requests have no blind pair. See "
                "KEY.md and SUBMISSION_LOCAL-571.md for the full account.\n")

    # KEY.md — 60 blank lines first, then the key
    with open(os.path.join(DEST, "KEY.md"), "w", encoding="utf-8") as fh:
        fh.write("\n" * 60)
        fh.write("\n".join(key_lines) + "\n")

    print(f"[blind pack] written to {DEST}")
    for fn in sorted(os.listdir(DEST)):
        print("  ", fn)


if __name__ == "__main__":
    main()
