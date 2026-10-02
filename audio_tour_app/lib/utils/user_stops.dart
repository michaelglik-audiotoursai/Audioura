// LOCAL-523 — The one mechanism for building a user's own stop list.
//
// Michael's ask: "an Audioura Mobile application loop for the user to enter the
// stops one by one, then present with the user's own selection, then generate
// the tour based on these stops."
//
// D564 (one mechanism, never two): the editor already grows a stop list one row
// at a time — `_addNewStop` / `_reorderStops` in `edit_tour_screen.dart`. Rather
// than write a second, subtly different list manager for the pre-generation
// loop, the *rules* of that mechanism live here as pure functions:
//
//   • a stop is the same `Map<String, dynamic>` shape the editor uses
//     ({stop_number, title, text, action, ...});
//   • adding appends then renumbers;
//   • deleting removes then renumbers;
//   • reordering moves then renumbers;
//   • `stop_number`, `title` ("Stop N") and `audio_file` ("audio_N.mp3") are
//     always kept consistent with list position — exactly as the editor does.
//
// Keeping the rules pure (no widgets, no I/O) means both the editor-style add
// loop and the new `UserStopsScreen` call the SAME code, and the whole loop is
// unit-testable without pumping a widget (AC #4).
//
// Inline validation (AC #3): the warnings LOCAL-521 shows are computed here and
// rendered INLINE by the screen as the user types / builds the list — never
// deferred to a post-generate error.

/// Bounds mirror the generate screen's "Number of stops (1-30)" field so a
/// user-named list can never ask the backend for something the free-text path
/// would reject.
const int kMinUserStops = 1;
const int kMaxUserStops = 30;

/// Build a fresh stop map for [text] at the end of a list of [existingCount]
/// stops. Shape matches the editor's `_addNewStop` (LOCAL-477): `action: 'add'`,
/// consistent `title`/`audio_file`. The number is provisional — [renumberStops]
/// makes it authoritative once the stop is in the list.
Map<String, dynamic> buildUserStop(String text, {required int existingCount}) {
  final number = existingCount + 1;
  return <String, dynamic>{
    'stop_number': number,
    'title': 'Stop $number',
    'text': text.trim(),
    'audio_file': 'audio_$number.mp3',
    'editable': true,
    'action': 'add',
  };
}

/// Renumber [stops] in place so `stop_number`, `title` and `audio_file` follow
/// 1-based list position. This is the invariant the editor restores after every
/// reorder (`_reorderStops`); centralising it means add/delete/reorder can never
/// drift out of sync.
void renumberStops(List<Map<String, dynamic>> stops) {
  for (var i = 0; i < stops.length; i++) {
    final n = i + 1;
    stops[i]['stop_number'] = n;
    stops[i]['title'] = 'Stop $n';
    stops[i]['audio_file'] = 'audio_$n.mp3';
  }
}

/// Append a stop for [text] and renumber. Returns the new list (also mutates
/// [stops] so callers using `setState` on the same reference see the change).
/// Blank / whitespace-only text is rejected — the caller shows the inline
/// warning instead of storing an empty stop.
List<Map<String, dynamic>> addStop(
  List<Map<String, dynamic>> stops,
  String text,
) {
  if (text.trim().isEmpty) return stops;
  stops.add(buildUserStop(text, existingCount: stops.length));
  renumberStops(stops);
  return stops;
}

/// Remove the stop at [index] and renumber. Out-of-range indices are ignored.
List<Map<String, dynamic>> removeStopAt(
  List<Map<String, dynamic>> stops,
  int index,
) {
  if (index < 0 || index >= stops.length) return stops;
  stops.removeAt(index);
  renumberStops(stops);
  return stops;
}

