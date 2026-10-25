// [LOCAL-762] Integration-test driver: writes each screenshot the test
// registers (via binding.takeScreenshot(name)) to a host-side PNG under
// build/local762_screenshots/. Run with:
//   flutter drive \
//     --driver=test_driver/local762_screenshot_driver.dart \
//     --target=integration_test/local762_price_screenshot_test.dart \
//     -d <booted-simulator-id>
import 'dart:io';
import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  await integrationDriver(
    onScreenshot:
        (String name, List<int> bytes, [Map<String, Object?>? args]) async {
      final dir = Directory('build/local762_screenshots');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      final file = File('${dir.path}/$name.png');
      file.writeAsBytesSync(bytes);
      return true;
    },
  );
}
