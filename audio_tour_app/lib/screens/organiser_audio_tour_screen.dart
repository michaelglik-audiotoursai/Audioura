// [LOCAL-754B / D658 addendum 2 / D708] Organiser-audio tour builder.
// [LOCAL-758] Rebuilt so stops are OBVIOUS to edit (Michael, 2026-10-24).
//
// The organiser builds a REAL tour from their OWN hosted audio — an RSS feed
// (Import → the episode list) and/or MP3 links (title + https URL). Audioura
// never stores the audio (D658 addendum 2): it links it. Each stop = one audio
// (an episode or a link) + a stop name + an optional location + optional text.
// A walking/biking/driving tour requires a location on every stop; an 'other'
// tour makes it optional. A rights checkbox is required per tour. Publish sends
// everything to POST /communities/<id>/build-audio-tour, which validates every
// audio URL and, on a failure, names the offending stop so this screen can
// point at it. No OpenAI cost; it does not use the generation allowance.
//
// [LOCAL-758] What the review asked for and this screen now does:
//   * Choosing episodes is a CHECKLIST (title · date · duration/size) with
//     "Select none / all"; nothing becomes a stop until ticked + "Add selected".
//   * Each stop is a COLLAPSIBLE card — collapsed shows number, name and a
//     location status (✓ / "Location needed"); expanded shows the editors.
//   * Reorder is by DRAG (ReorderableListView drag handle); the dead up-arrow
//     is gone.
//   * Remove is a LABELLED "Remove stop" text button with a 5 s Undo SnackBar
//     that restores the same stop at the same position — no icon-only destroyer.
//   * The stop name field shows the episode title under it ("Episode: …") and a
//     "Use episode title" button to restore it.
//   * Location is "Use my location", "Pick on map" (a full-screen tappable
//     flutter_map), and "Search address" (OpenStreetMap Nominatim — the same
//     geocoder Home uses). The chosen place shows as text + a small map preview;
//     raw lat/lng live only under "Advanced".
//   * Publish validation names the stop ("Stop 2 'The Trial…' needs a location").

import 'dart:ui' as ui;

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/communities_service.dart';
import '../services/builder_location_provider.dart';

/// [LOCAL-758] The tile provider used by the builder's maps. Production uses the
/// real network tiles (OpenStreetMap). Widget tests swap in
/// [transparentTileProvider] so the map renders without any network — otherwise
/// flutter_map's default provider throws unhandled ClientExceptions in the test
/// zone. This seam keeps the production code path unchanged.
TileProvider builderTileProvider() =>
    _overrideTileProvider ?? NetworkTileProvider();

TileProvider? _overrideTileProvider;

/// Test-only: force the builder's maps to use a network-free tile provider.
/// Pass null to restore the real network provider.
set debugBuilderTileProviderOverride(TileProvider? p) =>
    _overrideTileProvider = p;

/// A TileProvider that serves a single 1×1 transparent tile — no network, no
/// throw. Used by widget tests via [debugBuilderTileProviderOverride].
class TransparentTileProvider extends TileProvider {
  @override
  ImageProvider getImage(TileCoordinates coordinates, TileLayer options) =>
      _TransparentImage();
}

class _TransparentImage extends ImageProvider<_TransparentImage> {
  @override
  Future<_TransparentImage> obtainKey(ImageConfiguration configuration) =>
      SynchronousFuture<_TransparentImage>(this);

  @override
  ImageStreamCompleter loadImage(
      _TransparentImage key, ImageDecoderCallback decode) {
    return OneFrameImageStreamCompleter(_frame());
  }

  Future<ImageInfo> _frame() async {
    final recorder = ui.PictureRecorder();
    ui.Canvas(recorder);
    final image = await recorder.endRecording().toImage(1, 1);
    return ImageInfo(image: image);
  }

  @override
  bool operator ==(Object other) => other is _TransparentImage;

  @override
  int get hashCode => 0;
}

