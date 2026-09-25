import 'package:flutter/material.dart';

import '../utils/user_stops.dart';

/// LOCAL-523 — "I will name the stops" loop.
///
/// The generate screen opts a user into naming their own stops. This screen is
/// that loop: an add-one-at-a-time list (reorder + delete), with the LOCAL-521
/// validation warnings shown INLINE as the list is built (AC #3), then a review
/// step, then it pops the ordered stops back so the tour is generated from the
/// user's own selection (AC #2).
///
/// All list rules (add / delete / reorder / renumber / validate) come from
/// `user_stops.dart`, the same pure mechanism the editor's add-a-stop flow uses
/// — one mechanism, never two (D564).
///
/// On confirm it pops a `List<Map<String, dynamic>>` (the ordered stops). On
/// cancel/back it pops `null`, so the caller's default path is untouched
/// (AC #1).
class UserStopsScreen extends StatefulWidget {
  /// Optional starting stops. The generate screen passes any previously entered
  /// stops so re-opening the loop resumes where the user left off.
  ///
  /// Also the test seam (mirrors `EditTourScreen.debugInitialStops`): seeding
  /// stops lets a widget test start with a populated list without driving the
  /// text field through many pumps.
  final List<Map<String, dynamic>>? initialStops;

  const UserStopsScreen({super.key, this.initialStops});

  @override
  State<UserStopsScreen> createState() => _UserStopsScreenState();
}

/// Two phases of the loop: build the list, then review it before generating.
enum _Phase { building, review }

class _UserStopsScreenState extends State<UserStopsScreen> {
  final TextEditingController _entryController = TextEditingController();
  final List<Map<String, dynamic>> _stops = [];
  _Phase _phase = _Phase.building;

  /// Inline warning for the add-entry box, recomputed as the user types.
  StopWarning? _entryWarning;

  @override
  void initState() {
    super.initState();
    if (widget.initialStops != null) {
      _stops.addAll(
        widget.initialStops!.map((s) => Map<String, dynamic>.from(s)),
      );
      renumberStops(_stops);
    }
  }

  @override
  void dispose() {
    _entryController.dispose();
    super.dispose();
  }

  void _onEntryChanged(String value) {
    // Only surface a warning once the user has typed something; an empty box on
    // first paint should not shout at them. Duplicate / max warnings still show.
    setState(() {
      _entryWarning =
          value.trim().isEmpty ? null : validateNewStopEntry(value, _stops);
    });
  }

  void _addCurrentEntry() {
    final text = _entryController.text;
    final warning = validateNewStopEntry(text, _stops);
    if (warning != null) {
      setState(() => _entryWarning = warning);
      return;
    }
    setState(() {
      addStop(_stops, text);
      _entryController.clear();
      _entryWarning = null;
    });
  }

  void _delete(int index) {
    setState(() => removeStopAt(_stops, index));
  }

  void _reorder(int oldIndex, int newIndex) {
    setState(() => reorderStops(_stops, oldIndex, newIndex));
  }

  void _goToReview() {
    if (!isStopListReady(_stops)) return;
    setState(() => _phase = _Phase.review);
  }

  void _backToBuilding() {
    setState(() => _phase = _Phase.building);
  }

  void _confirm() {
    if (!isStopListReady(_stops)) return;
    Navigator.pop(context, List<Map<String, dynamic>>.from(_stops));
  }

