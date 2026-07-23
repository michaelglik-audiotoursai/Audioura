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

**You are Claude Code on the Mac Mini**, working in `~/Audioura` on branch
`storied`. A previous session was lost (terminal/crash/timeout). No chat memory
carried over — **that's expected**. None of the *work* was lost: it lives in the
files on disk and the `KIRO_*` markdown documents, not in chat. Reload context
from those, not from memory.

## The workflow

Collaborative loop: **you (Claude) review → Kiro executes → Michael coordinates.**
Nothing is committed until Michael approves. Review notes are written to disk so
any session (or crash) can resume:
- `~/Audioura/KIRO_REVIEW_*.md` — your review rounds
- `~/Audioura/KIRO_RESPONSE_*.md` — Kiro's execution reports

## FIRST STEPS (do these before trusting any summary)

The summary below is Kiro's account of what it did. The **git diff is ground
truth.** Verify one against the other:

```
cd ~/Audioura
git diff --stat                         # real uncommitted state
git status
ls -t KIRO_RESPONSE_*.md KIRO_REVIEW_*.md | head   # confirm latest round
```

Then read the latest response doc (currently
`KIRO_RESPONSE_10_transport_verify_gaps.md`) and verify its claims against the
actual diffs in `generate_tour_text.py` and `docker-compose-master.yml` before
approving anything.

## WHERE THINGS STAND — 10 rounds of review (Kiro's summary)

1. **Docker infra (R1–4):** wired missing services into
   `docker-compose-master.yml`: tour-generation-modernized-1 (5021), polly-tts-1
   (5018), translation-service (5030). Fixed `.dockerignore`; added
   `entitlements.py` to `Dockerfile.orchestrator`; fixed Flask send_file param
   (`download_name` → `attachment_filename`, Flask 1.1.4).
2. **Tour-type classification (R5–8):** fixed regression forcing all tours to
   "museum". Added movie/film/book/literary/novel to S15 regex. Added transport
   mode detection (`_TRANSPORT_MODE_KEYWORDS`) with distance tiers (animal 20km,
   bike 30km, vehicle 400km, country-scale containment). Four touchpoints:
   effective_tour_type suppression, S15 bypass, museum-containment bypass,
   tiered GEO-CHECK.
3. **Field-test issues (R9):** fixed title showing "Museum" instead of correct
   category. Added transport-stop constraint prompt +
   `_verify_transport_accessibility()` for unusual modes (camel/horse).
4. **Transport verify gaps (R10):** regex now handles "camelback riding tour"
   (compound + modifier). Extracted `_verify_transport_accessibility()` into a
   reusable function; applied to the Part C replacement loop so excluded resorts
   aren't silently re-added.

**Current state:** `KIRO_RESPONSE_10_transport_verify_gaps.md` is ready for
review. Changes are in `generate_tour_text.py` and `docker-compose-master.yml`,
plus new files (`Dockerfile.modernized`, `requirements-modernized.txt`, restored
`*_fixed.py`). **Nothing committed/pushed yet.**

## WHAT I NEED YOU TO DO

1. Run the FIRST STEPS above and read
   `KIRO_RESPONSE_10_transport_verify_gaps.md`.
2. Verify Round-10 changes in `generate_tour_text.py` against that report;
   flag anything the report claims that the diff doesn't show.
3. **Checkpoint-commit now — do not wait for final approval.** Ten rounds
   uncommitted is fragile (a lost session already happened; a disk issue would
   lose everything). Run:
   ```
   git add -A && git commit -m "WIP: Kiro rounds 1-10, pending review"
   ```
   We can amend/squash later. Then continue the review.
4. Confirm the stack actually runs, not just that the diff looks right:
   ```
   docker compose -f docker-compose-master.yml build
   docker compose -f docker-compose-master.yml up -d
   docker compose ps
   docker compose logs orchestrator
   ```
5. Once review passes and the stack is up: `git push origin storied`.

## PREVENT THE NEXT AMNESIA

After each round, update a running `REVIEW_STATE.md` (round #, files touched,
what's approved, what's pending) and keep the key project context in `CLAUDE.md`
so the next session auto-loads it. Commit often.

## ENVIRONMENT NOTES

- Mac Mini, **Apple M4 (arm64)**. Images build arm64 locally — usually fine. If a
  build fails on an amd64-only image, enable Rosetta in Docker Desktop →
  Settings → General, or set `platform: linux/amd64` on that one service.
  (Images built here won't run unchanged on the returning amd64 laptop.)
- `.env` is in `~/Audioura/.env` (Kiro added `OPENAI_API_KEY`; it's newer than
  the Windows copy — **do not overwrite it**). It's gitignored; a local backup is
  at `~/Audioura/.env.backup`.
- Repo root **is** the dev directory on the Mac (no `development/` subfolder).
  `docker-compose-master.yml` sits directly in `~/Audioura`.
- Python 3.9 base image is past end-of-life — a future bump to 3.11/3.12 is worth
  noting, not today's task.
