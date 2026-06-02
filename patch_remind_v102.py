path = 'C:/Users/micha/eclipse-workspace/AudioTours/development/remind_ios_ai.md'

with open(path, 'rb') as f:
    c = f.read()

replacements = [
    # 1. Key smoke test line — add Claude approval + extra test
    (
        b'**Key smoke test:** Audio mode \xe2\x80\x92 Listen tab \xe2\x80\x92 tap Refresh \xe2\x80\x92 list reloads in place, no black screen. Log must show `LISTEN: Manual refresh triggered`.',
        b'**Key smoke test:** Audio mode \xe2\x80\x92 Listen tab \xe2\x80\x92 tap Refresh \xe2\x80\x92 list reloads in place, no black screen. Log must show `LISTEN: Manual refresh triggered` followed by `LISTEN: Loading N articles from storage` / `LISTEN: Successfully loaded N articles`.\r\n**Extra test (Claude Q3):** Enter Select Articles mode on Listen tab \xe2\x80\x92 select some \xe2\x80\x92 tap Refresh \xe2\x80\x92 must not crash, selection exits cleanly, list reloads.\r\n**Claude review:** \xe2\x9c\x85 Approved `4948178`. No blocking issues. `onPressed: () => _manualRefresh()` is valid Dart. Double-tap re-entrancy is harmless. Selection-mode risk is pre-existing, not a blocker.'
    ),
    # 2. pubspec version note
    (
        b'- **pubspec.yaml version**: `1.2.9+65` in dev tree and on iPhone.',
        b'- **pubspec.yaml version**: `1.2.9+68` in dev tree. iPhone on +68. Next build targets +70.'
    ),
    # 3. KEY FILES table — assignments row
    (
        b'| `D:\\Audioura\\assignments\\mac_mini_assignments.md` | A#76 block at top. Git mirror: `usb/Audioura/assignments/mac_mini_assignments.md` |',
        b'| `D:\\Audioura\\assignments\\mac_mini_assignments.md` | A#77b block at top. Git mirror: `usb/Audioura/assignments/mac_mini_assignments.md` |\r\n| `C:\\Users\\micha\\eclipse-workspace\\AudioTours\\development\\a77b_review_request_for_claude.md` | A#77b Claude review request |\r\n| `C:\\Users\\micha\\eclipse-workspace\\AudioTours\\development\\claude_review_a77b_2026_06_02.md` | Claude review response \xe2\x80\x94 approved, no blockers |'
    ),
    # 4. Footer
    (
        b'**Last Updated**: 2026-06-02 \xe2\x80\x94 v101.0. iPhone on v1.2.9+68 (A#76 complete). A#77 (+69) built but failed smoke test \xe2\x80\x94 fixed wrong Refresh button. A#77b real fix committed at 4948178 \xe2\x80\x94 `_manualRefresh()` in `my_tours_screen.dart` replaced with in-place `_loadAppMode()` reload. Ready to build as v1.2.9+70.\r\r\n**iOS Amazon-Q Version**: 101.0\r\r\n',
        b'**Last Updated**: 2026-06-02 \xe2\x80\x94 v102.0. iPhone on v1.2.9+68 (A#76 complete). A#77 (+69) built but failed \xe2\x80\x94 wrong Refresh button. A#77b real fix at `4948178` \xe2\x80\x94 `_manualRefresh()` replaced with in-place `_loadAppMode()`. Claude approved (`claude_review_a77b_2026_06_02.md`). Extra smoke test: Refresh while in selection mode. Ready to build as v1.2.9+70.\r\r\n**iOS Amazon-Q Version**: 102.0\r\r\n'
    ),
]

results = []
for old, new in replacements:
    if old in c:
        c = c.replace(old, new, 1)
        results.append('OK: ' + repr(old[:60]))
    else:
        results.append('MISS: ' + repr(old[:60]))

with open(path, 'wb') as f:
    f.write(c)

print('\n'.join(results))
