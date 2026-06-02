import sys

TARGET = r'C:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\lib\screens\my_tours_screen.dart'
RESULT = r'D:\Audioura\results\patch_a78_import.txt'

DEAD_IMPORT_CRLF = b"import 'package:permission_handler/permission_handler.dart';\r\n"
DEAD_IMPORT_LF   = b"import 'package:permission_handler/permission_handler.dart';\n"

with open(TARGET, 'rb') as f:
    data = f.read()

if DEAD_IMPORT_CRLF in data:
    new_data = data.replace(DEAD_IMPORT_CRLF, b'', 1)
    result = 'SUCCESS: removed dead permission_handler import (CRLF)'
elif DEAD_IMPORT_LF in data:
    new_data = data.replace(DEAD_IMPORT_LF, b'', 1)
    result = 'SUCCESS: removed dead permission_handler import (LF)'
else:
    new_data = None
    result = 'ERROR: import line not found - already removed or line differs'

if new_data is not None:
    # Verify no Permission. references remain (other than comments)
    remaining = [line for line in new_data.split(b'\n')
                 if b'permission_handler' in line or b'Permission.' in line]
    if remaining:
        result += ' | WARNING: Permission refs still present: ' + str(remaining)
    with open(TARGET, 'wb') as f:
        f.write(new_data)

with open(RESULT, 'w') as f:
    f.write(result + '\n')
