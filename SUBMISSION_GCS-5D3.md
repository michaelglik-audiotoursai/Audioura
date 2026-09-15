# SUBMISSION — GCS-5D3

**Agent:** Services Kiro
**Base:** storied @ `0de517c` (verified ancestor of HEAD; branch `kiro/gcs-5d3`)
**ClickUp:** `wdvrdaycwj` (urgent)
**Authorised by:** Michael, 2026-09-15 ~14:22 — "Yes, deploy to Preview" (Preview only).
**Re-dispatch of:** GCS-5D2 (answer to its A/B question: **(A)**).

## Command run (exactly as authorised)

```bash
bash deploy_gcs5_tour_editing.sh --apply --editing-tag v1
```

No other flags. No `--stable`, no `--gw-tag`. Gateway tag auto-resolved to **v36**
(highest existing `api-gateway` tag was `v35`). No file edits to the deploy path.
Exit status: **0** (`PIPESTATUS_EXIT=0`).

## Base verification (before any git command)

```
$ git rev-parse HEAD
0de517c8cdd5d0c080b2f5dc4ab073667f7848f9
$ git merge-base --is-ancestor 0de517c HEAD ; echo $?
0
```

Branch `kiro/gcs-5d3` sits on `0de517c` (local storied), NOT on `origin/*`.

## Pre-flight read-only state (matches LEAD's check)

```
api-gateway         (Stable)  : api-gateway-00022-t88          @ api-gateway:v35
api-gateway-storied (Preview) : api-gateway-storied-00002-6kb  @ api-gateway:v35
highest api-gateway tag       : v35   (=> v36 free)
tour-editing image tags       : (none)
tour-editing service          : (not found)
```

## Read-only proofs during --apply (all PASS)

- **SHA gate** — staged gateway `main.py` byte-identical to the running v35 image
  (CRLF/BOM-normalised):
  `ef7cf1adc15eef5626d6c53cd8a5ca17109f7cde9d8fd9b871f8d781175fab18` (staged == image).
- **Route diff** — v35 routes.yaml (25 route-methods, 6 backends) → new (29 route-methods,
  7 backends). Added backend: `tour-editing`. Added routes (exactly 4, none removed):
  - `+ GET   /tour/<tour_id>/download`
  - `+ GET   /tour/<tour_id>/job-status/<job_id>`
  - `+ POST  /tour/<tour_id>/update-multiple-stops`
  - `+ POST  /tour/<tour_id>/update-stop`
- **Editing-route test** (against staged v35 main.py + this branch's routes): PASSED —
  all 4 routes registered, fail-closed without `X-API-Key` (no-key=401, wrong-key=401,
  good-key!=401).
- v35 pull digest: `sha256:a47117c141f34caa426c28830cf087b913d4c272a74a0dcf6a1d72ae0b3e3481`.

## Image tags actually pushed (with digests)

| Image | Tag | Digest |
|---|---|---|
| `.../services/tour-editing` | `v1`  | `sha256:b9258c8993d38c7e0b9cd3816054313ab5f05f33a22183201d4b45a0f301eaa6` |
| `.../services/api-gateway`  | `v36` | `sha256:e35fd3c596966d26670d992c85b1c32f7643f4e4af929bf858ef6e392b27fd07` |

(Registry repo prefix: `us-central1-docker.pkg.dev/audiotours-migration/services`.)
`tour-editing:v1` local build manifest-list digest matched the pushed digest
(`b9258c…01eaa6`). `api-gateway:v36` pushed digest confirmed (`e35fd3…27fd07`).

## tour-editing service

- **URL (authoritative, from `gcloud run services describe`):**
  `https://tour-editing-ixkp5nkrlq-uc.a.run.app`
  (deploy step also printed the alias `https://tour-editing-60899077572.us-central1.run.app`;
  both resolve to the same service. `TOUR_EDITING_URL` was wired from the describe value.)
- **Ready revision:** `tour-editing-00001-924`
- Config: command `python tour_editing_phase2.py`, port 5022, `--no-allow-unauthenticated`,
  Cloud SQL + R2 + AWS/Polly env & secrets (as staged by the script).
- **IAM:** `serviceAccount:60899077572-compute@developer.gserviceaccount.com` granted
  `roles/run.invoker` on `tour-editing` (the Preview gateway's SA).

## Gateways — before and after

| Service | Before revision / image | After revision / image |
|---|---|---|
| `api-gateway` (Stable) | `api-gateway-00022-t88` @ `api-gateway:v35` | `api-gateway-00022-t88` @ `api-gateway:v35` **(untouched)** |
| `api-gateway-storied` (Preview) | `api-gateway-storied-00002-6kb` @ `api-gateway:v35` | `api-gateway-storied-00003-5zp` @ `api-gateway:v36` |

Stable was never touched (no `--stable`), confirmed by identical before/after.

## No-key curl results (against `https://storied-api.audioura.com`)

All 4 editing routes fail-closed with **401** (never 404 — routes are baked into v36):

```
no-key update-multiple-stops -> 401 (expect 401)
no-key update-stop          -> 401 (expect 401)
no-key job-status           -> 401 (expect 401)
no-key download             -> 401 (expect 401)
```

Per rule 5, save/download **with** a key was NOT run — LEAD verifies.

## Rules compliance

1. Ran the one authorised command; stopped-at-first-failure logic never triggered (no failure).
2. Never touched `api-gateway` (Stable) or any service other than `api-gateway-storied`
   (+ the new `tour-editing` it depends on).
3. Before/after revision+image recorded for both gateways (above).
4. No SQL, no DB writes.
5. Only no-key curls run post-success (all 401).
6. No edits to `DECISIONS.md`, `CLAUDE.md`, `BACKLOG.md`, `.continuous_dev/STATUS.md`,
   `GCLOUD_STORIED_START_HERE.md`, `BUILD_NUMBERS.md`.
7. No blocking question arose.

## Full `--apply` output

The complete captured build/deploy log is committed alongside this file as
`_apply_output.log` on this branch (it is very large — full docker layer unpack,
push, both Cloud Run deploys, all three read-only proofs, and the printed
verification block). Key milestones from it are quoted above.

**Status: APPLIED to Preview. Success.**
