# SUBMISSION_LOCAL-405.md

## LOCAL-405: The coherence gate matches verbs, not nouns

**Branch:** `kiro/local405-relation-forms` off `storied`  
**Parent:** LOCAL-403 merged (on `storied`); LOCAL-404 NOT merged  
**Status:** Implementation complete; live run pending

---

## The Defect

LOCAL-402's temporal coherence gate rejected `"collaborated with Freud"` (verb)
but passed `"collaboration with Freud"` (noun). Same impossible claim, different
grammatical surface form.

The gate's `_INTERACTION_PATTERNS` list contained only verb forms:
```python
# BEFORE (verb-only)
_INTERACTION_PATTERNS = [
    r'collaborated\s+with',
    r'worked\s+with',
    ...
]
```

Two separate bugs:
1. **Pattern gap:** Only verb forms matched; noun/participle forms escaped.
2. **Context year gap:** `apply_temporal_coherence_gate` never extracted the POI's
   `year` field as contextual `event_year`. A sentence like "Dalí's collaboration
   with Freud" contains no year — so even if the regex matched, the temporal check
   couldn't fire (Dalí and Freud DO overlap in real life: 1904–1939). The year 1974
   comes from the *work*, not the sentence.

---

## The Fix

### 1. Expanded `_INTERACTION_PATTERNS` (temporal_coherence_gate.py)

Now covers verb, noun, and participle forms for every interaction word:

| Family | Forms covered |
|--------|---------------|
| collaborate | collaborated/collaborating/collaboration(s) + with/between |
| partner | partnered/partnering/partnership(s) + with/between |
| meet | met/met with/meeting(s) + with/between |
| work | worked/working + with/alongside |
| correspond | corresponded/corresponding/correspondence(s) + with/between |
| dialogue | dialogue(s)/in dialogue + with/between |
| joint | joint + project/work/effort/venture/exhibition/creation |
| alongside | standalone adverb |
| together | together with |
| co-author | co-authored/co-authoring/co-author(s) + with/by |
| co-create | co-created/co-creating/co-creation(s) + with/by |
| commission | commissioned/commissioning/commission(s) + by/from |

### 2. POI year as contextual event_year

`apply_temporal_coherence_gate` now extracts the POI's `year` field and passes it
as `event_year` to `check_temporal_coherence`. This means a 1974 livre d'artiste
stop will catch "collaboration with Freud" even though the sentence itself carries
no year (because 1974 > 1939 = Freud's death).

---

## Form → Caught Table (24 forms, all caught)

| Form | Caught? | Reason |
|------|---------|--------|
| collaborated with (verb) | ✅ yes | Freud d.1939, event 1974 |
| collaboration with (noun) | ✅ yes | Freud d.1939, event 1974 |
| collaboration between (noun+between) | ✅ yes | Freud d.1939, event 1974 |
| collaborating with (participle) | ✅ yes | Freud d.1939, event 1974 |
| partnered with (verb) | ✅ yes | Freud d.1939, event 1974 |
| partnership with (noun) | ✅ yes | Freud d.1939, event 1974 |
| met (verb) | ✅ yes | Freud d.1939, event 1974 |
| met with (verb+prep) | ✅ yes | Freud d.1939, event 1974 |
| meeting with (noun) | ✅ yes | Freud d.1939, event 1974 |
| worked with (verb) | ✅ yes | Freud d.1939, event 1974 |
| working with (participle) | ✅ yes | Freud d.1939, event 1974 |
| worked alongside (verb+alongside) | ✅ yes | Freud d.1939, event 1974 |
| working alongside (participle+alongside) | ✅ yes | Freud d.1939, event 1974 |
| corresponded with (verb) | ✅ yes | Freud d.1939, event 1974 |
| correspondence with (noun) | ✅ yes | Freud d.1939, event 1974 |
| in dialogue with (prepositional) | ✅ yes | Freud d.1939, event 1974 |
| dialogue with (noun) | ✅ yes | Freud d.1939, event 1974 |
| joint project with (adj+noun) | ✅ yes | Freud d.1939, event 1974 |
| alongside (adverb) | ✅ yes | Freud d.1939, event 1974 |
| together with (prepositional) | ✅ yes | Freud d.1939, event 1974 |
| co-authored with (verb) | ✅ yes | Freud d.1939, event 1974 |
| co-created with (verb) | ✅ yes | Freud d.1939, event 1974 |
| co-creation with (noun) | ✅ yes | Freud d.1939, event 1974 |
| commissioned by (verb) | ✅ yes | Freud d.1939, event 1974 |

---

## Tests

**File:** `test_local405_relation_forms.py`

| Class | Tests | Purpose |
|-------|-------|---------|
| TestRegexCoverage | 1 | All 24 forms match the compiled regex |
| TestAllFormsParametrised | 2 | All forms caught by `check_temporal_coherence` AND `apply_temporal_coherence_gate` with poi year |
| TestValidInteractionsPreserved | 4 | Valid interactions (Dalí-Miró 1925, Dalí-Broder 1960, Chagall-Mourlot) NOT rejected; non-interaction verbs pass |
| TestRealGenerationPath | 1 | Full `apply_temporal_coherence_gate` pipeline (D307) |
| TestRevertBreaksLogic | 3 | Revert detection: removing the noun patterns breaks these (D296) |
| **Total** | **11** | |

**Red-on-revert count:** 3 (TestRevertBreaksLogic — tests that the expanded regex
matches `collaboration with`, `partnership with`, `meeting with`).

**Existing tests:** `test_local402_temporal_coherence.py` — 11/11 pass (no regression).

---

## Files Changed

| File | Change |
|------|--------|
| `temporal_coherence_gate.py` | Expanded `_INTERACTION_PATTERNS` to cover verb/noun/participle; `apply_temporal_coherence_gate` extracts POI year as contextual event_year |
| `test_local405_relation_forms.py` | New: parametrised test over all interaction forms |
| `run_local405_acceptance.py` | New: acceptance runner |
| `SUBMISSION_LOCAL-405.md` | This file |

---

## What This Does NOT Address (out of scope for 405)

The ticket also mentions:
- **Appositive rejector regression** (Mourlot lost, "a gift challenges" fragment)
  — this is LOCAL-404's problem; we branch off `storied` which doesn't have 404's code.
- **Query improvement** (snippets containing only encyclopaedia first-lines)
  — separate concern; this fix ensures the gate catches impossible claims regardless
  of whether the LLM generates verb or noun forms.
- **"never make the tour smaller"** principle — the coherence gate correctly removes
  impossible claims (better to remove than to publish falsehoods). The ticket's
  concern about *appositive* removal without replacement is a 404 issue.

---

## Live Run

Pending. Run with:
```bash
python3 run_local405_acceptance.py
```

Requires: `SERP_API_KEY`, `SERP_PROVIDER`, running PostgreSQL on :5433,
`DISABLE_TOUR_CACHE=1`, `STORIED_MODE=true`.
