# Claude Code Review — Add "Report This Tour" (UGC Policy) (commit `c0b66d7`)

**Date:** 2026-06-23
**Branch:** `services-migration`
**Commit:** `c0b66d7`
**ClickUp task:** 86aj5x5e1

---

## What was done

Added a "Report this tour" action on the Listen page to satisfy Google Play's User-Generated Content policy (pairs with the "Users Interact" content-rating descriptor).

### UI — grey flag icon on each tour

Added after the delete button in the tour list item trailing row:
```dart
IconButton(
  icon: const Icon(Icons.flag_outlined, color: Colors.grey),
  tooltip: 'Report this tour',
  onPressed: () => _reportTour(tour),
),
```

### `_reportTour(tour)` method

1. Shows confirmation dialog: "Report [tour title] as objectionable content?"
2. On confirm: opens a `mailto:` URI to `support@audioura.com` with prefilled subject and body containing tour title + ID
3. If email client can't launch: shows orange snackbar with direct email address
4. Cancel path: dismisses dialog, no action

```dart
final mailtoUri = Uri.parse('mailto:support@audioura.com?subject=$subject&body=$body');
if (await canLaunchUrl(mailtoUri)) {
  await launchUrl(mailtoUri);
}
```

### Import added
```dart
import 'package:url_launcher/url_launcher.dart';
```
(`url_launcher` is already in `pubspec.yaml` dependencies.)

---

## Files changed

| File | Change |
|------|--------|
| `lib/screens/my_tours_screen.dart` | +66 lines: `_reportTour()` method + flag icon in trailing row + `url_launcher` import |

---

## Design decisions

- **mailto: approach** — simplest v1 implementation that satisfies the UGC policy requirement. No server-side report endpoint needed. Can be upgraded to a proper report API + moderation queue in the future.
- **Grey flag icon** — unobtrusive, doesn't compete with the primary actions (map, translate, edit, delete, play). Discoverable via tooltip.
- **Confirmation dialog** — prevents accidental reports.
- **Email includes tour ID** — enables support to identify and action the reported content.

---

## Test criteria

- [ ] Flag icon visible on each tour in Listen page
- [ ] Tap flag → confirmation dialog appears with tour title
- [ ] Cancel → dismisses, no action
- [ ] Confirm → opens device email client with prefilled report email
- [ ] If no email client: orange snackbar with support email shown
- [ ] Pending device test: confirm `canLaunchUrl` works on both Android and iOS

---

## Future enhancement (noted, not implemented)
- Server-side `/report-content` endpoint with moderation queue
- In-app report form (without needing email client)
- Report counter / auto-hide threshold for heavily reported content

---

## Verdict requested
Approve — satisfies UGC policy for v1 launch.
