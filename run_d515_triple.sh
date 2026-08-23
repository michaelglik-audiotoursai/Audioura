#!/bin/bash
# run_d515_triple.sh — three tours under D515, to compare against the three
# loop-off runs already recorded on 2026-08-23 (D513).
#
# The rule is run EXACTLY as approved — the two amendments LEAD proposed
# (confirmed>=1, C0 X0 as a failed adjudication) are deliberately NOT applied,
# because changing the rule mid-measurement measures something else.
set -u
cd "$(dirname "$0")"
LOG=D515_TRIPLE_$(date +%Y%m%d_%H%M).log
export LOOP_TOUR_STOPS=3
echo "D515 triple start $(date)" | tee -a "$LOG"
for i in 1 2 3; do
  echo "===== run $i start=$(date +%H:%M:%S) =====" | tee -a "$LOG"
  python3 run_loop_tour.py >> "$LOG" 2>&1
  echo "===== run $i exit=$? end=$(date +%H:%M:%S) =====" | tee -a "$LOG"
done
echo "D515 triple done $(date)" | tee -a "$LOG"
