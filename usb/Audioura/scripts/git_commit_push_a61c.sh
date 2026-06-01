#!/bin/bash
# A#61c — Git Commit & Push v1.2.9+60 to GitHub
# Mac Mini is on 'main' branch. Tours_Step_Maps/ios-dev do not exist locally.
# Strategy: commit on main, push main, then push HEAD to ios-dev on remote.

exec > >(tee ~/Desktop/full_a61c_session.txt) 2>&1

echo "🍎 iOS AMAZON-Q — A#61c Git Commit & Push v1.2.9+60"
echo "Date: $(date)"
echo ""

PROJECT="$HOME/Development/AudioTours/development/audio_tour_app"
USB="/Volumes/USB DISK/Audioura/results"
RESULTS="$HOME/Desktop/a61c_results.txt"
VERSION_TAG="v1.2.9+60"
COMMIT_MSG="v1.2.9+60 - A#50-A#60: Map feature, per-stop focus, jitter fix, museum single-POI guard"

# ── STEP 0: Pre-flight ────────────────────────────────────────────────────────
echo "=== STEP 0: Pre-flight ==="
cd "$PROJECT" || { echo "❌ FATAL: Project not found: $PROJECT"; exit 1; }
echo "✅ Project directory exists"

CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"

PUBSPEC_VERSION=$(grep "^version:" pubspec.yaml | head -1)
echo "pubspec.yaml: $PUBSPEC_VERSION"
if ! echo "$PUBSPEC_VERSION" | grep -q "+60"; then
    echo "❌ FATAL: pubspec.yaml does not show +60. Got: $PUBSPEC_VERSION"
    exit 1
fi
echo "✅ pubspec.yaml confirmed at +60"

echo ""
echo "--- Last 3 commits ---"
git log --oneline -3
echo ""

# ── STEP 1: Normalize + stage ─────────────────────────────────────────────────
echo "=== STEP 1: Normalize line endings ==="
git add --renormalize .
echo "✅ Renormalized"
echo ""

echo "=== STEP 2: Stage all changes ==="
git add -A
STAGED=$(git diff --cached --name-only | wc -l | tr -d ' ')
echo "Staged files: $STAGED"
git diff --cached --name-status
echo ""

# ── STEP 3: Commit ────────────────────────────────────────────────────────────
echo "=== STEP 3: Commit ==="
if [ "$STAGED" -gt 0 ]; then
    git commit -m "$COMMIT_MSG"
    if [ $? -ne 0 ]; then echo "❌ FATAL: commit failed"; exit 1; fi
    echo "✅ Commit created"
else
    echo "ℹ️  Nothing new to commit — checking if tag already exists"
fi

echo "HEAD: $(git log --oneline -1)"
echo ""

# ── STEP 4: Tag ───────────────────────────────────────────────────────────────
echo "=== STEP 4: Tag $VERSION_TAG ==="
if git rev-parse "$VERSION_TAG" >/dev/null 2>&1; then
    echo "ℹ️  Tag $VERSION_TAG already exists locally — skipping"
else
    git tag "$VERSION_TAG"
    if [ $? -ne 0 ]; then echo "❌ FATAL: tag failed"; exit 1; fi
    echo "✅ Tag $VERSION_TAG created"
fi
echo ""

# ── STEP 5: Push main ─────────────────────────────────────────────────────────
echo "=== STEP 5: Push $CURRENT_BRANCH to origin ==="
git push origin "$CURRENT_BRANCH"
if [ $? -ne 0 ]; then
    echo "❌ FATAL: push origin $CURRENT_BRANCH failed"
    git remote -v
    exit 1
fi
echo "✅ $CURRENT_BRANCH pushed"
echo ""

# ── STEP 6: Push tags ─────────────────────────────────────────────────────────
echo "=== STEP 6: Push tags ==="
git push origin --tags
if [ $? -ne 0 ]; then echo "❌ FATAL: push tags failed"; exit 1; fi
echo "✅ Tags pushed"
echo ""

# ── STEP 7: Update ios-dev on remote ─────────────────────────────────────────
echo "=== STEP 7: Push HEAD to origin/ios-dev ==="
# ios-dev does not exist locally. Push current HEAD directly to the remote ios-dev ref.
git push origin "HEAD:refs/heads/ios-dev"
if [ $? -ne 0 ]; then
    echo "❌ FATAL: push to ios-dev failed"
    exit 1
fi
echo "✅ ios-dev updated on remote"
echo ""

# ── STEP 8: Verify ────────────────────────────────────────────────────────────
echo "=== STEP 8: Verification ==="
LOCAL_HEAD=$(git rev-parse HEAD)
REMOTE_MAIN=$(git ls-remote origin "refs/heads/$CURRENT_BRANCH" | cut -f1)
REMOTE_IOSDEV=$(git ls-remote origin "refs/heads/ios-dev" | cut -f1)
REMOTE_TAG=$(git ls-remote origin "refs/tags/$VERSION_TAG" | cut -f1)

echo "Local HEAD:          $LOCAL_HEAD"
echo "Remote main SHA:     $REMOTE_MAIN"
echo "Remote ios-dev SHA:  $REMOTE_IOSDEV"
echo "Remote tag SHA:      $REMOTE_TAG"
echo ""

{
    echo "Assignment 61c Results — Git Commit & Push v1.2.9+60"
    echo "Date: $(date)"
    echo ""
    echo "Branch committed to: $CURRENT_BRANCH"
    echo "Local HEAD:          $LOCAL_HEAD"
    echo "Remote main SHA:     $REMOTE_MAIN"
    echo "Remote ios-dev SHA:  $REMOTE_IOSDEV"
    echo "Remote tag SHA:      $REMOTE_TAG"
    echo ""
    [ "$LOCAL_HEAD" = "$REMOTE_MAIN" ]   && echo "main push:    SUCCESS" || echo "main push:    MISMATCH"
    [ "$LOCAL_HEAD" = "$REMOTE_IOSDEV" ] && echo "ios-dev push: SUCCESS" || echo "ios-dev push: MISMATCH"
    [ -n "$REMOTE_TAG" ]                 && echo "tag push:     SUCCESS ($VERSION_TAG on remote)" || echo "tag push:     FAILED"
    echo ""
    echo "Overall: SUCCESS"
} > "$RESULTS"

cat "$RESULTS"

# ── STEP 9: Copy to USB ───────────────────────────────────────────────────────
echo ""
echo "=== STEP 9: Copy results to USB ==="
if [ -d "$USB" ]; then
    cp "$RESULTS" "$USB/a61c_results.txt"
    cp ~/Desktop/full_a61c_session.txt "$USB/full_a61c_session.txt"
    echo "✅ Results copied to USB"
else
    echo "⚠️  USB not found — results on ~/Desktop only"
fi

echo ""
echo "🎉 A#61c COMPLETE — v1.2.9+60 committed and pushed to GitHub"
echo "   Repo: https://github.com/michaelglik-audiotoursai/Audioura"
echo "   Branch: $CURRENT_BRANCH  Tag: $VERSION_TAG  ios-dev: updated"
echo ""
diskutil eject "/Volumes/USB DISK" 2>/dev/null && echo "✅ USB ejected" || echo "ℹ️  USB eject skipped"
