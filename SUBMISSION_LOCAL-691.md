# SUBMISSION — LOCAL-691: Legal pages for taking payments (DRAFTS for Michael)

**Agent:** Mac Mini Kiro
**Branch:** `LOCAL-691-legal-pages` (from `subscribed` = `ecfdb52f`)
**Base verified:** `git merge-base --is-ancestor ecfdb52f HEAD` → exit 0.

**Status: DRAFTS. Nothing is published.** The documents are for Michael (and a
lawyer if he chooses) to review before anything goes live outward-facing. The
app wiring is implemented and verified by `flutter analyze` + unit/widget tests;
the server endpoint + migration are proven green against the test DB. The app
UI itself was not run on a device (handing that to LEAD).

---

## Why
Audioura now takes money (tour purchases, packs, community passes), lets guides
sell tours, and hosts communities. audioura.com serves a privacy policy at
`/privacy` but has **no Terms** and nothing about payments, sellers, or
communities. This drafts those documents and wires the required acceptance
capture into the app.

> Note on sources: this worktree's `DECISIONS.md` ends at **D611** (the base is
> held unpushed behind the field-test gate per the BASE note), so the referenced
> D613 / D624 / D647–D658 are not present here as entries. I grounded every
> ruling in the committed submission docs that implemented them —
> `SUBMISSION_LOCAL-687` (content rating / review queue / 18+, D656),
> `SUBMISSION_LOCAL-688` (Audioura score, listeners take over from the 4th
> rating, D655), `SUBMISSION_LOCAL-690` + `690C` (communities: publisher of
> record, owner-hosted metadata-only audio, non-renewing passes, downloaded
> audio stays, report→owner + off switch, Listed needs location, waiver=Private,
> merchant of record, payouts not built — D657/D658) — plus the three delta
> files (`privacy_disclosure_delta.md`, `app_privacy_storied_delta.md`,
> `data_safety_storied_delta.md`). Company details: Audioura LLC, 44 Sharpe Rd,
> Newton Centre, MA 02459, info@audioura.com.

---

## What was written (plain English, short sections, `legal/`)

### Markdown drafts (`legal/*.md`) — version `2026-10-14-draft1`
| File | Covers |
|------|--------|
| `legal/TERMS.md` | Accounts; a purchase = one tour in one language, yours to keep + free re-download; passes fixed-length, no auto-renewal; Apple/Google process payment+refunds (we never see card numbers); acceptable use; user content (reviews, guide tours, community audio) + our display licence; content-rules summary; termination; disclaimers (tours may be inaccurate; follow local rules; physical-activity at your own risk); limitation of liability; Massachusetts law; changes; contact |
| `legal/PRIVACY.md` | The existing policy UPDATED with a **"What changed"** list: purchase records (no card numbers), tour_unlocks / community_memberships, public ratings & reviews, swipe/persona for Match %, editor score + content rating (automated evaluation of tour text; names OpenAI + Wikipedia), 18+ age confirmation, community data, retention, deletion. Keeps what is still true |
| `legal/REFUNDS.md` | Refunds requested from Apple/Google; a refunded tour → unlock removed at next online check + verified rating removed; a refunded pass → membership ends, downloaded audio stays |
| `legal/GUIDE_TERMS.md` | Price ladder; Audioura evaluation + content rating; review queue; the guide's responsibility for their edits; **payouts "to be announced before the first payout" (not built — said honestly)** |
| `legal/ORGANISER_TERMS.md` | Publisher of record; owns & hosts their audio; Audioura stores only titles/links & does NOT review owner audio; member waivers between organiser & members; members keep downloaded audio; report + off switch; Listed vs Private; Apple/Google payments with Audioura as merchant of record; payouts TBA |
| `legal/CONTENT_POLICY.md` | General / Mature (18+) / Not allowed with examples (D656), incl. **"a restaurant serving drinks is General"** and translations inherit the original's rating |
| `legal/LEAD_NOTES.md` | Open legal questions for Michael/a lawyer (Section 230 for AI content, waivers, sales tax as merchant of record, payouts-before-terms, 18+ gate adequacy, DMCA agent, consumer-law vs MA venue, COPPA, …), one line each |

### HTML versions (`legal/html/*.html`)
`legal/build_html.py` renders each public document (not LEAD_NOTES) into a
**self-contained, mobile-first HTML page** — inline CSS, no external CSS/JS,
`<meta robots=noindex>`, a visible "DRAFT — not published" banner, and the
audioura.com placeholder palette from `WEBSITE_BRIEF_audioura_com.md` (deep
indigo + warm amber, large rounded sans-serif), the same self-contained-HTML
approach as the public `how-we-score` page (LOCAL-688). The converter is
dependency-free (no Markdown package). All six pages validated with
`html.parser`. Regenerate with `python3 legal/build_html.py`.

---

## App wiring (acceptance capture)

### DB — `migration/sql/030_document_acceptance.sql` (additive, idempotent)
`document_acceptance (id, user_id, document, version, accepted_at)` with
`UNIQUE (user_id, document, version)` and an index on `(user_id, document)`.
`CREATE … IF NOT EXISTS`, wrapped in `BEGIN/COMMIT`; applying twice is a no-op.
No DROP/DELETE/retype.

### Server — `user-tracking/document_acceptance_api.py` (self-contained blueprint)
Registered in `user-tracking/app.py` (same pattern as entitlements /
communities). Endpoints:
- **`POST /document-acceptance`** `{user_id, document, version}` — records the
  acceptance; **idempotent** (`ON CONFLICT (user_id, document, version) DO
  NOTHING`), returns `{status:"recorded", already:bool}`. 400 on missing fields
  or an unknown document slug.
