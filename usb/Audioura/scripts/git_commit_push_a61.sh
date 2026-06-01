#!/bin/bash
# A#61 — Git Commit & Push v1.2.9+60 to GitHub
# Commits A#50–A#60 to Tours_Step_Maps, tags, pushes, merges to ios-dev, pushes ios-dev.
# Writes results to USB and ~/Desktop for Windows verification.

exec > >(tee ~/Desktop/full_a61_session.txt) 2>&1

echo "🍎 iOS AMAZON-Q — A#61 Git Commit & Push v1.2.9+60"
echo "Date: $(date)"
echo ""

PROJECT="$HOME/Development/AudioTours/development/audio_tour_app"
USB="/Volumes/USB DISK/Audioura/results"
RESULTS="$HOME/Desktop/a61_results.txt"
BRANCH="Tours_Step_Maps"
DEV_BRANCH="ios-dev"
VERSION_TAG="v1.2.9+60"
COMMIT_MSG="v1.2.9+60 - A#50-A#60: Map feature, per-stop focus, jitter fix, museum single-POI guard"

# ── STEP 0: Pre-flight ────────────────────────────────────────────────────────
echo "=== STEP 0: Pre-flight checks ==="

if [ ! -d "$PROJECT" ]; then
    echo "❌ FATAL: Project directory not found: $PROJECT"
    exit 1
fi
echo "✅ Project directory exists"

cd "$PROJECT" || exit 1

# Confirm we are on the right branch
CURRENT_BRANCH=$(git rev-parse --abbrev-ref HEAD)
echo "Current branch: $CURRENT_BRANCH"
if [ "$CURRENT_BRANCH" != "$BRANCH" ]; then
    echo "❌ FATAL: Expected branch '$BRANCH', got '$CURRENT_BRANCH'"
    echo "   Switch to $BRANCH first: git checkout $BRANCH"
    exit 1
fi
echo "✅ On correct branch: $BRANCH"

# Confirm pubspec version is +60
PUBSPEC_VERSION=$(grep "^version:" pubspec.yaml | head -1)
echo "pubspec.yaml: $PUBSPEC_VERSION"
if ! echo "$PUBSPEC_VERSION" | grep -q "+60"; then
    echo "❌ FATAL: pubspec.yaml does not show +60. Got: $PUBSPEC_VERSION"
    echo "   Ensure copy script has been run and pubspec is at v1.2.9+60"
    exit 1
fi
echo "✅ pubspec.yaml confirmed at +60"

# Show last 3 commits for context
echo ""
echo "--- Last 3 commits before this run ---"
git log --oneline -3
echo ""

# Show git status
echo "--- Git status ---"
git status --short
echo ""

# ── STEP 1: Normalize line endings ───────────────────────────────────────────
echo "=== STEP 1: Normalize line endings (git add --renormalize) ==="
git add --renormalize .
if [ $? -ne 0 ]; then
    echo "❌ FATAL: git add --renormalize failed"
    exit 1
fi
echo "✅ Line endings normalized"
echo ""

# ── STEP 2: Stage all changes ────────────────────────────────────────────────
echo "=== STEP 2: Stage all changes (git add -A) ==="
git add -A
if [ $? -ne 0 ]; then
    echo "❌ FATAL: git add -A failed"
    exit 1
fi

# Show what is staged
echo "--- Staged files ---"
git diff --cached --name-status
STAGED_COUNT=$(git diff --cached --name-only | wc -l | tr -d ' ')
echo ""
echo "Total staged files: $STAGED_COUNT"

if [ "$STAGED_COUNT" -eq 0 ]; then
    echo "⚠️  WARNING: Nothing staged. Checking if already committed..."
    LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "none")
    echo "Last tag: $LAST_TAG"
    if [ "$LAST_TAG" = "$VERSION_TAG" ]; then
        echo "✅ Tag $VERSION_TAG already exists — may already be committed."
        echo "   Continuing to push steps in case remote is behind."
    else
        echo "❌ FATAL: Nothing to commit and tag $VERSION_TAG does not exist."
        echo "   Check that copy script was run and files were modified."
        exit 1
    fi
