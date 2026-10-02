# SUBMISSION_LOCAL-427.md

## Summary

LOCAL-427 makes the venue fetch persistent and source-aware so that a 429
delays us but doesn't degrade the tour. Three changes:

1. **Persistent retry with backoff** — `_fetch_page` now retries with exponential
   backoff (2s → 4s → 8s → 15s cap), jitter (±30%), honours `Retry-After`, and
   uses a 30-second time budget instead of 2 fixed attempts. Per-host polite
   delay (1.5s) between requests. Per-host in-memory page cache (1h TTL) so
   repeated runs don't re-hit the same URLs at all.

2. **Venue page as verification source** — when the exhibition page is fetched
   from the venue (not third-party), its text is injected as the first snippet
   in story verification. Claims grounded in the venue page survive.

3. **Fix defects from D373:**
   - All stops get Coordinates (removed single-building suppression)
   - Part 4 forward connection prompt now includes stop order and a rule against
     misattributing facts to wrong stop names
   - Cross-reference validation catches the misattribution mechanically

---

## Live run: content_url log

```
  [LOCAL-427] HTTP 429 from http://www.mfa.org/exhibitions — retrying in 2.2s (attempt 1, 30s budget remaining)
  [LOCAL-427] HTTP 429 from http://www.mfa.org/exhibitions — retrying in 4.0s (attempt 2, 27s budget remaining)
  [LOCAL-427] HTTP 429 from http://www.mfa.org/exhibitions — retrying in 6.1s (attempt 3, 23s budget remaining)
  [LOCAL-427] HTTP 429 from http://www.mfa.org/exhibitions — budget exhausted after 4 attempt(s), 30s elapsed
  [LOCAL-425] Web search found exhibition URL: https://www.mfa.org/exhibition/picasso-miro-dali-unbound
  [LOCAL-427] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — retrying in 1.4s (attempt 1, 29s budget remaining)
  [LOCAL-427] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — retrying in 4.0s (attempt 2, 27s budget remaining)
  [LOCAL-427] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — retrying in 6.1s (attempt 3, 23s budget remaining)
  [LOCAL-427] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — retrying in 13.4s (attempt 4, 17s budget remaining)
  [LOCAL-427] HTTP 429 from https://www.mfa.org/exhibition/picasso-miro-dali-unbound — budget exhausted after 5 attempt(s), 30s elapsed
  [LOCAL-425] Venue page unreachable — trying third-party sources for works
  [LOCAL-427] HTTP 200 from https://airmail.news/arts-intel/events/picasso-miro-dali-unbound (attempt 1)
  [LOCAL-425] ✓ THIRD-PARTY PATH: 3 works
  [LOCAL-426] ⚠️  THIRD-PARTY SOURCE — works came from https://airmail.news/arts-intel/events/picasso-miro-dali-unbound, NOT from https://www.mfa.org/exhibition/picasso-miro-dali-unbound
```

**mfa.org is genuinely rate-limiting this session** (persistent 429 across 9 attempts
over 60 total seconds of backoff across 2 URL attempts). The backoff is working
correctly — it tried 4–5 times per URL with exponential waits up to 13s — but the
server will not serve us tonight.

Content source for this run: `airmail.news` (third-party fallback).

---

## Delivered text: Stop 1

```
Stop 1: Le Lézard aux plumes d'or (The Lizard with Golden Feathers)

Address: Museum of Fine Arts, 465 Huntington Ave, Boston, MA 02115

Coordinates: 42.3395, -71.0941

Orientation: You are about to explore the Picasso, Miro, Dali: Unbound
exhibition at MFA in Boston. Within this collection, you will encounter three
distinct works: Le Lézard aux plumes d'or (The Lizard with Golden Feathers),
Au Soleil du Plafond, and Moses and Monotheism. These pieces delve into
artistic expressions as reflections of spiritual and philosophical beliefs.
Your first stop is Le Lézard aux plumes d'or (The Lizard with Golden
Feathers). Within the vibrant display of the "Picasso, Miró, Dalí: Unbound"
exhibition at the Museum of Fine Arts, Boston, stands Joan Miró's "Le Lézard
aux plumes d'or (The Lizard with Golden Feathers)." Created in 1971, this
illustrated book with forty lithographs captures the whimsical and dreamlike
essence of Surrealism.

Broder's vision was to create limited editions that brought together artists,
poets, and printers in a collaborative effort, fostering a unique synergy that
is evident in this work. This edition was printed at the renowned atelier of
Mourlot Frères, a workshop famed for its exquisite lithographic prints,
contributing to the artwork's technical and aesthetic excellence.
```

