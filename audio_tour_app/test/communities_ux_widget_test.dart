// [LOCAL-700] Widget tests for the Communities UX round-1 screens.
//
// These run OFFLINE: with empty SharedPreferences, EntitlementsService.me()
// returns Entitlements.unknown (level 'l1') without a network call, and the
// Communities HTTP calls fail transport-side and return their safe defaults
// (null / empty). So the screens build deterministically.
//
// Covered:
//   §2 the About → Communities screen shows a "Have an invite code?" field and
//      a Join button (join from the Communities screen), and the My communities
//      screen shows the same join field.
//   §3 the Create screen, on the Introduction level (the offline default),
//      shows the plan explanation and a "Your plan" button — the form is gated.
//   §4 the RSS feed URL field is ABSENT from the Create screen (no field with
//      that label is ever rendered on either the gate or the form).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/communities_about_screen.dart';

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() {
    // Empty prefs → no user_id → EntitlementsService.me() returns unknown
    // (level 'l1') with no network; Communities calls fail → safe defaults.
    SharedPreferences.setMockInitialValues({});
  });

  testWidgets('§2 About → Communities has a join-by-code field + Join button',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CommunitiesAboutScreen()));
    await tester.pump();

    // The join section is below the long description; scroll it into view.
    await tester.scrollUntilVisible(
      find.widgetWithText(TextField, 'Invite code'),
      200,
      scrollable: find.byType(Scrollable),
    );

    expect(find.text('Have an invite code?'), findsOneWidget);
    expect(find.widgetWithText(TextField, 'Invite code'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Join'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Create a community'),
        findsOneWidget);
  });

  testWidgets('§1 About describes both content kinds + close warning',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CommunitiesAboutScreen()));
    await tester.pump();

    // The About body is one big Text; assert on the visible fragments.
    expect(find.textContaining('Your own audio'), findsOneWidget);
    expect(find.textContaining('made with Audioura'), findsOneWidget);
    expect(find.textContaining('cannot be closed'), findsOneWidget);
  });

  testWidgets('§3 Create is gated for Introduction — shows Your plan',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CreateCommunityScreen()));
    // Let _checkPlan() resolve (returns unknown/l1 offline).
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // The plan explanation and the "Your plan" button, not the form.
    expect(find.textContaining('needs a plan'), findsOneWidget);
    expect(find.widgetWithText(ElevatedButton, 'Your plan'), findsOneWidget);
    // The form fields are NOT shown while gated.
    expect(find.widgetWithText(ElevatedButton, 'Create community'),
        findsNothing);
  });

  testWidgets('§4 Create screen never shows an RSS feed URL field',
      (tester) async {
    await tester.pumpWidget(const MaterialApp(home: CreateCommunityScreen()));
    await tester.pump();
    await tester.pump(const Duration(milliseconds: 50));

    // No field or text mentions an RSS feed URL (removed in LOCAL-700 §4).
    expect(find.textContaining('RSS feed URL'), findsNothing);
    expect(find.textContaining('RSS'), findsNothing);
  });
}
