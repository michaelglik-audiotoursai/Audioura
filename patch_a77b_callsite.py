import sys

path = 'C:/Users/micha/eclipse-workspace/AudioTours/development/audio_tour_app/lib/screens/my_tours_screen.dart'

with open(path, 'rb') as f:
    content = f.read()

# CRLF variant
old_crlf = b'            onPressed: _manualRefresh,\r\n            tooltip: \'Manual Refresh (Test Navigation Reset)\','
new_crlf = b'            onPressed: () => _manualRefresh(),\r\n            tooltip: \'Refresh\','

# LF variant
old_lf = b'            onPressed: _manualRefresh,\n            tooltip: \'Manual Refresh (Test Navigation Reset)\','
new_lf = b'            onPressed: () => _manualRefresh(),\n            tooltip: \'Refresh\','

if old_crlf in content:
    patched = content.replace(old_crlf, new_crlf, 1)
    variant = 'CRLF'
elif old_lf in content:
    patched = content.replace(old_lf, new_lf, 1)
    variant = 'LF'
else:
    with open('D:/Audioura/results/patch_a77b_callsite_result.txt', 'w') as out:
        out.write('FAIL: call site tooltip string not found\n')
    sys.exit(1)

with open(path, 'wb') as f:
    f.write(patched)

with open('D:/Audioura/results/patch_a77b_callsite_result.txt', 'w') as out:
    out.write(f'SUCCESS ({variant}): onPressed wrapped in closure, tooltip updated\n')