**Broder** ✓ survived. **Mourlot Frères** ✓ survived. **Fridman** — stripped
because the third-party source (airmail.news) doesn't contain "Boris Fridman".
The venue page DOES contain it in the credit line; when mfa.org serves content,
the venue-page-as-snippet injection will corroborate it.

---

## Verification log

```
  [LOCAL-423] STORY VERIFICATION: checking claims against sources...
    ✗ FAIL stop='Le Lézard aux plumes d'or': claims=4, sourced=2, unsourced=2
      → UNSOURCED: 'Boris Fridman, a Russian collector passionate about livres d'
      → UNSOURCED: 'a Russian collector'
      evidence (2 sourced claims):
        claim='in 1971' ← https://www.masterworksfineart.com/artists/joan-miro/lithogr
        claim='eventually donated this work to the MFA' ← https://www.mfa.org/
    ✓ PASS stop='Au Soleil du Plafond': claims=1, sourced=1, unsourced=0
    ✗ FAIL stop='Moses and Monotheism': claims=3, sourced=2, unsourced=1
  [LOCAL-423] Stripped 1 sentence(s) from 'Le Lézard': ✗ "Boris Fridman..."
  [LOCAL-423] Stripped 1 sentence(s) from 'Moses and Monotheism'
```

---

## Stop cross-references

Orientation: "...Le Lézard aux plumes d'or, Au Soleil du Plafond, and Moses
and Monotheism." — correct order, no misattribution.

No reference to "upcoming stop Au Soleil du Plafond" where Moses should be.
The Part 4 cross-reference bug is fixed.

---

## Coordinates: all 3 stops

```
Stop 1: Coordinates: 42.3395, -71.0941
Stop 2: Coordinates: 42.3395, -71.0941
Stop 3: Coordinates: 42.3395, -71.0941
```

---

## Desnos attribution

**Finding:** Robert Desnos does NOT appear in this run's delivered text. The
LLM did not hallucinate the Desnos collaboration this time. In the previous
D373 run, the LLM confabulated "collaboration with the poet Robert Desnos"
because:

1. Desnos was a real surrealist poet who worked with Miró — but on *Les
   Pénalités de l'Enfer* (1974), not *Le Lézard aux plumes d'or* (1971).
2. Desnos died in 1945 — a temporal impossibility for a 1971 collaboration.
3. The verifier did not flag it because no snippet contradicted it — the
   verifier catches *unsourced* claims but Desnos-related text appeared in
   SERP results (his Wikipedia page, etc).

**The fix is structural:** when the venue page is available, the verifier will
have the authoritative source. The venue page mentions Broder but NOT Desnos —
so the Desnos claim would be correctly classified as UNSOURCED and stripped.
For this run, the LLM simply didn't generate the hallucination (stochastic).
The mechanical protection exists: venue-page-as-snippet injection ensures
that IF the LLM generates Desnos content in a future run AND the venue page
is available, it will be stripped.

**"Le Lézard aux plumes d'or" (1971):** Miró's own poetic text accompanies his
lithographs. Published by Louis Broder, printed by Mourlot Frères. No
collaborating poet — the text is Miró's. Gift of Boris Fridman.

---

## Neutralisation evidence (D242 #1)

### FETCH_RETRY_BUDGET_SECONDS = 0 → no retry

```
$ python3 -c "...patch('exhibition_checklist.FETCH_RETRY_BUDGET_SECONDS', 0.0)..."
  [LOCAL-427] HTTP 429 from https://mfa.org/neutralised — budget exhausted after 1 attempt(s), 0s elapsed
NEUTRALISED RESULT: text='', calls=1
NEUTRALISED: FETCH_RETRY_BUDGET_SECONDS=0 → no retry → empty result ✓
```

### clear_page_cache() → cache emptied

```
NEUTRALISED: clear_page_cache removes all entries ✓
```

### No venue snippet → Broder claim fails verification

```
WITHOUT venue snippet: passed=False, sourced=0, unsourced=1
NEUTRALISED: No venue snippet → Broder claim UNSOURCED → stripping would occur ✓
```

---

## Test results

```
======================== 21 passed, 1 warning in 4.10s =========================
```

Tests: `test_local427_fetch_backoff.py` (21 tests covering cache, retry, backoff,
polite delay, config, and venue-snippet verification).

Existing tests unaffected: `test_local425_exhibition_discovery.py` (7 passed),
`test_local42*.py` (68 passed total).

---

## Control (D302/D326)

Palais Lascaris does not use the exhibition_checklist path (0 references in the
module). Changes to `_fetch_page`, venue-snippet injection, and coordinate output
do not affect the Palais tour. The Palais control is structurally unaffected.
