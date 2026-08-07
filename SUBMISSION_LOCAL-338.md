##### READY FOR REVIEW

## Commit

```
61bc970 LOCAL-338: Voice services (water/toilet) and next-stop distance guidance
```

## Per-file summary

| File | Change |
|------|--------|
| `audio_tour_app/pubspec.yaml` | Added `flutter_tts: ^4.2.0` dependency |
| `audio_tour_app/lib/services/navigation_service.dart` | **New.** Runtime service: queries LOCAL-337 `/nearby-services` for water/toilet; computes next-stop distance from `audio_N.txt` coordinates using `Geolocator.distanceBetween`. Three-state result enum (`found`/`noneFound`/`couldNotSearch`). Graceful fallback when LOCAL-337 is unreachable. |
| `audio_tour_app/lib/services/voice_control_service.dart` | Extended `_processAdvancedCommand` dispatch chain with water (`water`/`drink`/`fountain`), toilet (`toilet`/`bathroom`/`restroom`/`loo`), and distance (`how far`/`distance`/`where am i`) phrases → `find_water`, `find_toilet`, `next_stop_distance` actions. |
| `audio_tour_app/lib/screens/voice_methods.dart` | Added `flutter_tts` + `NavigationService`. TTS init, `_speakNavigation()` duck-speak-resume pattern, `_isMuseumTour()` guard, `_handleServiceLookup()` and `_handleNextStopDistance()` with three-state spoken replies. New cases in `handleVoiceCommand` switch. |
| `audio_tour_app/lib/screens/my_tours_screen.dart` | Store `current_tour_type` in SharedPreferences on tour play (line 1413). |
| `audio_tour_app/test/navigation_service_test.dart` | **New.** 16 unit tests: data model, three-state message logic, no reminder promise, phrase matching. |
| `audio_tour_app/pubspec.lock` | Lock updated for flutter_tts 4.2.5 |
| `audio_tour_app/macos/*`, `audio_tour_app/windows/*` | Generated plugin registrant changes from flutter_tts |

## Three reply states (literal strings the user would hear)

### Water

| State | Spoken |
|-------|--------|
| found | `Water — there's a public fountain 200 metres ahead, just past the church.` |
| noneFound | `I checked nearby but couldn't find a water source on this stretch.` |
| couldNotSearch | `I can't search for water right now — location or network unavailable.` |

### Toilet

| State | Spoken |
|-------|--------|
| found | `Toilet — there's one 150 metres ahead, near the park entrance.` |
| noneFound | `I checked nearby but couldn't find a toilet on this stretch.` |
| couldNotSearch | `I can't search for toilets right now — location or network unavailable.` |

### Next-stop distance

| State | Spoken |
|-------|--------|
| found | `The next stop is 300 metres ahead.` |
| noneFound | `I don't have location data for the next stop.` |
| couldNotSearch | `I can't check the distance right now — location unavailable.` |

## Museum-tour guard

```dart
Future<bool> _isMuseumTour() async {
  final prefs = await SharedPreferences.getInstance();
  final tourType = prefs.getString('current_tour_type') ?? '';
  return tourType == 'museum' || tourType == 'museum_tour' || tourType == 'exhibit';
}
```

All three navigation commands (`find_water`, `find_toilet`, `next_stop_distance`) check `_isMuseumTour()` first and silently break (with a debug log) if true. Indoor tours get no navigation chatter.

## Verification evidence

### flutter analyze (touched files only)

```
$ flutter analyze lib/services/navigation_service.dart lib/services/voice_control_service.dart lib/screens/voice_methods.dart lib/screens/my_tours_screen.dart
No errors. 8 warnings (all pre-existing: unused_import, unused_element, unused_field).
105 info-level lints (prefer_const_constructors, use_build_context_synchronously — pre-existing patterns).
```

`navigation_service.dart` alone: **No issues found.**

### flutter test

```
$ flutter test test/navigation_service_test.dart
00:00 +16: All tests passed!
```

### git status

```
$ git status --short
(clean)
```

## Limitations

- **On-device behaviour is unverified.** No simulator or device available on this machine. TTS ducking, audio resume, and geolocator calls are untested at runtime.
- **LOCAL-337 endpoint is stubbed.** `NavigationService._queryServer()` attempts a real HTTP call to port 5009; if the server is unreachable (connection refused, timeout, 404) it returns `couldNotSearch`. The found/noneFound paths will only execute once LOCAL-337 is deployed.
- **No background geofence.** "I'll tell you when you're there" is deliberately not spoken — there is no geofence trigger. Only current-moment distance is reported.
- **No left/right directions.** Compass bearing at walking speed is unreliable (D-agreed). Only distance + landmark.
- **flutter_tts runtime** requires iOS speech synthesis entitlement (already present for speech_to_text). No new iOS permissions added.
