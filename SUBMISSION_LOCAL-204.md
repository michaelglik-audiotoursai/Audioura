##### READY FOR REVIEW

**Task:** LOCAL-204 — Build path for subscribed-track services  
**Branch:** `kiro/local204-subscribed-build-path`  
**Commit:** `ddb4d8a004dbebeadbfdd3490fc367f0a9b70030`

---

## Per-File Summary

| File | Change |
|------|--------|
| `docker-compose-subscribed.yml` | Rewrote to cover all 3 subscribed services (generator, orchestrator, news-orchestrator). Set project name `subscribed-204`, distinct container names (`-204` suffix), offset ports +200, separate database `audiotours_subscribed`. |

---

## Design Decisions

### 1. Build sources from the `subscribed` worktree (LOCAL-204)

This worktree is checked out to `kiro/local204-subscribed-build-path` which is based on `subscribed`. The Dockerfiles use `COPY *.py /app/` (generator) and explicit `COPY` per module (orchestrator, news-orchestrator), so building from this directory includes all subscribed-only modules.

No separate worktree mechanism needed — the existing worktree model already provides source isolation.

### 2. Compose project name: `subscribed-204`

Three compose projects now coexist without collision:
- `audioura` — storied stack (Michael's phone)
- `local-156` — legacy subscribed containers (running on 5100/5102)
- `subscribed-204` — this task's fresh build

A rebuild in `subscribed-204` can never orphan or replace containers from `audioura` or `local-156` because Docker Compose scopes all operations to the project name.

### 3. Ports

| Service | Host Port | Justification |
|---------|-----------|---------------|
| subscribed-generator-204 | 5200 | Storied uses 5000; local-156 uses 5100; +200 avoids both |
| subscribed-orchestrator-204 | 5202 | Storied uses 5002; local-156 uses 5102; +200 avoids both |
| subscribed-news-orchestrator-204 | 5212 | Storied uses 5012; no prior subscribed instance; +200 pattern |

All three verified free via `lsof -nP -iTCP -sTCP:LISTEN`.

### 4. Database: `audiotours_subscribed`

Separate database name ensures subscribed services never write to storied tables. The database does not yet exist (verified via `pg_database` query) — it will be created at first deploy (or by a migration script).

---

## Evidence

### Module presence — tour-generator image

```
=== TOUR-GENERATOR (subscribed-204-subscribed-generator) ===
-rw-r--r-- 1 root root  8947 Aug  4 10:36 /app/pricing.py
-rw-r--r-- 1 root root 25480 Aug  4 10:36 /app/wallet_ledger.py
```

### Module presence — tour-orchestrator image

```
=== TOUR-ORCHESTRATOR (subscribed-204-subscribed-orchestrator) ===
-rw-r--r-- 1 root root 11839 Aug  4 10:36 /app/cost_meter.py
-rw-r--r-- 1 root root  5101 Aug  4 10:36 /app/cost_rates.py
-rw-r--r-- 1 root root  8947 Aug  4 10:36 /app/pricing.py
-rw-r--r-- 1 root root 25480 Aug  4 10:36 /app/wallet_ledger.py
```

### Module presence — news-orchestrator image

```
=== NEWS-ORCHESTRATOR (subscribed-204-subscribed-news-orchestrator) ===
-rw-r--r-- 1 root root 11839 Aug  4 10:36 /app/cost_meter.py
-rw-r--r-- 1 root root  5101 Aug  4 10:36 /app/cost_rates.py
-rw-r--r-- 1 root root  8947 Aug  4 10:36 /app/pricing.py
-rw-r--r-- 1 root root 25480 Aug  4 10:36 /app/wallet_ledger.py
```

### Storied stack dry-run (all Running)

```
 Container news-generator-1 Running
 Container background-article-processor-1 Running
 Container development-postgres-2-1 Running
 Container audioura-treats-1 Running
 Container audioura-tour-orchestrator-1 Running
 Container audioura-polly-tts-1-1 Running
 Container audioura-tour-id-resolution-1 Running
 Container audioura-tour-generation-modernized-1-1 Running
 Container tour-editing-phase2-1 Running
 Container newsletter-link-extractor-1 Running
 Container news-processor-1 Running
 Container audioura-translation-service-1 Running
 Container simple-news-search-1 Running
 Container audioura-coordinates-fromai-1 Running
 Container news-orchestrator-1 Running
 Container audioura-tour-update-1 Running
 Container audioura-tour-generator-1 Running
 Container audioura-user-api-2-1 Running
```

### docker ps before/after build — IDENTICAL

```
$ diff /tmp/docker_ps_before.txt /tmp/docker_ps_after.txt
(no output — files identical)
```

Container IDs unchanged:
```
CONTAINER ID   NAMES                                     STATUS
c8139603567a   audioura-tour-orchestrator-1              Up 16 hours
674ac0e8ce3a   audioura-tour-generator-1                 Up 16 hours (healthy)
513d1f3e8219   tour-editing-phase2-1                     Up 16 hours (healthy)
b90c2652a0bf   audioura-translation-service-1            Up 17 hours
6ffd22dfbf9d   news-orchestrator-1                       Up 18 hours
ebac96996601   subscribed-orchestrator                   Up 18 hours (healthy)
f2505fb0a665   subscribed-generator                      Up 18 hours (healthy)
8e779e7399d2   audioura-tour-generation-modernized-1-1   Up 18 hours
91a678b57a05   audioura-coordinates-fromai-1             Up 18 hours (healthy)
244c089807d2   audioura-user-api-2-1                     Up 18 hours
fb3491c10c39   audioura-map-delivery-1                   Up 18 hours (unhealthy)
c0725ddf36f6   audioura-tour-id-resolution-1             Up 18 hours
f36e96834945   background-article-processor-1            Up 18 hours
98025f84bb44   audioura-treats-1                         Up 18 hours
b2662486124b   news-processor-1                          Up 18 hours
dea1bfa4da3e   audioura-tour-update-1                    Up 18 hours
999a74d07615   news-generator-1                          Up 18 hours
91a1d4b3e1fc   simple-news-search-1                      Up 18 hours
1a4271178938   development-postgres-2-1                  Up 18 hours
7b6bff2e4ddf   audioura-tour-processor-1                 Up 18 hours (unhealthy)
bc09b1f382bf   newsletter-link-extractor-1               Up 18 hours
4ed8f74f12f4   audioura-polly-tts-1-1                    Up 18 hours
cfc6797748f8   audioura-voice-control-1                  Up 18 hours (unhealthy)
```

### git status --short (clean)

```
(empty)
```

---

## Limitations

1. **Database not yet created.** `audiotours_subscribed` does not exist in postgres-2. A `CREATE DATABASE` or migration step is required before the subscribed stack can actually run. This was intentional — the task scope is build-path plumbing, not schema migration.

2. **Legacy subscribed containers still running.** The `local-156` containers (`subscribed-generator` on 5100, `subscribed-orchestrator` on 5102) remain. When LEAD deploys the 204 stack, the old ones should be torn down (`docker compose -p local-156 -f docker-compose-subscribed.yml down` from the LOCAL-156 worktree).

3. **STORIED_MODE=false.** The subscribed-generator sets `STORIED_MODE=false` since it serves the subscribed tier. The storied containers keep `STORIED_MODE=true`.

4. **Referenced docs not found.** DECISIONS.md D48/D53/D58/D76, CONTAINER_OWNERSHIP.md, and DORMANT_SERVICES.md do not exist in this worktree. The task was completed based on the available compose files, Dockerfiles, and running state.

5. **Cost: $0.00.** Build used only local Docker; no cloud resources consumed.