/// One draft stop in the builder: an audio URL, a name, an optional location,
/// and optional text. Backed by controllers so edits persist across rebuilds.
class _DraftStop {
  final TextEditingController name;
  final TextEditingController audioUrl;
  final TextEditingController lat;
  final TextEditingController lng;
  final TextEditingController text;

  /// [LOCAL-758] The episode title this stop came from, so "Use episode title"
  /// can restore it after the organiser edits the name. Empty for a bare link.
  final String episodeTitle;

  /// [LOCAL-758] A human label for the chosen place ("My location", an address),
  /// shown instead of raw numbers. Null until a location is set.
  String? placeLabel;

  /// [LOCAL-758] Each stop is collapsible; this holds its expand/collapse state.
  bool expanded;

  /// [LOCAL-758] A stable key so ReorderableListView and Undo keep identity.
  final Key key;

  _DraftStop({
    String name = '',
    String audioUrl = '',
    String lat = '',
    String lng = '',
    String text = '',
    this.episodeTitle = '',
    this.expanded = false,
    Key? key,
  })  : name = TextEditingController(text: name),
        audioUrl = TextEditingController(text: audioUrl),
        lat = TextEditingController(text: lat),
        lng = TextEditingController(text: lng),
        text = TextEditingController(text: text),
        key = key ?? UniqueKey();

  bool get hasLocation =>
      double.tryParse(lat.text.trim()) != null &&
      double.tryParse(lng.text.trim()) != null;

  void setPlace(double latV, double lngV, String? label) {
    lat.text = latV.toStringAsFixed(6);
    lng.text = lngV.toStringAsFixed(6);
    placeLabel = label;
  }

  void dispose() {
    name.dispose();
    audioUrl.dispose();
    lat.dispose();
    lng.dispose();
    text.dispose();
  }

  Map<String, dynamic> toJson() {
    final latV = double.tryParse(lat.text.trim());
    final lngV = double.tryParse(lng.text.trim());
    return {
      'name': name.text.trim(),
      'audio_url': audioUrl.text.trim(),
      if (latV != null) 'lat': latV,
      if (lngV != null) 'lng': lngV,
      'text': text.text.trim(),
    };
  }
}

/// [LOCAL-758] A ticked/unticked episode in the import checklist. Nothing here
/// becomes a stop until the organiser ticks it and taps "Add selected".
class _EpisodeChoice {
  final String title;
  final String audioUrl;
  final String meta; // "date · duration · size"
  final String? description;
  bool selected = false;

  _EpisodeChoice({
    required this.title,
    required this.audioUrl,
    this.meta = '',
    this.description,
  });
}

class OrganiserAudioTourScreen extends StatefulWidget {
  final Community community;

  /// [LOCAL-755 / D709] When editing an EXISTING organiser-audio tour, its
  /// server tour id. On publish the builder sends `tour_id` so the server
  /// replaces it in place, and shows the "I changed this tour — tell my members"
  /// checkbox: ticked → the version is bumped and members see "Updated by the
  /// organiser — Re-download" (opt-in; never pushed); unticked → a silent save
  /// (typo fix) that leaves the version unchanged. Null for a brand-new tour.
  final int? editTourId;

  /// [LOCAL-758] Injected so widget tests can drive "Use my location" and
  /// address search with a fake — no device, no network. Defaults to the real
  /// geolocator + Nominatim provider.
  final BuilderLocationProvider locationProvider;

  const OrganiserAudioTourScreen({
    super.key,
    required this.community,
    this.editTourId,
    this.locationProvider = const BuilderLocationProvider(),
  });

  @override
  State<OrganiserAudioTourScreen> createState() =>
      _OrganiserAudioTourScreenState();
}

class _OrganiserAudioTourScreenState extends State<OrganiserAudioTourScreen> {
  final _tourName = TextEditingController();
  final _feedUrl = TextEditingController();
  final _linkTitle = TextEditingController();
  final _linkUrl = TextEditingController();

