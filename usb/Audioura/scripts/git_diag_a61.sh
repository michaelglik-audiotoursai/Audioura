#!/bin/bash
# A#61b — Git diagnostic: show full branch/tag/commit state

PROJECT="$HOME/Development/AudioTours/development/audio_tour_app"
OUTPUT="$HOME/Desktop/a61_git_diag.txt"
USB="/Volumes/USB DISK/Audioura/results"

exec > >(tee "$OUTPUT") 2>&1

echo "🍎 iOS AMAZON-Q — A#61b Git Diagnostic"
echo "Date: $(date)"
echo ""

cd "$PROJECT" || { echo "❌ Project not found: $PROJECT"; exit 1; }

echo "=== Current branch ==="
git rev-parse --abbrev-ref HEAD
echo ""

echo "=== All local branches ==="
git branch -v
echo ""

echo "=== All remote branches ==="
git branch -r
echo ""

echo "=== All tags (last 20) ==="
git tag | sort -V | tail -20
echo ""

echo "=== Last 10 commits on current branch ==="
git log --oneline -10
echo ""

echo "=== Git status ==="
git status --short
echo ""

echo "=== pubspec.yaml version ==="
grep "^version:" pubspec.yaml
echo ""

echo "=== Remote URL ==="
git remote -v
echo ""

echo "=== Branch existence check ==="
for b in main ios-dev Newsletters Tours_Step_Maps; do
    if git rev-parse --verify "$b" >/dev/null 2>&1; then
        echo "$b (local):  $(git log --oneline -1 $b)"
    else
        echo "$b (local):  NOT FOUND"
    fi
done
echo ""

echo "=== Remote refs ==="
git ls-remote origin 2>/dev/null | grep -E "refs/heads|refs/tags/v1\.2" | head -30
echo ""

if [ -d "$USB" ]; then
    cp "$OUTPUT" "$USB/a61_git_diag.txt"
    echo "✅ Results copied to USB"
else
    echo "⚠️  USB not found — results on ~/Desktop only"
fi

diskutil eject "/Volumes/USB DISK" 2>/dev/null && echo "✅ USB ejected" || echo "ℹ️  USB eject skipped"
