// [LOCAL-763 / D711 §2] Widget tests for the Listen ⋮ menu polish (Michael's
// retest 2026-10-25):
//   * The role line is a BRIGHT coloured strip (not grey), readable, that WRAPS
//     to fit its text — even the longest label on the narrowest (320 px) phone
//     is fully visible, nothing hidden behind the next item.
//   * The role line carries a ✕ (tooltip "Close") that closes the menu.
//   * A disabled action (Edit / Translate / Price) keeps a GREY title + icon
//     but its trailing ⓘ is in the PRIMARY colour and is tappable.
//
// RED before the fix: the old role line was a grey, fixed-height (32 px)
// PopupMenuItem with a grey ⓘ and no ✕.

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';

import 'package:audio_tour_app_dev/utils/tour_role_label.dart';
import 'package:audio_tour_app_dev/widgets/role_line_menu_entry.dart';

// The longest label the role line can show (community name included).
const _longest =
    'Broadcast tour · The Greater Salem Historical & Paranormal Society — '
    'you are the organiser';

Widget _host(Widget child, {Brightness brightness = Brightness.light}) {
  return MaterialApp(
    theme: ThemeData(brightness: brightness),
    home: Scaffold(body: Center(child: child)),
  );
}

void main() {
  testWidgets(
    '[LOCAL-763] role line wraps and is fully visible at 320 px, no overflow',
    (tester) async {
      tester.view.physicalSize = const Size(320, 800);
      tester.view.devicePixelRatio = 1.0;
      addTearDown(tester.view.reset);

      await tester.pumpWidget(_host(
        // 320-px-wide box like the narrowest phone's menu.
        SizedBox(
          width: 320,
          child: RoleLineMenuEntry<String>(
            line: const TourRoleLine(
                _longest, TourRoleIcon.broadcast, TourRoleKind.broadcastPurple),
            icon: Icons.podcasts,
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // No RenderFlex / text overflow was thrown during layout.
      expect(tester.takeException(), isNull);

      // The full label is present (wrapped, not truncated/ellipsised).
      final textFinder = find.text(_longest);
      expect(textFinder, findsOneWidget);
      final textWidget = tester.widget<Text>(textFinder);
      expect(textWidget.overflow, isNot(TextOverflow.ellipsis));

      // It really wrapped to more than one line at this width.
      final size = tester.getSize(textFinder);
      expect(size.height, greaterThan(20),
          reason: 'the long label must wrap to multiple lines');
    },
  );

  testWidgets('[LOCAL-763] role line strip is a bright (non-grey) colour',
      (tester) async {
    await tester.pumpWidget(_host(
      SizedBox(
        width: 320,
        child: RoleLineMenuEntry<String>(
          line: const TourRoleLine(
              'Your tour', TourRoleIcon.person, TourRoleKind.ownBlue),
          icon: Icons.person_outline,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    final strip = tester.widget<Container>(
      find.byKey(kRoleLineStripKey),
    );
    final decoration = strip.decoration as BoxDecoration;
    final fill = decoration.color!;
    // The fill is a saturated colour, not the old grey. Blue dominates for the
    // own-tour kind.
    expect(fill.b, greaterThan(fill.r),
        reason: 'ownBlue strip should be blue-dominant, not grey');
    expect(fill, isNot(Colors.grey));
  });

  testWidgets('[LOCAL-763] ✕ has a Close tooltip and fires onClose',
      (tester) async {
    var closed = false;
    await tester.pumpWidget(_host(
      SizedBox(
        width: 320,
        child: RoleLineMenuEntry<String>(
          line: const TourRoleLine(
              'Your tour', TourRoleIcon.person, TourRoleKind.ownBlue),
          icon: Icons.person_outline,
          onClose: () => closed = true,
        ),
      ),
    ));
    await tester.pumpAndSettle();

    expect(find.byKey(kRoleLineCloseKey), findsOneWidget);
    expect(
      find.byTooltip('Close'),
      findsOneWidget,
      reason: 'the ✕ must carry a "Close" tooltip',
    );

    await tester.tap(find.byKey(kRoleLineCloseKey));
    await tester.pump();
    expect(closed, isTrue);
  });

  testWidgets(
    '[LOCAL-763] ✕ on the real menu closes the whole ⋮ menu',
    (tester) async {
      await tester.pumpWidget(_host(
        Builder(builder: (context) {
          return PopupMenuButton<String>(
            itemBuilder: (context) => [
              RoleLineMenuEntry<String>(
                line: const TourRoleLine(
                    'Your tour', TourRoleIcon.person, TourRoleKind.ownBlue),
                icon: Icons.person_outline,
                onClose: () => Navigator.of(context).pop(),
              ),
              const PopupMenuItem<String>(value: 'rate', child: Text('Rate')),
            ],
          );
        }),
      ));

      await tester.tap(find.byType(PopupMenuButton<String>));
      await tester.pumpAndSettle();
      // Menu is open — the Rate item is visible.
      expect(find.text('Rate'), findsOneWidget);

      await tester.tap(find.byKey(kRoleLineCloseKey));
      await tester.pumpAndSettle();
      // Menu closed — the Rate item is gone.
      expect(find.text('Rate'), findsNothing);
    },
  );

  testWidgets(
    '[LOCAL-763] disabled row: grey title/icon but a bright, tappable ⓘ',
    (tester) async {
      const primary = Color(0xFF1E88E5);
      await tester.pumpWidget(MaterialApp(
        theme: ThemeData(colorScheme: const ColorScheme.light(primary: primary)),
        home: Scaffold(
          body: Center(
            child: Builder(
              builder: (context) =>
                  disabledMenuInfoChild(context, icon: Icons.edit, title: 'Edit'),
            ),
          ),
        ),
      ));
      await tester.pumpAndSettle();

      // The ⓘ is the PRIMARY colour, not grey.
      final infoIcon = tester.widget<Icon>(find.byKey(kDisabledInfoIconKey));
      expect(infoIcon.color, primary);
      expect(infoIcon.color, isNot(Colors.grey));

      // The title stays grey (reads as unavailable).
      final title = tester.widget<Text>(find.text('Edit'));
      expect(title.style?.color, Colors.grey);

      // The ⓘ carries its reason tooltip (tappable affordance).
      expect(find.byTooltip('Why is this unavailable?'), findsOneWidget);
    },
  );
}
