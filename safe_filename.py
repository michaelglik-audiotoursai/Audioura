"""[LOCAL-894B] One helper for every path component built from user text.

A described request ("Create a half day driving tour from ... ", 777 chars, Vietnamese
place names) reaches ``location`` whole since LOCAL-894 removed the 200-char cut. Any
file name or directory built from it then exceeds the 255-BYTE limit of the file
system ("[Errno 36] File name too long"), and a tour is lost after it was paid for.

Rules:
  * A text whose sanitised slug fits in ``max_bytes`` (UTF-8 bytes, default 80) is
    returned EXACTLY as the old builders produced it, so existing short names, the
    shared tour store and downloads keep working.
  * A longer text is cut on a character boundary (never mid-codepoint), then an
    8-char hash of the FULL text is appended so two long requests that share a prefix
    never collide.
  * ``preferred`` (a derived short title / place) replaces the raw text as the visible
    part of an over-long name; the hash is still of the full text.

Stored file names are read back from the job / database (``output_zip``,
``extract_dir``, ``zip_filename``) -- nothing re-derives them from the text.
"""
import hashlib
import unicodedata

MAX_SLUG_BYTES = 80
HASH_CHARS = 8
# A whole name must stay under the file system limit with room for prefix/suffix.
MAX_NAME_BYTES = 255


def _alnum_style(text):
    """Generator style: every non-alphanumeric character becomes '_'."""
    return ''.join(c if c.isalnum() else '_' for c in text)


def _orch_style(text):
    """Orchestrator style (unchanged from the old inline builder), plus the path
    separators the old builder missed (a NUL or '..' can never reach a path)."""
    return (text.replace(' ', '_').replace(',', '').replace(':', '')
            .replace('/', '_').replace('\\', '_').replace('\x00', '').lower())


_STYLES = {'alnum': _alnum_style, 'orch': _orch_style}


def _byte_len(s):
    return len(s.encode('utf-8'))


def _cut_bytes(s, max_bytes):
    """Longest prefix of ``s`` that is <= max_bytes UTF-8 bytes (whole characters)."""
    out, used = [], 0
    for ch in s:
        n = len(ch.encode('utf-8'))
        if used + n > max_bytes:
            break
        out.append(ch)
        used += n
    return ''.join(out)


def text_hash(text, chars=HASH_CHARS):
    return hashlib.sha1((text or '').encode('utf-8')).hexdigest()[:chars]


def safe_component(text, preferred=None, style='alnum', max_bytes=MAX_SLUG_BYTES):
    """Return a file-name-safe slug for ``text``.

    Short input -> identical to the old builder for ``style``. Over-long input ->
    ``<slug cut to max_bytes - 9 bytes>_<hash8 of the full text>`` (<= max_bytes).
    """
    fn = _STYLES[style]
    text = unicodedata.normalize('NFC', str(text or ''))
    slug = fn(text)
    if _byte_len(slug) <= max_bytes:
        return slug
    base = fn(unicodedata.normalize('NFC', str(preferred))) if preferred else slug
    room = max_bytes - HASH_CHARS - 1
    head = _cut_bytes(base, room).strip('_.- ')
    h = text_hash(text)
    return f"{head}_{h}" if head else h


def bound_text(text, max_bytes=40):
    """Keep ``text`` verbatim when it fits (e.g. a tour_type like "driving"); otherwise
    cut + hash. For short fields that sit next to the slug in a name."""
    text = str(text or '')
    if _byte_len(text) <= max_bytes:
        return text
    head = _cut_bytes(text, max_bytes - HASH_CHARS - 1).strip('_.- ')
    return f"{head}_{text_hash(text)}" if head else text_hash(text)


def safe_name(stem, ext='', suffix='', max_total=MAX_NAME_BYTES):
    """Final guard on an assembled name: ``stem + suffix + ext`` is never longer than
    ``max_total`` bytes. Unchanged when it already fits."""
    full = f"{stem}{suffix}{ext}"
    if _byte_len(full) <= max_total:
        return full
    keep = max_total - _byte_len(suffix) - _byte_len(ext) - HASH_CHARS - 1
    head = _cut_bytes(stem, max(keep, 1)).strip('_.- ')
    return f"{head}_{text_hash(stem)}{suffix}{ext}"


# ── named builders: one place for each shape, so the callers and the tests agree ──
def tour_zip_names(location, tour_type, job_id, preferred=None):
    """Orchestrator: ``(zip_filename, extract_dir)``. Short input keeps the historical shape
    ``<location>_<tour_type>_<job8>[.zip]`` exactly."""
    stem = safe_component(location, preferred=preferred, style='orch')
    suffix = f"_{bound_text(tour_type)}_{(job_id or '')[:8]}"
    return safe_name(stem, ext=".zip", suffix=suffix), safe_name(stem, suffix=suffix)


def generator_output_filename(location, tour_type, timestamp):
    """Generator text file: ``<location>_<tour_type>_tour_<timestamp>.txt`` (alnum style)."""
    return safe_name(safe_component(location, style='alnum'), ext=".txt",
                     suffix=f"_{safe_component(tour_type, style='alnum', max_bytes=40)}_tour_{timestamp}")


def download_name(request_string):
    """Map delivery: ``<request>_tour.zip``."""
    return safe_name(safe_component(request_string, style='orch'), ext="_tour.zip")
