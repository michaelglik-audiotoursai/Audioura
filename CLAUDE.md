# Mac Mini Setup — COMPLETE STEP-BY-STEP INSTRUCTIONS
## (Print this or keep it open on your phone — it's all you need)

---

## WHAT YOU'LL NEED
- The E: USB drive (plugged into Mac Mini)
- Your browser logged into github.com (email: michael.glik@gmail.com)
- ~30 minutes

---

## STEP 1: Plug in the USB drive
The drive will appear at `/Volumes/USB DISK/` (or similar name — look in Finder).
All references below use `USBPATH` — replace with your actual mount path.

## STEP 2: Open Terminal
Spotlight (Cmd+Space) → type "Terminal" → Enter

## STEP 3: Install Homebrew (if not already installed)
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```
Follow the prompts (press Enter, enter your Mac password if asked).
After install, run this to add brew to your PATH:
```bash
eval "$(/opt/homebrew/bin/brew shellenv)"
```

## STEP 4: Install GitHub CLI
```bash
brew install gh
```

## STEP 5: Authenticate with GitHub (NO keys or passwords needed — just your browser)
```bash
gh auth login
```
It will ask:
- **What account?** → `GitHub.com`
- **Protocol?** → `HTTPS`
- **Authenticate?** → `Login with a web browser`

It shows a one-time code (like: `A1B2-C3D4`). Press Enter.
Your browser opens github.com — paste the code, click "Authorize".
Done. You can now clone repos.

## STEP 6: Clone the Audioura repo
```bash
mkdir -p ~/Audioura
cd ~
gh repo clone michaelglik-audiotoursai/Audioura ~/Audioura
cd ~/Audioura
git checkout storied
```

## STEP 7: Copy the .env file from the USB drive
Find your USB drive path first:
```bash
ls /Volumes/
```
Then copy (replace `USB DISK` with whatever your drive is called):
```bash
cp "/Volumes/USB DISK/Audioura/assets/windows_env.env" ~/Audioura/development/.env
```
Verify:
```bash
cat ~/Audioura/development/.env | head -3
```
You should see `OPENAI_API_KEY=sk-...` etc.

## STEP 8: Install Docker Desktop
1. Open Safari, go to: https://www.docker.com/products/docker-desktop/
2. Download the **Apple Silicon** version (.dmg)
3. Open the .dmg, drag Docker to Applications
4. Launch Docker from Applications
5. Wait until the whale icon in the menu bar says "Running"

⚠️ **Port 5000 conflict**: macOS uses port 5000 for AirPlay Receiver.
Go to: System Settings → General → AirDrop & Handoff → turn OFF "AirPlay Receiver"

## STEP 9: Build and start the services
```bash
cd ~/Audioura/development
docker-compose -f docker-compose-master.yml build tour-generator
docker-compose -f docker-compose-master.yml up -d
```
Verify:
```bash
docker ps
curl http://localhost:5000/health
```

## STEP 10: Install Python and run tests
```bash
brew install python@3.13
cd ~/Audioura/development
python3 test_sq4_merge.py
python3 test_palais_fix_lead_fixture.py
```
Both should say `ALL TESTS PASSED`.

## STEP 11: Test tour generation
```bash
docker exec development-tour-generator-1 python -c "
import sys, os
sys.path.insert(0, '/app')
os.environ['STORIED_MODE'] = 'true'
from generate_tour_text import generate_tour_text
text, _, _ = generate_tour_text('Palais Lascaris, Nice, France', 'museum', '/tmp/t.txt', 6)
print(f'SUCCESS: {len(text)} chars') if text else print('FAILED')
"
```
Expected: `SUCCESS: ~10000+ chars`

---

## YOU'RE DONE! 🎉

The Mac Mini is now a full development environment. To continue working:
- Edit code in `~/Audioura/development/`
- After changes: `docker-compose -f docker-compose-master.yml build tour-generator && docker-compose -f docker-compose-master.yml up -d tour-generator`
- Push changes: `git add . && git commit -m "message" && git push origin storied`

---

## REFERENCE INFO

| Item | Value |
|------|-------|
| GitHub repo | `michaelglik-audiotoursai/Audioura` |
| Branch | `storied` |
| GitHub email | `michael.glik@gmail.com` |
| Version | `2.2.0+1` |
| Docker port | `localhost:5000` |
| Postgres | `localhost:5432` (user: admin, pass: password123) |
| ClickUp list | `1000410000000733` (🟦 Services — Kiro) |

## TROUBLESHOOTING
- **"port 5000 already in use"** → Disable AirPlay Receiver (Step 8)
- **Docker build fails with architecture error** → In Docker Desktop settings, enable "Use Rosetta for x86/amd64 emulation"
- **"Permission denied" on git push** → Re-run `gh auth login`
- **Python tests import error** → Make sure you're in `~/Audioura/development/` directory


---

# SESSION HANDOFF — Audioura review (read this first)
## Last updated: 2026-07-29 evening (tour-quality loop root cause found)

### FIRST ACTIONS ON A FRESH SESSION
1. `git log --oneline -3` and `cat .continuous_dev/STATUS.md`.
2. Say/expect **"restart continuous dev"** — the watcher loop is
   session-scoped and dies with the session. Detached `kiro-cli` worker
   processes SURVIVE a restart; only the review loop needs re-arming.
3. Check in-flight work: `tail -6 kiro_sessions_ran.md`, `git worktree list`,
   and each `~/audioura-worktrees/LOCAL-NN/SUBMISSION_LOCAL-NN.md`.

**Permissions:** `.claude/settings.json` has
`"permissions.defaultMode": "bypassPermissions"` (committed `b8eb3eb` at
Michael's explicit request). `defaultMode` is read **at session start** —
mid-session edits do nothing, which is why a restart was needed. Allow-rules
DO hot-reload. Shift+Tab only reaches "auto-accept edits", which does not
cover Bash — that was the original source of the prompt fatigue.

**2026-07-29 delta — the loop's premise was wrong, and this is the headline:**
Rounds 1–4 of the tour-improvement loop all fought fabrication symptoms in
the fill logic. LEAD traced the real ceiling to the **data layer**:
- **Corpus size caps the score.** max = `(100/N)*(2C-N)` before bonuses,
  C = venue canonical titles, N = requested stops. Asian Arts Museum has
  C=6, N=8 → base cap 50.
- **CORRECTION (Michael challenged this, he was right):** 75 IS reachable
  at N=8 — the rubric's **cross-stop correlation bonus (+50%, explicitly
  "can push total >100")** and venue-identity bonus (+10%) were omitted
  from that first calculation. With all-RICH stops: 55 with no callbacks,
  **75.6 with callbacks on half the stops, 96.2 with callbacks throughout.**
  Break-even per-stop quality: 1.24 (impossible) without the correlation
  bonus, 0.83 with it. So **75 mandates building the dominant-story
  feature** — it cannot be reached by per-stop quality alone.
- **Zero per-stop source material.** Every stop logged `No RAG context —
  cannot generate fact sheet`. Phase 5 writes from parametric memory only.
- **`story_elements_json` was empty for all 16 venues** via three silent
  breaks: `corpus_result.get('story_elements')` reads a key `story_miner`
  never emits; `extract_story_elements_from_pages`/`persist_story_elements`
  did not exist (ImportError swallowed by try/except); and the complete
  SQ3/SQ4 engine in `story_element_extractor.py` had **zero production
  callers**. The oft-cited "11/11 suites green" included suites exercising
  dead code — green tests over orphaned modules prove nothing.
- **`STORY_QUALITY_DESIGN.md` already specifies everything.** §SQ-S6b IS the
  "dominant story" (theme threads, deterministic entity clustering then one
  grounded LLM naming pass, coverage-proportional multi-thread blending,
  degradation rules). §2c/2d specify the swipe/personalization feature and
  `stop_metrics.class_details/class_historic/class_social` — **live, 315
  classified rows**. SQ4b == deferred ClickUp task `wdvrdawdje`.

**Michael's gate (2026-07-29):** he runs the iPhone field test only once the
internal score reaches **75 at N=8 on the Asian Arts Museum**. Deliberately
not softened to N=6 — that would let a weaker system pass.

**State:** `storied` @ `33e306f`, **26 commits unpushed** (field-test gate).
LOCAL-19 merged @ `04e726d` (R4 replenishment now actually runs, and it
carried the LOCAL-16 verified-only gate which had never reached storied).
In flight: **LOCAL-21** (story wiring r2), **LOCAL-22** (title corruption at
source — unfixed for 7 rounds, claimed fixed 3×), **LOCAL-23** (multi-source
corpus expansion: Tier 1 = Wikipedia + museum's own site co-equal, Tier 2 =
Joconde/POP; most famous first; keep the smaller set if unverifiable).

**ClickUp rate-limited ~2026-07-29 21:2x for ~253 min (clears ~01:40).**
Use `CLICKUP_OFFLINE_QUEUE.md` and post retroactively — established pattern.
Open ClickUp tasks: `wdvrdax5j8` (LOCAL-18/21), `wdvrdax5j9` (LOCAL-19,
approved), `wdvrdax5ja` (LOCAL-20/22). LOCAL-23 has no ClickUp task yet.

**Discussion to resume with Michael (in order):** (1) how to build the
dominant story — he wants ideas, and SQ-S6b already has his own worked
example; (2) a generic approach for ANY feature, not just tours —
Subscription, and swipe-to-sway-stops correlated to story properties
(Historical / details / social); (3) document that approach so it can be
replicated on the Windows machine for parallel feature development.
**Blocker for (3): nothing reaches Windows until `storied` is pushed.**

- **LIVE-ARTIFACT HARD GATE (Michael, 2026-07-27)** — see
  `remind_Services_ai.md`; summary below in DISPATCH PROTOCOL.
- **Concurrency lesson (2026-07-29):** dispatch task prompts must tell each
  agent to write to its own `SUBMISSION_LOCAL-NN.md`, NOT the shared
  `CLICKUP_OFFLINE_QUEUE.md` — absolute paths defeat worktree isolation.
  Verified working with 3 concurrent agents; no collision.

**You are Claude Code on the Mac Mini**, working in `~/Audioura` on branch
`storied`. Chat sessions can be lost (crash/timeout) — **that's expected**.
The work lives in the files on disk and the `KIRO_*` markdown documents, not
in chat. Reload context from those, not from memory.

## The workflow

Collaborative loop: **Claude reviews → Kiro executes → Michael coordinates/approves.**
Review notes are written to disk so any session (or crash) can resume:
- `~/Audioura/KIRO_REVIEW_*.md` — Claude's review rounds (verdicts appended at bottom)
- `~/Audioura/KIRO_RESPONSE_*.md` — Kiro's execution reports (addenda at bottom)

**The git diff/log is ground truth** — always verify report claims against it:
```
cd ~/Audioura
git status && git log --oneline -5
ls -t KIRO_RESPONSE_*.md KIRO_REVIEW_*.md | head   # latest round
```

## WHERE THINGS STAND — Rounds 1–11 complete and APPROVED

1. **Docker infra (R1–4):** wired tour-generation-modernized (5021),
   polly-tts (5018), translation-service (5030) into
   `docker-compose-master.yml`; fixed `.dockerignore`, `Dockerfile.orchestrator`
   entitlements, Flask 1.1.4 send_file param.
2. **Tour-type classification (R5–8):** fixed museum-forcing regression; added
   transport mode detection (`_TRANSPORT_MODE_KEYWORDS`) with distance tiers
   (animal 20km, bike 30km, vehicle 400km, country-scale containment).
3. **Field-test fixes (R9–10):** title category fix, transport-stop constraint,
   `_verify_transport_accessibility()` incl. Part C replacement loop.
4. **Field-test round 11 (dog tour, Big Lake AK) — APPROVED 2026-07-22:**
   - `stops_count` persisted on INSERT + both UPDATE paths
     (`tour_orchestrator_service.py`) and inherited by translations
     (`translation-service/translation_service.py`).
   - dog/dogsled/mushing/husky added to animal transport regex
     (`generate_tour_text.py:65`).
   - Mode-derived display titles (`Dog Sledding Tour`, `Camelback`, `Cycling`…).
   - DB `tour_name` now parsed from generated content's effective category, not
     the app's raw `tour_type` (fixes "museum" leaking into names/translations).
   - Intent-LLM prompt broadened for unknown transports (robot/segway/drone) +
     `[TRANSPORT] UNRECOGNIZED MODE CANDIDATE` log guardrail.
   - Museum narrative register gated to museum category only; no invented
     named people in non-museum prompts; Orientation dedupe; transport-aware
     directions language.
   - Verified on regenerated tours 8 (en) / 9 (ru): stops_count=2 both, no
     museum wording, one Orientation per stop. Both test suites green.

## CURRENT STATE / NEXT STEPS

1. **Committed locally as checkpoint** (rounds 1–11, see `git log`). **NOT
   pushed yet** — push waits for Michael's iPhone field test:
   - tour list shows "Dog Sledding" (not museum); stop count correct; audio
     plays; ru translation has no «музеям».
   - After pass: `git push origin storied`.
2. **Known open items (not blockers):**
   - Issue 8.2: canonical-location cross-check for real venues (Happy Trails
     Kennel got Eagle River coords) — needs infrastructure, deferred.
   - App-side ticket: iPhone app should prefer server's `actual_stops` over
     requested count.
   - Translated title redundancy cosmetic ("тур на собачьих упряжках … - тур
     на собачьих упряжках").
   - `audio_tours.language` column says 'en' even for ru rows (pre-existing).
   - Python 3.9 base image past EOL — future bump to 3.11/3.12.
3. **Dual-machine development starting:** Windows laptop (amd64) is back.
   Rules: GitHub is the only sync channel; branch-per-task per machine; each
   machine builds its own Docker images (never share images across arch);
   `.env` synced manually via USB (Mac copy is newest — has OPENAI_API_KEY);
   each machine has its own Postgres (disposable dev data); the iPhone app
   points at one server IP (currently Mac Mini 192.168.0.137) — switch in app
   settings when testing against the laptop.

## DISPATCH PROTOCOL — two machines, multiple agents (adopted 2026-07-23)

ClickUp is the control panel, but it is NOT a self-serve queue (no reliable
concurrent claiming across machines). **All work is explicitly dispatched by
Michael or Claude.**

**Agent IDs:** `Mac Mini Kiro` (this machine) · `Services Kiro` (Windows laptop)
· `Mobile Kiro` (Windows laptop) · `Claude` (reviewer/dispatcher).

**Lists per space** (current space: Storied; Development folder):
🔵 Claude — Review (`1000410000000732`) · 🟦 Services — Kiro (`1000410000000733`)
· 🟩 Mobile — Kiro (`1000410000000734`) · 👤 Michael (`1000410000000735`).

**Flow:**
1. **Michael** creates a Feature task describing requirements and puts it in
   🔵 Claude — Review (or says "Claude, work on your queue").
2. **Claude** decomposes it into independent per-agent tasks in the target
   agent's list. Every task description starts with `**Agent:** <ID>` and
   specifies: git branch (`kiro/<task_id>`), acceptance criteria, test plan.
   Dependent tasks are created only when unblocked (or clearly marked blocked).
3. **Kiro** on "work on your queue": read own list top-to-bottom, take only
   tasks bearing YOUR Agent ID with status *to do*. Set *in progress* +
   comment when starting. Work on the specified branch; push when pausing.
   When done: comment with commit hash + response doc name, move the task to
   🔵 Claude — Review.
4. **Claude** on "work on your queue": review tasks in 🔵 Claude — Review
   against the actual git diff. APPROVED → comment, mark complete, handle
   merge to `storied`. Rejected → comment what's wrong, move back to the
   agent's list as *to do*.
5. **Michael** only touches the 👤 Michael list (field tests, approvals,
   business decisions).

**Git rules:** one branch per task named after the task ID; never share a
branch across machines; pull when starting, push when stopping; only Claude
merges to `storied` after review.

**Live-artifact hard gate (Michael's binding ruling, 2026-07-27):** no
"COMPLETE" claim on grounding-pipeline tasks without a committed artifact
from a real end-to-end run (code_sha + behavior-specific log lines + DB
evidence where relevant + verbatim regression exits). Offline fixtures are
supporting evidence only. "Unproven, handing to LEAD" is always an
acceptable report; an unproven claim stated as complete is not. Full text
in `remind_Services_ai.md`.

**Mac Mini Kiro ClickUp access:** via MCP (`~/.kiro/settings/mcp.json`,
mcp-remote → https://mcp.clickup.com/mcp, browser OAuth as
michael.glik@gmail.com). Node.js installed via brew.

## ENVIRONMENT NOTES

- Mac Mini, **Apple M4 (arm64)**. Images build arm64 locally. If a build fails
  on an amd64-only image: Docker Desktop → Settings → enable Rosetta, or set
  `platform: linux/amd64` on that service.
- `.env` at `~/Audioura/.env` (gitignored; backup `~/Audioura/.env.backup`).
  **Do not overwrite with the old Windows copy.**
- Repo root **is** the dev directory on the Mac (no `development/` subfolder);
  `docker-compose-master.yml` sits directly in `~/Audioura`. (The Windows clone
  historically used `development/` — verify layout after pulling there.)
- Postgres container: `development-postgres-2-1`, db `audiotours`, user admin.
- ClickUp list: `1000410000000733` (🟦 Services — Kiro).

## CONTINUOUS DEVELOPMENT — CONTROL INTERFACE (adopted 2026-07-28)

Background: bugs Michael finds while testing get written up as
`new_kiro_session_is_required_N.md` task files at the repo root.
`~/Audioura/kiro_dispatcher.py` watches for unclaimed ones and forks a
detached, headless `kiro-cli chat --trust-all-tools --no-interactive`
session per file — logging start/completion to `kiro_sessions_ran.md`.
Claude (LEAD) runs a recurring watcher loop that reviews completed
submissions (full rigor: diff read, regression suite, live verification —
never trust the report) and either merges + rebuilds the shared container,
or writes a new task file with the required fix so the next dispatch cycle
picks it up automatically. Full design/rationale lives in this session's
conversation history and the `round12-review-state.md` memory file — this
section is only the control surface.

**State/control files, all under `~/Audioura/.continuous_dev/`:**
- `PAUSE` — sentinel file. If present, the watcher skips all
  dispatch/review work on its next tick (but keeps ticking lightly so it
  notices removal). Michael can `touch`/`rm` this directly, no need to ask
  Claude.
- `STATUS.md` — auto-updated every tick: active bug-threads, round counts
  per thread, any stagnation flags, whether currently paused. Read anytime
  with `cat ~/Audioura/.continuous_dev/STATUS.md` — no need to wait for a
  narrated summary.
- `last_boot.txt` — records the machine's boot time as of the last tick,
  used to detect a reboot happened and recover cleanly (see below).

**Plain-language triggers Michael can use in any session (current or future):**
- **"status" / "what's the continuous dev status"** → read `STATUS.md` and
  summarize.
- **"pause continuous dev"** → create the `PAUSE` sentinel.
- **"resume continuous dev"** → remove the `PAUSE` sentinel.
- **"stop continuous dev"** → full teardown: cancel the recurring
  watcher job (`CronDelete`/`ScheduleWakeup stop`), confirm no dispatcher
  processes are left running.
- **"restart continuous dev"** → re-arm the watcher loop from scratch;
  this is also the recovery step after a detected reboot (see below).
- **"check now"** → run one watcher tick immediately, out of band from
  the schedule.

**Reboot handling (deliberately simplified 2026-07-28):** full
launchd-based unattended durability was considered and set aside as
unnecessary — reboots are rare enough that detect-and-recover is the
right amount of engineering, not full self-resurrection. On each tick,
compare the current boot time against `last_boot.txt`; a mismatch means a
reboot happened since the last tick. Recovery: any task with a `STARTED`
record but no terminal (`COMPLETED`/`FAILED`/`TIMEOUT`) record is
abandoned (its process died with the reboot) — mark it `ABANDONED
(reboot detected)` in `kiro_sessions_ran.md` and let normal dispatch logic
re-claim and re-run it fresh on the next scan. Task files themselves are
plain files on disk and always survive a reboot untouched — nothing is
ever lost, only the in-flight attempt is discarded and restarted. The
watcher loop itself does NOT restart automatically after a reboot (it was
session-bound and died with the session) — use the "restart continuous
dev" trigger above once someone notices the machine came back.
