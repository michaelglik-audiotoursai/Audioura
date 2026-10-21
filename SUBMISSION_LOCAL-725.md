# SUBMISSION — LOCAL-725: Final legal texts (pay-per-download, D688)

**Agent:** Mac Mini Kiro · **Branch:** `LOCAL-725-legal-finals` (from `subscribed` 46301f3d) · **Date:** 2026-10-21

Six legal documents produced as **final text** = the joined ClickUp drafts + every correction in their comments, with the option (A) "free re-download / non-consumable / Restore Purchases" sentences replaced by **option (B)** per **D688** (Michael, 2026-10-21): *every download of a paid tour is paid; deleting = buying again; a lost/replaced phone restores the Listen page — paid tours included — with the recovery code at no charge; a failed or interrupted download may be retried at no charge.* The current `legal/*.md` on `subscribed` (which already follow D660 per LOCAL-693) were the reference for the per-download wording.

Each file carries `**Version:** 2026-10-21-final`. `legal/build_html.py` was run and the six generated pages are committed under `legal/html/`. **Not deployed** — publishing is LEAD's, after Michael says "publish".

Sources (ClickUp comments, read-only): Terms draft 5 `wdvrdayztb`, Refunds draft 5 `wdvrdayztc`, Guide Terms draft 5 `wdvrdayztd`, Privacy draft 5 `wdvrdayzte`, Organiser draft 2 + 16 lawyer answers `wdvrdayzt2`, Content Policy approved `wdvrdayzt1`.

> Note on D688/D660/D661: the `DECISIONS.md` in this worktree ends at D611, so D688/D660/D661 are not readable here. I did not edit DECISIONS.md. The D688 rule was taken from the task brief, and the per-download reference wording from the pre-existing `legal/*.md` on this base (which implement D660/LOCAL-693) and from migrations 031/032.

---

## TERMS.md — changes against Terms of Service draft 5 (`wdvrdayztb`)

- §2(a): replaced draft 5's "non-consumable licence … download, delete, and re-download at no extra charge … using Restore Purchases" with option (B): one download per purchase; deleting or moving to a new phone is a new purchase; yours to keep once downloaded.
- §2(b): kept draft 5's per-language wording (the correction comment confirmed D653 is live; no open decision).
- §2(d): kept "a download that fails or is interrupted does not use up your purchase — retry at no extra charge" (D688 keeps this).
- §2(e): recovery code reframed as **the** restore path for a lost/replaced phone (not "a backup to Restore Purchases"); removed the Restore-Purchases-is-primary sentence.
- §4, §8: kept the refund-revocation wording from draft 5.
- §5 (item 10): added "we may remove content and suspend or end the access of anyone who breaks these rules" and the user **block** sentence (block a member or organiser).
- §8 (item 10): added "a report you make about a tour is also visible to Audioura".
- §9 (item 10): added "we may remove content and ban violators".
- §6 (item 1): kept "Tours that Audioura generates are Audioura's own content, and Audioura is their publisher."
- §10 (item 2): expanded the single accuracy line into the **three layers** the lawyer required — Terms ("informational only, not navigational/legal/safety advice"), a first-run in-app notice, and assumption-of-risk for physical-activity tours (with the gross-negligence carve-out).
- §15–16 (item 3): kept the DMCA Agent line and the §16 notice-and-takedown / counter-notice / repeat-infringer clause, agent = "Audioura LLC, 44 Sharpe Rd, Newton Centre, MA 02459, info@audioura.com".
- §13 (item 12): kept the local-consumer-rights (EEA/UK/other non-waivable) sentence.
- **CHOSE** — §10 wording of the three-layer accuracy/assumption-of-risk text. The lawyer (item 2) described the three layers but gave no sentences; I wrote them. Needs his sign-off.
- **CHOSE** — §16 DMCA clause wording. Flagged in the draft-5 comment as "mine, needs review"; carried as written. Only becomes true once the agent is registered with the Copyright Office.

## REFUNDS.md — changes against Refunds draft 5 (`wdvrdayztc`)

- §3: restored the per-download framing ("each tour purchase pays for one download … downloading again later is a new purchase; a lost/replaced phone restores the Listen page with the recovery code, without paying again") and the draft-5 "not yet used to download → unlock removed" bullet.
- §4(c): **removed** draft 5's "Restore Purchases … same Apple ID / Google Play account". Recovery-code restore of the Listen page is now the only restore path for tours.
- §4(d) (draft 5) folded into §4(c): recovery code is the restore mechanism, not a backup to Restore Purchases.
- §4(a): kept "failed or interrupted download … retry at no extra charge".
- §3(a) kept "at your device's next online check"; §3(c) kept "a refund does not delete files already on your device".
- §6: kept per-language wording (the correction comment reverted the draft-4 all-languages error).
- **CHOSE** — none beyond the (A)→(B) flip; all other wording is draft 5's.

## GUIDE_TERMS.md — changes against Guide Terms draft 5 (`wdvrdayztd`)

