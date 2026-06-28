# Audioura Branch Model

## Branches

| Branch | Purpose | Ships to |
|--------|---------|----------|
| `main` | **Beta line** — the exact code in Google Play + Apple TestFlight | Play / TestFlight |
| `storied` | **Next release** (v2.2.0+) — Storied features developed here | Not yet shipping |
| `services-migration` | Historical — original services work (preserved, not deleted) | — |
| `Newsletters` | Historical — newsletter feature (preserved, not deleted) | — |

## Rules

### Bug fixes to Beta (main)
1. Fix on `main` directly (or a short-lived branch off main).
2. Bump version (e.g. 2.1.1+19), test, tag: `git tag -a beta-2.1.1+19 <sha> -m "..."`
3. Push tag + main.
4. **Merge forward into storied** so it stays current:
   ```bash
   git checkout storied
   git merge main
   git push origin storied
   ```

### Storied development
1. Work on `storied` (version 2.2.0+).
2. Storied does NOT ship to stores until it's declared its own release.
3. Periodically merge `main` into `storied` to pick up Beta fixes.

### Standing rules (all agents)
- Never force-push `main` or move the Beta tag.
- Never delete `services-migration` or `Newsletters` (history/audit trail).
- Do not create `_backup`, `_fixed`, `.bak` files — use git for history.
- Write throwaway/debug files to `scratch/` (gitignored).

## Tags

- `beta-2.1.1+18` — Frozen Beta (Google Play closed test + Apple TestFlight, commit `700d579`)
- Future tags follow: `beta-<version>` for store submissions
