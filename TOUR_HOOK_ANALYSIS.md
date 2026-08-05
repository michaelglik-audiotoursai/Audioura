# TOUR_HOOK_ANALYSIS — LOCAL-118

**Branch:** `kiro/local118-tour-hook-analysis`  
**Date:** 2026-08-02  
**Agent:** Mac Mini Kiro  
**Method:** Database query (host-side via `tests/db_connection.py`), static code reading, Flutter source inspection.

---

## 1. Does the spine actually produce a hook?

**Yes.** Every spine generation produces a `tour_hook` field. The `tour_cache` table contains 41 cached spines, all with non-empty `tour_hook` values. The hooks are 11–25 words (75–148 characters).

### Verbatim `tour_hook` values from real tours (7 quoted):

| # | Location | Type | tour_hook |
|---|----------|------|-----------|
| 1 | Musée National Marc Chagall, Nice | museum | "How did Marc Chagall's dedication to the Biblical Message shape the very foundation of the Musée National Marc Chagall?" |
| 2 | Musée International d'Art Naïf Anatole Jakovsky, Nice | museum | "How did a collection of naïve art from 27 different countries find its home in Nice?" |
| 3 | Palais Lascaris, Nice | art/instruments | "What secret connection between the instruments of Palais Lascaris tells the story of a forgotten musical era?" |
| 4 | Arnold Arboretum, Jamaica Plain, Boston MA | nature | "What hidden stories do the trees of Arnold Arboretum whisper about the past lives of Jamaica Plain?" |
| 5 | Musee Oceanographique de Monaco | museum | "Why did Prince Albert I dedicate his life to the ocean and establish the Oceanographic Museum in 1910?" |
| 6 | Nice France (walking) | walking | "What secrets lie beneath the sun-soaked elegance of Nice's vibrant streets?" |
| 7 | French Riviera biking tour | biking | "What secrets of timeless allure whisper through the sun-drenched streets of the French Riviera, hidden in plain sight?" |

### Quality assessment

