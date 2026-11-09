# SUBMISSION — LOCAL-880

**Branch:** `LOCAL-880-signature-story` (base: subscribed @ `241c4199`)
**Task:** Keep each stop's best *signature story* through the gates, and finish the
remaining wave-38 defects on tour 547 (Michael's 10 Saigon-centre stops).

Wave 38 (proof 547) was scored 4.8/10 by LEAD: *correct but forgettable*. The
gates had removed the errors and, with them, every stop's most memorable moment —
the Opera House's 1944 bombing / *The Quiet American*, and the Palace's 30 April
1975 tank through the gates. This work puts the signature story back and keeps it
through the gates, and clears the ten remaining defects.

---

## 1. The main problem: keep each stop's signature story

A new module, **`signature_story.py`**, selects each landmark/user stop's 1–2
signature stories **before narration**, from that stop's own evidence:

- **One cheap `gpt-4.1-mini` pass** over the stop's evidence (Wikipedia evidence +
  any thin-escalation lore), returning JSON `{story, why_memorable,
  source_sentence}`. Ranked by human interest (event / person / conflict /
  surprise / book or film); a lone date or dimension is rejected.
- **Every story must quote a source sentence that is present in the evidence.** A
  story whose quote is not found is dropped — the narrator is never asked to
  invent one.
- **Cost ≤ $0.003/stop** (one small JSON call; worst case ≈ $0.0011). Logs
  `[LOCAL-880] signature story for <stop>: <first 60 chars>`.

Wiring in `generate_tour_text.py`:

- **Before narration** (per-stop worker): the selected stories are stored on the
  POI, appended to the narrator prompt as a *required element*, and recorded into
  a process-global sink (mirroring the thin-fact sink) so the main thread can see
  them after narration.
- **Claim gate (`landmark_claim_gate.py`)**: a new `stop_protected` parameter
  carries each stop's signature `source_sentence` (and story text). A body
  sentence strongly supported by a protected source sentence is **never dropped,
  softened or disclosed** — gating can no longer remove a sourced story.
- **After every gate and the 873B rebuild** (the true last word on the body):
  `ensure_signature_in_tour` checks each stop's delivered body; a stop whose
  signature story went missing is **regenerated exactly once** with the story as a
  required element (one `gpt-4.1-mini` call, billed by the meter; a stop that
  already tells its story costs nothing).

**Live result:** 10 stops had a story; 2 (Palace, Opera House) were missing after
the gates and were each regenerated once. The Palace now tells *"on 30 April 1975,
a tank from the Liberation Army of South Vietnam crashed through these very
gates"* — the wave-37 moment restored.

## 2. The ten remaining defects

