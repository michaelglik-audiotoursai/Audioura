// [LOCAL-774] Integration-test driver: writes each screenshot the test
// registers (via binding.takeScreenshot(name)) to a host-side PNG under
// build/local774_screenshots/. Run with:
//   flutter drive \
//     --driver=test_driver/local774_screenshot_driver.dart \
//     --target=integration_test/local774_refusal_dialog_screenshot_test.dart \
//     -d <booted-emulator-id>
import 'dart:io';
import 'package:integration_test/integration_test_driver_extended.dart';

Future<void> main() async {
  await integrationDriver(
    onScreenshot:
        (String name, List<int> bytes, [Map<String, Object?>? args]) async {
      final dir = Directory('build/local774_screenshots');
      if (!dir.existsSync()) dir.createSync(recursive: true);
      final file = File('${dir.path}/$name.png');
      file.writeAsBytesSync(bytes);
      return true;
    },
  );
}
