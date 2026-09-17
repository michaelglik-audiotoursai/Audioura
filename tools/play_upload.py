#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Upload a signed Android App Bundle to Google Play closed testing.

Design (see SUBMISSION_GCS-PLAY1.md and the task brief):

* No downloadable service-account key. Auth is short-lived impersonation of
  ``play-publisher@audiotours-migration.iam.gserviceaccount.com``.
* Dry run is the DEFAULT. ``--apply`` is required to commit anything.
* Track is resolved at runtime from ``edits.tracks.list`` (never hard-coded).
* Every check fails fast with a clear message.

This module is import-safe and side-effect-free at import time so the offline
test-suite can exercise the logic with the Play API mocked. The real Google
client is only constructed inside ``build_service`` / ``get_access_token``.
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field

# Local, dependency-free AAB reader.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from aab_manifest import read_aab_version, AabManifestError  # noqa: E402

PACKAGE_NAME = "com.audioura.audiotours"
SERVICE_ACCOUNT = "play-publisher@audiotours-migration.iam.gserviceaccount.com"
ANDROIDPUBLISHER_SCOPE = "https://www.googleapis.com/auth/androidpublisher"
EXPECTED_SIGNER_CN = "CN=Mikhail Glik"
EXPECTED_SIGNER_O = "O=Audioura LLC"
DEBUG_SIGNER = "CN=Android Debug"


class UploadError(Exception):
    """A fail-fast error with a human-readable message."""


# ---------------------------------------------------------------------------
# Result plumbing so callers/tests can inspect what happened.
# ---------------------------------------------------------------------------

@dataclass
class UploadPlan:
    aab_path: str
    version_code: int
    version_name: str
    release_name: str
    notes: str
    track: str
    apply: bool
    build_numbers_path: str = ""
    committed: bool = False
    edit_id: str | None = None
    console_url: str | None = None
    steps: list[str] = field(default_factory=list)

    def log(self, msg: str) -> None:
        self.steps.append(msg)
        print(msg)


# ---------------------------------------------------------------------------
# pubspec / version helpers
# ---------------------------------------------------------------------------

_PUBSPEC_VERSION_RE = re.compile(r"^version:\s*([^\s#]+)", re.MULTILINE)


