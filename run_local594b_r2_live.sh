#!/usr/bin/env bash
# run_local594b_r2_live.sh — LOCAL-594B r2 isolated live run in a DISPOSABLE
# container (never audioura-*). Proves the grounding cut keeps story quality with
# Gemini grounding LIVE (r1 bounced because both runs were 402'd).
#
# Runs TWO tours, each BEFORE (storied-equivalent: STORY_LOOP_MAX_GROUNDED=4,
# grounded r2, grounded leads provider on) and AFTER (defaults = the cut):
#   1. McMullen Museum of Art, Boston College  — museum, 7 stops
#   2. Freedom Trail, Boston, MA               — walking, 5 stops
# AFTER runs first per tour (cheap) so a cost trip still leaves a usable AFTER.
#
# Total cap $8 INCLUDING Gemini grounding (COST_HARD_LIMIT_USD applies per
# generate_tour_text run; the orchestrator also hard-stops the batch at $8).
# Tour cache + stop pool OFF (fresh grounding each run). audio_tours DB is only
# counted, never written/deleted. Image removed at the end.
#
# Usage: ./run_local594b_r2_live.sh
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
IMAGE="local594b-gen-img"
ENV_FILE="${HERE}/.env"
OUT_DIR="${HERE}/tours/local594b_r2_live"
mkdir -p "${OUT_DIR}"
LOG="${OUT_DIR}/local594b_r2_live.log"
: > "${LOG}"

echo "[local594b] stamping git sha ..." | tee -a "${LOG}"
git -C "${HERE}" rev-parse HEAD > "${HERE}/.git_sha" 2>/dev/null || echo "?" > "${HERE}/.git_sha"

echo "[local594b] building ${IMAGE} ..." | tee -a "${LOG}"
docker build -f "${HERE}/Dockerfile.generator" -t "${IMAGE}" "${HERE}" >/tmp/local594b_build.log 2>&1 \
  || { echo "BUILD FAILED"; tail -40 /tmp/local594b_build.log; exit 1; }

NAME="local594b-gen"
# Per-run generate_tour_text hard limit on LLM spend. Measured live McMullen LLM
# ~$1.47-1.70; $1.80 keeps a single run bounded. Grounding ($0.014/query) adds a
# small amount on top. The batch gate below enforces the real $8 ceiling.
common=(
  --rm --name "${NAME}"
  --memory 3g --cpus 2
  --network development_default
  -e DATABASE_URL=postgresql://admin:password123@postgres-2:5432/audiotours
  -e DB_HOST=postgres-2 -e DB_PORT=5432 -e DB_NAME=audiotours
  -e DB_USER=admin -e DB_PASSWORD=password123
  -e STORIED_MODE=true
  -e DISABLE_TOUR_CACHE=1
  -e DISABLE_STOP_POOL=1
  -e COST_HARD_LIMIT_USD=1.80
  -v "${OUT_DIR}:/app/tours"
)
[ -f "${ENV_FILE}" ] && common+=(--env-file "${ENV_FILE}")

# ---- $8 batch budget gate ---------------------------------------------------
# Guarantee the ticket's "$8 total" cap. We track cumulative tour_total_cost
# (LLM + search + TTS + grounding) read from each run's JSON. Before each run we
# require >= $2.20 headroom (a single run's worst case: $1.80 LLM cap + grounding
# + TTS). If not, the batch stops and reports what it managed.
BATCH_CAP="8.00"
SPENT="0.00"

batch_spent () { python3 -c "print(f'{$SPENT:.4f}')"; }

# The JSON is written to the mounted tours/ dir, but the authoritative batch
# accounting reads the "Tour total:" line from the tee'd log after each run.
last_tour_total () {   # echoes the most recent "Tour total:" dollar figure
  grep -Eo 'Tour total:[[:space:]]+\$[0-9]+\.[0-9]+' "${LOG}" | tail -1 \
    | grep -Eo '[0-9]+\.[0-9]+' || echo "0"
}

run_one () {   # label  slug  location  type  stops  extra-env...
  local label="$1" slug="$2" loc="$3" typ="$4" stops="$5"; shift 5
  # batch gate
  local headroom
  headroom=$(python3 -c "print(f'{${BATCH_CAP} - ${SPENT}:.4f}')")
  if python3 -c "import sys; sys.exit(0 if ${headroom} >= 2.20 else 1)"; then
    :
  else
    echo "[local594b] BATCH BUDGET GATE: only \$${headroom} of \$${BATCH_CAP} left (<\$2.20 headroom) — stopping before ${slug} [${label}]." | tee -a "${LOG}"
    return 9
  fi
  echo "" | tee -a "${LOG}"
  echo "[local594b] ===== ${slug} [${label}] : ${loc} / ${typ} / ${stops} stops   (batch spent so far: \$${SPENT} / \$${BATCH_CAP}) =====" | tee -a "${LOG}"
  docker run "${common[@]}" \
    -e LOCAL594_LABEL="${label}" \
    -e LOCAL594_SLUG="${slug}" \
    -e LOCAL594_LOCATION="${loc}" \
    -e LOCAL594_TYPE="${typ}" \
    -e LOCAL594_STOPS="${stops}" \
    "$@" \
    "${IMAGE}" python run_local594_mcmullen.py 2>&1 | tee -a "${LOG}"
  # accumulate this run's cost
  local this_cost
  this_cost=$(last_tour_total)
  SPENT=$(python3 -c "print(f'{${SPENT} + ${this_cost}:.4f}')")
  echo "[local594b] run ${slug} [${label}] tour_total=\$${this_cost}  batch total now \$${SPENT} / \$${BATCH_CAP}" | tee -a "${LOG}"
}

# BEFORE = storied-equivalent: grounded r2, per-stop budget 4, grounded leads on.
BEFORE_ENV=( -e STORY_LOOP_MAX_GROUNDED=4 -e STORY_LOOP_R2_GROUNDED=1 -e STORY_LEADS_GROUNDED=1 )
# AFTER = defaults (the cut): STORY_LOOP_MAX_GROUNDED default 1, r2 ungrounded,
# leads provider dropped. Pass nothing.

# ---- Tour 1: McMullen (museum, 7) — AFTER then BEFORE ----
run_one AFTER  MCMULLEN "McMullen Museum of Art, Boston College, Boston, MA" museum 7
run_one BEFORE MCMULLEN "McMullen Museum of Art, Boston College, Boston, MA" museum 7 "${BEFORE_ENV[@]}"

# ---- Tour 2: Freedom Trail (walking, 5) — AFTER then BEFORE ----
run_one AFTER  FREEDOMTRAIL "Freedom Trail, Boston, MA" walking 5
run_one BEFORE FREEDOMTRAIL "Freedom Trail, Boston, MA" walking 5 "${BEFORE_ENV[@]}"

echo "[local594b] cleanup image ..." | tee -a "${LOG}"
docker rmi -f "${IMAGE}" >/dev/null 2>&1 || true

echo "" | tee -a "${LOG}"
echo "#################### LOCAL-594B r2 full log at ${LOG} ####################" | tee -a "${LOG}"
