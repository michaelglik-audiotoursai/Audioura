import sys

path = 'C:/Users/micha/eclipse-workspace/AudioTours/development/audio_tour_app/lib/screens/my_tours_screen.dart'

with open(path, 'rb') as f:
    content = f.read()

# The bad _manualRefresh — uses \r\n (file has CRLF in this region? check both)
old = (
    b'  void _manualRefresh() {\r\n'
    b'    Navigator.of(context).pop();\r\n'
    b'    WidgetsBinding.instance.addPostFrameCallback((_) {\r\n'
    b'      if (mounted) {\r\n'
    b'        Navigator.of(context).pushReplacement(\r\n'
    b'          MaterialPageRoute(builder: (context) => MyToursScreen()),\r\n'
    b'        );\r\n'
    b'      }\r\n'
    b'    });\r\n'
    b'  }'
)

new = (
    b'  Future<void> _manualRefresh() async {\r\n'
    b'    await DebugLogHelper.addDebugLog(\'LISTEN: Manual refresh triggered\');\r\n'
    b'    if (!mounted) return;\r\n'
    b'    await _loadAppMode();\r\n'
    b'  }'
)

if old not in content:
    # Try LF-only variant
    old = (
        b'  void _manualRefresh() {\n'
        b'    Navigator.of(context).pop();\n'
        b'    WidgetsBinding.instance.addPostFrameCallback((_) {\n'
        b'      if (mounted) {\n'
        b'        Navigator.of(context).pushReplacement(\n'
        b'          MaterialPageRoute(builder: (context) => MyToursScreen()),\n'
        b'        );\n'
        b'      }\n'
        b'    });\n'
        b'  }'
    )
    new = (
        b'  Future<void> _manualRefresh() async {\n'
        b'    await DebugLogHelper.addDebugLog(\'LISTEN: Manual refresh triggered\');\n'
        b'    if (!mounted) return;\n'
        b'    await _loadAppMode();\n'
        b'  }'
    )

if old not in content:
    with open('D:/Audioura/results/patch_a77b_result.txt', 'w') as out:
        out.write('FAIL: target string not found in file\n')
    sys.exit(1)

patched = content.replace(old, new, 1)

with open(path, 'wb') as f:
    f.write(patched)

with open('D:/Audioura/results/patch_a77b_result.txt', 'w') as out:
    out.write('SUCCESS: _manualRefresh replaced with in-place _loadAppMode reload\n')