def read_pubspec_version(pubspec_path: str) -> tuple[str, int]:
    """Return (versionName, versionCode) from pubspec.yaml's ``version:`` line.

    Flutter's ``version: 2.3.2+26`` means versionName 2.3.2 / versionCode 26.
    """
    try:
        with open(pubspec_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError as exc:
        raise UploadError(f"cannot read pubspec.yaml at {pubspec_path}: {exc}") from exc
    m = _PUBSPEC_VERSION_RE.search(text)
    if not m:
        raise UploadError(f"no 'version:' line found in {pubspec_path}")
    raw = m.group(1)
    if "+" not in raw:
        raise UploadError(f"pubspec version '{raw}' has no +buildNumber")
    name, _, code = raw.partition("+")
    try:
        return name, int(code)
    except ValueError as exc:
        raise UploadError(f"pubspec build number '{code}' is not an integer") from exc


# ---------------------------------------------------------------------------
# Check 1 + 2: AAB exists, version matches pubspec, signer is the real key
# ---------------------------------------------------------------------------

def check_aab_exists(aab_path: str) -> None:
    if not os.path.isfile(aab_path):
        raise UploadError(
            f"AAB not found: {aab_path}\n"
            "Build it first on Ubuntu (bash build_flutter_clean.sh) and make sure "
            "the shared folder is mounted so audioura-release.aab is visible here."
        )


def check_version_matches_pubspec(aab_path: str, pubspec_path: str) -> tuple[int, str]:
    """Read versionCode/Name from the AAB itself and compare to pubspec."""
    try:
        aab = read_aab_version(aab_path)
    except AabManifestError as exc:
        raise UploadError(f"could not read version from AAB: {exc}") from exc
    ps_name, ps_code = read_pubspec_version(pubspec_path)
    if aab.version_code != ps_code or aab.version_name != ps_name:
        raise UploadError(
            "AAB/pubspec version mismatch — refusing.\n"
            f"  AAB:     {aab.version_name}+{aab.version_code}\n"
            f"  pubspec: {ps_name}+{ps_code}\n"
            "Rebuild from the current tree so the bundle matches pubspec.yaml."
        )
    return aab.version_code, aab.version_name


def _run_keytool(aab_path: str, keytool: str) -> str:
    try:
        proc = subprocess.run(
            [keytool, "-printcert", "-jarfile", aab_path],
            capture_output=True, text=True, encoding="utf-8", timeout=120,
        )
    except FileNotFoundError as exc:
        raise UploadError(f"keytool not found at {keytool}") from exc
    if proc.returncode != 0:
        raise UploadError(
            f"keytool -printcert failed:\n{proc.stderr.strip() or proc.stdout.strip()}"
        )
    return proc.stdout


def check_signer(aab_path: str, keytool: str) -> str:
    """Fail unless the AAB is signed with CN=Mikhail Glik, O=Audioura LLC.

    A debug signature (CN=Android Debug) must be refused.
    """
    out = _run_keytool(aab_path, keytool)
    if DEBUG_SIGNER in out:
        raise UploadError(
            "AAB is signed with the DEBUG key (CN=Android Debug) — refusing.\n"
            "key.properties was not picked up during the build."
        )
    if EXPECTED_SIGNER_CN not in out or EXPECTED_SIGNER_O not in out:
        owner = next((ln.strip() for ln in out.splitlines() if "Owner:" in ln), "(no Owner line)")
        raise UploadError(
            "AAB signer is not the Audioura upload key — refusing.\n"
            f"  expected: {EXPECTED_SIGNER_CN}, {EXPECTED_SIGNER_O}\n"
            f"  found:    {owner}"
        )
    return out


# ---------------------------------------------------------------------------
# Check 3: version number not already consumed
# ---------------------------------------------------------------------------

def build_numbers_has_android_upload(build_numbers_path: str, version_code: int) -> bool:
    """True if BUILD_NUMBERS.md already records this Android build as uploaded.

    Rule (case-insensitive, ``**`` markdown stripped): a row counts as uploaded
    only when its outcome says it actually reached Play — it contains
    ``"uploaded to play"`` or ``"shipped to play"`` — AND it does NOT contain a
    negation, ``"not uploaded"`` or ``"never shipped"``. A row that merely
    contains the substring ``"upload"`` (e.g. "not uploaded to Play") is NOT a
    duplicate: the number was never consumed on Play.
    """
    try:
        with open(build_numbers_path, "r", encoding="utf-8") as fh:
            text = fh.read()
    except OSError:
        return False
    for line in text.splitlines():
        if not line.strip().startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 5:
            continue
        build = cells[0]
        platform = cells[1].lower()
        # Ignore markdown emphasis markers so "**uploaded to Play**" matches.
        outcome = cells[4].lower().replace("*", "")
        if build != str(version_code) or platform != "android":
            continue
        reached_play = ("uploaded to play" in outcome
                        or "shipped to play" in outcome)
        negated = ("not uploaded" in outcome
                   or "never shipped" in outcome)
        if reached_play and not negated:
            return True
    return False


def collect_all_track_version_codes(service, package_name: str, edit_id: str) -> set[int]:
    """Union of versionCodes referenced by releases across every track."""
    tracks_resp = service.edits().tracks().list(
        packageName=package_name, editId=edit_id
    ).execute()
    codes: set[int] = set()
    for track in tracks_resp.get("tracks", []):
        for release in track.get("releases", []):
            for vc in release.get("versionCodes", []) or []:
                try:
                    codes.add(int(vc))
                except (TypeError, ValueError):
                    pass
    return codes


def check_version_not_used(service, edit_id: str, version_code: int,
                           build_numbers_path: str) -> None:
    if build_numbers_has_android_upload(build_numbers_path, version_code):
        raise UploadError(
            f"BUILD_NUMBERS.md already records Android build {version_code} as "
            "uploaded to Play — refusing to reuse a consumed number."
        )
    used = collect_all_track_version_codes(service, PACKAGE_NAME, edit_id)
    if version_code in used:
        raise UploadError(
            f"versionCode {version_code} is already present on a Play track "
            f"(existing: {sorted(used)}) — refusing."
        )


# ---------------------------------------------------------------------------
# Track resolution
# ---------------------------------------------------------------------------

# Closed testing tracks are the non-production, non-open, non-internal ones.
_RESERVED_TRACKS = {"production", "beta", "internal"}


def resolve_closed_track(service, edit_id: str, requested: str | None) -> str:
    resp = service.edits().tracks().list(
        packageName=PACKAGE_NAME, editId=edit_id
    ).execute()
    track_names = [t.get("track") for t in resp.get("tracks", []) if t.get("track")]
    if requested:
        if requested not in track_names:
            raise UploadError(
                f"requested track '{requested}' not found. Available: {track_names}"
            )
        return requested
    closed = [t for t in track_names if t not in _RESERVED_TRACKS]
    if not closed:
        raise UploadError(
            f"no closed testing track found among {track_names}; pass --track <name>"
        )
    if len(closed) > 1:
        raise UploadError(
            f"multiple closed tracks {closed}; disambiguate with --track <name>"
        )
    return closed[0]


# ---------------------------------------------------------------------------
# Auth (real path — never called by offline tests)
# ---------------------------------------------------------------------------

def _gcloud_exe() -> str:
    """Resolve the gcloud launcher. On Windows it is gcloud.cmd, which
    subprocess cannot exec without the extension, so look it up explicitly."""
    import shutil
    for name in ("gcloud", "gcloud.cmd", "gcloud.CMD"):
        found = shutil.which(name)
        if found:
            return found
    return "gcloud"


def get_access_token() -> str:  # pragma: no cover - needs gcloud + network
    """Impersonate the publisher SA and return a scoped access token."""
    cmd = [
        _gcloud_exe(), "auth", "print-access-token",
        f"--impersonate-service-account={SERVICE_ACCOUNT}",
        f"--scopes={ANDROIDPUBLISHER_SCOPE}",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8")
    if proc.returncode != 0:
        raise UploadError(
            "failed to mint an impersonated access token:\n" + proc.stderr.strip()
        )
    token = proc.stdout.strip()
    if not token:
        raise UploadError("gcloud returned an empty access token")
    return token


def build_service(token: str):  # pragma: no cover - needs google client + network
    """Build the androidpublisher client from an OAuth2 access token."""
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build
    except ImportError as exc:
        raise UploadError(
            "google-api-python-client is not installed. Create the venv:\n"
            "  python -m venv tools/.venv-play\n"
            "  tools/.venv-play/Scripts/pip install -r tools/play_upload_requirements.txt"
        ) from exc
    creds = Credentials(token=token)
    return build("androidpublisher", "v3", credentials=creds, cache_discovery=False)


# ---------------------------------------------------------------------------
# The edit workflow (works against a real or mocked ``service``)
# ---------------------------------------------------------------------------

def _console_url(track: str) -> str:
    return (
        "https://play.google.com/console/u/0/developers/app/"
        f"{PACKAGE_NAME}/tracks/{track}"
    )


def _translate_api_error(exc: Exception) -> UploadError:
    """Turn a googleapiclient HttpError into a clear fail-fast message."""
    status = getattr(getattr(exc, "resp", None), "status", None)
    try:
        status = int(status)
    except (TypeError, ValueError):
        status = None
    if status == 403:
        return UploadError(
            "Play API returned 403 (The caller does not have permission).\n"
            "This is expected until Michael invites the service account in Play "
            "Console → Users and permissions → Invite new user →\n"
            f"  {SERVICE_ACCOUNT}\n"
            "with app Audioura, 'Release to testing tracks' + 'View app information'.\n"
            "See PLAY_UPLOAD.md → One-time setup. (Auth/plumbing is working — the "
            "token was minted and the API was reached.)"
        )
    return UploadError(f"Play API call failed: {exc}")


def run_upload(service, plan: UploadPlan) -> UploadPlan:
    """Execute the edit lifecycle. Honors plan.apply for dry-run vs commit."""
    try:
        edit = service.edits().insert(packageName=PACKAGE_NAME, body={}).execute()
    except UploadError:
        raise
    except Exception as exc:  # noqa: BLE001 - translate API/transport errors
        raise _translate_api_error(exc) from exc
    edit_id = edit["id"]
    plan.edit_id = edit_id
    plan.log(f"edits.insert -> edit {edit_id}")

    try:
        # Resolve track and guard the number BEFORE any upload.
        track = resolve_closed_track(service, edit_id, plan.track or None)
        plan.track = track
        plan.log(f"resolved closed track: {track}")

        check_version_not_used(service, edit_id, plan.version_code, plan.build_numbers_path)
        plan.log(f"versionCode {plan.version_code} is free on all tracks")

        if not plan.apply:
            # Dry run: do everything we safely can, then delete the edit.
            plan.log("DRY RUN: skipping bundles.upload")
            try:
                service.edits().validate(
                    packageName=PACKAGE_NAME, editId=edit_id
                ).execute()
                plan.log("edits.validate ok")
            except Exception as exc:  # noqa: BLE001 - validate is best-effort in dry run
                plan.log(f"edits.validate skipped/failed (non-fatal in dry run): {exc}")
            service.edits().delete(packageName=PACKAGE_NAME, editId=edit_id).execute()
            plan.log("edits.delete (dry run committed nothing)")
            return plan

        # --apply path.
        with open(plan.aab_path, "rb") as _f:  # ensure readable before upload
            _f.read(1)
        bundle = service.edits().bundles().upload(
            packageName=PACKAGE_NAME, editId=edit_id, media_body=plan.aab_path
        ).execute()
        uploaded_code = int(bundle.get("versionCode", plan.version_code))
        plan.log(f"bundles.upload -> versionCode {uploaded_code}")
        if uploaded_code != plan.version_code:
            raise UploadError(
                f"uploaded versionCode {uploaded_code} != expected {plan.version_code}"
            )

        service.edits().tracks().update(
            packageName=PACKAGE_NAME, editId=edit_id, track=track,
            body={
                "track": track,
                "releases": [
                    {
                        "name": plan.release_name,
                        "status": "completed",
                        "versionCodes": [str(plan.version_code)],
                        "releaseNotes": [
                            {"language": "en-US", "text": plan.notes}
                        ],
                    }
                ],
            },
        ).execute()
        plan.log(f"tracks.update {track} release '{plan.release_name}' (completed)")

        commit = service.edits().commit(
            packageName=PACKAGE_NAME, editId=edit_id
        ).execute()
        plan.committed = True
        plan.edit_id = commit.get("id", edit_id)
        plan.console_url = _console_url(track)
        plan.log(f"edits.commit -> {plan.edit_id}")
        plan.log(f"Play Console: {plan.console_url}")
        return plan
    except UploadError:
        # Abandon the edit so a failed run leaves nothing half-open.
        _safe_delete(service, edit_id, plan)
        raise
    except Exception as exc:  # noqa: BLE001 - translate + clean up
        _safe_delete(service, edit_id, plan)
        raise _translate_api_error(exc) from exc


def _safe_delete(service, edit_id: str, plan: UploadPlan) -> None:
    if plan.committed:
        return
    try:
        service.edits().delete(packageName=PACKAGE_NAME, editId=edit_id).execute()
        plan.log(f"edits.delete (cleanup of {edit_id})")
    except Exception:  # noqa: BLE001 - cleanup is best effort
        pass


# ---------------------------------------------------------------------------
# Ledger
# ---------------------------------------------------------------------------

def append_build_numbers_row(build_numbers_path: str, version_code: int,
                             version_name: str, commit_short: str,
                             edit_id: str, date_str: str) -> str:
    """Insert the Android ledger row INSIDE the ``## Ledger`` table.

    The row is placed:
      * directly BEFORE the ``NEXT`` placeholder row if that section has one, or
      * after the last table row of the ``## Ledger`` section otherwise.

    Existing rows (including the ``NEXT`` placeholder) are never modified;
    bumping ``NEXT`` is the operator's choice. The file's existing line endings
    are preserved and it is written back as UTF-8. Raises ``UploadError`` if the
    ``## Ledger`` table cannot be located — we never append blindly.
    """
    with open(build_numbers_path, "r", encoding="utf-8", newline="") as fh:
        raw = fh.read()

    # Preserve the file's dominant line ending.
    newline = "\r\n" if "\r\n" in raw else "\n"
    # Split on any newline flavour but keep the content; we re-join with `newline`.
    lines = raw.splitlines()
    trailing_newline = raw.endswith(("\n", "\r"))

    row = (
        f"| {version_code} | Android | {version_name} | `{commit_short}` | "
        f"**uploaded to Play closed testing** (edit `{edit_id}`) | {date_str} |"
    )

    def is_table_row(s: str) -> bool:
        return s.strip().startswith("|")

    # Find the `## Ledger` heading.
    ledger_idx = None
    for i, ln in enumerate(lines):
        if ln.strip().lower().startswith("## ledger"):
            ledger_idx = i
            break
    if ledger_idx is None:
        raise UploadError(
            f"Could not find a '## Ledger' section in {build_numbers_path} — "
            "refusing to append the ledger row blindly."
        )

    # The section ends at the next '## ' heading (or end of file).
    section_end = len(lines)
    for i in range(ledger_idx + 1, len(lines)):
        if lines[i].strip().startswith("## "):
            section_end = i
            break

    # Collect the table-row line indices within this section.
    table_rows = [i for i in range(ledger_idx + 1, section_end)
                  if is_table_row(lines[i])]
    if not table_rows:
        raise UploadError(
            f"The '## Ledger' section in {build_numbers_path} has no table — "
            "refusing to append the ledger row blindly."
        )

    # Locate the NEXT placeholder row (a table row whose outcome cell, with
    # markdown emphasis stripped, is exactly "NEXT").
    insert_at = None
    for i in table_rows:
        cells = [c.strip() for c in lines[i].strip().strip("|").split("|")]
        if len(cells) >= 5 and cells[4].replace("*", "").strip().upper() == "NEXT":
            insert_at = i  # insert BEFORE the NEXT placeholder
            break
    if insert_at is None:
        insert_at = table_rows[-1] + 1  # after the last table row of the section

    lines.insert(insert_at, row)

    out = newline.join(lines)
    if trailing_newline:
        out += newline
    with open(build_numbers_path, "w", encoding="utf-8", newline="") as fh:
        fh.write(out)
    return row


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _git_short_head(repo_root: str) -> str:  # pragma: no cover - needs git
    try:
        proc = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=repo_root, capture_output=True, text=True, encoding="utf-8",
        )
        if proc.returncode == 0:
            return proc.stdout.strip()
    except FileNotFoundError:
        pass
    return "unknown"


def _resolve_notes(args) -> str:
    if args.notes_file:
        try:
            with open(args.notes_file, "r", encoding="utf-8") as fh:
                return fh.read().strip()
        except OSError as exc:
            raise UploadError(f"cannot read notes file {args.notes_file}: {exc}") from exc
    if args.notes is not None:
        return args.notes.strip()
    return ""


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="upload_play",
        description="Upload a signed AAB to Google Play closed testing (dry run by default).",
    )
    p.add_argument("--apply", action="store_true",
                   help="Actually commit. Without this, runs a dry run that commits nothing.")
    p.add_argument("--notes", help="Release notes text (en-US).")
    p.add_argument("--notes-file", help="Path to a file with release notes (en-US).")
    p.add_argument("--aab", default=None, help="Path to the .aab (default: <repo>/audioura-release.aab).")
    p.add_argument("--track", default=None, help="Closed track name (auto-resolved if omitted).")
    p.add_argument("--keytool", default=os.environ.get("KEYTOOL", "keytool"),
                   help="Path to keytool.")
    p.add_argument("--repo-root", default=None, help="Repo root (default: parent of tools/).")
    return p.parse_args(argv)


