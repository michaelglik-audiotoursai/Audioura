# Review for Mobile Amazon-Q — Fix Korean / Chinese language mix-up

**Date:** 2026-06-08
**Lane:** Mobile (Android Flutter, `audio_tour_app/`) ONLY. Do not touch services.
**Priority:** Blocker for Korean. Server side is already fixed and deployed-ready (`ko` / Polly `Seoyeon` voice live in `translation_service.py`). Korean is broken end-to-end **only** because of the app.

---

## Symptom

Test (v2.1.1+7), Boston 9-stop tour, tester requested **Korean**. The app sent `zh` to the server (log `log_android_06072026_2305.txt`, confirmed `ru, zh`). Result: the "Korean" tour came back as Chinese/English, never Korean.

## Root cause (verified in code)

There is **no Korean option in the app**. The language picker only offers Chinese (`zh`). When the tester wanted Korean, the only non-Latin chip available was 中文 (`zh`), so `zh` is what got sent. This is not a remapping bug — it's a missing language plus missing display labels.

The chip list is centralized in one widget, so the fix is small and applies everywhere:

`lib/widgets/language_selector.dart` (lines 20–27) — the only source of truth for selectable languages, consumed by all 5 call sites (`home_screen.dart` 603, 755, 2535; `tour_generator_screen.dart` 1112, 1125):

```dart
static const Map<String, String> languages = {
  'en': 'English',
  'ru': 'Русский',
  'es': 'Español',
  'fr': 'Français',
  'de': 'Deutsch',
  'zh': '中文',
};
```

`lib/screens/home_screen.dart` `_getLanguageName()` (lines 707–717) — display helper used for saved/translated tour labels — also has **no `ko` case** (Korean would fall through to the `default` and render as `KO`).

---

## The fix

**1. Add Korean to the picker.** In `lib/widgets/language_selector.dart`, add to the `languages` map:

```dart
'ko': '한국어',
```

The chip emits `entry.key` straight to the request, so this sends `ko` to the server with no other plumbing needed. (Confirm Chinese is still intended as an offering; if `zh` was only ever a stand-in for Korean and Chinese isn't actually supported server-side, drop `'zh'` to remove the temptation — your call, server currently supports `en, ru, es, fr, de, zh, ko`.)

**2. Add the Korean display label.** In `lib/screens/home_screen.dart` `_getLanguageName()`, add:

```dart
case 'ko': return 'Korean';
```

So Korean tours show "Korean", not "KO", in My Tours / origin labels.

**3. Self-check before handing back.** Grep the app for any other hardcoded language list or label switch (`zh`, `Chinese`, `_getLanguageName`-style maps) and make sure none of them silently coerce a Korean selection into `zh`. The two spots above are the only ones I found, but you own this lane — confirm there isn't a second copy.

---

## Acceptance test

1. Open the language picker → **한국어** appears as a selectable chip.
2. Request a tour with Korean selected → outgoing request carries `ko` (not `zh`). Verify in the Android log.
3. Server returns a Korean (Seoyeon-voiced) tour; My Tours labels it **Korean**, not **KO**.
4. Audio plays back in Korean, matched per stop.

If the RU retest passes but Korean still looks off **after** this ships, ping me — but it should be clean once `ko` is actually sent.

---

## Out of scope for this doc

The separate Listen-Page title issue (some save paths store the English `original_request`/`location` instead of the server's translated `tour_name`, e.g. `tour_generator_screen.dart` line 800 vs. the correct manifest-read path at 544–586) is a **different** Mobile-AQ item. Say the word and I'll write that one up on its own so we keep one concern per doc.
