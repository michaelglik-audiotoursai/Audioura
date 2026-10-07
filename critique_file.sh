#!/bin/zsh
# critique_file.sh — LOCAL-616 adaptation of ~/Audioura/.continuous_dev/calib/critique.sh
# for ISOLATED-run output FILES (the isolated run uses a disposable Postgres, so the
# delivered tour is a .txt file, not a row in the live audio_tours table).
#
# Same rubric and same spoken-text hygiene (D617: strip the Sources line / URLs so the
# critique judges only the SPOKEN text) as the canonical critique.sh.
#
# usage: critique_file.sh <delivered_tour.txt> <label>
set -uo pipefail
SRC="$1"; LABEL="$2"
D=~/Audioura/.continuous_dev/calib/critique; mkdir -p "$D"
OUT_TXT="$D/tour_LOCAL616_${LABEL}.txt"
OUT_MD="$D/critique_LOCAL616_${LABEL}.md"

python3 -c "import sys; sys.path.insert(0,'/Users/micha/audioura-subscribed-local'); from spoken_text_hygiene import strip_sources_and_urls as s; print(s(open('$SRC', encoding='utf-8').read())[0])" > "$OUT_TXT"

cd "$D" && kiro-cli chat --no-interactive --trust-tools=fs_read "You are a demanding audio-tour editor reviewing tour file $OUT_TXT (read it). Judge it as a LISTENER standing in the museum, using the owner's criteria:
1) each stop is about the WORK and ARTIST (what it shows, meaning, what critics said, the artist's life at that moment) with emotional content, not museum/donor history;
2) no story repeated across stops;
3) hours and admission are SPOKEN, not 'check the website';
4) no URLs or source lists in narration;
5) no leftovers of other tours (recaps or restaurant offers MID-tour; one restaurant offer as the very LAST sentence is intentional house design, do not flag it);
6) a real conclusion;
7) stop count vs requested, explained if short;
8) factual red flags (claims that sound invented).
Output ONLY markdown: a score /10, then a table of defects (stop, quote <=20 words, criterion, severity), then the 3 highest-value code-level improvements. Do not modify any file." > "$OUT_MD" 2>&1
echo "$OUT_MD"
