# Storied Release — Rollback Plan

Three-tier rollback procedure for the Audioura Storied release. Each tier is self-contained and executable without developer assistance.

---

## Tier 1: Flag Rollback (< 2 minutes)

Disables Storied behavior instantly by toggling the feature flag. Beta behavior is restored immediately — no code changes or rebuilds required.

### Commands

```bash
docker exec development-tour-generator-1 env STORIED_MODE=false
docker restart development-tour-generator-1
```

### What it does

- Sets `STORIED_MODE=false` in the container environment
- Restarts the tour-generator container to pick up the new value
- All tour generation reverts to Beta behavior (no spine, no story types, no persona injection)

### Verification

After restart, generate a test tour and confirm:
- No `[Storied]` log lines appear
- Output matches Beta format (no Introduction block, no Artist's View labels)

---

## Tier 2: Service Rollback (~5 minutes)

Restores the Beta-era service files from `main` branch. Use when Tier 1 is insufficient (e.g., a code defect in shared paths that runs regardless of the flag).

### Commands

```bash
docker-compose stop tour-generator
git checkout main -- generate_tour_text.py generate_tour_text_service.py
docker-compose up -d tour-generator
```

### What it does

- Stops the tour-generator container
- Checks out the `main` branch versions of the two core service files
- Restarts the container with known-good Beta code

### Verification

After restart, generate a test tour and confirm:
- Service responds on `/health`
- Tour output matches Beta baseline (same structure as `chagall_current_tour.txt`)

---

## Tier 3: Full Branch Rollback

Complete revert to the `beta-2.1.1+18` tagged release on both stores. Use when Tier 2 is insufficient or if multiple files beyond the two service files are affected.

### Commands

```bash
git checkout main
docker-compose down
docker-compose build --no-cache
docker-compose up -d
```

### What it does

- Switches the entire working tree back to `main` (which matches the `beta-2.1.1+18` tag)
- Tears down all containers
- Rebuilds all container images from scratch using main-branch code
- Brings the full stack back up with verified Beta behavior

### Verification

After full redeploy:
- All services respond on their `/health` endpoints
- Generate a test tour — output must exactly match Beta format
- Confirm no Storied-specific modules are loaded (no `spine_generator`, `story_type_assigner`, etc.)

---

## Decision Matrix

| Symptom | Tier |
|---------|------|
| Tours generate but Storied content is wrong/broken | Tier 1 |
| Service errors or crashes under Storied code paths | Tier 2 |
| Multiple services affected or data corruption | Tier 3 |
| Unsure | Start at Tier 1, escalate if unresolved after 2 min |
