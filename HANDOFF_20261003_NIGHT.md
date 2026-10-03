# HANDOFF — night of 2026-10-03 (Storied_Tours). READ FIRST after `restart`.

Michael's instruction (verbatim intent): keep working overnight on minimising the two large per-tour costs:
**(A) OpenAI — writing and checks; (B) Voices.** He will judge Kokoro vs Polly neural BY EAR before any switch.

## Real per-tour costs (corrected ledger + Cloud Billing, 2026-10-02)
4-stop tour ≈ $0.40: OpenAI $0.18–0.29 · Gemini ≈ $0.04 · Polly neural ≈ $0.15. Museum tour ≈ $1.05 (OpenAI $0.83–0.95,
D1 verification). Gemini optimisation is DROPPED (D595). New translation approved (D595), subscribed @ 02aa094.

## In flight (Kiro, released, capped)
- **LOCAL-564** closure binding (storied) — COMPLETED, NOT REVIEWED. Review first: tests from the exact Weehawken/BarLola
  snippets red→green; La Marée still closed; then merge to storied and forward-merge to subscribed.
- **LOCAL-566** writer cost profile + one content-neutral saving (prompt caching / dedup), OpenAI cap $6.
- **LOCAL-567** blind voice sample pack → ~/Desktop/Audioura_voice_samples/ (Kokoro vs Polly neural etc.), cap $3.

## Overnight loop (after Michael types `restart continuous dev`)
1. Review each finished task by effect (D-rules: never trust the report; tests red→green; recompute numbers).
2. (A) From 566's profile, dispatch the next content-neutral OpenAI saving (each ≤ $6 cap, record/replay where checks
   are touched — Michael's 100%-recall rule from LOCAL-560). Content-changing ideas = proposals only, blind review later.
3. (B) After 567: if Kokoro sounds plausible, prepare a **clean blind A/B for Michael**: 3 English stops × {Kokoro, Polly
   neural}, letters only, key at the bottom of KEY.md. NO switch without his ear verdict.
4. Never deploy to GCloud. Never DELETE from audio_tours. Keep RELEASED.txt to the tasks you dispatch.
5. Morning message to Michael: what changed in $ per tour (measured), and the listening test location.
