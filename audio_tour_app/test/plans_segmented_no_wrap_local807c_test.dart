// [LOCAL-807C] Regression test for the segmented-control label wrap.
//
// At iPhone width (375pt logical), the Day/Week/Month/Year SegmentedButton in
// PlansScreen split the row into four equal cells and the 5-letter "Month" (and
// "Week") label wrapped onto a SECOND line with the default 14sp Material label
// style. The fix uses a smaller label style and tighter per-segment padding so
// every label fits on ONE line.
//
// This test pumps PlansScreen inside a 375pt-wide viewport, reveals the Pass
// panel, and asserts that EACH segment label ("Day", "Week", "Month", "Year")
// renders as a single line — its laid-out paragraph reports no overflow and its
// rendered height is under a two-line threshold. It fails if any label wraps.

import 'package:flutter/material.dart';
import 'package:flutter/rendering.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:audio_tour_app_dev/screens/plans_screen.dart';
import 'package:audio_tour_app_dev/services/entitlements_service.dart';

Entitlements _ent(String level) => Entitlements.fromJson({
      'level': level,
      'display_name': level,
      'levels': const [],
      'allowances_left': const {},
    });

/// Walk the render tree under [textFinder]'s element to the RenderParagraph so
/// we can read the actual laid-out line metrics (not just the widget config).
RenderParagraph _paragraphFor(WidgetTester tester, Finder textFinder) {
  final element = tester.element(textFinder);
  RenderParagraph? found;
  void visit(RenderObject obj) {
    if (found != null) return;
    if (obj is RenderParagraph) {
      found = obj;
      return;
    }
    obj.visitChildren(visit);
  }

  final ro = element.renderObject;
  if (ro != null) visit(ro);
  expect(found, isNotNull,
      reason: 'expected a RenderParagraph under the label');
  return found!;
}

void main() {
  TestWidgetsFlutterBinding.ensureInitialized();

  setUp(() => SharedPreferences.setMockInitialValues({}));

  testWidgets('Day/Week/Month/Year segment labels do not wrap at 375pt width',
      (tester) async {
    // iPhone logical width is 375pt (iPhone 6–8/SE2/SE3, the narrowest common
    // device). Pin the surface to that width so the SegmentedButton lays out
    // exactly as it would on that phone.
    tester.view.devicePixelRatio = 1.0;
    tester.view.physicalSize = const Size(375, 812);
    addTearDown(tester.view.resetPhysicalSize);
    addTearDown(tester.view.resetDevicePixelRatio);

    await tester.pumpWidget(MaterialApp(
      home: PlansScreen(
        initialEntitlements: _ent('l1'),
        initialStubMode: false,
        priceOverride: (id) => '\$9.99',
      ),
    ));
    await tester.pumpAndSettle();

    // Reveal the Pass panel (segmented control lives there).
    await tester.tap(find.byKey(const Key('choice_pass')));
    await tester.pumpAndSettle();
    expect(find.byKey(const Key('pass_options')), findsOneWidget);

    for (final label in const ['Day', 'Week', 'Month', 'Year']) {
      final finder = find.text(label);
      expect(finder, findsOneWidget, reason: 'segment "$label" should render');

      final para = _paragraphFor(tester, finder);
      // The paragraph must not have clipped/overflowed its maxLines…
      expect(para.didExceedMaxLines, isFalse,
          reason: 'segment "$label" overflowed its single line at 375pt');

      // …and it must occupy a single text line. A wrapped label would be ~2x
      // the font height; assert the rendered height stays under 1.6 lines.
      final fontSize = para.text.style?.fontSize ?? 14.0;
      expect(para.size.height, lessThan(fontSize * 1.6),
          reason: 'segment "$label" wrapped to a second line at 375pt '
              '(height ${para.size.height} for fontSize $fontSize)');
    }
  });
}