  String _tourType = 'walking';
  String _visibility = 'members';
  bool _rightsAccepted = false;
  // [LOCAL-755 / D709] EDIT only — "I changed this tour — tell my members".
  bool _notifyMembers = false;
  bool _busy = false;
  String? _error;
  String? _failingStop;

  // [LOCAL-758] The import checklist (ticked ones become stops) and the stops.
  final List<_EpisodeChoice> _choices = [];
  final List<_DraftStop> _stops = [];

  static const _tourTypes = ['walking', 'biking', 'driving', 'museum', 'other'];

  bool get _needsLocation =>
      _tourType == 'walking' || _tourType == 'biking' || _tourType == 'driving';

  @override
  void initState() {
    super.initState();
    // [LOCAL-758] Seed the CHECKLIST from the community's existing episodes.
    // Nothing becomes a stop until the organiser ticks it (Michael: "Nothing
    // becomes a stop without being ticked").
    _loadChoices(widget.community.episodes);
  }

  void _loadChoices(List<CommunityEpisode> episodes) {
    final seen = _choices.map((c) => c.audioUrl).toSet();
    for (final e in episodes) {
      if (e.audioUrl.isEmpty || seen.contains(e.audioUrl)) continue;
      _choices.add(_EpisodeChoice(
        title: e.title,
        audioUrl: e.audioUrl,
        meta: e.metaLine,
        description: e.description,
      ));
      seen.add(e.audioUrl);
    }
  }

  @override
  void dispose() {
    _tourName.dispose();
    _feedUrl.dispose();
    _linkTitle.dispose();
    _linkUrl.dispose();
    for (final s in _stops) {
      s.dispose();
    }
    super.dispose();
  }

