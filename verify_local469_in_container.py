#!/usr/bin/env python3
"""verify_local469_in_container.py — AC4 proof, run INSIDE the tour-generator
container against a COPY of the code (throwaway /tmp path), never touching /app
or restarting anything.

It execs the REAL PHASE 5.152 block extracted from the container's own
/app/generate_tour_text.py, with a monkeypatched requests.post so it costs $0 and
hits no network, and feeds it Michael's Example A + the real Cimiez Monastery
paragraph. Proves the gate's log line fires inside the container's Python env,
with the stop and the reason.
"""
import os, sys, io, json, re, contextlib

# The gate module copy lives beside this harness in /tmp/local469; deps in /app.
sys.path.insert(0, '/tmp/local469')
sys.path.insert(0, '/app')

GEN = '/tmp/local469/generate_tour_text.py'

# --- monkeypatch requests.post: deterministic, offline verdicts ---
import requests as _rq

class _Resp:
    status_code = 200
    def __init__(self, c): self._c = c
    def json(self): return {"choices":[{"message":{"content":self._c}}],
                            "usage":{"total_tokens":1,"prompt_tokens":1,"completion_tokens":1}}

def _post(url, headers=None, data=None, timeout=None):
    u = json.loads(data)["messages"][-1]["content"]
    if 'VERDICT: SPECIFIC | TRANSFERABLE' in u:
        if 'Saint-Pons' in u or '1546' in u:
            return _Resp("VERDICT: SPECIFIC\nREASON: dated 1546 Saint-Pons swap, false elsewhere")
        return _Resp("VERDICT: TRANSFERABLE\nREASON: generic scene-setting, nothing breaks")
    if 'VERDICT: GROUNDED | UNGROUNDED' in u:
        if 'Fitzgerald' in u:
            return _Resp("VERDICT: UNGROUNDED\nREASON: sentiment only, no link to this stop")
        return _Resp("VERDICT: GROUNDED\nREASON: link stated")
    return _Resp("VERDICT: TRANSFERABLE\nREASON: default")

_rq.post = _post

# --- extract the real PHASE 5.152 block from the container's generate_tour_text.py ---
src = open(GEN, encoding='utf-8').read()
start = src.index('# -------- [LOCAL-469] PHASE 5.152: Stop-specificity gate --------')
end = src.index('# -------- [LOCAL-263] PHASE 5.156: Unsupported-claim gate --------', start)
block = '\n'.join(ln[4:] if ln.startswith('    ') else ln
                  for ln in src[start:end].splitlines())

EXAMPLE_A = ("Cycling on the French Riviera, stop at Cap d'Antibes to experience the "
             "enduring power of nature, inspiring creativity and stimulating the "
             "imagination while admiring panoramic views and soaking up the atmosphere "
             "of this everyday paradise.")
EXAMPLE_B = ("As you stand on Cap d'Antibes with Mediterranean sea stretching out before "
             "you Imagine the scene that once captivated Scott Fitzgerald inspiring the "
             "setting of his timeless novels.")
CIMIEZ = ("The Cimiez Monastery, with roots stretching back to the 9th century, stands "
          "as a silent witness to the passage of time. In 1546, a pivotal moment unfolded "
          "when Franciscan friars negotiated a property swap with Benedictine monks of "
          "Saint-Pons Abbey, acquiring a small chapel and plot of land in Cimiez.")

poi_list = [
    {'name': "Cap d'Antibes", 'description': EXAMPLE_A + "\n\n" + EXAMPLE_B},
    {'name': 'Cimiez Monastery', 'description': CIMIEZ},
    {'name': 'Villa Leopolda', 'description': 'Villa Leopolda was built in 1902.'},
]

ns = {'os': os, 'sys': sys, 'poi_list': poi_list, 'api_key': 'stub-key'}
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    exec(compile(block, GEN, 'exec'), ns, ns)
out = buf.getvalue()
print(out)
print("=== POST-GATE Cap d'Antibes description ===")
print(poi_list[0]['description'])
