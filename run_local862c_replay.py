#!/usr/bin/env python3
"""run_local862c_replay.py - offline (no network, no spend) replay of the FINAL 862C
post-processing on (a) the saved live 862C tour and (b) the 862B source facts that
produced the garbled legends.  Not a substitute for the live run."""
import json, os, re, subprocess, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import user_stop_context as usc
from user_stop_narration import _split_sentences

H = os.path.dirname(os.path.abspath(__file__))
rep = json.load(open(os.path.join(H, "submission_artifacts/local862c/enrichment_report.json"), encoding="utf-8"))
text = open(os.path.join(H, "submission_artifacts/local862c/live_tour_7stops.txt"), encoding="utf-8").read()
old = json.loads(subprocess.check_output(
    ["git", "show", "4f803d9c:submission_artifacts/local862b/enrichment_report_final.json"], cwd=H))

print("== (a) legend source facts from 862B through the 862C block gate ==")
for st in old["stops"]:
    for f in st.get("facts", []):
        if f[1] == "legend":
            word = {"Rambutan": "rambutan", "Longan": "longan"}.get(st["stop"], "")
            blk = usc.legend_block(_split_sentences(f[2]), word)
            print(f"  {st['stop']}: {'KEPT -> ' + usc.legend_block_text(blk) if blk else 'OMITTED (fragment / does not tie back to the name)'}")

print("\n== (b) final bridge / kind guard on the live 862C facts ==")
for st in rep["stops"]:
    facts = [{"kind": f[1], "text": f[2], "layer": f[4]} for f in st.get("facts", [])]
    cat = next((re.sub(r"^.*? as: ", "", f["text"]).rstrip(".") for f in facts if f["kind"] == "category"), "")
    br = usc.bridge_sentence(st["stop"], cat, facts)
    print(f"  {st['stop']:20s} category={cat!r:20} bridge={br!r}")
thi = next(l for l in text.split("\n") if l.startswith("Thi Bar Saigon is rated"))
print("\n  Thi Bar before:", thi[:170])
print("  Thi Bar after :", usc.kind_guard(thi, "Gay bar")[:200])
print("\n== (c) 862B Thi Bar sentence, duplicate street name ==")
s = "The bar is located on Đề Thám Street, which along with Phạm Ngũ Lão and Đề Thám Streets, forms Saigon's Backpacker District."
print("  before:", s); print("  after :", usc.dedupe_names(s))