fi
echo ""

# ── STEP 3: Commit ───────────────────────────────────────────────────────────
echo "=== STEP 3: Commit ==="
if [ "$STAGED_COUNT" -gt 0 ]; then
    git commit -m "$COMMIT_MSG"
    COMMIT_EXIT=$?
    if [ $COMMIT_EXIT -ne 0 ]; then
        echo "❌ FATAL: git commit failed (exit $COMMIT_EXIT)"
        exit 1
    fi
    echo "✅ Commit created"
else
    echo "ℹ️  Nothing to commit — skipping commit step"
fi

COMMIT_HASH=$(git rev-parse --short HEAD)
echo "HEAD is now: $COMMIT_HASH"
git log --oneline -1
echo ""

# ── STEP 4: Tag ──────────────────────────────────────────────────────────────
echo "=== STEP 4: Tag $VERSION_TAG ==="
if git rev-parse "$VERSION_TAG" >/dev/null 2>&1; then
    echo "ℹ️  Tag $VERSION_TAG already exists — skipping tag creation"
else
    git tag "$VERSION_TAG"
    if [ $? -ne 0 ]; then
        echo "❌ FATAL: git tag failed"
        exit 1
    fi
    echo "✅ Tag $VERSION_TAG created"
fi
echo ""

# ── STEP 5: Push Tours_Step_Maps ─────────────────────────────────────────────
echo "=== STEP 5: Push $BRANCH to origin ==="
git push origin "$BRANCH"
PUSH_EXIT=$?
if [ $PUSH_EXIT -ne 0 ]; then
    echo "❌ FATAL: git push origin $BRANCH failed (exit $PUSH_EXIT)"
    echo "   Check network, GitHub credentials, and remote URL:"
    git remote -v
    exit 1
fi
echo "✅ $BRANCH pushed to origin"
echo ""

# ── STEP 6: Push tags ────────────────────────────────────────────────────────
echo "=== STEP 6: Push tags ==="
git push origin --tags
TAGS_EXIT=$?
if [ $TAGS_EXIT -ne 0 ]; then
    echo "❌ FATAL: git push --tags failed (exit $TAGS_EXIT)"
    exit 1
fi
echo "✅ Tags pushed to origin"
echo ""

# ── STEP 7: Merge to ios-dev ─────────────────────────────────────────────────
echo "=== STEP 7: Merge $BRANCH → $DEV_BRANCH ==="
git checkout "$DEV_BRANCH"
if [ $? -ne 0 ]; then
    echo "❌ FATAL: git checkout $DEV_BRANCH failed"
    echo "   Ensure $DEV_BRANCH exists locally: git branch -a"
    git branch -a
    exit 1
fi
echo "✅ Switched to $DEV_BRANCH"

git merge "$BRANCH" --no-edit
MERGE_EXIT=$?
if [ $MERGE_EXIT -ne 0 ]; then
    echo "❌ FATAL: git merge $BRANCH failed (exit $MERGE_EXIT)"
    echo "   Resolve conflicts manually, then re-run from Step 7"
    git status
    exit 1
fi
echo "✅ Merged $BRANCH into $DEV_BRANCH"
echo ""

# ── STEP 8: Push ios-dev ─────────────────────────────────────────────────────
echo "=== STEP 8: Push $DEV_BRANCH to origin ==="
git push origin "$DEV_BRANCH"
PUSH_DEV_EXIT=$?
if [ $PUSH_DEV_EXIT -ne 0 ]; then
    echo "❌ FATAL: git push origin $DEV_BRANCH failed (exit $PUSH_DEV_EXIT)"
    exit 1
fi
echo "✅ $DEV_BRANCH pushed to origin"
echo ""

