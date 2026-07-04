# Storied v2.2.0 — Aug 1 Pre-Submission Launch Checklist

Every item must be PASS before submitting to Google Play (closed test) + Apple TestFlight.

---

## Automated Gates (Claude/Kiro verify)

- [ ] `python integration_test_storied_full.py` exits 0 — **Owner: Claude** — Blocking: yes
- [ ] `python regression_all_tour_types.py` exits 0 — **Owner: Claude** — Blocking: yes
- [ ] `python content_qa_runner.py storied_chagall.txt` scores ≥ 8/11 + factual checks PASS — **Owner: Claude** — Blocking: yes
- [ ] `python content_qa_runner.py` on walking tour scores ≥ 8/11 + factual checks PASS — **Owner: Claude** — Blocking: yes
- [ ] `python content_qa_runner.py` on restaurant tour scores ≥ 8/11 + factual checks PASS — **Owner: Claude** — Blocking: yes
- [ ] `python content_qa_runner.py` on book/movie tour scores ≥ 8/11 + factual checks PASS — **Owner: Claude** — Blocking: yes
- [ ] `python regression_beta_parity.py` exits 0 — **Owner: Claude** — Blocking: yes
- [ ] `python storied_smoke_test.py` exits 0 — **Owner: Claude** — Blocking: yes
- [ ] `python run_storied_db_migration.py` exits 0 (all 5 tables validated) — **Owner: Claude** — Blocking: yes

## Manual Gates (Michael verifies)

- [ ] Privacy policy updated with persona + referral + attestation disclosures — **Owner: Michael** — Blocking: yes
- [ ] Google Play Data Safety form updated per `data_safety_storied_delta.md` — **Owner: Michael** — Blocking: yes
- [ ] Apple App Privacy labels updated per `app_privacy_storied_delta.md` — **Owner: Michael** — Blocking: yes
- [ ] Demo account created for store reviewers — **Owner: Michael** — Blocking: yes
- [ ] Background audio playback justification written (Apple requirement) — **Owner: Michael** — Blocking: yes (iOS only)
- [ ] Android keystore backed up in 3 places — **Owner: Michael** — Blocking: yes (Android only)

## Configuration Gates

- [ ] `docker exec development-tour-generator-1 printenv STORIED_MODE` returns `true` — **Owner: Claude** — Blocking: yes
- [ ] `docker exec development-tour-generator-1 printenv ATTESTATION_MODE` returns `log_only` — **Owner: Claude** — Blocking: yes
- [ ] `docker exec development-tour-generator-1 printenv DATABASE_URL` is set — **Owner: Claude** — Blocking: yes

## Final Steps

- [ ] `storied-v2.2.0-services` git tag pushed — **Owner: Claude** — Blocking: yes
- [ ] `storied_handoff_for_mobile.md` delivered to Mobile Q — **Owner: Claude** — Blocking: no
- [ ] `storied_handoff_for_ios.md` delivered to iOS Q — **Owner: Claude** — Blocking: no

---

## Status Key

| Symbol | Meaning |
|--------|---------|
| `[ ]` | Not started |
| `[P]` | PENDING (Michael-owned, awaiting action) |
| `[✓]` | PASS |
| `[✗]` | FAIL (blocks submission) |
