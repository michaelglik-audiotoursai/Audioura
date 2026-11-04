"""stop_headers.py -- structural stop header lines survive any rewrite (LOCAL-866).

A stop's ``Address:`` / ``Coordinates:`` / ``Type/Specialty:`` / ``Specific Examples:``
lines are STRUCTURE, not prose: the app builds the stop's map pin from Coordinates.
Any pass that rewrites a stop block (the LOCAL-540 scorer retry, the LOCAL-628 editor,
...) can drop them -- the LOCAL-862C Sophia run shipped Stop 7 with no Coordinates
line although the listener's own link had given a pin.

``restore_stop_headers(text, poi_list)`` re-attaches them from the poi dicts, for
every stop. Rules:
  * Coordinates: always equals the poi coordinate (inserted if missing/empty,
    replaced if different).
  * Address / Type/Specialty / Specific Examples: inserted if missing or empty,
    never overwritten (a later pass may have cleaned the wording on purpose).
Idempotent: a block that already carries correct lines is returned unchanged.
"""

import re

_STOP_LINE = re.compile(r'^Stop\s+(\d+):[^\n]*$', re.M)

# (label, poi key) in the order the assembler writes them.
HEADER_FIELDS = (
    ('Address', 'address'),
    ('Coordinates', 'coordinates'),
    ('Type/Specialty', 'type_specialty'),
    ('Specific Examples', 'specific_examples'),
)


def _norm(s):
    return re.sub(r'[^a-z0-9]+', ' ', (s or '').lower()).strip()


def _title(stop_line):
    return stop_line.split(':', 1)[1].strip() if ':' in stop_line else ''


def _poi_for_block(num, title, pois):
    """Match a delivered block to its poi: by name first (titles are shortened but
    stay contained), else by stop_number."""
    nt = _norm(title)
    if nt:
        for p in pois:
            np_ = _norm(p.get('name'))
            if np_ and (np_ == nt or nt.startswith(np_) or np_.startswith(nt)):
                return p
    for p in pois:
        try:
            if int(p.get('stop_number')) == num:
                return p
        except (TypeError, ValueError):
            continue
    return None


def _same_coord(a, b):
    na = re.findall(r'-?\d+(?:\.\d+)?', a or '')
    nb = re.findall(r'-?\d+(?:\.\d+)?', b or '')
    if len(na) < 2 or len(nb) < 2:
        return False
    return all(abs(float(x) - float(y)) < 5e-7 for x, y in zip(na[:2], nb[:2]))


def _fix_block(block, poi, clean_address=None):
    lines = block.split('\n')
    title_idx = 0
    out_changed = False
    # Existing header lines anywhere in the block (paragraph-start labels).
    for label, key in HEADER_FIELDS:
        want = poi.get(key)
        want = str(want).strip() if want not in (None, '') else ''
        # A listener-pinned stop's address is only trusted after the product's own
        # cleaner (LOCAL-855E: no "15 Đ." stub); never re-introduce one.
        if (label == 'Address' and want and clean_address
                and str(poi.get('coord_source') or '').startswith('user_')):
            want = clean_address(want) or ''
        if not want:
            continue
        rx = re.compile(r'^' + re.escape(label) + r':[ \t]*(.*)$')
        idx = next((i for i, ln in enumerate(lines) if rx.match(ln)), None)
        if idx is not None:
            have = rx.match(lines[idx]).group(1).strip()
            if label == 'Coordinates':
                if have and _same_coord(have, want):
                    continue
                lines[idx] = f'Coordinates: {want}'
                out_changed = True
                continue
            if have:
                continue
            lines[idx] = f'{label}: {want}'
            out_changed = True
            continue
        # Missing: insert after the last earlier-ordered header line present, else
        # right after the Stop title line.
        anchor = title_idx
        for lab2, _k2 in HEADER_FIELDS:
            if lab2 == label:
                break
            rx2 = re.compile(r'^' + re.escape(lab2) + r':')
            for i, ln in enumerate(lines):
                if rx2.match(ln):
                    anchor = max(anchor, i)
        lines[anchor + 1:anchor + 1] = ['', f'{label}: {want}']
        out_changed = True
    return '\n'.join(lines) if out_changed else block


def restore_stop_headers(text, poi_list, log=None, clean_address=None):
    """Return ``text`` with every stop block's structural header lines restored
    from ``poi_list``. Blocks that match no poi are left untouched."""
    if not text or not poi_list:
        return text
    heads = list(_STOP_LINE.finditer(text))
    if not heads:
        return text
    pieces, pos, fixed = [], 0, []
    for i, m in enumerate(heads):
        end = heads[i + 1].start() if i + 1 < len(heads) else len(text)
        block = text[m.start():end]
        poi = _poi_for_block(int(m.group(1)), _title(m.group(0)), poi_list)
        new = _fix_block(block, poi, clean_address) if poi else block
        if new != block:
            labs = [lab for lab, _k in HEADER_FIELDS
                    if (lab + ':') in new and
                    [ln for ln in new.split('\n') if ln.startswith(lab + ':')] !=
                    [ln for ln in block.split('\n') if ln.startswith(lab + ':')]]
            fixed.append(f"{int(m.group(1))}({'/'.join(labs)})")
        pieces.append(text[pos:m.start()])
        pieces.append(new)
        pos = end
    pieces.append(text[pos:])
    if fixed and log:
        log(f"  [LOCAL-866] restored stop header lines on stop(s) {fixed}")
    return ''.join(pieces)
