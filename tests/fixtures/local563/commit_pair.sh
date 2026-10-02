#!/usr/bin/env bash
# LOCAL-563 — commit+push one completed tour pair's artifacts.
# Usage: commit_pair.sh <slug> <N> <message-tail>
# Reverts the unrelated prompt_dump_stop1.txt churn the generator writes to the
# repo root, stages only the pair's baseline artifacts (never the gitignored
# spawn logs), commits and pushes.
set -euo pipefail
slug="$1"; n="$2"; tail="${3:-}"
root="$(git rev-parse --show-toplevel)"
cd "$root"
git checkout -- prompt_dump_stop1.txt 2>/dev/null || true
d="tests/fixtures/local563"
files=()
for run in run1 run2; do
  for ext in json txt log gemini.jsonl; do
    f="$d/runs/${slug}_${run}.${ext}"
    [ -f "$f" ] && files+=("$f")
  done
  ev="$d/runs/${slug}_${run}_evidence.json"
  [ -f "$ev" ] && files+=("$ev")
done
files+=("$d/budget.log" "$d/budget_state.json")
git add "${files[@]}"
git commit -q -m "LOCAL-563: baseline pair ${n}/10 — ${slug}

${tail}"
git push
git rev-list --count f5bc845..HEAD
