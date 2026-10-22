// [LOCAL-735] Integration-test driver: writes each screenshot the test
// registers (via binding.takeScreenshot(name)) to a host-side PNG under
// build/local735_screenshots/. Run with:
//   flutter drive \
//     --driver=test_driver/local735_screenshot_driver.dart \
//     --target=integration_test/plan_screen_order_screenshot_test.dart \
//     -d <booted-simulator-id> \
//     --dart-define=DEBUG_SERVER_IP=127.0.0.1
import 'dart:io';
import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  await integrationDriver(
    onScreenshot: (String name, List<int> bytes, [Map<String, Object?>? args]) async {
      final dir = Directory('build/local735_screenshots');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      final file = File('${dir.path}/$name.png');
      file.writeAsBytesSync(bytes);
      return true;
    },
  );
}