/// Move a stop from [oldIndex] to [newIndex] and renumber. Uses the same index
/// adjustment Flutter's `ReorderableListView.onReorder` needs (and that the
/// editor's `_reorderStops` applies), so the screen can wire this straight to
/// the callback.
List<Map<String, dynamic>> reorderStops(
  List<Map<String, dynamic>> stops,
  int oldIndex,
  int newIndex,
) {
  if (oldIndex < 0 || oldIndex >= stops.length) return stops;
  var target = newIndex;
  if (oldIndex < target) target -= 1;
  if (target < 0) target = 0;
  if (target > stops.length - 1) target = stops.length - 1;
  final moved = stops.removeAt(oldIndex);
  stops.insert(target, moved);
  renumberStops(stops);
  return stops;
}

/// A single inline warning about a proposed / existing stop entry.
///
/// [field] is `'entry'` for the "type a stop, press add" box and `'list'` for
/// list-wide problems (too few / too many). The screen decides where to paint
/// it; keeping it a value keeps validation testable.
class StopWarning {
  final String field;
  final String message;
  const StopWarning(this.field, this.message);

  @override
  bool operator ==(Object other) =>
      other is StopWarning &&
      other.field == field &&
      other.message == message;

  @override
  int get hashCode => Object.hash(field, message);

  @override
  String toString() => 'StopWarning($field, $message)';
}

/// Validate the text the user is about to add (LOCAL-521 rules, shown INLINE as
/// they type — AC #3). Returns `null` when [candidate] is a fine new stop.
///
/// Rules:
///   • empty / whitespace-only → warn (don't add an empty stop);
///   • duplicate of an existing stop's text (case-insensitive, trimmed) → warn;
///   • adding would exceed [kMaxUserStops] → warn.
StopWarning? validateNewStopEntry(
  String candidate,
  List<Map<String, dynamic>> existing,
) {
  final trimmed = candidate.trim();
  if (trimmed.isEmpty) {
    return const StopWarning('entry', 'Enter a name for the stop before adding it.');
  }
  final lower = trimmed.toLowerCase();
  final isDuplicate = existing.any(
    (s) => (s['text'] as String? ?? '').trim().toLowerCase() == lower,
  );
  if (isDuplicate) {
    return const StopWarning('entry', 'That stop is already in your list.');
  }
  if (existing.length >= kMaxUserStops) {
    return const StopWarning('entry', "You've reached the maximum of $kMaxUserStops stops.");
  }
  return null;
}

/// Validate the whole list before it may be reviewed / used to generate
/// (AC #2, #3). Returns every applicable warning so they can all be shown
/// inline at once; an empty list means "good to generate".
List<StopWarning> validateStopList(List<Map<String, dynamic>> stops) {
  final warnings = <StopWarning>[];
  if (stops.length < kMinUserStops) {
    warnings.add(const StopWarning('list', 'Add at least one stop before generating.'));
  }
  if (stops.length > kMaxUserStops) {
    warnings.add(const StopWarning('list', 'Remove stops — the maximum is $kMaxUserStops.'));
  }
  // Any blank stop that slipped in (defensive: addStop rejects blanks).
  final hasBlank = stops.any((s) => (s['text'] as String? ?? '').trim().isEmpty);
  if (hasBlank) {
    warnings.add(const StopWarning('list', 'One or more stops have no name.'));
  }
  // Duplicate names anywhere in the list.
  final seen = <String>{};
  var hasDuplicate = false;
  for (final s in stops) {
    final key = (s['text'] as String? ?? '').trim().toLowerCase();
    if (key.isEmpty) continue;
    if (!seen.add(key)) hasDuplicate = true;
  }
  if (hasDuplicate) {
    warnings.add(const StopWarning('list', 'Two or more stops have the same name.'));
  }
  return warnings;
}

/// True when [stops] is a valid, ready-to-generate list (no warnings).
bool isStopListReady(List<Map<String, dynamic>> stops) =>
    validateStopList(stops).isEmpty;

/// The ordered list of stop names to hand to tour generation. This is the
/// "user's own selection" the tour is generated from.
List<String> stopTitlesForGeneration(List<Map<String, dynamic>> stops) =>
    stops.map((s) => (s['text'] as String? ?? '').trim()).toList();