The hooks are **formulaic but functional.** Nearly all follow the pattern "What [hidden/secret/forgotten] [noun] [lie/whisper/echo] beneath [location's] [adjective] [noun]?" They work as a seed for expansion but are not compelling standalone — they are questions, not statements, and they lean heavily on "secrets lie beneath" phrasing. The museum hooks are slightly better (they reference specific factual premises — Chagall's dedication, 27 countries, Prince Albert I).

The `tour_hook_generator.py` specification says the expanded output should "NOT end with a question mark" — but the raw hooks from the spine are almost all questions. This mismatch means the expansion step (whether via `tour_hook_generator.py` or the live prolog prompt) must convert the question into a statement.

---

## 2. What would consuming it involve? (Answer: it's already consumed)

**The hook IS already consumed.** This is the critical finding that changes the framing.

### The live pipeline (file: `generate_tour_text.py`, lines 6091–6199):

1. `_tour_hook = _storied_spine.get("tour_hook", "")` — extracted from spine (line 6091)
2. Fed into a GPT-3.5-turbo prompt as `Tour hook: {_tour_hook}` (line 6142)
3. The prompt generates an 80–190 word prolog paragraph in second-person present tense
4. Result stored in `_saved_prolog` (line 6189)
5. `_saved_prolog` is injected into Stop 1's text body (line 6324–6325)
6. Stop 1 text → TTS via `build_mp3.py` / Polly → MP3 audio the listener hears

**Verified in database:** Tour ID 29 (French Riviera Biking Tour) — Stop 1 contains the paragraph "You are about to embark on a journey through the sun-soaked streets of the French Riviera, a tapestry woven with threads of timeless allure and hidden tales..." This IS the expanded hook, already spoken in the audio.

### What `tour_hook_generator.py` does differently

The UNWIRED module (`tour_hook_generator.py`) is a **40–60 word** expansion using GPT-3.5 with a simpler prompt. The LIVE pipeline already does a **80–190 word** expansion with a richer prompt that includes:
- The connecting thread
- Chapter previews
- Venue-identity facts (LOCAL-11, LOCAL-42)
- Story-element grounding constraints (LOCAL-21)
- Thread promise injection (SQ-S6b)

The live implementation is strictly superior to the unwired module — it's longer, better-grounded, and aware of downstream story elements.

### Insertion point (if `tour_hook_generator.py` were wired)

The natural point would be `generate_tour_text.py:6189` (the fallback path when the prolog LLM call fails). Currently, on failure, the raw `_tour_hook` string is used as `_saved_prolog`. The module could replace that fallback. But the live primary path (the prolog prompt) already handles the job better.

---

## 3. What does the app expect?

**The app has no separate intro track slot.** The `TourPlayerScreen` (249 lines) loads `index.html` in an InAppWebView and auto-starts `audio1` (Stop 1). The audio file numbering is `stop_01.txt → stop_01.mp3`, starting at 1. There is no `stop_00`, no `intro.mp3`, no separate pre-stop-1 audio concept.

The prolog already plays because it's text within Stop 1 — no app change is needed for the current behavior. If someone wanted a **separate** intro track (played before Stop 1), the app would need:
1. A new audio element (`audio0` or `intro`)
2. Modified `startTour()` JavaScript to play it before advancing to Stop 1
3. A modified `break_text_to_pois_fixed.py` to emit the prolog as a separate file

None of this infrastructure exists. The app plays stops 1–N sequentially. The prolog-in-Stop-1 approach is the correct one for the current architecture.

---

## 4. Cost

### If `tour_hook_generator.py` were wired (hypothetical)

| Component | Cost |
|-----------|------|
| GPT-3.5-turbo expansion (~250 tokens) | $0.0005 |
| Polly TTS of ~325 chars result | $0.0013 |
| **Total per tour** | **$0.0018** |

Against the current tour cost of ~$0.068, this would be a 2.6% increase.

### Actual cost of the live prolog (already incurred)

| Component | Cost |
|-----------|------|
| GPT-3.5-turbo prolog generation (~400 tokens) | $0.0008 |
| Polly TTS of ~850 chars (part of Stop 1's full text) | $0.0034 |
| **Total** | **$0.0042** |

This cost is already being paid on every storied tour. The prolog characters are part of Stop 1's text that goes through Polly.

### Verdict on cost

The question is moot. The hook-to-audio path already runs at a cost slightly higher than what `tour_hook_generator.py` would add, and it produces better output. Wiring the dead module would be redundant spending.

---

## 5. Recommendation: Do NOT wire `tour_hook_generator.py`

**The problem described in the UNWIRED_AUDIT — "hook never becomes audio" — is incorrect.** The hook DOES become audio, through a different (and better) code path than the one the audit identified.

### What actually happens:

1. Spine generates `tour_hook` ✓
2. `generate_tour_text.py` reads it and feeds it to a prolog-generation prompt ✓
3. The generated prolog (80–190 words, grounded, thread-aware) becomes the opening of Stop 1 ✓
4. Stop 1 goes through TTS ✓
5. The listener hears it ✓

### Why `tour_hook_generator.py` is dead code, not a missing feature:

- It was written for an earlier pipeline version (Task [S37] per its docstring) that predates the current prolog system
- The current prolog generation (lines 6091–6199) does the same job with more context
- It has no importers because it was **superseded**, not forgotten
- The UNWIRED_AUDIT correctly identified zero importers but misdiagnosed the severity — the feature exists via a different implementation

### What to do with it:

`tour_hook_generator.py` should be reclassified from **UNWIRED** to **DEAD (superseded)** in the audit. It can be removed as dead code (candidate for LOCAL-117-style cleanup). No task should be created to wire it.

### Caveat — the raw-hook fallback:

When the prolog LLM call fails (network error, timeout), the code falls back to `_saved_prolog = _tour_hook` — the raw 11–25 word question. This fallback is weak (short, question-form, formulaic). `tour_hook_generator.py` would be slightly better than raw-hook-as-fallback, but the correct fix is to make the primary path more resilient (retry, or pre-generate the prolog), not to wire a weaker expansion module as a secondary fallback.

---

## Summary Table

| Question | Answer |
|----------|--------|
| Does the spine produce a hook? | Yes — all 41 cached spines have one |
| Is the hook text good? | Formulaic ("What secrets lie beneath...") but functional as a prompt seed |
| Does it become audio? | **Yes** — via the prolog generation in `generate_tour_text.py:6091–6199`, folded into Stop 1 |
| Does `tour_hook_generator.py` add value? | No — it's a weaker predecessor of the live prolog system |
| Does the app support a separate intro? | No — plays stops 1–N, prolog is inside Stop 1 |
| Cost of hypothetical wiring | $0.0018/tour (moot — the live prolog already costs $0.0042) |
| Recommendation | **Do not wire.** Reclassify as DEAD (superseded). Safe to delete. |

---

## Reclassification for UNWIRED_AUDIT

Finding #6 in the audit states:

> **`tour_hook_generator.py` — hook field unused:**  
> Spine JSON includes a `tour_hook` field. `tour_hook_generator.py` was written  
> to expand it into a spoken TTS introduction. Nothing calls it. The hook exists  
> in the data but never reaches the audio output.

**Correction:** The `tour_hook` field IS consumed — by `generate_tour_text.py:6091` — and reaches audio output as the opening paragraph of Stop 1. The module `tour_hook_generator.py` is not a missing wiring but a dead predecessor. The audit's deduplicated UNWIRED count should drop from 8 to 7.

---

## Database verification

```
Row count before: 88
Row count after:  88
```

No rows inserted, deleted, or modified.
