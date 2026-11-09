# SUBMISSION — LOCAL-882B

Finishes LOCAL-882: the three narration defects its warm run left (a foreign
institutional name read literally as a hotel, an orphan "to seat guests", an
unsourced "both houses" claim) are fixed generically, and the cloud-parity warm
run now PASSES clean.

**Base:** LOCAL-882-proof-parity (852a4a90) — `git merge-base --is-ancestor
852a4a90 HEAD` exits 0.
**Branch:** LOCAL-882B-finish
**Commits:** 622cfa13 (the three fixes + tests), 6a394194 (keep the sourced
date/architect when the false-friend clause is dropped).

## The three fixes (generic — no venue names in code paths, D769)

### §1 A foreign institutional name read literally ("hôtel de ville" = city hall)
LOCAL-882's City Hall shipped: *"opened in 1909 as a hotel named Hotel de Ville …
This hotel became a gathering place for colonial officials and visitors."* A
literal read of the French **hôtel de ville** (= city hall).

- `landmark_claim_gate.venue_function_claims()` flags a sentence that assigns the
  venue a **function** ("a hotel", "a hospital", "a market", …) the stop's
  evidence does not support. It is always tested against the stop's **own**
  evidence — a real hotel whose evidence says "hotel" keeps the word.
- A **false-friend glossary** feeds the gate as reference DATA (not a venue key):
  `_FALSE_FRIEND_INSTITUTIONS` = hôtel de ville, Rathaus, ayuntamiento, palazzo
  comunale, mairie, câmara municipal, each mapped to the English word it is
  wrongly read as and the true-function tokens (city hall / town hall / municipal
  / hall) that belong to it.
- `venue_function_correction()` excises **only** the false-friend clause, so the
  sentence's sourced build year and architect survive: the City Hall sentence
  keeps "completed in 1908 … designed by … Gardè … opened in 1909" and loses only
  "as a hotel named Hotel de Ville". If the excision would empty the sentence, it
  is dropped.
- Narrator prompt: a FOREIGN-NAME rule tells the writer never to explain a
  foreign name by its literal translation unless the source states the meaning.

Warm text now reads: *"The building before you, completed in 1908 and officially
opened in 1909, was designed by the French architect Fernand Gardè. It rose
between 1898 and 1908 during the French colonial period and was originally known
as the Hôtel de Ville de Saïgon."* — no "hotel", the French name named correctly,
years intact.

### §2 Orphan quantity "to seat guests"
LOCAL-882's Opera House shipped: *"Designed by the French architect Félix Olivier
to seat guests"* — LOCAL-880C removed the number but left the purpose clause.

- `spoken_text_hygiene.strip_orphan_capacity_clause()` removes a **numberless**
  capacity clause: "to seat guests", "with a capacity to seat", "seating guests"
  (and a dangling "to seat ."). Run on `audit_seating_capacity`'s no-number path
  and again after the number pass. Idempotent.
- LOCAL-880C's deliberate kept verbal form ("seated 500 guests nightly" →
  "seated guests nightly") is preserved; "seat themselves" / "serves guests" are
  untouched.

Warm text now reads: *"Its venue auditorium was crafted not just for performance
but also for public gathering"* — no orphan "to seat guests".

### §3 "home to both the Lower House and the Senate" — must be sourced
`landmark_claim_gate.political_institution_claims()`: a sentence that ties the
venue to a named legislature ("home to … the Lower House … the Senate", "seat of
the National Assembly") needs an evidence sentence; else it is dropped.
`production_claims` now skips a political-institution phrase so a **sourced**
bicameral claim is not mis-dropped as a "production".

Decision logged: in the warm run the claim IS sourced by the Opera House's own
Wikipedia evidence, so it is KEPT. Source sentence:

> "After the National Assembly became a bicameral legislature, the Opera House
> became home to the Lower House (Hạ Nghị Viện) and the Senate or Upper House
> (Thượng Nghị Viện) of the National Assembly of what was South Vietnam."

Warm text: *"When the government shifted to a bicameral legislature, this same
building housed both the Lower House (Hạ Nghị Viện) and the Senate (Thượng Nghị
Viện)."* (In LOCAL-882 this was flagged unsourced only because the older evidence
snapshot lacked it; with the warm cache serving the full article it is sourced,
and the gate keeps it — exactly the control case the tests cover.)

## Tests
`tests/test_local882b_narration_defects.py` (18): all three fixes + controls —
a real hotel keeps "hotel"; "seat themselves" / "serves guests" untouched; a
sourced bicameral claim is kept; the sourced year/architect survive the hotel
drop. 145 related tests pass (872 / 872b / 872c / 879 / 880 / 880c / 881 / 882 /
882b). The 4 failures in `test_local88_tour_pollution.py` are PRE-EXISTING (they
fail on the clean base too; they need a live DB) — not a regression from this
work.

## Live — cloud-parity warm proof (budget enforced)
`run_cloud_parity_proof.py` (LOCAL-882's harness), `TASK_BUDGET_ID=LOCAL-882B
TASK_BUDGET_USD=0.30`, own DB (:55982, `docker-compose.local882-proof.yml`,
`-p local882`); the shared `audioura-*` containers were never touched. The cache
was SEEDED by running the previous subscribed commit (a31ead22) against the same
own DB (landmark_wiki_cache = 76 rows); the WARM run reuses it and measures this
branch's committed code.

**WARM PASS — all criteria, $0.2399 of $0.30:**
- 10/10 stops; every stop ≥ 5 content sentences; no banned wave-40 strings.
- City Hall is the Hôtel de Ville (1908/1909, Gardè) — **no "hotel"**, no Gia Long.
- Opera House — **no orphan "to seat guests"**; the bicameral claim is sourced.
- Palace: 30 April 1975 tank; Ngô Đình Diệm named in full.
- Post Office: Vildieu / Foulhoux (Eiffel only as the earlier building).
- Opera House not credited to Ferret alone.
- Stop 1 Directions is a real next-stop direction.

Warm text: `submission_artifacts/local882b/saigon_warm_final.txt`.

Run logs and meter logs (`_local882b_meterlogs/`) are machine-local and not
committed.
