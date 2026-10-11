#!/bin/zsh
# Amazon Q (kiro-cli) listener-critique of a delivered tour. Read-only: writes only the critique file.
# usage: critique.sh <audio_tour_id> [requested_stops]
ID=$1; REQ=${2:-$(docker exec development-postgres-2-1 psql -U admin -d audiotours -Atc "select stops_count from audio_tours where id=$1")}; D=~/Audioura/.continuous_dev/calib/critique; mkdir -p $D
# Pull the raw tour_content once so we can read its Tour-Category BEFORE the field
# lines are stripped out of the spoken text below.
RAW=$(docker exec development-postgres-2-1 psql -U admin -d audiotours -Atc "select tour_content from audio_tours where id=$ID")
# [LOCAL-675 item 3] Criterion 3 was museum-only ("hours and admission are SPOKEN"),
# which penalises walking tours that have no admission desk. Read Tour-Category and,
# for a walking tour, judge the between-stops navigation instead. Everything else is
# unchanged. Default (museum / unknown / anything else) keeps the original criterion.
CAT=$(printf '%s' "$RAW" | sed -nE 's/^Tour-Category:[[:space:]]*([A-Za-z]+).*/\1/Ip' | head -1 | tr '[:upper:]' '[:lower:]')
if [ "$CAT" = "walking" ]; then
  CRIT3="directions between stops are clear, with distances"
else
  CRIT3="hours and admission are SPOKEN, not 'check the website'"
fi
# Critique the SPOKEN text (D617: the Sources line lives only in the text view and is not narrated).
printf '%s' "$RAW" \
  | python3 -c "import sys; sys.path.insert(0,'/Users/micha/audioura-subscribed-local'); from spoken_text_hygiene import strip_sources_and_urls as s; import re; t=s(sys.stdin.read())[0]; t='\\n'.join(re.sub(r'^\\s*(Orientation|Directions)\\s*:\\s*','',l) for l in t.split('\\n') if not re.match(r'^\\s*(Address|Coordinates|Tour-Category|Type/Specialty|Museum Information)\\s*:',l)); print(t)" > $D/tour_$ID.txt
cd $D && kiro-cli chat --no-interactive --trust-tools=fs_read "You are a demanding audio-tour editor reviewing tour file $D/tour_$ID.txt (read it). It is the exact text the voice speaks (field lines removed). The listener REQUESTED $REQ stop(s); a short tour is by request, not a defect. Judge it as a LISTENER standing in the museum, using the owner's criteria:
1) each stop LEADS with the WORK and ARTIST (what it shows, meaning, what critics said, the artist's life at that moment) with emotional content; genuine collector/provenance/museum STORIES (named people, motive, consequence — e.g. a theft and recovery) are a welcome minority story type, but dry institutional filler (dates of accession, budgets, renovations) is a defect;
2) no story repeated across stops;
3) ${CRIT3};
4) no URLs or source lists in narration;
5) no leftovers of other tours (restaurant offers MID-tour, re-telling a previous stop's facts); one restaurant offer as the very LAST sentence is intentional house design, do not flag it. Linking a stop to an earlier one is WELCOME continuity when it happens a couple of times per tour with a real connection; flag it only if nearly every stop does it or it re-tells earlier content;
6) a real conclusion;
7) stop count vs requested, explained if short;
8) factual red flags (claims that sound invented), INCLUDING any stop whose artwork is actually held by a different museum than the one this tour is for (e.g. a Tate Britain painting in a National Gallery tour) and wrong admission prices — use your own knowledge of where famous works hang.
Output ONLY markdown: a score /10, then a table of defects (stop, quote ≤20 words, criterion, severity), then the 3 highest-value code-level improvements. Do not modify any file." > $D/critique_$ID.md 2>&1
echo "$D/critique_$ID.md"