def main(argv=None) -> int:  # pragma: no cover - exercised via upload_play.sh
    args = parse_args(argv)
    repo_root = args.repo_root or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    aab_path = args.aab or os.path.join(repo_root, "audioura-release.aab")
    pubspec_path = os.path.join(repo_root, "audio_tour_app", "pubspec.yaml")
    build_numbers_path = os.path.join(repo_root, "BUILD_NUMBERS.md")

    try:
        notes = _resolve_notes(args)
        if args.apply and not notes:
            raise UploadError("--apply requires release notes (--notes or --notes-file)")

        # Check 1: AAB exists + version equals pubspec (read from the AAB itself).
        check_aab_exists(aab_path)
        version_code, version_name = check_version_matches_pubspec(aab_path, pubspec_path)
        print(f"[ok] AAB version {version_name}+{version_code} matches pubspec")

        # Check 2: signer is the real upload key, not debug.
        check_signer(aab_path, args.keytool)
        print(f"[ok] signer is {EXPECTED_SIGNER_CN}, {EXPECTED_SIGNER_O}")

        release_name = f"{version_name} ({version_code})"
        plan = UploadPlan(
            aab_path=aab_path, version_code=version_code, version_name=version_name,
            release_name=release_name, notes=notes, track=args.track or "",
            apply=args.apply, build_numbers_path=build_numbers_path,
        )

        # Auth + client (real path only).
        token = get_access_token()
        print(f"[ok] impersonated access token acquired (length {len(token)})")
        service = build_service(token)

        run_upload(service, plan)

        if plan.committed:
            commit_short = _git_short_head(repo_root)
            from datetime import date
            row = append_build_numbers_row(
                build_numbers_path, version_code, version_name,
                commit_short, plan.edit_id or "?", date.today().isoformat(),
            )
            print("\n[ledger] appended to BUILD_NUMBERS.md:")
            print("  " + row)
            print("\nCommit the ledger yourself (this script never git-commits):")
            print(f'  git add BUILD_NUMBERS.md && git commit -m '
                  f'"chore(play): record Android build {version_code} uploaded to closed testing"')
        else:
            print("\nDry run complete — nothing was committed to Play.")
            print("Re-run with --apply (and --notes) to publish.")
        return 0
    except UploadError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
