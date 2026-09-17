# -*- coding: utf-8 -*-
"""Offline tests for the Play upload tool. The Play API is fully mocked.

Run from the repo root:
    py -m pytest tools/tests -q

These tests are self-contained (no DB, no network, no gcloud). They cover
acceptance criterion #1:
  * happy path commits with the right release name, notes and track;
  * a duplicate versionCode is refused;
  * a debug signature is refused;
  * a pubspec mismatch is refused;
  * the dry run never calls edits.commit.
A test goes RED if the duplicate-versionCode check is removed
(test_removing_duplicate_check_would_be_caught documents/guards that).
"""
import io
import os
import sys
import zipfile

import pytest

TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if TOOLS not in sys.path:
    sys.path.insert(0, TOOLS)

import aab_manifest  # noqa: E402
import play_upload as pu  # noqa: E402


# ---------------------------------------------------------------------------
# Minimal protobuf encoder to build a synthetic AAB manifest for tests.
# ---------------------------------------------------------------------------

def _varint(n):
    out = bytearray()
    while True:
        b = n & 0x7F
        n >>= 7
        if n:
            out.append(b | 0x80)
        else:
            out.append(b)
            return bytes(out)


def _tag(field_no, wire):
    return _varint((field_no << 3) | wire)


def _ld(field_no, payload):  # length-delimited
    return _tag(field_no, 2) + _varint(len(payload)) + payload


def _vint(field_no, value):  # varint field
    return _tag(field_no, 0) + _varint(value)


def _str(field_no, s):
    return _ld(field_no, s.encode("utf-8"))


def build_manifest_proto(version_code, version_name):
    """Encode an aapt.pb.XmlNode with a <manifest> element carrying versions,
    matching the REAL bundletool schema (element name = field 3, attribute
    value = field 3 as a plain string)."""
    # XmlAttribute versionCode { name=2, value=3="26" }
    attr_code = _str(2, "versionCode") + _str(3, str(version_code))
    # XmlAttribute versionName { name=2, value=3="2.3.2" }
    attr_name = _str(2, "versionName") + _str(3, version_name)
    # A namespace decl at field 1 (so the parser must skip past it to name@3).
    ns_decl = _str(1, "android") + _str(2, "http://schemas.android.com/apk/res/android")
    # XmlElement { namespace_declaration=1, name=3 "manifest", attribute=4 (x2) }
    element = _ld(1, ns_decl) + _str(3, "manifest") + _ld(4, attr_code) + _ld(4, attr_name)
    # XmlNode { element = 1 }
    node = _ld(1, element)
    return node


def make_aab(tmp_path, version_code=26, version_name="2.3.2", name="audioura-release.aab"):
    aab_path = os.path.join(str(tmp_path), name)
    manifest = build_manifest_proto(version_code, version_name)
    with zipfile.ZipFile(aab_path, "w") as zf:
        zf.writestr("base/manifest/AndroidManifest.xml", manifest)
        zf.writestr("BundleConfig.pb", b"")
    return aab_path


def make_pubspec(tmp_path, version="2.3.2+26"):
    d = os.path.join(str(tmp_path), "audio_tour_app")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "pubspec.yaml")
    with open(p, "w", encoding="utf-8") as fh:
        fh.write("name: audio_tour_app\n")
        fh.write(f"version: {version}\n")
        fh.write("environment:\n  sdk: '>=3.0.0 <4.0.0'\n")
    return p


# ---------------------------------------------------------------------------
# Fake Play API service — records every call.
# ---------------------------------------------------------------------------

class _Req:
    def __init__(self, result):
        self._result = result

    def execute(self):
        return self._result


class FakeEdits:
    def __init__(self, service):
        self.s = service

    def insert(self, packageName, body):
        self.s.calls.append(("insert", packageName))
        return _Req({"id": "edit-123"})

    def tracks(self):
        return FakeTracks(self.s)

    def bundles(self):
        return FakeBundles(self.s)

    def validate(self, packageName, editId):
        self.s.calls.append(("validate", editId))
        return _Req({"id": editId})

    def commit(self, packageName, editId):
        self.s.calls.append(("commit", editId))
        return _Req({"id": editId})

    def delete(self, packageName, editId):
        self.s.calls.append(("delete", editId))
        return _Req({})


