# Container Ownership Audit — 2026-08-03

## ⚠️ Active Label Conflict

`tour-editing-phase2-1` carries compose label `service=tour-generator` (inherited from
its base image `audioura-tour-generator:latest`). This makes **two** running containers
present as `audioura:tour-generator` to compose tooling. No port duplication exists today
(tour-generator is on 5000, tour-editing-phase2 is on 5022), but compose does not
recognise `tour-editing-phase2-1` as its own service — the next `docker compose -f
docker-compose-master.yml up -d` would create a **second** `tour-editing-phase2-1` and
fail on port 5022.

---

## Orphaned Containers

| Container | Project | Service | Working Dir | Dry-Run Result | Port at Risk | Re-adoption Command |
|-----------|---------|---------|-------------|----------------|--------------|---------------------|
| `tour-editing-phase2-1` | audioura | tour-editing-phase2 | (none — not compose-created) | **Creating** | 5022 | `cd ~/Audioura && docker compose -f docker-compose-master.yml up -d --force-recreate tour-editing-phase2` |
| `subscribed-orchestrator` | local-156 | subscribed-orchestrator | /Users/micha/audioura-worktrees/LOCAL-156 | **Creating** (from ~/Audioura) | 5102 | `cd ~/Audioura && docker compose -f docker-compose-subscribed.yml up -d --force-recreate subscribed-orchestrator` |
| `subscribed-generator` | local-156 | subscribed-generator | /Users/micha/audioura-worktrees/LOCAL-156 | **Creating** (from ~/Audioura) | 5100 | `cd ~/Audioura && docker compose -f docker-compose-subscribed.yml up -d --force-recreate subscribed-generator` |

Notes on the subscribed containers:
- They ARE owned by their original compose file when run from LOCAL-156:
  `cd /Users/micha/audioura-worktrees/LOCAL-156 && docker compose -f docker-compose-subscribed.yml up -d --dry-run` → `Running`
- They are orphaned from `~/Audioura` because their project label is `local-156`, not `audioura`.
- If the LOCAL-156 worktree is deleted, no compose file will own them.

---

## Owned Containers — Running (no config drift)

| Container | Project | Service | Working Dir | Dry-Run Result | Port |
|-----------|---------|---------|-------------|----------------|------|
| `audioura-coordinates-fromai-1` | audioura | coordinates-fromai | /Users/micha/Audioura | Running | 5006 |
| `audioura-translation-service-1` | audioura | translation-service | /Users/micha/Audioura | Running | 5030 |
| `audioura-tour-update-1` | audioura | tour-update | /Users/micha/Audioura | Running | 5004 |
| `audioura-user-api-2-1` | audioura | user-api-2 | /Users/micha/Audioura | Running | 5003 |
| `audioura-tour-id-resolution-1` | audioura | tour-id-resolution | /Users/micha/Audioura | Running | 5025 |
| `audioura-tour-generation-modernized-1-1` | audioura | tour-generation-modernized-1 | /Users/micha/Audioura | Running | 5021 |
| `audioura-polly-tts-1-1` | audioura | polly-tts-1 | /Users/micha/Audioura | Running | 5018 |
| `audioura-treats-1` | audioura | treats | /Users/micha/Audioura | Running | 5007 |
| `development-postgres-2-1` | audioura | postgres-2 | /Users/micha/Audioura | Running | 5433 |
| `newsletter-link-extractor-1` | audioura | newsletter-link-extractor | /Users/micha/Audioura | Running | 5014 |
| `background-article-processor-1` | audioura | background-article-processor | /Users/micha/Audioura | Running | 5015 |
| `simple-news-search-1` | audioura | simple-news-search | /Users/micha/Audioura | Running | 5016 |
| `news-generator-1` | audioura | news-generator-1 | /Users/micha/Audioura | Running | 5010 |
| `news-processor-1` | audioura | news-processor-1 | /Users/micha/Audioura | Running | 5011 |
| `news-orchestrator-1` | audioura | news-orchestrator-1 | /Users/micha/Audioura | Running | 5012 |

---

## Owned Containers — Recreate (config drift, still owned)

These containers are recognised by compose but would be rebuilt on next `up -d` due to
image or configuration changes since they were last started. They are NOT orphaned.

| Container | Project | Service | Working Dir | Dry-Run Result | Port |
|-----------|---------|---------|-------------|----------------|------|
| `audioura-tour-generator-1` | audioura | tour-generator | /Users/micha/Audioura | Recreate | 5000 |
| `audioura-tour-orchestrator-1` | audioura | tour-orchestrator | /Users/micha/Audioura | Recreate | 5002 |
| `audioura-tour-processor-1` | audioura | tour-processor | /Users/micha/Audioura | Recreate | 5001 |
| `audioura-map-delivery-1` | audioura | map-delivery | /Users/micha/Audioura | Recreate | 5005 |
| `audioura-voice-control-1` | audioura | voice-control | /Users/micha/Audioura | Recreate | 5008 |

---

## Verification

```
docker ps -q | wc -l = 23 (before audit)
docker ps -q | wc -l = 23 (after audit)
```

All dry runs used `--dry-run` flag only. No containers were stopped, started, removed, or recreated.

---

## Method

Per D43's rule:
- `docker compose -f <file> up -d --dry-run <service>`
- **Running** = compose owns the container, no changes needed
- **Recreate** = compose owns the container, but would rebuild it (config drift)
- **Creating** = compose does NOT own the container; would create a duplicate on the same port
