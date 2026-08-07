import 'package:flutter_test/flutter_test.dart';
import '../lib/services/navigation_service.dart';

void main() {
  group('NavigationService — ServiceLookupState', () {
    test('ServiceLookupResult stores found state with description', () {
      const result = ServiceLookupResult(
        state: ServiceLookupState.found,
        description: 'a public fountain 200 metres ahead, just past the church',
        distanceMetres: 200,
        landmark: 'the church',
      );
      expect(result.state, ServiceLookupState.found);
      expect(result.description, contains('fountain'));
      expect(result.distanceMetres, 200);
      expect(result.landmark, 'the church');
    });

    test('ServiceLookupResult noneFound has no description', () {
      const result = ServiceLookupResult(state: ServiceLookupState.noneFound);
      expect(result.state, ServiceLookupState.noneFound);
      expect(result.description, isNull);
      expect(result.distanceMetres, isNull);
    });

    test('ServiceLookupResult couldNotSearch has no description', () {
      const result = ServiceLookupResult(state: ServiceLookupState.couldNotSearch);
      expect(result.state, ServiceLookupState.couldNotSearch);
      expect(result.description, isNull);
    });

    test('NextStopResult stores found state with distance', () {
      const result = NextStopResult(
        state: ServiceLookupState.found,
        distanceDescription: '300 metres ahead',
        distanceMetres: 300,
        stopName: 'St Patrick\'s Cathedral',
      );
      expect(result.state, ServiceLookupState.found);
      expect(result.distanceDescription, '300 metres ahead');
      expect(result.distanceMetres, 300);
      expect(result.stopName, contains('Cathedral'));
    });

    test('NextStopResult noneFound for missing coordinates', () {
      const result = NextStopResult(state: ServiceLookupState.noneFound);
      expect(result.state, ServiceLookupState.noneFound);
      expect(result.distanceDescription, isNull);
    });

    test('NextStopResult couldNotSearch for location unavailable', () {
      const result = NextStopResult(state: ServiceLookupState.couldNotSearch);
      expect(result.state, ServiceLookupState.couldNotSearch);
      expect(result.distanceMetres, isNull);
    });
  });

  group('NavigationService — three states produce distinct messages', () {
    // These test the logic that voice_methods uses to produce spoken strings.
    // The actual TTS calls require a device; here we validate the string logic.

    String waterMessage(ServiceLookupState state, {String? description, int? distance, String? landmark}) {
      switch (state) {
        case ServiceLookupState.found:
          final desc = description ?? '${distance ?? 200} metres ahead${landmark != null ? ', near $landmark' : ''}';
          return 'Water — there\'s $desc.';
        case ServiceLookupState.noneFound:
          return 'I checked nearby but couldn\'t find a water source on this stretch.';
        case ServiceLookupState.couldNotSearch:
          return 'I can\'t search for water right now — location or network unavailable.';
      }
    }

    String toiletMessage(ServiceLookupState state, {String? description, int? distance, String? landmark}) {
      switch (state) {
        case ServiceLookupState.found:
          final desc = description ?? '${distance ?? 200} metres ahead${landmark != null ? ', near $landmark' : ''}';
          return 'Toilet — there\'s one $desc.';
        case ServiceLookupState.noneFound:
          return 'I checked nearby but couldn\'t find a toilet on this stretch.';
        case ServiceLookupState.couldNotSearch:
          return 'I can\'t search for toilets right now — location or network unavailable.';
      }
    }

    String nextStopMessage(ServiceLookupState state, {String? distanceDesc}) {
      switch (state) {
        case ServiceLookupState.found:
          return 'The next stop is $distanceDesc.';
        case ServiceLookupState.noneFound:
          return 'I don\'t have location data for the next stop.';
        case ServiceLookupState.couldNotSearch:
          return 'I can\'t check the distance right now — location unavailable.';
      }
    }

    test('water found matches agreed phrasing', () {
      final msg = waterMessage(
        ServiceLookupState.found,
        description: 'a public fountain 200 metres ahead, just past the church',
      );
      expect(msg, 'Water — there\'s a public fountain 200 metres ahead, just past the church.');
    });

    test('water noneFound is distinct from couldNotSearch', () {
      final none = waterMessage(ServiceLookupState.noneFound);
      final cant = waterMessage(ServiceLookupState.couldNotSearch);
      expect(none, isNot(equals(cant)));
      expect(none, contains('couldn\'t find'));
      expect(cant, contains('can\'t search'));
    });

    test('toilet found matches agreed phrasing', () {
      final msg = toiletMessage(
        ServiceLookupState.found,
        description: 'one 150 metres ahead, near the park entrance',
      );
      expect(msg, contains('Toilet'));
      expect(msg, contains('150 metres'));
    });

    test('next stop found matches agreed phrasing', () {
      final msg = nextStopMessage(ServiceLookupState.found, distanceDesc: '300 metres ahead');
      expect(msg, 'The next stop is 300 metres ahead.');
    });

    test('next stop all three states are distinct', () {
      final found = nextStopMessage(ServiceLookupState.found, distanceDesc: '200 metres ahead');
      final none = nextStopMessage(ServiceLookupState.noneFound);
      final cant = nextStopMessage(ServiceLookupState.couldNotSearch);
      expect({found, none, cant}.length, 3); // all distinct
    });

    test('no message contains a reminder promise', () {
      // "I'll remind you when you reach it" is NOT in this task
      final allMessages = [
        waterMessage(ServiceLookupState.found, description: 'a fountain 100 metres ahead'),
        waterMessage(ServiceLookupState.noneFound),
        waterMessage(ServiceLookupState.couldNotSearch),
        toiletMessage(ServiceLookupState.found, description: 'one 200 metres ahead'),
        toiletMessage(ServiceLookupState.noneFound),
        toiletMessage(ServiceLookupState.couldNotSearch),
        nextStopMessage(ServiceLookupState.found, distanceDesc: '300 metres ahead'),
        nextStopMessage(ServiceLookupState.noneFound),
        nextStopMessage(ServiceLookupState.couldNotSearch),
      ];
      for (final msg in allMessages) {
        expect(msg.toLowerCase(), isNot(contains('remind')));
        expect(msg.toLowerCase(), isNot(contains('when you')));
        expect(msg.toLowerCase(), isNot(contains('i\'ll tell you')));
      }
    });
  });

  group('Voice command phrase matching', () {
    // Simulate the matching logic from _processAdvancedCommand
    String? matchCommand(String input) {
      String cmd = input.toLowerCase().trim();
      if (cmd.startsWith('play ')) cmd = cmd.substring(5).trim();

      if (cmd.contains('next tour') || cmd.contains('nexttour') || cmd.contains('next door')) {
        return 'next_tour';
      } else if (cmd.contains('next stop') || cmd.contains('next step') || (cmd.contains('next') && !cmd.contains('tour'))) {
        return 'next_and_play';
      } else if (cmd.contains('previous tour') || cmd.contains('previoustour')) {
        return 'previous_tour';
      } else if (cmd.contains('forward') || (cmd.contains('move') && cmd.contains('forward'))) {
        return 'forward_and_play';
      } else if (cmd.contains('backward') || (cmd.contains('move') && cmd.contains('backward'))) {
        return 'backward_and_play';
      } else if (cmd.contains('previous stop') || cmd.contains('previous step') || (cmd.contains('previous') && !cmd.contains('tour')) || (cmd.contains('back') && !cmd.contains('backward'))) {
        return 'previous_and_play';
      } else if (cmd.contains('repeat')) {
        return 'repeat_and_play';
      } else if (cmd.contains('pause') || cmd.contains('stop')) {
        return 'pause';
      } else if (cmd.contains('water') || cmd.contains('drink') || cmd.contains('fountain')) {
        return 'find_water';
      } else if (cmd.contains('toilet') || cmd.contains('bathroom') || cmd.contains('restroom') || cmd.contains('loo')) {
        return 'find_toilet';
      } else if (cmd.contains('how far') || cmd.contains('distance') || cmd.contains('where am i')) {
        return 'next_stop_distance';
      } else if (cmd.isEmpty || cmd.contains('play')) {
        return 'play';
      } else {
        return 'play'; // unrecognized
      }
    }

    test('water phrases', () {
      expect(matchCommand('water'), 'find_water');
      expect(matchCommand('I need water'), 'find_water');
      expect(matchCommand('where can I get a drink'), 'find_water');
      expect(matchCommand('fountain'), 'find_water');
      expect(matchCommand('is there a drinking fountain'), 'find_water');
    });

    test('toilet phrases', () {
      expect(matchCommand('toilet'), 'find_toilet');
      expect(matchCommand('I need a bathroom'), 'find_toilet');
      expect(matchCommand('where is the restroom'), 'find_toilet');
      expect(matchCommand('loo'), 'find_toilet');
      expect(matchCommand('find me a loo please'), 'find_toilet');
    });

    test('distance phrases', () {
      expect(matchCommand('how far'), 'next_stop_distance');
      expect(matchCommand('how far to go'), 'next_stop_distance');
      expect(matchCommand('distance'), 'next_stop_distance');
      expect(matchCommand('where am i'), 'next_stop_distance');
    });

    test('existing commands still work', () {
      expect(matchCommand('next'), 'next_and_play');
      expect(matchCommand('next stop'), 'next_and_play');
      expect(matchCommand('pause'), 'pause');
      expect(matchCommand('play'), 'play');
      expect(matchCommand('previous'), 'previous_and_play');
      expect(matchCommand('repeat'), 'repeat_and_play');
      expect(matchCommand('next tour'), 'next_tour');
    });
  });
}