class FakeTracks:
    def __init__(self, service):
        self.s = service

    def list(self, packageName, editId):
        self.s.calls.append(("tracks.list", editId))
        return _Req({"tracks": self.s.tracks})

    def update(self, packageName, editId, track, body):
        self.s.calls.append(("tracks.update", track, body))
        self.s.last_track_update = body
        return _Req(body)


class FakeBundles:
    def __init__(self, service):
        self.s = service

    def upload(self, packageName, editId, media_body):
        self.s.calls.append(("bundles.upload", media_body))
        return _Req({"versionCode": self.s.uploaded_version_code})


class FakeService:
    def __init__(self, tracks, uploaded_version_code=26):
        self.calls = []
        self.tracks = tracks
        self.uploaded_version_code = uploaded_version_code
        self.last_track_update = None

    def edits(self):
        return FakeEdits(self)


def one_closed_track(version_codes=None):
    return [{"track": "closed-testers",
             "releases": [{"versionCodes": [str(v) for v in (version_codes or [])]}]}]


def called(service, name):
    return [c for c in service.calls if c[0] == name]


# ---------------------------------------------------------------------------
# aab_manifest parser
# ---------------------------------------------------------------------------

def test_reads_version_from_aab(tmp_path):
    aab = make_aab(tmp_path, 26, "2.3.2")
    v = aab_manifest.read_aab_version(aab)
    assert v.version_code == 26
    assert v.version_name == "2.3.2"


def test_bad_zip_is_reported(tmp_path):
    bad = os.path.join(str(tmp_path), "x.aab")
    with open(bad, "wb") as fh:
        fh.write(b"not a zip")
    with pytest.raises(aab_manifest.AabManifestError):
        aab_manifest.read_aab_version(bad)


# ---------------------------------------------------------------------------
# version / pubspec checks
# ---------------------------------------------------------------------------

def test_version_matches_pubspec(tmp_path):
    aab = make_aab(tmp_path, 26, "2.3.2")
    ps = make_pubspec(tmp_path, "2.3.2+26")
    code, name = pu.check_version_matches_pubspec(aab, ps)
    assert code == 26 and name == "2.3.2"


def test_pubspec_mismatch_refused(tmp_path):
    aab = make_aab(tmp_path, 26, "2.3.2")
    ps = make_pubspec(tmp_path, "2.3.2+25")
    with pytest.raises(pu.UploadError) as e:
        pu.check_version_matches_pubspec(aab, ps)
    assert "mismatch" in str(e.value).lower()


# ---------------------------------------------------------------------------
# signer check (keytool is stubbed via monkeypatch)
# ---------------------------------------------------------------------------

def _patch_keytool(monkeypatch, output):
    monkeypatch.setattr(pu, "_run_keytool", lambda aab, keytool: output)


def test_signer_accepts_real_key(tmp_path, monkeypatch):
    _patch_keytool(monkeypatch,
                   "Owner: CN=Mikhail Glik, O=Audioura LLC, L=Boston\nValid from ...")
    pu.check_signer("x.aab", "keytool")  # should not raise


def test_signer_refuses_debug(tmp_path, monkeypatch):
    _patch_keytool(monkeypatch, "Owner: CN=Android Debug, O=Android, C=US")
    with pytest.raises(pu.UploadError) as e:
        pu.check_signer("x.aab", "keytool")
    assert "debug" in str(e.value).lower()


def test_signer_refuses_unknown(tmp_path, monkeypatch):
    _patch_keytool(monkeypatch, "Owner: CN=Someone Else, O=Other LLC")
    with pytest.raises(pu.UploadError):
        pu.check_signer("x.aab", "keytool")


# ---------------------------------------------------------------------------
# duplicate versionCode
# ---------------------------------------------------------------------------

def test_duplicate_versioncode_on_track_refused(tmp_path):
    service = FakeService(tracks=one_closed_track([26]))
    with pytest.raises(pu.UploadError) as e:
        pu.check_version_not_used(service, "edit-123", 26, os.path.join(str(tmp_path), "NOPE.md"))
    assert "already present" in str(e.value).lower()


def test_duplicate_versioncode_in_ledger_refused(tmp_path):
    bn = os.path.join(str(tmp_path), "BUILD_NUMBERS.md")
    with open(bn, "w", encoding="utf-8") as fh:
        fh.write("| build | platform | version | commit | outcome | date |\n")
        fh.write("| 26 | Android | 2.3.2 | `abc1234` | uploaded to Play closed testing | 2026-09-17 |\n")
    service = FakeService(tracks=one_closed_track([]))
    with pytest.raises(pu.UploadError) as e:
        pu.check_version_not_used(service, "edit-123", 26, bn)
    assert "build_numbers" in str(e.value).lower()


