// [LOCAL-853] Integration-test driver: writes each screenshot the test
// registers (via binding.takeScreenshot(name)) to a host-side PNG under
// submission_artifacts/local853/. Run with:
//   flutter drive \
//     --driver=test_driver/local853_screenshot_driver.dart \
//     --target=integration_test/local853_tile_resilience_screenshot_test.dart \
//     -d <booted-simulator-id>
import 'dart:io';
import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  await integrationDriver(
    onScreenshot:
        (String name, List<int> bytes, [Map<String, Object?>? args]) async {
      final dir = Directory('submission_artifacts/local853');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      final file = File('${dir.path}/$name.png');
      file.writeAsBytesSync(bytes);
      return true;
    },
  );
}