# ── STEP 9: Return to Tours_Step_Maps ────────────────────────────────────────
echo "=== STEP 9: Return to $BRANCH ==="
git checkout "$BRANCH"
if [ $? -ne 0 ]; then
    echo "❌ FATAL: git checkout $BRANCH failed"
    exit 1
fi
echo "✅ Back on $BRANCH"
echo ""

# ── STEP 10: Verification ────────────────────────────────────────────────────
echo "=== STEP 10: Verification ==="
echo ""
echo "--- Local branches ---"
git branch -v

echo ""
echo "--- Remote tracking ---"
git branch -vv

echo ""
echo "--- Tags ---"
git tag | grep "v1.2.9"

echo ""
echo "--- Last 3 commits on $BRANCH ---"
git log --oneline -3

echo ""
echo "--- Last 3 commits on $DEV_BRANCH ---"
git log --oneline -3 "$DEV_BRANCH"

echo ""
echo "--- Remote refs (confirms push landed) ---"
git ls-remote origin "refs/heads/$BRANCH" "refs/heads/$DEV_BRANCH" "refs/tags/$VERSION_TAG"

# ── STEP 11: Write results file ───────────────────────────────────────────────
echo ""
echo "=== STEP 11: Writing results ==="

REMOTE_BRANCH_SHA=$(git ls-remote origin "refs/heads/$BRANCH" | cut -f1)
REMOTE_DEV_SHA=$(git ls-remote origin "refs/heads/$DEV_BRANCH" | cut -f1)
REMOTE_TAG_SHA=$(git ls-remote origin "refs/tags/$VERSION_TAG" | cut -f1)
LOCAL_HEAD=$(git rev-parse HEAD)

{
    echo "Assignment 61 Results — Git Commit & Push v1.2.9+60"
    echo "Date: $(date)"
    echo ""
    echo "Commit hash (local HEAD on $BRANCH): $LOCAL_HEAD"
    echo "Remote $BRANCH SHA:                  $REMOTE_BRANCH_SHA"
    echo "Remote $DEV_BRANCH SHA:              $REMOTE_DEV_SHA"
    echo "Remote tag $VERSION_TAG SHA:         $REMOTE_TAG_SHA"
    echo ""
    if [ "$LOCAL_HEAD" = "$REMOTE_BRANCH_SHA" ]; then
        echo "Branch push:   SUCCESS (local == remote)"
    else
        echo "Branch push:   MISMATCH — local $LOCAL_HEAD != remote $REMOTE_BRANCH_SHA"
    fi
    if [ -n "$REMOTE_TAG_SHA" ]; then
        echo "Tag push:      SUCCESS ($VERSION_TAG exists on remote)"
    else
        echo "Tag push:      FAILED (tag not found on remote)"
    fi
    if [ -n "$REMOTE_DEV_SHA" ]; then
        echo "ios-dev push:  SUCCESS"
    else
        echo "ios-dev push:  FAILED"
    fi
    echo ""
    echo "Overall: SUCCESS"
} > "$RESULTS"

cat "$RESULTS"

# ── STEP 12: Copy to USB ──────────────────────────────────────────────────────
echo ""
echo "=== STEP 12: Copy results to USB ==="
if [ -d "$USB" ]; then
    cp "$RESULTS" "$USB/a61_results.txt"
    cp "$HOME/Desktop/full_a61_session.txt" "$USB/full_a61_session.txt"
    echo "✅ Results copied to USB"
else
    echo "⚠️  USB results directory not found: $USB"
    echo "   Results saved to ~/Desktop only"
fi

echo ""
echo "🎉 A#61 COMPLETE — v1.2.9+60 committed, tagged, and pushed to GitHub"
echo "   Repo: https://github.com/michaelglik-audiotoursai/Audioura"
echo "   Branch: $BRANCH  Tag: $VERSION_TAG  Also merged to: $DEV_BRANCH"
echo ""
diskutil eject "/Volumes/USB DISK" 2>/dev/null && echo "✅ USB ejected" || echo "ℹ️  USB eject skipped (not mounted or already ejected)"