def test_free_versioncode_passes(tmp_path):
    service = FakeService(tracks=one_closed_track([25, 24]))
    pu.check_version_not_used(service, "edit-123", 26, os.path.join(str(tmp_path), "NOPE.md"))


def test_removing_duplicate_check_would_be_caught(tmp_path):
    """This is the guard the brief asks for: if the duplicate check no longer
    raised, run_upload(--apply) would proceed to commit a duplicate. Here we
    assert the check itself raises, so deleting its body turns this red."""
    service = FakeService(tracks=one_closed_track([26]))
    raised = False
    try:
        pu.check_version_not_used(service, "e", 26, "NOPE.md")
    except pu.UploadError:
        raised = True
    assert raised, "duplicate-versionCode check must refuse a used number"


# ---------------------------------------------------------------------------
# track resolution
# ---------------------------------------------------------------------------

def test_resolve_single_closed_track():
    service = FakeService(tracks=[{"track": "production"}, {"track": "closed-testers"}])
    assert pu.resolve_closed_track(service, "e", None) == "closed-testers"


def test_resolve_requires_disambiguation_when_many():
    service = FakeService(tracks=[{"track": "alpha"}, {"track": "closed-2"}])
    with pytest.raises(pu.UploadError):
        pu.resolve_closed_track(service, "e", None)


def test_resolve_honors_requested_track():
    service = FakeService(tracks=[{"track": "alpha"}, {"track": "closed-2"}])
    assert pu.resolve_closed_track(service, "e", "closed-2") == "closed-2"


# ---------------------------------------------------------------------------
# run_upload: dry run vs apply
# ---------------------------------------------------------------------------

def _plan(tmp_path, apply, aab=None, track=""):
    return pu.UploadPlan(
        aab_path=aab or make_aab(tmp_path),
        version_code=26, version_name="2.3.2",
        release_name="2.3.2 (26)", notes="Bug fixes.",
        track=track, apply=apply,
        build_numbers_path=os.path.join(str(tmp_path), "NOPE.md"),
    )


def test_dry_run_never_commits(tmp_path):
    service = FakeService(tracks=one_closed_track([25]))
    plan = _plan(tmp_path, apply=False)
    pu.run_upload(service, plan)
    assert not plan.committed
    assert called(service, "commit") == []
    assert called(service, "bundles.upload") == []
    assert called(service, "delete"), "dry run must delete the edit"


def test_apply_commits_with_right_release(tmp_path):
    service = FakeService(tracks=one_closed_track([25]), uploaded_version_code=26)
    plan = _plan(tmp_path, apply=True)
    pu.run_upload(service, plan)
    assert plan.committed
    assert called(service, "commit")
    body = service.last_track_update
    assert body["track"] == "closed-testers"
    rel = body["releases"][0]
    assert rel["name"] == "2.3.2 (26)"
    assert rel["status"] == "completed"
    assert rel["versionCodes"] == ["26"]
    assert rel["releaseNotes"][0]["language"] == "en-US"
    assert rel["releaseNotes"][0]["text"] == "Bug fixes."


def test_apply_refuses_duplicate_before_upload(tmp_path):
    service = FakeService(tracks=one_closed_track([26]))
    plan = _plan(tmp_path, apply=True)
    with pytest.raises(pu.UploadError):
        pu.run_upload(service, plan)
    assert called(service, "bundles.upload") == []
    assert called(service, "commit") == []
    assert called(service, "delete"), "failed apply must abandon the edit"


def test_apply_refuses_versioncode_mismatch_from_upload(tmp_path):
    # Play reports a different versionCode than expected -> refuse, no commit.
    service = FakeService(tracks=one_closed_track([25]), uploaded_version_code=99)
    plan = _plan(tmp_path, apply=True)
    with pytest.raises(pu.UploadError):
        pu.run_upload(service, plan)
    assert called(service, "commit") == []


# ---------------------------------------------------------------------------
# ledger append
# ---------------------------------------------------------------------------

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                       "BUILD_NUMBERS.fixture.md")


def _read_bytes(path):
    with open(path, "rb") as fh:
        return fh.read()