  Future<String?> _userId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('user_id');
  }

  Future<void> _importFeed() async {
    final url = _feedUrl.text.trim();
    if (url.isEmpty) return;
    setState(() => _busy = true);
    final userId = await _userId();
    final ok = userId != null &&
        await CommunitiesService.importFeed(widget.community.id, userId,
            feedUrl: url);
    if (!mounted) return;
    if (ok) {
      // Re-fetch the community so the newly imported episodes appear, then add
      // any we do not already have to the CHECKLIST (not straight to stops).
      final refreshed =
          await CommunitiesService.get(widget.community.id, userId: userId);
      if (refreshed != null) {
        _loadChoices(refreshed.episodes);
      }
    }
    setState(() {
      _busy = false;
      _error = ok ? null : 'Could not import that feed.';
    });
  }

  // --- Checklist → stops ----------------------------------------------------

  void _setAllSelected(bool v) {
    setState(() {
      for (final c in _choices) {
        c.selected = v;
      }
    });
  }

  void _addSelected() {
    final picked = _choices.where((c) => c.selected).toList();
    if (picked.isEmpty) return;
    setState(() {
      for (final c in picked) {
        _stops.add(_DraftStop(
          name: c.title,
          audioUrl: c.audioUrl,
          episodeTitle: c.title,
          text: c.description ?? '',
          expanded: false,
        ));
      }
      // Ticked episodes are now stops — remove them from the checklist so they
      // are not added twice.
      _choices.removeWhere((c) => c.selected);
    });
  }

  void _addLink() {
    final title = _linkTitle.text.trim();
    final url = _linkUrl.text.trim();
    if (url.isEmpty) return;
    setState(() {
      _stops.add(_DraftStop(
        name: title.isEmpty ? 'Stop ${_stops.length + 1}' : title,
        audioUrl: url,
        episodeTitle: title,
        expanded: true,
      ));
      _linkTitle.clear();
      _linkUrl.clear();
    });
  }

  // --- Remove + Undo --------------------------------------------------------

  void _removeStop(int i) {
    if (i < 0 || i >= _stops.length) return;
    final removed = _stops[i];
    final name = removed.name.text.trim();
    setState(() => _stops.removeAt(i));
    final messenger = ScaffoldMessenger.of(context);
    messenger.clearSnackBars();
    messenger.showSnackBar(
      SnackBar(
        duration: const Duration(seconds: 5),
        content: Text(
            'Removed ${name.isEmpty ? 'the stop' : '"$name"'}.'),
        action: SnackBarAction(
          label: 'Undo',
          onPressed: () {
            // Restore the SAME stop object at the SAME position.
            setState(() {
              final at = i.clamp(0, _stops.length);
              _stops.insert(at, removed);
            });
          },
        ),
      ),
    );
  }

  void _reorder(int oldIndex, int newIndex) {
    setState(() {
      if (newIndex > oldIndex) newIndex -= 1;
      final s = _stops.removeAt(oldIndex);
      _stops.insert(newIndex, s);
    });
  }

  // --- Location -------------------------------------------------------------

  Future<void> _useMyLocation(_DraftStop s) async {
    setState(() => _busy = true);
    final place = await widget.locationProvider.currentLocation();
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (place != null) {
        s.setPlace(place.latitude, place.longitude,
            place.label ?? 'My location');
      } else {
        _error = 'Could not get your location. Check location permission, or '
            'pick on the map.';
      }
    });
  }

  Future<void> _searchAddress(_DraftStop s, String query) async {
    if (query.trim().isEmpty) return;
    setState(() => _busy = true);
    final place = await widget.locationProvider.geocode(query);
    if (!mounted) return;
    setState(() {
      _busy = false;
      if (place != null) {
        s.setPlace(place.latitude, place.longitude, place.label ?? query.trim());
      } else {
        _error = 'No place found for "$query". Try a different address, or pick '
            'on the map.';
      }
    });
  }

  Future<void> _pickOnMap(_DraftStop s) async {
    final initial =
        s.hasLocation ? LatLng(
            double.parse(s.lat.text.trim()), double.parse(s.lng.text.trim()))
        : null;
    final result = await Navigator.of(context).push<LatLng>(
      MaterialPageRoute(
        builder: (_) => _MapPickerScreen(initial: initial),
      ),
    );
    if (result != null && mounted) {
      setState(() {
        s.setPlace(result.latitude, result.longitude,
            'Pinned on map (${result.latitude.toStringAsFixed(4)}, '
            '${result.longitude.toStringAsFixed(4)})');
      });
    }
  }

  // --- Validation + publish -------------------------------------------------

  String? _clientValidate() {
    if (_tourName.text.trim().isEmpty) return 'Give the tour a name.';
    if (_stops.isEmpty) return 'Add at least one stop.';
    for (var i = 0; i < _stops.length; i++) {
      final s = _stops[i];
      final label = "Stop ${i + 1} '${s.name.text.trim()}'";
      if (s.name.text.trim().isEmpty) return 'Stop ${i + 1} needs a name.';
      if (s.audioUrl.text.trim().isEmpty) return '$label has no audio.';
      if (_needsLocation && !s.hasLocation) {
        return '$label needs a location for a $_tourType tour.';
      }
    }
    if (!_rightsAccepted) {
      return 'Confirm you have the right to publish this audio.';
    }
    return null;
  }

  Future<void> _publish() async {
    setState(() {
      _error = null;
      _failingStop = null;
    });
    final clientError = _clientValidate();
    if (clientError != null) {
      setState(() => _error = clientError);
      return;
    }
    setState(() => _busy = true);
    final userId = await _userId();
    if (userId == null) {
      setState(() {
        _busy = false;
        _error = 'Could not identify this device.';
      });
      return;
    }
    final body = {
      'user_id': userId,
      'tour_name': _tourName.text.trim(),
      'tour_type': _tourType,
      'visibility': _visibility,
      'rights_accepted': _rightsAccepted,
      'stops': _stops.map((s) => s.toJson()).toList(),
    };
    if (widget.editTourId != null) {
      body['tour_id'] = widget.editTourId as Object;
      body['notify_members'] = _notifyMembers;
    }
    final result =
        await CommunitiesService.buildAudioTour(widget.community.id, body);
    if (!mounted) return;
    if (result.ok) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Tour published to your community.')),
      );
      Navigator.of(context).pop(true);
      return;
    }
    setState(() {
      _busy = false;
      _failingStop = result.stopName;
      _error = result.message ?? 'Could not publish the tour.';
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
          title: Text(widget.editTourId != null
              ? 'Edit your audio tour'
              : 'Make a tour from your audio')),
      body: AbsorbPointer(
        absorbing: _busy,
        child: ListView(
          padding: const EdgeInsets.all(16),
          children: [
            TextField(
              controller: _tourName,
              decoration: const InputDecoration(
                  labelText: 'Tour name', border: OutlineInputBorder()),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                const Text('Type: '),
                const SizedBox(width: 8),
                DropdownButton<String>(
                  value: _tourType,
                  items: _tourTypes
                      .map((t) =>
                          DropdownMenuItem(value: t, child: Text(t)))
                      .toList(),
                  onChanged: (v) =>
                      setState(() => _tourType = v ?? 'walking'),
                ),
                const Spacer(),
                const Text('Visibility: '),
                DropdownButton<String>(
                  value: _visibility,
                  items: const [
                    DropdownMenuItem(value: 'members', child: Text('Members')),
                    DropdownMenuItem(value: 'public', child: Text('Public')),
                  ],
                  onChanged: (v) =>
                      setState(() => _visibility = v ?? 'members'),
                ),
              ],
            ),
            const Divider(height: 28),

            // Audio sources.
            const Text('Audio source',
                style: TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 6),
            TextField(
              controller: _feedUrl,
              decoration: InputDecoration(
                labelText: 'RSS feed URL',
                border: const OutlineInputBorder(),
                suffixIcon: TextButton(
                  onPressed: _busy ? null : _importFeed,
                  child: const Text('Import'),
                ),
              ),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _linkTitle,
                    decoration: const InputDecoration(
                        labelText: 'Link title', border: OutlineInputBorder()),
                  ),
                ),
                const SizedBox(width: 8),
                Expanded(
                  flex: 2,
                  child: TextField(
                    controller: _linkUrl,
                    decoration: const InputDecoration(
                        labelText: 'MP3 URL (https)',
                        border: OutlineInputBorder()),
                  ),
                ),
                IconButton(
                  onPressed: _busy ? null : _addLink,
                  icon: const Icon(Icons.add_circle_outline),
                  tooltip: 'Add this link as a stop',
                ),
              ],
            ),
            const Divider(height: 28),

            // [LOCAL-758] The episode CHECKLIST.
            _buildChecklist(),

            const Divider(height: 28),

            // Stops.
            Row(
              children: [
                Text('Stops (${_stops.length})',
                    style: const TextStyle(fontWeight: FontWeight.bold)),
              ],
            ),
            if (_needsLocation)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text(
                    'A walking/biking/driving tour needs a location on every stop.',
                    style: TextStyle(fontSize: 12, color: Colors.black54)),
              ),
            if (_stops.isEmpty)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 12),
                child: Text(
                    'No stops yet. Tick episodes above and tap "Add selected", '
                    'or add an MP3 link.',
                    style: TextStyle(color: Colors.black54)),
              )
            else
              ReorderableListView.builder(
                shrinkWrap: true,
                physics: const NeverScrollableScrollPhysics(),
                buildDefaultDragHandles: false,
                itemCount: _stops.length,
                onReorder: _reorder,
                itemBuilder: (context, i) => _stopCard(i, _stops[i]),
              ),

            const SizedBox(height: 16),

            // Rights.
            CheckboxListTile(
              value: _rightsAccepted,
              onChanged: (v) => setState(() => _rightsAccepted = v ?? false),
              controlAffinity: ListTileControlAffinity.leading,
              title: const Text(
                  'I have the right to publish this audio to my members.'),
            ),

            if (widget.editTourId != null)
              CheckboxListTile(
                value: _notifyMembers,
                onChanged: (v) => setState(() => _notifyMembers = v ?? false),
                controlAffinity: ListTileControlAffinity.leading,
                title: const Text('I changed this tour — tell my members.'),
                subtitle: const Text(
                    'Members will be offered a re-download. Leave unticked for a '
                    'silent fix (e.g. a typo).'),
              ),

            if (_error != null)
              Padding(
                padding: const EdgeInsets.only(top: 8),
                child: Text(
                  _failingStop != null
                      ? 'Problem with "$_failingStop": $_error'
                      : _error!,
                  style: const TextStyle(color: Colors.redAccent),
                ),
              ),

            const SizedBox(height: 12),
            FilledButton.icon(
              onPressed: _busy ? null : _publish,
              icon: _busy
                  ? const SizedBox(
                      width: 16,
                      height: 16,
                      child: CircularProgressIndicator(strokeWidth: 2))
                  : const Icon(Icons.publish),
              label: Text(_busy ? 'Publishing…' : 'Publish'),
            ),
            const SizedBox(height: 32),
          ],
        ),
      ),
    );
  }

  Widget _buildChecklist() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            const Expanded(
              child: Text('Choose episodes',
                  style: TextStyle(fontWeight: FontWeight.bold)),
            ),
            if (_choices.isNotEmpty) ...[
              TextButton(
                onPressed: () => _setAllSelected(false),
                child: const Text('Select none'),
              ),
              TextButton(
                onPressed: () => _setAllSelected(true),
                child: const Text('Select all'),
              ),
            ],
          ],
        ),
        if (_choices.isEmpty)
          const Padding(
            padding: EdgeInsets.symmetric(vertical: 8),
            child: Text(
                'Import a feed or add an MP3 link to choose episodes.',
                style: TextStyle(color: Colors.black54)),
          )
        else ...[
          const Text('Ticked episodes become stops, in feed order.',
              style: TextStyle(fontSize: 12, color: Colors.black54)),
          const SizedBox(height: 4),
          ..._choices.asMap().entries.map((e) {
            final c = e.value;
            return CheckboxListTile(
              key: ValueKey('choice_${c.audioUrl}'),
              value: c.selected,
              onChanged: (v) => setState(() => c.selected = v ?? false),
              controlAffinity: ListTileControlAffinity.leading,
              dense: true,
              title: Text(c.title),
              subtitle: c.meta.isEmpty ? null : Text(c.meta),
            );
          }),
          const SizedBox(height: 8),
          Align(
            alignment: Alignment.centerLeft,
            child: ElevatedButton.icon(
              onPressed:
                  _choices.any((c) => c.selected) ? _addSelected : null,
              icon: const Icon(Icons.playlist_add),
              label: const Text('Add selected'),
            ),
          ),
        ],
      ],
    );
  }

  Widget _stopCard(int i, _DraftStop s) {
    final locationOk = s.hasLocation;
    final statusText = locationOk
        ? (s.placeLabel ?? 'Location set')
        : (_needsLocation ? 'Location needed' : 'No location (optional)');
    final statusColor = locationOk
        ? Colors.green.shade700
        : (_needsLocation ? Colors.redAccent : Colors.black54);
    final statusIcon = locationOk ? Icons.check_circle : Icons.location_off;

    return Card(
      key: s.key,
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Collapsed header: number, name, location status, drag handle.
          ListTile(
            leading: CircleAvatar(radius: 14, child: Text('${i + 1}')),
            title: Text(
              s.name.text.trim().isEmpty
                  ? 'Stop ${i + 1}'
                  : s.name.text.trim(),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            subtitle: Row(
              children: [
                Icon(statusIcon, size: 14, color: statusColor),
                const SizedBox(width: 4),
                Expanded(
                  child: Text('Stop ${i + 1} · $statusText',
                      maxLines: 1,
                      overflow: TextOverflow.ellipsis,
                      style: TextStyle(fontSize: 12, color: statusColor)),
                ),
              ],
            ),
            trailing: Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                ReorderableDragStartListener(
                  index: i,
                  child: const Tooltip(
                    message: 'Drag to reorder',
                    child: Padding(
                      padding: EdgeInsets.all(8),
                      child: Icon(Icons.drag_handle),
                    ),
                  ),
                ),
                Icon(s.expanded ? Icons.expand_less : Icons.expand_more),
              ],
            ),
            onTap: () => setState(() => s.expanded = !s.expanded),
          ),
          if (s.expanded) _stopEditor(i, s),
        ],
      ),
    );
  }

  Widget _stopEditor(int i, _DraftStop s) {
    return Padding(
      padding: const EdgeInsets.fromLTRB(12, 0, 12, 12),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Name + episode title + "Use episode title".
          TextField(
            controller: s.name,
            decoration: const InputDecoration(
                labelText: 'Stop name', isDense: true),
            onChanged: (_) => setState(() {}),
          ),
          if (s.episodeTitle.isNotEmpty)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                children: [
                  Expanded(
                    child: Text('Episode: ${s.episodeTitle}',
                        style: const TextStyle(
                            fontSize: 12, color: Colors.black54)),
                  ),
                  TextButton(
                    onPressed: () => setState(() {
                      s.name.text = s.episodeTitle;
                    }),
                    child: const Text('Use episode title'),
                  ),
                ],
              ),
            ),
          const SizedBox(height: 8),

          // Location block.
          const Text('Location',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
          const SizedBox(height: 4),
          Wrap(
            spacing: 8,
            runSpacing: 4,
            children: [
              OutlinedButton.icon(
                onPressed: () => _useMyLocation(s),
                icon: const Icon(Icons.my_location, size: 18),
                label: const Text('Use my location'),
              ),
              OutlinedButton.icon(
                onPressed: () => _pickOnMap(s),
                icon: const Icon(Icons.location_pin, size: 18),
                label: const Text('Pick on map'),
              ),
            ],
          ),
          const SizedBox(height: 8),
          TextField(
            decoration: const InputDecoration(
              labelText: 'Search address',
              isDense: true,
              prefixIcon: Icon(Icons.search),
              border: OutlineInputBorder(),
            ),
            textInputAction: TextInputAction.search,
            onSubmitted: (v) => _searchAddress(s, v),
          ),

          // Chosen place + small map preview.
          if (s.hasLocation) ...[
            const SizedBox(height: 8),
            Row(
              children: [
                const Icon(Icons.check_circle, size: 16, color: Colors.green),
                const SizedBox(width: 6),
                Expanded(
                  child: Text(s.placeLabel ?? 'Location set',
                      style: const TextStyle(fontSize: 13)),
                ),
              ],
            ),
            const SizedBox(height: 6),
            SizedBox(
              height: 120,
              child: ClipRRect(
                borderRadius: BorderRadius.circular(8),
                child: _miniMap(LatLng(double.parse(s.lat.text.trim()),
                    double.parse(s.lng.text.trim()))),
              ),
            ),
          ],

          // Advanced: raw lat/lng.
          ExpansionTile(
            tilePadding: EdgeInsets.zero,
            childrenPadding: EdgeInsets.zero,
            title: const Text('Advanced',
                style: TextStyle(fontSize: 13, color: Colors.black54)),
            children: [
              Row(
                children: [
                  Expanded(
                    child: TextField(
                      controller: s.lat,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true, signed: true),
                      decoration: const InputDecoration(
                          labelText: 'Latitude', isDense: true),
                      onChanged: (_) => setState(() => s.placeLabel = null),
                    ),
                  ),
                  const SizedBox(width: 8),
                  Expanded(
                    child: TextField(
                      controller: s.lng,
                      keyboardType: const TextInputType.numberWithOptions(
                          decimal: true, signed: true),
                      decoration: const InputDecoration(
                          labelText: 'Longitude', isDense: true),
                      onChanged: (_) => setState(() => s.placeLabel = null),
                    ),
                  ),
                ],
              ),
              TextField(
                controller: s.audioUrl,
                decoration: const InputDecoration(
                    labelText: 'Audio URL', isDense: true),
              ),
            ],
          ),

          const SizedBox(height: 4),
          TextField(
            controller: s.text,
            maxLines: 2,
            decoration: const InputDecoration(
                labelText: 'Notes / text (optional)', isDense: true),
          ),
          const SizedBox(height: 4),

          // Remove as a LABELLED destructive text button.
          Align(
            alignment: Alignment.centerRight,
            child: TextButton.icon(
              onPressed: () => _removeStop(i),
              icon: const Icon(Icons.delete_outline, size: 18),
              label: const Text('Remove stop'),
              style: TextButton.styleFrom(foregroundColor: Colors.redAccent),
            ),
          ),
        ],
      ),
    );
  }

  Widget _miniMap(LatLng point) {
    return FlutterMap(
      options: MapOptions(
        initialCenter: point,
        initialZoom: 14,
        interactionOptions:
            const InteractionOptions(flags: InteractiveFlag.none),
      ),
      children: [
        TileLayer(
          urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
          userAgentPackageName: 'com.audioura.audiotours',
          tileProvider: builderTileProvider(),
        ),
        MarkerLayer(
          markers: [
            Marker(
              point: point,
              width: 30,
              height: 30,
              child: const Icon(Icons.location_pin,
                  color: Colors.redAccent, size: 30),
            ),
          ],
        ),
      ],
    );
  }
}