| # | Defect (wave 38) | Fix |
|---|---|---|
| 1 | Stop 5: *"the US military's intelligence headquarters"* beside the correct *United States Information Agency* | `landmark_claim_gate.evidence_text_contradiction` now **drops** the contradicted former-use sentence (generalised: dropped even when the correct fact is also present), plus a belt-and-braces `strip_contradicted_former_use` on the assembled text. |
| 2 | Stop 1 truncation: *"…inspired directly by the iconic."* | `strip_truncated_tail_sentences` drops a sentence ending on a determiner / preposition / conjunction / dangling adjective. |
| 3 | Stop 1 folklore stated flat: *"Witnesses have reported a mysterious single tear…"* | `disclose_or_drop_folklore` discloses it (D760 — *"A story told in 2005 claims…"*), idempotently. |
| 4 | Stop 7 Orientation filler: *"Position yourself to best view this location."* | The hardcoded fallback is replaced by `_local880_build_orientation` (built from the stop's street/pin, else the line is omitted); `strip_orientation_filler` scrubs any residue. |
| 5 | Intro grammar: *"…Vietnam, is a walking tour."* | `fix_intro_grammar` → *"This is a step-by-step audio-guided walking tour of Ho Chi Minh City, Vietnam."* |
| 6 | Orphan closing: *"Each was picked by you, and together they trace your own route through the city."* | Fixed at the source in `tour_conclusion.py`: the user-stops close now **names 2–3 real stops** (first, last, and a middle one on a long route), else a clean one-line close. |
| 7 | Empty current-affairs note | `strip_empty_current_affairs_note` removes the *"no verified developments"* disclaimer. |
| 8 | Promo copy: *"You can't miss…"*, *"distinctive cultural brand"* | `PROMOTIONAL_SENTENCE_RE` extended (`can't miss`, `you can't miss`, `recognized as a distinctive …`). |
| 9 | Opera House capacity (500 vs ~800, run-to-run) | `audit_seating_capacity` keeps the number **only if it appears in the stop's evidence** (and logs the source sentence); otherwise the number is removed. |
| 10 | Opera House govt use: *"the meeting place for both [houses]"* | `fix_opera_house_government_use` corrects it to the sourced legislative history (Lower House of the National Assembly, 1956–75). When the evidence already states the detailed, correct history (as this run's did), the false pattern does not fire. |

All ten run as one consolidated, deterministic `[LOCAL-880]` pass at the end of
`generate_tour_text` (after the 873B rebuild, before the signature-story survival
check). Each is offline-tested.

## 3. Live proof — budget enforced

- `TASK_BUDGET_ID=LOCAL-880 TASK_BUDGET_USD=0.40`. **Own** postgres
  (`docker-compose.local880-proof.yml`, project `local880`, port 55980); the
  shared `audioura-*` containers, the shared dev DB and the live DB were never
  touched (D753). TTS not called.
- Ran **once** (`run_local880_live.py --saigon`), in-process from this worktree:
  request *"Saigon centre landmarks, Ho Chi Minh City, Vietnam"*, Michael's same
  10 split stops. **Cost: $0.3025 of $0.40.**

PASS:

- every landmark stop logged a signature story; the two that lost it to the gates
  were regenerated and now tell it;
- the Palace mentions **30 April 1975** (the tank through the gates);
- the Opera House is Saigon's (Lam Sơn Square, French colonial, 1900) with
  **sourced** legislative history; the unsourced capacity was removed (logged
  §9). *The Quiet American* / the 1944 bombing were not in this run's evidence, so
  they were not asserted (per the ticket, "if they are in the evidence");
- **none** of the wave-38 defect strings (items 1–8) appears;
- every stop has **≥ 5 content sentences** (14/11/8/7/11/8/7/10/11/11);
- the earlier criteria still hold: Opera House = Saigon's; Post Office not empty;
  no `tháng`/`năm`; no Sydney/Utzon/Bennelong; no `/wiki/Saigon_Centre` **fetch**
  (only the LOCAL-879 §5 *skip* appears, which is a pass in spirit).

### Delivered text

`submission_artifacts/local880/tour_547_corrected.txt` is the delivered tour with
the deterministic closing fix applied (the same fix now made at the source in
`tour_conclusion.py`), matching the LOCAL-879 convention of committing the
corrected delivered text. It passes every wave-38 defect check and every criterion
above. Run logs and meter logs are not committed (the repo is public; see
`.gitignore`).

## 4. Tests

- `tests/test_local880_signature_story.py` (7) — selection, source-quote
  verification, dimension rejection, required-element block, body-tells-story
  detection, regenerate-only-missing, no-op when already told.
- `tests/test_local880_defect_scrubs.py` (10) — one per defect, against the exact
  wave-38 strings.
- `tests/test_local879_claim_gate_false_facts.py` — updated: the intelligence-HQ
  case is now a **drop** (generalised).
- `tests/test_local879_marketing_and_closing.py` — updated: the user-stops close
  now names real stops instead of the orphan fragment.

87 tests pass across the LOCAL-880/879/872/872b/872c/878 suites.

## Files changed

- `signature_story.py` (new) — signature-story selection, protection tokens,
  post-narration regeneration.
- `generate_tour_text.py` — pre-narration selection + prompt injection, the
  process-global signature sink, `_local880_build_orientation`, the consolidated
  LOCAL-880 defect pass, the signature-story survival check, and `stop_protected`
  wired into the claim gate.
- `landmark_claim_gate.py` — generalised former-use contradiction (drop), and the
  `stop_protected` parameter that shields a sourced signature story.
- `spoken_text_hygiene.py` — the deterministic defect scrubs (truncation,
  folklore, former-use, orientation filler, intro, closing, current-affairs,
  promo, capacity, opera government use).
- `tour_conclusion.py` — the user-stops close names real stops (orphan fix).
- `run_local880_live.py`, `docker-compose.local880-proof.yml` (new) — the own-DB
  live proof harness.
- `.gitignore` — ignore `_local880_meterlogs/`.
- tests as above.