  @override
  Widget build(BuildContext context) {
    final listWarnings = validateStopList(_stops);
    return Scaffold(
      appBar: AppBar(
        title: Text(_phase == _Phase.building ? 'Name your stops' : 'Review your stops'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _phase == _Phase.building
          ? _buildBuilding(listWarnings)
          : _buildReview(listWarnings),
    );
  }

  // ── Phase 1: build the list one stop at a time ─────────────────────────────
  Widget _buildBuilding(List<StopWarning> listWarnings) {
    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          color: Colors.blue.shade50,
          child: Text(
            'Add your stops one at a time. Drag to reorder, swipe or tap delete '
            'to remove. When you are happy, review and generate.',
            style: TextStyle(color: Colors.blue.shade800),
          ),
        ),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Expanded(
                child: TextField(
                  controller: _entryController,
                  onChanged: _onEntryChanged,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _addCurrentEntry(),
                  decoration: const InputDecoration(
                    labelText: 'Stop name or description',
                    hintText: 'e.g. "The old lighthouse"',
                    border: OutlineInputBorder(),
                    filled: true,
                    fillColor: Colors.white,
                  ),
                ),
              ),
              const SizedBox(width: 8),
              ElevatedButton.icon(
                onPressed: _addCurrentEntry,
                icon: const Icon(Icons.add),
                label: const Text('Add'),
                style: ElevatedButton.styleFrom(
                  backgroundColor: const Color(0xFF27ae60),
                  foregroundColor: Colors.white,
                  padding: const EdgeInsets.symmetric(vertical: 18, horizontal: 12),
                ),
              ),
            ],
          ),
        ),
        // Inline entry warning (AC #3).
        if (_entryWarning != null)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 8),
            child: _WarningRow(message: _entryWarning!.message),
          ),
        // Inline list-wide warnings (AC #3).
        for (final w in listWarnings)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 0, 16, 4),
            child: _WarningRow(message: w.message),
          ),
        Expanded(
          child: _stops.isEmpty
              ? const Center(
                  child: Text(
                    'No stops yet — add your first one above.',
                    style: TextStyle(color: Colors.grey, fontSize: 16),
                  ),
                )
              : ReorderableListView.builder(
                  itemCount: _stops.length,
                  onReorder: _reorder,
                  itemBuilder: (context, index) {
                    final stop = _stops[index];
                    return Card(
                      key: ValueKey('user-stop-${stop['stop_number']}-${stop['text']}'),
                      margin: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
                      child: ListTile(
                        leading: CircleAvatar(
                          backgroundColor: const Color(0xFF3498db),
                          child: Text('${stop['stop_number']}'),
                        ),
                        title: Text(stop['text'] as String? ?? ''),
                        trailing: Row(
                          mainAxisSize: MainAxisSize.min,
                          children: [
                            IconButton(
                              icon: const Icon(Icons.delete, color: Colors.red),
                              tooltip: 'Delete stop',
                              onPressed: () => _delete(index),
                            ),
                            const Icon(Icons.drag_handle, color: Colors.grey),
                          ],
                        ),
                      ),
                    );
                  },
                ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: () => Navigator.pop(context, null),
                    child: const Text('Cancel'),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: ElevatedButton(
                    onPressed: isStopListReady(_stops) ? _goToReview : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF2c3e50),
                      foregroundColor: Colors.white,
                    ),
                    child: const Text('Review'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }

  // ── Phase 2: review the ordered selection before generating ────────────────
  Widget _buildReview(List<StopWarning> listWarnings) {
    return Column(
      children: [
        Container(
          width: double.infinity,
          padding: const EdgeInsets.all(16),
          color: Colors.green.shade50,
          child: Text(
            'Your tour will be generated from these ${_stops.length} stops, in this order.',
            style: TextStyle(color: Colors.green.shade900, fontWeight: FontWeight.w500),
          ),
        ),
        for (final w in listWarnings)
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 8, 16, 0),
            child: _WarningRow(message: w.message),
          ),
        Expanded(
          child: ListView.builder(
            itemCount: _stops.length,
            itemBuilder: (context, index) {
              final stop = _stops[index];
              return ListTile(
                leading: CircleAvatar(
                  backgroundColor: const Color(0xFF3498db),
                  foregroundColor: Colors.white,
                  child: Text('${stop['stop_number']}'),
                ),
                title: Text(stop['text'] as String? ?? ''),
              );
            },
          ),
        ),
        SafeArea(
          top: false,
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Row(
              children: [
                Expanded(
                  child: OutlinedButton(
                    onPressed: _backToBuilding,
                    child: const Text('Back'),
                  ),
                ),
                const SizedBox(width: 16),
                Expanded(
                  child: ElevatedButton(
                    onPressed: isStopListReady(_stops) ? _confirm : null,
                    style: ElevatedButton.styleFrom(
                      backgroundColor: const Color(0xFF27ae60),
                      foregroundColor: Colors.white,
                    ),
                    child: const Text('Use these stops'),
                  ),
                ),
              ],
            ),
          ),
        ),
      ],
    );
  }
}

class _WarningRow extends StatelessWidget {
  final String message;
  const _WarningRow({required this.message});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Icon(Icons.warning_amber_rounded, color: Colors.orange.shade800, size: 18),
        const SizedBox(width: 6),
        Expanded(
          child: Text(
            message,
            style: TextStyle(color: Colors.orange.shade900, fontSize: 13),
          ),
        ),
      ],
    );
  }
}