- **`GET /document-acceptance?user_id=…[&document=…]`** — lists a user's
  acceptances, newest first.
- Auth mirrors the other blueprints (`X-API-Key`, with the
  `ALLOW_UNAUTHENTICATED_ENTITLEMENTS` escape for local/tests). Document slugs:
  `terms, privacy, refunds, guide_terms, organiser_terms, content_policy` (plus
  friendly aliases, e.g. `guide → guide_terms`).

### App (Flutter, `audio_tour_app`)
- `lib/services/document_acceptance_service.dart` — pure helpers
  (`kLegalDocsVersion = '2026-10-14-draft1'`, `LegalDoc` slugs,
  `legalDocPath/Url/Title`) + a networked `DocumentAcceptanceService`
  (`record` / `list` / `hasAccepted`) over `Service.userDb`.
- **About tab** (`about_screen.dart`): a **Legal** card with **Terms**,
  **Privacy**, **Content policy** links that open the audioura.com URLs
  (`/terms`, `/privacy`, `/content-policy`). They 404 until Michael publishes —
  expected; shown anyway.
- **Buy & Download sheet** (`tour_buy_sheet.dart`) and **community pass sheet**
  (`community_page_screen.dart`): a shared **`TermsAgreeLine`** — "By buying you
  agree to the **Terms**" (tappable link) — and a `terms` acceptance recorded on
  a successful purchase.
- **Guide price control** (`my_tours_screen.dart`): when a guide chooses a paid
  price, a **required "I accept the Guide Terms" checkbox** gates Save (seeded
  from `hasAccepted` so a returning guide is not re-prompted); accepting records
  `guide_terms`.
- **Create Community** (`communities_about_screen.dart`): a **required "I accept
  the Organiser Terms" checkbox** gates Create; accepting records
  `organiser_terms`.

Nothing else in the app changed.

---

## Tests

### Server — `tests/test_local691_document_acceptance.py` → **9 pass**
```
ALLOW_UNAUTHENTICATED_ENTITLEMENTS=true \
  python3 -m pytest tests/test_local691_document_acceptance.py -q
# 9 passed
```
Against `audiotours_test` (localhost:5433); migration 030 applied idempotently
in a module fixture. Covers: table shape matches migration 030; record a new
acceptance (`already:false`); re-accept is idempotent (`already:true`, still one
row); a new version adds a second row (history kept); GET newest-first + filter
by document; missing-fields → 400; unknown document → 400; alias normalisation
(`guide → guide_terms`, `organizer_terms → organiser_terms`); GET requires
`user_id`. Safety: every row uses a `TEST-691-` user id; cleanup deletes ONLY
those rows; no other table touched.

### Dart — `audio_tour_app/test/document_acceptance_test.dart` → **9 pass**
```
cd audio_tour_app && flutter test test/document_acceptance_test.dart --no-pub
# All tests passed!
```
Covers: canonical slugs match the server's set; `legalDocPath`/`legalDocUrl` map
each document to its audioura.com route; titles; `kLegalDocsVersion`;
`AcceptanceRecord.fromJson` is defensive (missing fields never throw); the
`TermsAgreeLine` widget renders "By buying you agree to the Terms" with a
tappable **Terms** link.

### No regressions
`communities_service_test` + `paid_tour_download_test` + `pay_before_download_test`
still green alongside the new test (35 total). `flutter analyze` on every touched
Dart file: **0 errors** (only pre-existing lints in the large existing screens).

---

## Honest status
- **Proven:** 9 server tests + 9 Dart tests pass; migration 030 applies
  idempotently against the test DB; HTML validates; `flutter analyze` clean
  (0 errors) on all touched files; no test regressions.
- **Not exercised live:** no device run of the app UI (About links tapped, the
  Buy/pass agree line, the Guide/Organiser checkboxes); the acceptance POST was
  proven through the in-process Flask test client against `audiotours_test`, not
  against a running user-api container. Handing the on-device check to LEAD.
- **Drafts only:** nothing published; the legal text awaits Michael's (and a
  lawyer's) review — see `legal/LEAD_NOTES.md`.

## PROCESS compliance
- Branched from HEAD (`subscribed = ecfdb52f`); ancestor check exits 0.
- No live check used a shared container; the server tests ran in-process against
  `audiotours_test` on my own `postgres` host port 5433. No `-p audioura`, no
  `audioura-*` container renamed. **Nothing published anywhere.**
- Did **not** edit DECISIONS.md, CLAUDE.md, BACKLOG.md, WORK_QUEUE.md, or
  `.continuous_dev/*`.
- For LEAD: apply migration **030** to the live DB; deploy the updated
  `user-tracking/app.py` + `document_acceptance_api.py`; publish the `legal/html`
  pages at `/terms`, `/privacy`, `/refunds`, `/content-policy`, `/guide-terms`,
  `/organiser-terms` once approved; on-device check of the links + acceptance
  checkboxes.

## Commits (per step, on `LOCAL-691-legal-pages` from `ecfdb52f`)
1. `dafd22d0` — Markdown legal drafts (7 docs)
2. `94a6bffd` — styled self-contained HTML versions + generator
3. `883219e9` — migration 030 + server blueprint + 9 server tests
4. `d11059dd` — app wiring (About links, Terms line + acceptance, required Guide/Organiser checkboxes)
5. `fcb4e7ab` — Dart tests (helpers + TermsAgreeLine), 9 pass
