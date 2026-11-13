/// [LOCAL-908] Simulator / emulator proof harness for "On the way".
///
/// Writes a small tour (4 stops, short silent WAVs, the LOCAL-907 `fillings`
/// payload fixture shape) into the app's Documents folder and opens the REAL
/// [TourPlayerScreen] on it — the same WebView, JS bridge, controller, panel,
/// sheet, event queue and notification the app uses. The page auto-advances
/// from one stop to the next on 'ended' (like the translation pages) so the
/// "hold" is exercised for real.
///
/// Needs no network except an optional stub for POST /listening-events:
///   python3 tools/otw_stub_events.py 15003     (own port; never the shared stack)
///   flutter run -t lib/main_on_the_way_proof.dart -d <sim> \
///     --dart-define=DEBUG_SERVER_IP=127.0.0.1 --dart-define=DEBUG_PORT_OFFSET=10000
///
/// The simulator's GPS is moved with `xcrun simctl location <udid> set lat,lng`.
library;

import 'dart:convert';
import 'dart:io';
import 'dart:math' as math;
import 'dart:typed_data';

import 'package:flutter/material.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'screens/tour_player_screen.dart';
import 'services/on_the_way_notification.dart';
import 'services/on_the_way_settings.dart';

/// '' (default: auto-play, full flow) | 'quiet' (auto-play off) | 'menu' (auto-play
/// off, then the lock-screen action is simulated after 16 s).
const String kProofMode = String.fromEnvironment('OTW_PROOF');

const String kProofUser = 'sim-otw908';
const String kProofTourId = '908';

// Stop coordinates (Boston waterfront). Stop 2 is where the simulator is moved
// to simulate arrival.
const List<List<double>> kStops = [
  [42.3601, -71.0589],
  [42.3736, -71.0560],
  [42.3867, -71.0640],
  [42.3954, -71.0810],
];

Uint8List _wav(double seconds, double hz) {
  const rate = 8000;
  final n = (seconds * rate).round();
  final data = ByteData(44 + n * 2);
  void s(int o, String t) {
    for (var i = 0; i < t.length; i++) {
      data.setUint8(o + i, t.codeUnitAt(i));
    }
  }

  s(0, 'RIFF');
  data.setUint32(4, 36 + n * 2, Endian.little);
  s(8, 'WAVE');
  s(12, 'fmt ');
  data.setUint32(16, 16, Endian.little);
  data.setUint16(20, 1, Endian.little);
  data.setUint16(22, 1, Endian.little);
  data.setUint32(24, rate, Endian.little);
  data.setUint32(28, rate * 2, Endian.little);
  data.setUint16(32, 2, Endian.little);
  data.setUint16(34, 16, Endian.little);
  s(36, 'data');
  data.setUint32(40, n * 2, Endian.little);
  for (var i = 0; i < n; i++) {
    final v = (math.sin(2 * math.pi * hz * i / rate) * 600).round();
    data.setInt16(44 + i * 2, v, Endian.little);
  }
  return data.buffer.asUint8List();
}

Future<String> _writeTour() async {
  final docs = await getApplicationDocumentsDirectory();
  final dir = Directory('${docs.path}/otw908_tour');
  if (await dir.exists()) await dir.delete(recursive: true);
  await dir.create(recursive: true);

  const names = ['Old Fort', 'Harbour Market', 'Charlestown Navy Yard', 'Lighthouse Point'];
  final audios = StringBuffer();
  for (var i = 0; i < 4; i++) {
    await File('${dir.path}/stop${i + 1}.wav').writeAsBytes(_wav(8, 440));
    await File('${dir.path}/audio_${i + 1}.txt').writeAsString(
        '${names[i]}\nCoordinates: ${kStops[i][0]}, ${kStops[i][1]}\n');
    audios.writeln('<h2 id="stopTitle${i + 1}">Stop ${i + 1}: ${names[i]}</h2>'
        '<audio id="audio${i + 1}" controls src="stop${i + 1}.wav"></audio>');
  }
  await File('${dir.path}/index.html').writeAsString('''<!doctype html>
<html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<style>body{font-family:-apple-system;padding:14px;color:#223}audio{width:100%}</style></head>
<body><p style="color:#777">LOCAL-908 proof page - stops auto-advance on end (like translation pages)</p>
$audios
<script>
var els = document.querySelectorAll('audio');
els.forEach(function (a, i) {
  a.addEventListener('ended', function () {
    if (i < els.length - 1) { setTimeout(function () { els[i + 1].play(); }, 300); }
  });
});
function startTour() { els[0].play(); }
</script></body></html>''');

  // Topics: absolute file:// URLs (the audio lives on the device).
  final titles = [
    'The harbour that built the town',
    'Marsh, tide and shore birds',
    'What the first settlers ate',
    'The painters of the waterfront',
    'How the railway changed everything',
    'The ghost lights of the bay',
  ];
  final themes = ['history', 'nature', 'food', 'arts', 'transport', 'legends'];
  final mins = [12.7, 9.0, 10.2, 11.0, 13.0, 10.0];
  Map<String, dynamic> item(int k) => {
        'segment_id': k + 1,
        'title': titles[k],
        'theme': themes[k],
        'minutes': mins[k],
        'audio_url': 'file://${dir.path}/topic${k + 1}.wav',
        'credit_line':
            'This segment is based on Wikipedia articles, used under the Creative Commons Attribution-ShareAlike licence.',
        'sentence_ends': [4.0, 8.0, 12.0, 16.0, 20.0, 24.0, 28.0, 32.0],
      };
  for (var k = 0; k < 6; k++) {
    await File('${dir.path}/topic${k + 1}.wav').writeAsBytes(_wav(40, 330));
  }
  await File('${dir.path}/fillings.json').writeAsString(jsonEncode({
    'fillings': [
      {
        'leg': 0, 'after_stop': 1, 'minutes': 40.1,
        'items': [item(0), item(1), item(2), item(3)]
      },
      {
        'leg': 2, 'after_stop': 3, 'minutes': 37.2,
        'items': [item(4), item(5)]
      },
    ]
  }));
  return dir.path;
}

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final prefs = await SharedPreferences.getInstance();
  await prefs.setString('user_id', kProofUser);
  await prefs.setString('server_mode', 'local');
  await prefs.setString('server_ip', '127.0.0.1');
  await prefs.setBool('onboarding_complete', true);
  await prefs.setBool(OnTheWaySettings.autoPlayKey, kProofMode.isEmpty);
  final path = await _writeTour();
  final nav = GlobalKey<NavigatorState>();
  Widget player() => TourPlayerScreen(
        tourPath: path,
        tourTitle: 'Boston Harbour Drive',
        tourId: kProofTourId,
        originalLanguage: 'en',
      );
  runApp(MaterialApp(
    navigatorKey: nav,
    title: 'On the way proof',
    debugShowCheckedModeBanner: false,
    home: Scaffold(
      appBar: AppBar(title: const Text('LOCAL-908 proof')),
      body: Center(
        child: ElevatedButton(
          key: const Key('open_player'),
          onPressed: () =>
              nav.currentState!.push(MaterialPageRoute(builder: (_) => player())),
          child: const Text('Open tour'),
        ),
      ),
    ),
  ));
  if (kProofMode == 'menu') {
    // The same signal the lock-screen "Topics" action raises.
    Future<void>.delayed(const Duration(seconds: 16), OnTheWayNotification.requestMenu);
  }
  // Open the player straight away; no tap needed on the simulator.
  Future<void>.delayed(const Duration(milliseconds: 800), () {
    nav.currentState?.push(MaterialPageRoute(builder: (_) => player()));
  });
}