- §1(c): the draft's ⛔-marked option-(A) sentence ("non-consumable licence … download, delete and re-download at no extra charge … via Restore Purchases") was **deleted** and rewritten as option (B): one download per purchase; delete / new phone = buy again; recovery-code Listen-page restore at no charge; failed download retried at no charge. (The task said "delete §1(c)"; I kept the (c) label and replaced its content with the per-download rule so the clause set stays complete.)
- §1(a): kept the $2–$200 ladder, quick picks, snap-to-step, and "pre-ladder tours keep their price" (from the draft's migration-026 correction).
- §1(b): kept per-language ("a listener who buys English does not receive Spanish").
- §2: kept "Not listed", best-effort ratings, re-rate on edit.
- §4: kept the lawyer's indemnity and one-free-re-score.
- §5: kept the licence, including survival for already-downloaded copies and the Apple/Google sublicence.
- §6: kept payouts-not-built, W-9 / W-8BEN, "all sales revenue is Audioura's until Payout Terms".
- §8: kept MA governing law without the EEA/UK consumer sentence (Guide Terms are B2B, per the draft-5 note).
- **CHOSE** — §1(c) replacement wording (option B for guides). Written to mirror Terms §2 and the pre-existing per-download legal wording; needs confirming that the guide-facing phrasing is acceptable.

## PRIVACY.md — changes against Privacy draft 5 (`wdvrdayzte`)

- Purchase records: flipped the ⛔ (A) sentence to the (B) sentence given in the draft-5 comment — "…so that we can **unlock your download and record which purchases you have made**" (each tour purchase pays for one download).
- Recovery code: kept the live-policy wording and added "including paid tours" to the restore sentence, matching D688.
- Processor list: kept **DeepL removed / AWS Translate added**; kept Gemini "(where enabled)"; kept R2 + Google Cloud named under Sharing.
- Kept the **no-DPA-claim** position (no "DPAs in place" sentence).
- Retention: kept "**as long as tax and accounting law requires**" (not the unverified 7-year figure).
- Kept "Not listed" (not "Not Allowed").
- §"Your local rights" (item 12): **added** a local-consumer/data-rights sentence (EEA/UK/other non-waivable), which the draft did not have.
- **CHOSE** — the heading/section layout. Draft 5 arrived as running prose; I rendered it under the same headings as the existing `legal/PRIVACY.md` so the HTML builder produces a structured page. No wording was changed by this beyond adding the local-rights section.

## ORGANISER_TERMS.md — changes against Organiser draft 2 (`wdvrdayzt2`)

- §5: rewrote the single "Restore Purchases … same store account" paragraph into **three rules** per D688: (i) **passes** = fixed-duration, non-renewing, downloaded audio stays (own rule); (ii) **Audioura-generated tours** = per-download, delete/new-phone = buy again, recovery-code Listen-page restore at no charge, failed retry free; (iii) organiser-hosted audio already downloaded stays on device under the organiser's licence.
- §10(c): replaced "restore … via Restore Purchases … recovery code as a backup" with recovery-code Listen-page restore as the method; clarified that for tours each download is a separate purchase and the code restores what the member already owns (no extra downloads).
- §2: kept the lawyer's indemnity sentence and "no obligation to monitor, but may remove".
- §3: kept the waiver-law-compliance sentence and Private-only for waiver communities.
- §6: kept merchant-of-record (Apple/Google) vs seller-of-record (Audioura) split.
- §7: kept payouts-not-built, no escrow/wallet/balance, W-9 / W-8BEN.
- §8: kept "report routed to owner **and visible to Audioura**", off switch, "members keep audio already downloaded".
- §11 (item 12): kept MA law + Middlesex venue + the EEA/UK local-rights sentence; kept DMCA Agent line.
- **CHOSE** — §5 three-way split wording (passes vs tours vs hosted audio). The draft 2 §5 predates D688 and treated all paid content identically via Restore Purchases; I split it so tours follow per-download while passes and hosted audio keep their own rules. Needs sign-off.
- **CHOSE** — §10(c) rewrite wording (recovery-code restore, no Restore Purchases). Same reason.

## CONTENT_POLICY.md — changes against approved Content Policy draft 2 (`wdvrdayzt1`)

- Item 9: changed the Mature line from "tours focused on crime" to "tours focused on the **history of crime**", in both the "In short" block and the Mature section; and added to the Not-listed section the explicit distinction "a tour explaining how to commit a crime, as distinct from the history of one".
- Item 12: **added** a "Your local rights" section (EEA/UK/other non-waivable consumer rights).
- Kept "Not listed" throughout; kept the "In short" + "The detail" structure; kept the self-declared, off-by-default 18+ gate; kept "rated after generation, may list as General briefly"; kept translation-inherits-rating.
- The separate App Store Connect review note from the draft is **not** part of the published page (it was explicitly "not part of the document"); it is left in ClickUp.
- **CHOSE** — none beyond the two required items; wording of the crime distinction follows the lawyer's own phrasing in item 9.

---

## Consistency check

Every statement about purchases, re-download, recovery code, passes, refunds, ratings and payouts says the same thing across the six documents, and matches the code.

| Topic | Says | TERMS | REFUNDS | GUIDE | ORGANISER | PRIVACY | CONTENT | Code match |
|---|---|---|---|---|---|---|---|---|
| Purchase = one download | each paid download is a purchase; delete/new phone = buy again | §2(a) | §3 | §1(c) | §5 | Purchase records | — | migrations 031 `consumed_at` + partial index `uq_tour_unlocks_active`, 032 consume-on-last-byte |
| Re-download of a deleted tour | a new purchase (no free re-download) | §2(a) | §3 | §1(c) | §5 | Purchase records | — | 031 `record_unlock()` writes a new active row once spent |
| Failed/interrupted download | retried at no charge, does not consume | §2(d) | §4(a) | §1(c) | §5 | — | — | 032 restores the purchase once within 24h |
| Recovery code (lost/replaced phone) | restores the Listen page incl. paid tours, no charge; hashed copy only stored | §2(e) | §4(c) | §1(c) | §5, §10(c) | Recovery code | — | `recovery_code_service.py` stores salted PBKDF2 hash only |
| Restore Purchases for tours | not offered (removed) | absent | absent | absent | absent | absent | — | `_restorePurchases()` is a stub; no store entitlement path for tours |
| Languages | each language a separate product/purchase | §2(b) | §6 | §1(b) | — | Purchase records | translation inherits rating | `tour_pricing_service.py:249` D653 per-language unlock |
| Passes | fixed-duration, no auto-renew, downloaded audio stays | §3 | §5 | — | §5 | Tour unlocks… | — | `029_communities.sql` non-renewing pass, server computes expiry |
| Pass / tour price ladder | passes from $1; tours $2–$200 (picker), legacy .99 kept not offered | — | — | §1(a) tours $2–$200 | §6 pass list price | — | — | `026_price_ladder.sql` tiers 8–41 ($2–$200), 1–7 `.99` `in_picker=FALSE`; `029` passes from $1 |
| Refunds | requested from/decided by Apple/Google; access may be revoked at next online check | §4 | §1–§3 | — | §10 | Ratings/reviews | — | Google voided poller live; Apple REFUND path noted outstanding (not in user text) |
| Merchant of record | Apple/Google merchant; Audioura seller of record | §4 | §1 | §1(a) | §6 | Purchase records | — | all sales via IAP |
| Content ratings | General / Mature (18+) / Not listed; 18+ self-declared, off by default | §7 | — | §2 | §2 (via Content Policy) | Automated evaluation | In short + detail | `tour_content_rating.py` values general/mature/not_allowed → shown as General/Mature(18+)/Not listed |
| Publisher | Audioura publishes its own tours; organiser publishes community audio | §6 | — | — | §1, §2 | Communities | Community audio | metadata-only storage for community audio |
| Payouts | not built; W-9/W-8BEN before first payout; no escrow/wallet/balance | — | — | §6 | §7 | — | — | no payout code exists |

### Code-fact notes
- **"Not listed" vs code.** The classifier stores the internal value `not_allowed` (`tour_content_rating.py:43`), surfaced to users as **"Not listed"** in all six documents. The internal constant is not user-facing; there is no "Not Allowed" string in the texts.
- **Consumption is live.** 031 opens with Michael's D660 words and overrules buy-once/free-re-download; 032 stamps `consumed_at` on the last byte of the zip and restores a failed download once within 24h. The (B) texts match the running server; the old approved (A) drafts did not.
- **Per-language.** `tour_pricing_service.py:249-250` (D653): buying Russian unlocks Russian only. A translation inherits its source's price, not its unlock.

### Grep audit (all six `.md`)
| Term | Hits | Verdict |
|---|---|---|
| `Restore Purchases` | 0 | Gone — correct under (B); no store-entitlement restore promised for tours. |
| `non-consumable` / `consumable` | 0 | Gone — the (A) product-type framing is removed. |
| `DeepL` | 0 | Gone — replaced by AWS Translate (not used in code). |
| `Not Allowed` | 0 | Gone — all usages are "Not listed". |
| `no charge` / `no extra charge` / `without paying again` | 11 | All justified: each is either the **failed-download retry** (D688 keeps it) or the **recovery-code Listen-page restore** (D688's sanctioned restore for a lost/replaced phone). None promises a free re-download of a deleted tour. |

---

## Build
`python3 legal/build_html.py` wrote `legal/html/{terms,privacy,refunds,guide-terms,organiser-terms,content-policy}.html`. Verified: correct `<title>`, `2026-10-21-final` present, bold/headings/tables render, no raw Markdown leaked, no draft markers (⛔/🔸) in text or HTML. Website **not** deployed.

## Outstanding (for the lawyer / Michael, not blocking this text)
These remain open from the draft comments and are unchanged by this pass: register the DMCA agent with the Copyright Office (makes §15–16 true); sign DPAs (lets the Privacy DPA sentence return); confirm the Gemini production key (decides whether it stays listed); confirm the retention figure; the four Terms wording confirmations (merchant phrasing, §16 DMCA, §13 form, §6 publisher sentence). Code-side: the (B) texts are now true of the server for consumption; the Apple out-of-band REFUND path and the real block-member/organiser function remain filed as separate tasks.
