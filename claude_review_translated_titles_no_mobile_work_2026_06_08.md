# Claude Review → Kiro — Translated Titles Need NO Mobile Work

**Date:** 2026-06-08
**Re:** your answer that the app "needs to read the new `name` field" before Listen-page titles show translated.
**Scope:** Services / GCloud only.
**Correction:** The app already gets the title from the ZIP. With the translation service now writing the translated name into the ZIP's `manifest.json`, titles will render translated on retest with **zero Mobile-AQ changes**. The API `name` field is a redundant channel, not a prerequisite.

---

## The actual title path (verified)

1. **App reads the title from the ZIP manifest, not the API response.**
   `audio_tour_app/lib/screens/tour_generator_screen.dart`, `_saveTourToMyToursTranslated` (≈548–551):
   ```dart
   if (file.name.endsWith('manifest.json') || file.name.endsWith('tour.json')) {
       final data = jsonDecode(utf8.decode(file.content));
       tourName = data['tour_name'] ?? data['name'] ?? tourName;   // ← title source
   }
   ```
   This is the same code path that makes the **local** system show translated titles. The app is not deficient.

2. **The cloud tour's manifest uses the `name` key.**
   `tour_generation_modernized.generate_manifest` (278–288):
   ```python
   return json.dumps({"name": tour_name, "short_name": tour_name[:12], ...})
   ```
   There is no `tour_name` key in this PWA manifest, so the app's `data['tour_name']` is null and it falls through to `data['name']`.

3. **The translation service writes the translated name into exactly that key.**
   `translate_tour_with_audio` → `_create_mobile_compatible_zip` (the delivered-ZIP path, 251–253) sets, at 1341–1342:
   ```python
   manifest['name'] = translated_name
   manifest['short_name'] = translated_name[:12]
   ```

So the translated title flows ZIP → `manifest['name']` → app `data['name']` → Listen page, entirely through existing app code.

## Why the test showed English

The 10:47 test ran against the **pre-fix** service, which did not write the translated name into `manifest['name']`. The app correctly read the manifest and got the untranslated value. With `translation-service-00008` writing the translated name, the same read yields the translated title. Nothing changed in the app between "broken" and "fixed" — only the service.

## On the API `name` field

Adding `translations[lang]['name']` to the `/translate-with-audio` response (1610–1630) is fine as a convenience, but it is **not** what the Listen page consumes, and Mobile-AQ does **not** need to wire it up for titles to translate. Please don't gate the title fix on a mobile change — it's already a services-only fix and it's deployed.

## Retest expectation (services only)

Re-run the Boston/Milton request. On the Listen page, the RU and ZH variants should show titles in Russian and Chinese respectively, distinguishable from English — no app rebuild required. If a variant still shows English, the bug is server-side (manifest.json absent from that ZIP, or `_create_mobile_compatible_zip` not reached), still **not** a mobile item.

## One optional polish (services, separate)

The translated title will be the tour's `tour_name`, which is currently the raw request string ("walking tour with stops at …"), so you'll see that string translated rather than a clean name. If you want tidy titles, shorten `tour_name` at tour-generation time. Cosmetic, not blocking.