def test_append_build_numbers_row(tmp_path):
    bn = os.path.join(str(tmp_path), "BUILD_NUMBERS.md")
    with open(bn, "w", encoding="utf-8") as fh:
        fh.write("## Ledger\n\n")
        fh.write("| build | platform | version | commit | outcome | date |\n")
        fh.write("|---|---|---|---|---|---|\n")
        fh.write("| 25 | iOS | 2.3.2 | `abc` | uploaded to TestFlight | 2026-09-16 |\n")
    row = pu.append_build_numbers_row(bn, 26, "2.3.2", "abc1234", "edit-123", "2026-09-17")
    assert "| 26 | Android | 2.3.2 |" in row
    with open(bn, "r", encoding="utf-8") as fh:
        assert "uploaded to Play closed testing" in fh.read()


def test_append_inserts_before_next_placeholder_on_real_ledger(tmp_path):
    """Acceptance #1: on a verbatim copy of the real BUILD_NUMBERS.md the 26
    Android row lands immediately before the `27 NEXT` row, and every other
    line is byte-identical."""
    bn = os.path.join(str(tmp_path), "BUILD_NUMBERS.md")
    original = _read_bytes(FIXTURE)
    with open(bn, "wb") as fh:
        fh.write(original)

    pu.append_build_numbers_row(bn, 26, "2.3.2", "5e53c56", "edit-123", "2026-09-17")

    before_lines = original.decode("utf-8").splitlines(keepends=True)
    after_lines = _read_bytes(bn).decode("utf-8").splitlines(keepends=True)

    # Exactly one line added.
    assert len(after_lines) == len(before_lines) + 1

    # Find the inserted row and the NEXT row in the new file.
    new_idx = next(i for i, l in enumerate(after_lines)
                   if l.strip().startswith("| 26 | Android | 2.3.2 |"))
    next_idx = next(i for i, l in enumerate(after_lines) if "**NEXT**" in l)
    assert new_idx + 1 == next_idx, "26 Android row must sit right before the NEXT row"

    # Every other line is byte-identical: removing the inserted line reproduces
    # the original file exactly (bytes and line endings).
    rebuilt = "".join(after_lines[:new_idx] + after_lines[new_idx + 1:])
    assert rebuilt.encode("utf-8") == original

    # Preserved CRLF endings on the inserted line too.
    assert after_lines[new_idx].endswith("\r\n")


def test_append_no_ledger_table_errors_and_leaves_file_unchanged(tmp_path):
    """Acceptance #1: no `## Ledger` table -> clear error, file unchanged."""
    bn = os.path.join(str(tmp_path), "BUILD_NUMBERS.md")
    content = b"# Something else\r\n\r\nNo ledger here.\r\n"
    with open(bn, "wb") as fh:
        fh.write(content)
    with pytest.raises(pu.UploadError) as e:
        pu.append_build_numbers_row(bn, 26, "2.3.2", "abc", "edit", "2026-09-17")
    assert "ledger" in str(e.value).lower()
    assert _read_bytes(bn) == content, "file must be unchanged when the table is absent"


def test_duplicate_guard_on_real_ledger(tmp_path):
    """Acceptance #2: the fixed duplicate guard on the verbatim fixture."""
    # 20 Android -> "shipped to Play closed testing" -> uploaded.
    assert pu.build_numbers_has_android_upload(FIXTURE, 20) is True
    # 22 Android -> "never shipped" -> not uploaded.
    assert pu.build_numbers_has_android_upload(FIXTURE, 22) is False
    # 23 Android -> "not uploaded to Play" -> not uploaded.
    assert pu.build_numbers_has_android_upload(FIXTURE, 23) is False
    # 26 Android -> absent -> not uploaded.
    assert pu.build_numbers_has_android_upload(FIXTURE, 26) is False


def test_duplicate_guard_true_after_fixed_append(tmp_path):
    """Acceptance #2: after the fixed append writes the 26 Android row, the
    guard reports 26 as uploaded."""
    bn = os.path.join(str(tmp_path), "BUILD_NUMBERS.md")
    with open(bn, "wb") as fh:
        fh.write(_read_bytes(FIXTURE))
    assert pu.build_numbers_has_android_upload(bn, 26) is False
    pu.append_build_numbers_row(bn, 26, "2.3.2", "5e53c56", "edit-123", "2026-09-17")
    assert pu.build_numbers_has_android_upload(bn, 26) is True
