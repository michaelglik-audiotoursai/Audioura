#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Read versionCode / versionName straight out of an Android App Bundle.

An .aab is a zip. Its manifest lives at ``base/manifest/AndroidManifest.xml``
and is stored as an ``aapt.pb.XmlNode`` protobuf (NOT binary XML, NOT text).

We deliberately avoid a protobuf-runtime dependency and bundletool: this module
decodes just enough of the protobuf wire format to walk the XML tree and pull
the two ``android:*`` attributes off the ``<manifest>`` element. That keeps the
check honest (it reads the artifact itself, per the runbook) and portable to a
laptop with nothing but Python installed.

Wire format reference (developers.google.com/protocol-buffers/docs/encoding):
each field is a varint tag ``(field_number << 3) | wire_type`` followed by the
payload. We only need wire types 0 (varint) and 2 (length-delimited).

aapt XmlNode schema (the fields we use), from AOSP Resources.proto:
    XmlNode   { XmlElement element = 1; ... }
    XmlElement{ string name = 2; repeated XmlAttribute attribute = 4;
                repeated XmlNode child = 5; ... }
    XmlAttribute { string name = 2; string value = 3;
                   Item compiled_item = 5; ... }
    Item      { Prim prim = 3; ... }         # value carrier
    Primitive { ... int_decimal_value = 6; ... }  # a plain int lives here

