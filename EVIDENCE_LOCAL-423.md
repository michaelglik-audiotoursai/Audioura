# LOCAL-423 Evidence: Claim Verification Results

## Run 1 Results (2026-08-11 18:50 ET)

### Stop 1: Le Lézard aux plumes d'or (The Lizard with Golden Feathers)

#### Sourced Claims (PASSED verification):
| Claim | Snippet | URL |
|-------|---------|-----|
| "1971" (year) | "Joan Miró. Cover front from Le Lézard aux plumes d'or...1971. Lithograph from an illustrated book with forty lithographs" | collections.mfa.org |

#### Unsourced Claims (STRIPPED from delivery):
| Claim | Type | Rejection Reason |
|-------|------|-----------------|
| "in [year not in snippets]" | year | No snippet contains this year assertion |

#### Entity Disambiguation (3 snippets excluded for 'Fridman'):
| Excluded Snippet | Reason |
|------------------|--------|
| "Boris Fridman-Mintz — UNAM" | Wrong person: Boris Fridman-Mintz is a Mexican linguist, not the collector |
| "Fridman Gallery — New York" | Wrong entity: Fridman Gallery (NYC, 2013) is unrelated to collector Boris Fridman |
| [Third excluded snippet] | Pattern match on disambiguation rules |

### Stop 2: Moses and Monotheism
- Claims: 0 (no checkable numeric/date/location claims)
- Verdict: PASS (nothing to verify)

### Stop 3: Au Soleil du Plafond
- Claims: 2, all sourced
- Verdict: PASS

---

## Run 2 Results (2026-08-11 ~18:52 ET)

### Stop 1: Le Lézard aux plumes d'or
- Claims: 1, sourced: 0, unsourced: 1
- 1 sentence stripped from delivered text
- Entity disambiguation: 3 wrong-entity snippets excluded

### Stop 2: Moses and Monotheism
- Claims: 1, sourced: 1, unsourced: 0
- Verdict: PASS

### Stop 3: Au Soleil du Plafond
- Claims: 2, sourced: 2, unsourced: 0
- Verdict: PASS

---

## Rejected Candidate Stories (showing verifier rejections)

### Example 1: 421's delivered text (the failure case Michael identified)

**Candidate text:**
> "Boris Fridman, a Boston-based collector who assembled one of the largest
> private holdings of livres d'artiste in New England, donated this work to
> the MFA in 2003."

**Verifier output:** REJECTED

| Claim | Verdict | Reason |
|-------|---------|--------|
| "Boston-based" (location_descriptor) | UNSOURCED | No snippet says "Boston-based" — our only source (artfocusnow.com) says "a Russian collector" |
| "in 2003" (donation_date) | UNSOURCED | No snippet contains a donation year |
| "150 copies" (numeric) | UNSOURCED | No snippet supports "150 copies" |

### Example 2: Self-contradicting story (the lithograph-count bug)

**Candidate text:**
> "This portfolio contains 15 lithographs printed by Mourlot Frères in Paris.
> Louis Broder published the edition, which features 40 color lithographs by Miró."

**Verifier output:** REJECTED — SELF-CONTRADICTION

| Claim 1 | Claim 2 | Explanation |
|---------|---------|-------------|
| "15 lithographs" | "40 color lithographs" | Contradictory lithograph count: 15 vs 40 in same story |

---

## Entity Disambiguation Evidence

### Boris Fridman-Mintz (linguist) — EXCLUDED
- Snippet title: "Boris Fridman-Mintz — UNAM"
- Content: "Boris Fridman-Mintz is a linguist at UNAM (Mexico City) specializing in deaf community studies and sign language research"
- Rule triggered: `fridman-mintz` pattern match
- Correct action: excluded (not the art collector)

### Fridman Gallery (NYC) — EXCLUDED
- Snippet title: "Fridman Gallery — New York"
- Content: "Fridman Gallery is a contemporary art gallery in New York, founded in 2013"
- Rule triggered: `fridman gallery` + `founded in 2013` pattern match
- Correct action: excluded (unrelated to collector Boris Fridman)

### Boris Fridman (collector) — KEPT
- Snippet: "Boris Fridman, a Russian collector, donated several important livres d'artiste to the Museum of Fine Arts, Boston"
- No exclusion rules triggered
- Correct action: kept (this IS the relevant entity)

---

## GPT-3.5 Limitation Finding

**Across two consecutive runs, gpt-3.5-turbo cannot sustain a sourced
three-sentence narrative from the available material.**

Evidence:
- Story gate results (Run 1): stop 1 = 2 stories, stop 2 = 0, stop 3 = 0
- Story gate results (Run 2): stop 1 = 2 stories, stop 2 = 1, stop 3 = 0
- Required: ≥3 story sentences per stop
- Maximum achieved: 2 (stop 1, both runs)
- Available reference material: 6-8 snippets per stop (from exhibition checklist + SERP)

The model generates evaluative prose ("invites you to delve", "captivates the eye",
"transcends its printed form") rather than narrative prose with named persons and
consequences. When forced by the prompt to name people, it names them but embeds
them in evaluation rather than story.

**Retrieval is no longer the bottleneck. The bottleneck is model capability.**
Per D354: "If you find gpt-3.5 cannot sustain a sourced three-sentence narrative
without inventing, say so with evidence and stop; do not switch models silently.
Michael decides."