/// [LOCAL-758] Full-screen map; tap to drop the pin, confirm to return the
/// chosen LatLng. Reuses the app's flutter_map + OpenStreetMap tiles (the same
/// stack tour_map_screen uses).
class _MapPickerScreen extends StatefulWidget {
  final LatLng? initial;
  const _MapPickerScreen({this.initial});

  @override
  State<_MapPickerScreen> createState() => _MapPickerScreenState();
}

class _MapPickerScreenState extends State<_MapPickerScreen> {
  final MapController _controller = MapController();
  LatLng? _picked;

  @override
  void initState() {
    super.initState();
    _picked = widget.initial;
  }

  @override
  Widget build(BuildContext context) {
    final center = _picked ?? widget.initial ?? const LatLng(42.5195, -70.8967);
    return Scaffold(
      appBar: AppBar(
        title: const Text('Pick the stop on the map'),
        actions: [
          TextButton(
            onPressed:
                _picked == null ? null : () => Navigator.of(context).pop(_picked),
            child: Text('Use this pin',
                style: TextStyle(
                    color: _picked == null ? Colors.white38 : Colors.white)),
          ),
        ],
      ),
      body: Stack(
        children: [
          FlutterMap(
            mapController: _controller,
            options: MapOptions(
              initialCenter: center,
              initialZoom: 13,
              onTap: (_, latLng) => setState(() => _picked = latLng),
            ),
            children: [
              TileLayer(
                urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                userAgentPackageName: 'com.audioura.audiotours',
                tileProvider: builderTileProvider(),
              ),
              if (_picked != null)
                MarkerLayer(
                  markers: [
                    Marker(
                      point: _picked!,
                      width: 40,
                      height: 40,
                      child: const Icon(Icons.location_pin,
                          color: Colors.redAccent, size: 40),
                    ),
                  ],
                ),
            ],
          ),
          const Positioned(
            top: 12,
            left: 12,
            right: 12,
            child: Card(
              child: Padding(
                padding: EdgeInsets.all(10),
                child: Text('Tap the map to drop the pin, then "Use this pin".',
                    textAlign: TextAlign.center),
              ),
            ),
          ),
        ],
      ),
    );
  }
}
