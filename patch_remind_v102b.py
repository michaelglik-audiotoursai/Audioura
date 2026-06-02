path = 'C:/Users/micha/eclipse-workspace/AudioTours/development/remind_ios_ai.md'

with open(path, 'rb') as f:
    c = f.read()

old = b'**Key smoke test:** Audio mode \xe2\x86\x92 Listen tab \xe2\x86\x92 tap Refresh \xe2\x86\x92 list reloads in place, no black screen. Log must show `LISTEN: Manual refresh triggered`.'

new = (
    b'**Key smoke test:** Audio mode \xe2\x86\x92 Listen tab \xe2\x86\x92 tap Refresh \xe2\x86\x92 list reloads in place, no black screen. Log must show `LISTEN: Manual refresh triggered` followed by `LISTEN: Loading N articles from storage` / `LISTEN: Successfully loaded N articles`.\r\n'
    b'**Extra test (Claude Q3):** Enter Select Articles mode on Listen tab \xe2\x86\x92 select some \xe2\x86\x92 tap Refresh \xe2\x86\x92 must not crash, selection exits cleanly, list reloads.\r\n'
    b'**Claude review:** \xe2\x9c\x85 Approved `4948178`. No blocking issues. `onPressed: () => _manualRefresh()` is valid Dart. Double-tap re-entrancy is harmless. Selection-mode risk is pre-existing, not a blocker.'
)

if old in c:
    c = c.replace(old, new, 1)
    print('OK')
else:
    print('MISS')

with open(path, 'wb') as f:
    f.write(c)
