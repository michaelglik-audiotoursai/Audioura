"""
Fix Issue B: Black screen on newsletter Refresh button.

Root cause: Refresh handler sets _isLoading=true which triggers the wrong
"Home" scaffold (Tours mode spinner) to render in Audio mode. If the widget
rebuilds during the async HTTP gap and state becomes inconsistent, the screen
goes black with no way to recover.

Fix: Remove setState(_isLoading=true) from the refresh handler.
_loadNewsletters() already manages its own state via cached-newsletters
fallback — it sets _isLoading=false at completion in all branches.
"""

path = r"C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\lib\screens\home_screen.dart"

with open(path, 'r', encoding='utf-8', newline='') as f:
    content = f.read()

original = content

# The refresh button in _buildNewsletterView AppBar actions
old = "        IconButton(\r\n            icon: Icon(Icons.refresh),\r\n            onPressed: () async {\r\n              await DebugLogHelper.addDebugLog('HOME: Manual newsletter refresh triggered');\r\n              setState(() {\r\n                _isLoading = true;\r\n              });\r\n              await _loadNewsletters();\r\n            },\r\n          ),"

new = "        IconButton(\r\n            icon: Icon(Icons.refresh),\r\n            onPressed: () async {\r\n              await DebugLogHelper.addDebugLog('HOME: Manual newsletter refresh triggered');\r\n              await _loadNewsletters();\r\n            },\r\n          ),"

if old in content:
    content = content.replace(old, new)
    print("Fix applied: removed setState(_isLoading=true) from newsletter refresh handler")
else:
    print("ERROR: target snippet not found — check line endings or whitespace")

if content == original:
    print("WARNING: no changes written")
else:
    with open(path, 'w', encoding='utf-8', newline='') as f:
        f.write(content)
    print(f"Written: {path}")
