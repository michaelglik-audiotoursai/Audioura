#!/bin/bash
# run_ab_d511.sh — the A/B Michael asked for, 2026-08-22.
#
#   "a single old-vs-new comparison gives me nothing as old can be random and
#    so is new"  — correct at sd 4.9 (D484). Three runs per arm, D480's rule.
#
# ARMS ALTERNATE (OFF, ON, OFF, ON, OFF, ON) rather than batching each arm:
# retrieval drifts over an hour — Serper results and page availability change —
# and batching would hand that drift entirely to one arm.
#
# Both arms are pinned to 3 stops so the comparison is like-for-like; the
# release-check script defaults to 4 and the loop script to 3.
set -u
cd "$(dirname "$0")"
LOG=AB_D511_$(date +%Y%m%d_%H%M).log
export RELEASE_CHECK_STOPS=3 LOOP_TOUR_STOPS=3

echo "A/B start $(date)" | tee -a "$LOG"
for i in 1 2 3; do
  for arm in OFF ON; do
    if [ "$arm" = OFF ]; then SCRIPT=run_full_tour_release_check.py; else SCRIPT=run_loop_tour.py; fi
    echo "===== run $i arm=$arm script=$SCRIPT start=$(date +%H:%M:%S) =====" | tee -a "$LOG"
    python3 "$SCRIPT" >> "$LOG" 2>&1
    echo "===== run $i arm=$arm exit=$? end=$(date +%H:%M:%S) =====" | tee -a "$LOG"
  done
done
echo "A/B done $(date)" | tee -a "$LOG"