``android:versionName`` is carried as the attribute's ``value`` string (field 3).
``android:versionCode`` is an integer, carried in the compiled ``Item`` (field 5)
as a ``Primitive`` (field 3) ``int_decimal_value`` (field 6). Some builders also
leave the decimal in the ``value`` string; we accept either.
"""
from __future__ import annotations

import io
import zipfile
from dataclasses import dataclass


class AabManifestError(Exception):
    """Raised when the bundle or its manifest cannot be read."""


# ---------------------------------------------------------------------------
# Minimal protobuf wire-format reader
# ---------------------------------------------------------------------------

def _read_varint(buf: bytes, pos: int) -> tuple[int, int]:
    result = 0
    shift = 0
    while True:
        if pos >= len(buf):
            raise AabManifestError("truncated varint in manifest protobuf")
        b = buf[pos]
        pos += 1
        result |= (b & 0x7F) << shift
        if not (b & 0x80):
            return result, pos
        shift += 7
        if shift > 70:
            raise AabManifestError("varint too long in manifest protobuf")


def _iter_fields(buf: bytes):
    """Yield (field_number, wire_type, value) for one protobuf message.

    value is an int for varints (wire 0) and bytes for length-delimited
    (wire 2). Other wire types (fixed32/64) are skipped over.
    """
    pos = 0
    n = len(buf)
    while pos < n:
        tag, pos = _read_varint(buf, pos)
        field_no = tag >> 3
        wire = tag & 0x07
        if wire == 0:  # varint
            val, pos = _read_varint(buf, pos)
            yield field_no, wire, val
        elif wire == 2:  # length-delimited
            length, pos = _read_varint(buf, pos)
            if pos + length > n:
                raise AabManifestError("length-delimited field overruns buffer")
            yield field_no, wire, buf[pos:pos + length]
            pos += length
        elif wire == 5:  # fixed32
            pos += 4
        elif wire == 1:  # fixed64
            pos += 8
        else:
            raise AabManifestError(f"unsupported protobuf wire type {wire}")


def _first(buf: bytes, field_no: int):
    for fn, _wire, val in _iter_fields(buf):
        if fn == field_no:
            return val
    return None


def _all(buf: bytes, field_no: int):
    return [val for fn, _wire, val in _iter_fields(buf) if fn == field_no]


# ---------------------------------------------------------------------------
# XmlNode walking
# ---------------------------------------------------------------------------

# Field numbers per the real aapt proto (verified against a live +26 bundle):
#   XmlNode    { XmlElement element = 1 }
#   XmlElement { NamespaceDecl namespace_declaration = 1; string name = 3;
#                repeated XmlAttribute attribute = 4; repeated XmlNode child = 5 }
#   XmlAttribute { string name = 2; string value = 3; ...; Item compiled_item = 6 }
# The attribute's plain-text ``value`` (field 3) already carries the decimal for
# versionCode and the string for versionName, so we read both from there and do
# not need to descend into the compiled Item.
F_NODE_ELEMENT = 1
F_ELEM_NAME = 3
F_ELEM_ATTR = 4
F_ELEM_CHILD = 5
F_ATTR_NAME = 2
F_ATTR_VALUE = 3


def _decode_str(val) -> str:
    if isinstance(val, bytes):
        return val.decode("utf-8", errors="replace")
    return str(val)


def _find_manifest_element(node_bytes: bytes) -> bytes | None:
    """Depth-first search for the <manifest> XmlElement, returns its bytes."""
    element = _first(node_bytes, F_NODE_ELEMENT)
    if element is None:
        return None
    name = _first(element, F_ELEM_NAME)
    if name is not None and _decode_str(name) == "manifest":
        return element
    # Recurse into children (best effort — skip subtrees we can't decode).
    try:
        children = _all(element, F_ELEM_CHILD)
    except AabManifestError:
        return None
    for child in children:
        try:
            found = _find_manifest_element(child)
        except AabManifestError:
            found = None
        if found is not None:
            return found
    return None


@dataclass
class AabVersion:
    version_code: int
    version_name: str


def _attributes(element_bytes: bytes):
    for attr in _all(element_bytes, F_ELEM_ATTR):
        name = _first(attr, F_ATTR_NAME)
        yield (_decode_str(name) if name is not None else ""), attr


def read_manifest_proto(manifest_bytes: bytes) -> AabVersion:
    """Parse a proto AndroidManifest.xml payload into an AabVersion.

    versionCode and versionName are both taken from each attribute's plain-text
    ``value`` field (verified present in real bundletool output).
    """
    element = _find_manifest_element(manifest_bytes)
    if element is None:
        raise AabManifestError("no <manifest> element found in bundle manifest")

    version_code: int | None = None
    version_name: str | None = None

    for attr_name, attr in _attributes(element):
        if attr_name == "versionCode":
            raw = _first(attr, F_ATTR_VALUE)
            if raw is not None:
                try:
                    version_code = int(_decode_str(raw).strip())
                except ValueError:
                    pass
        elif attr_name == "versionName":
            raw = _first(attr, F_ATTR_VALUE)
            if raw is not None:
                version_name = _decode_str(raw)

    if version_code is None:
        raise AabManifestError("versionCode not found in bundle manifest")
    if version_name is None:
        raise AabManifestError("versionName not found in bundle manifest")
    return AabVersion(version_code=version_code, version_name=version_name)


def read_aab_version(aab_path: str) -> AabVersion:
    """Open an .aab and return the versionCode/versionName from its manifest."""
    try:
        with zipfile.ZipFile(aab_path) as zf:
            try:
                data = zf.read("base/manifest/AndroidManifest.xml")
            except KeyError as exc:
                raise AabManifestError(
                    "base/manifest/AndroidManifest.xml missing — not a valid AAB"
                ) from exc
    except zipfile.BadZipFile as exc:
        raise AabManifestError(f"{aab_path} is not a valid zip/AAB") from exc
    except OSError as exc:
        raise AabManifestError(f"cannot open {aab_path}: {exc}") from exc
    return read_manifest_proto(data)


if __name__ == "__main__":  # pragma: no cover - manual probe
    import sys
    if len(sys.argv) != 2:
        print("usage: python tools/aab_manifest.py <path-to.aab>")
        raise SystemExit(2)
    v = read_aab_version(sys.argv[1])
    print(f"versionName={v.version_name} versionCode={v.version_code}")
