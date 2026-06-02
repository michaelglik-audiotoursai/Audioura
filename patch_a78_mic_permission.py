path = 'C:/Users/micha/eclipse-workspace/AudioTours/development/audio_tour_app/lib/screens/my_tours_screen.dart'

with open(path, 'rb') as f:
    c = f.read()

# CRLF variant (matches what we see in the file)
old = (
    b'    final permission = await Permission.microphone.request();\r\n'
    b'    if (!permission.isGranted) {\r\n'
    b'      ScaffoldMessenger.of(context).showSnackBar(\r\n'
    b"        SnackBar(content: Text('Microphone permission required')),\r\n"
    b'      );\r\n'
    b'      return;\r\n'
    b'    }\r\n'
    b'    \r\n'
)

new = b''  # remove entirely — speech_to_text.initialize() already handles mic permission

if old in c:
    c = c.replace(old, new, 1)
    result = 'SUCCESS: redundant Permission.microphone.request() block removed'
else:
    # try LF variant
    old = (
        b'    final permission = await Permission.microphone.request();\n'
        b'    if (!permission.isGranted) {\n'
        b'      ScaffoldMessenger.of(context).showSnackBar(\n'
        b"        SnackBar(content: Text('Microphone permission required')),\n"
        b'      );\n'
        b'      return;\n'
        b'    }\n'
        b'    \n'
    )
    if old in c:
        c = c.replace(old, new, 1)
        result = 'SUCCESS (LF): redundant Permission.microphone.request() block removed'
    else:
        result = 'FAIL: target block not found'

with open(path, 'wb') as f:
    f.write(c)

print(result)
