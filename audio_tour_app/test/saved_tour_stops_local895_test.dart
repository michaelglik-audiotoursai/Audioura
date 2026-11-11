import 'dart:convert';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/utils/saved_tour_stops.dart';

void main() {
  late Directory tmp;
  setUp(() => tmp = Directory.systemTemp.createTempSync('l895'));
  tearDown(() => tmp.deleteSync(recursive: true));

  Directory tourWith(int n) {
    final d = Directory('${tmp.path}/t$n')..createSync();
    for (var i = 1; i <= n; i++) {
      File('${d.path}/audio_$i.mp3').writeAsBytesSync([0]);
    }
    File('${d.path}/index.html').writeAsStringSync('x');
    return d;
  }

  test('user list has 8 and the box says 10 -> saved 8', () {
    // No folder, no server count: the user list is the only real number.
    final n = resolveRealStopCount(userListLength: 8);
    expect(stopsEntry(n), {'stops': '8'});
  });

  test('mp3s on disk beat server and user list', () {
    final d = tourWith(8);
    expect(
        resolveRealStopCount(
            tourDirPath: d.path, serverCount: 9, userListLength: 10),
        8);
  });

  test('server count used when no folder', () {
    expect(serverStopCount({'actual_stops': 8, 'stops_count': 10}), 8);
    expect(serverStopCount({'stops_count': '7'}), 7);
    expect(resolveRealStopCount(serverCount: 7, userListLength: 10), 7);
  });

  test('unknown -> no count', () {
    final n = resolveRealStopCount(tourDirPath: '${tmp.path}/nope');
    expect(n, isNull);
    expect(stopsEntry(n).containsKey('stops'), isFalse);
    expect(serverStopCount(null), isNull);
  });

  test('repair fixes a 10 to an 8, leaves others alone', () {
    final d8 = tourWith(8);
    final good = tourWith(3);
    final list = [
      jsonEncode({'title': 'a', 'path': d8.path, 'stops': '10'}),
      jsonEncode({'title': 'b', 'path': good.path, 'stops': '3'}),
      jsonEncode({'title': 'c', 'path': '${tmp.path}/gone', 'stops': '10'}),
      jsonEncode({'title': 'd', 'path': d8.path}),
      'not json',
    ];
    final r = repairSavedTourStops(list);
    expect(r.changed, isTrue);
    expect(jsonDecode(r.tours[0])['stops'], '8');
    expect(r.tours[1], list[1]);
    expect(jsonDecode(r.tours[2])['stops'], '10'); // folder missing: untouched
    expect(jsonDecode(r.tours[3])['stops'], '8');
    expect(r.tours[4], 'not json');
    expect(repairSavedTourStops(r.tours).changed, isFalse);
  });
}
