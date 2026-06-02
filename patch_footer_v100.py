import sys

path = 'remind_ios_ai.md'
with open(path, 'r', encoding='utf-8') as f:
    content = f.read()

marker = '**Last Updated**'
i = content.rfind(marker)
if i == -1:
    with open('patch_footer_result.txt', 'w') as out:
        out.write('ERROR: marker not found\n')
    sys.exit(1)

head = content[:i]
new_tail = ('**Last Updated**: 2026-06-02 \u2014 v100.0. '
            'iPhone on v1.2.9+68 (A#76 complete). '
            'A#77 ready to build (v1.2.9+69, newsletter Refresh fix committed at 4dba042). '
            'Android Q onboarding doc created (android_q_onboarding.md) \u2014 '
            'Android bundle ID com.audioura.app, debug keystore committed, '
            'key risk is stale path healing marker difference vs iOS.\r\n'
            '**iOS Amazon-Q Version**: 100.0\r\n')

result = head + new_tail
with open(path, 'w', encoding='utf-8') as f:
    f.write(result)

with open('patch_footer_result.txt', 'w') as out:
    out.write('OK: wrote v100.0 footer\n')
    out.write('head length: %d\n' % len(head))
    out.write('new tail: %s\n' % new_tail[:80])
