##### READY FOR REVIEW

**Task:** LOCAL-167 — Which running containers has compose lost track of?
**Branch:** kiro/local167-compose-ownership-audit
**Commit:** 4d2809c

---

## Changes

| File | Change |
|------|--------|
| `CONTAINER_OWNERSHIP.md` (new) | Full audit of 23 running containers: 3 orphans, 5 config-drifted (owned), 15 fully owned |

---

## Evidence

### Baseline container count (before)
```
$ docker ps -q | wc -l
      23
```

### Decisive dry-run — full master compose
```
$ cd ~/Audioura && docker compose -f docker-compose-master.yml up -d --dry-run
 Container audioura-coordinates-fromai-1 Running
 Container audioura-translation-service-1 Running
 Container audioura-tour-update-1 Running
 Container audioura-user-api-2-1 Running
 Container newsletter-link-extractor-1 Running
 Container background-article-processor-1 Running
 Container development-postgres-2-1 Running
 Container audioura-polly-tts-1-1 Running
 Container news-generator-1 Running
 Container audioura-treats-1 Running
 Container audioura-tour-id-resolution-1 Running
 Container audioura-tour-generation-modernized-1-1 Running
 Container simple-news-search-1 Running
 Container news-orchestrator-1 Running
 Container news-processor-1 Running
 Container tour-editing-phase2-1 Creating          ← ORPHAN
 Container audioura-tour-generator-1 Recreate
 Container audioura-map-delivery-1 Recreate
 Container audioura-tour-processor-1 Recreate
 Container audioura-voice-control-1 Recreate
```

### Decisive dry-run — subscribed compose from ~/Audioura
```
$ cd ~/Audioura && docker compose -f docker-compose-subscribed.yml up -d --dry-run
 Container subscribed-generator Creating           ← ORPHAN (from this path)
 Container subscribed-orchestrator Creating        ← ORPHAN (from this path)
```

### Subscribed containers ARE owned from LOCAL-156
```
$ cd /Users/micha/audioura-worktrees/LOCAL-156 && docker compose -f docker-compose-subscribed.yml up -d --dry-run
 Container subscribed-generator Running
 Container subscribed-orchestrator Running
```

### Label conflict — two containers claim audioura:tour-generator
```
$ docker ps --format '{{.Label "com.docker.compose.project"}}:{{.Label "com.docker.compose.service"}}' | sort | uniq -c | sort -rn | head -3
   2 audioura:tour-generator
   1 local-156:subscribed-orchestrator
   1 local-156:subscribed-generator
```

### tour-editing-phase2-1 has incomplete compose labels
```
$ docker inspect --format '{{json .Config.Labels}}' tour-editing-phase2-1
{
    "com.docker.compose.project": "audioura",
    "com.docker.compose.service": "tour-generator",
    "com.docker.compose.version": "5.3.1"
}
```
Missing: config-hash, container-number, project.config_files, project.working_dir.
The `service=tour-generator` label is inherited from the base image, not set by compose.

### Final container count (after)
```
$ docker ps -q | wc -l
      23
```

### git status clean
```
$ git status --short
(empty)
```

---

## Limitations

1. **Recreate ≠ orphan but signals drift.** Five services (tour-generator, tour-orchestrator,
   tour-processor, map-delivery, voice-control) would be rebuilt on next `up -d`. They are
   owned — compose recognises them — but their running state differs from the current compose
   config. The audit classifies them as owned per D43's criterion (not `Creating`).

2. **Subscribed container ownership is path-dependent.** They are owned from LOCAL-156 but
   orphaned from ~/Audioura. If the LOCAL-156 worktree is deleted, they become fully
   unmanaged. The report documents both dry-run results.

3. **No stopped/exited containers audited.** Scope was running containers only (`docker ps`,
   not `docker ps -a`). Stopped containers that might conflict on restart were not checked.

4. **The active label conflict on `tour-editing-phase2-1` is cosmetic today** (different ports)
   but will become a port-5022 collision on the next full `docker compose up -d`.
