#!/usr/bin/env bash
# Release tagging for Audioura deploys — sourced by the deploy scripts.
#
# WHY THIS EXISTS
# The version a tester sees must let you reconstitute exactly what was deployed.
# A commit count cannot do that: on 2026-09-01, `main` (count 75) contained the
# reversed-coordinate fix while `storied` (count 2126) did not, because the fix
# had been PORTED rather than merged. A higher number did not mean "has
# everything the lower one had". Only a tag pinned to a commit answers it:
#
#     git checkout v2t357        # exactly what shipped
#
# THE SCHEME  (Michael, 2026-09-01)
#
#     v<line>t<seq>       e.g.  v2t357
#
#   <line>  Release-line IDENTITY, permanent. beta=1, storied=2, subscribed=3.
#           It is NOT the Stable/Preview slot. When Storied is promoted it still
#           displays v2t..., which is the point: the number says where the build
#           came from, and it does not change under promotion.
#           It also guarantees ordering arithmetically -- a v3t... Preview is
#           always above any v2t... Stable, no matter how many fixes Stable
#           takes. Commit counts could not promise that.
#
#   <seq>   Sequential per line, computed from existing tags. Not a date: dates
#           look informative, collide on two deploys in one day, and do not
#           answer the question anyone actually asks ("is this newer than what I
#           had?").
#
# WHY THE SCRIPT DOES IT AND NOT A HUMAN
# Tagging is a manual step at the END of a deploy, which is when attention is
# lowest. The evidence is in this repo: 15 tags in FOUR incompatible formats
# (1.2.9.61, v1.2.8.102, v1.2.9+65, beta-2.1.1+18) and no deploy script that
# ever created one. Every existing tag was hand-made and they drifted.

release_line_for_branch() {
    # Map a branch to its permanent release-line ordinal.
    case "$1" in
        main|beta)        echo 1 ;;
        storied)          echo 2 ;;
        subscribed)       echo 3 ;;
        *)                echo "" ;;   # unknown -> caller decides
    esac
}

# Refuse to tag a tree whose IMAGE CONTENT is dirty.
#
# Deliberately narrow: this repo's working tree is shared with Kiro, so docs and
# build artifacts are routinely modified by another agent. Refusing on any dirt
# would block every deploy for reasons that cannot affect the image. Only files
# that Dockerfile.cloudrun actually copies matter.
#
# A tag on a dirty tree is a lie, and it destroys the reconstitution guarantee
# this whole scheme exists to provide.
assert_image_content_clean() {
    local dirty
    dirty=$(git status --porcelain -- '*.py' 'Dockerfile*' 'requirements*.txt' 2>/dev/null)
    if [ -n "$dirty" ]; then
        printf '\n\033[31mREFUSING TO TAG: image content is uncommitted\033[0m\n' >&2
        printf '%s\n' "$dirty" | sed 's/^/    /' >&2
        printf '\n  The tag must describe exactly what shipped. Commit or stash these\n' >&2
        printf '  first. Unrelated dirt (docs, .apk) is ignored on purpose -- the tree\n' >&2
        printf '  is shared with Kiro.\n\n' >&2
        return 1
    fi
    return 0
}

# next_release_tag <line>  ->  prints e.g. v2t358
next_release_tag() {
    local line="$1" highest
    git fetch --tags --quiet origin 2>/dev/null || true
    highest=$(git tag --list "v${line}t*" \
              | sed "s/^v${line}t//" \
              | grep -E '^[0-9]+$' \
              | sort -n | tail -1)
    [ -z "$highest" ] && highest=0
    echo "v${line}t$((highest + 1))"
}

# create_and_push_release_tag <tag> <commit> <service> <image>
create_and_push_release_tag() {
    local tag="$1" commit="$2" service="$3" image="$4"
    git tag -a "$tag" "$commit" -m "$(printf '%s\n\n%s\n%s\n%s\n%s\n' \
        "Release $tag" \
        "service : $service" \
        "image   : $image" \
        "commit  : $commit" \
        "branch  : $(git rev-parse --abbrev-ref HEAD)")" || return 1
    # Push it. An unpushed tag cannot reconstitute anything from another machine,
    # which is most of the point.
    git push --quiet origin "$tag" || {
        printf '\033[31m  tag %s created locally but PUSH FAILED — it is not durable\033[0m\n' "$tag" >&2
        return 1
    }
    return 0
}
