# Storied — Merge-Forward Procedure

When a Beta bug is fixed on `main`, use this procedure to merge the fix into the `storied` branch.

---

## Prerequisites

- Bug fix is committed and tagged on `main` (e.g. `beta-2.1.1+19`)
- `storied` branch is clean (no uncommitted changes)
- All tests pass on `storied` before merging

---

## Procedure

### Step 1: Fetch latest from both branches

```bash
git fetch origin
git checkout storied
git pull origin storied
```

### Step 2: Merge main into storied

```bash
git merge origin/main --no-ff -m "merge: forward Beta fix from main into storied"
```

### Step 3: Resolve conflicts (if any)

If conflicts arise in `generate_tour_text.py` or other shared files:
- Keep BOTH the Beta fix AND the Storied additions
- The Storied code is guarded by `if _storied_mode:` blocks — these should not conflict with Beta-path fixes
- After resolving: `git add <resolved files>` then `git merge --continue`

### Step 4: Verify parity

```bash
STORIED_MODE=false python regression_beta_parity.py
```

This must exit 0 — confirming the Beta fix is active and Storied modifications are dormant when flag is off.

### Step 5: Run Storied validation

```bash
STORIED_MODE=true python validate_storied_tour.py
```

Confirm Storied features still work after the merge.

### Step 6: Push

```bash
git push origin storied
```

---

## Rules

1. **Never hand-apply** a fix to both branches. Fix on `main`, then merge forward.
2. **Never rebase** `storied` onto `main` — use merge to preserve history.
3. **Never force-push** — merge conflicts are resolved locally.
4. **Test both modes** after every merge (STORIED_MODE=false AND true).

---

## Conflict Hotspots

| File | Likely conflict pattern | Resolution |
|------|------------------------|------------|
| `generate_tour_text.py` | Beta fix in shared path + Storied blocks | Keep both; Storied guards (`if _storied_mode:`) won't interfere |
| `docker-compose-master.yml` | New env vars | Merge both sets of env vars |
| `Dockerfile.generator` | Package additions | Merge both COPY/RUN lines |

---

## Verification Checklist

- [ ] `regression_beta_parity.py` exits 0 (Beta parity preserved)
- [ ] `validate_storied_tour.py` exits 0 (Storied features work)
- [ ] `git log --graph --oneline -10` shows clean merge commit
- [ ] No `<<<<<<` conflict markers in any file
