// [LOCAL-754B / D658 addendum 2 / D708] Organiser-audio tour builder.
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
// On Listen the built tour is indistinguishable from a generated one — the
// server builds the SAME package (shared renderer, map buttons, voice control)
// with a remote_audio.json the phone resolves to audio_N.mp3 on download.

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../services/communities_service.dart';

/// One draft stop in the builder: an audio URL, a name, an optional location,
/// and optional text. Backed by controllers so edits persist across rebuilds.
class _DraftStop {
  final TextEditingController name;
  final TextEditingController audioUrl;
  final TextEditingController lat;
  final TextEditingController lng;
  final TextEditingController text;

  _DraftStop({
    String name = '',
    String audioUrl = '',
    String lat = '',
    String lng = '',
    String text = '',
  })  : name = TextEditingController(text: name),
        audioUrl = TextEditingController(text: audioUrl),
        lat = TextEditingController(text: lat),
        lng = TextEditingController(text: lng),
        text = TextEditingController(text: text);

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

class OrganiserAudioTourScreen extends StatefulWidget {
  final Community community;

  const OrganiserAudioTourScreen({super.key, required this.community});

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
  bool _busy = false;
  String? _error;
  String? _failingStop;

  final List<_DraftStop> _stops = [];

  static const _tourTypes = ['walking', 'biking', 'driving', 'museum', 'other'];

  bool get _needsLocation =>
      _tourType == 'walking' || _tourType == 'biking' || _tourType == 'driving';

  @override
  void initState() {
    super.initState();
    // Seed stops from the community's existing episodes (the organiser can edit
    // names / add locations / remove any before publishing).
    for (final e in widget.community.episodes) {
      _stops.add(_DraftStop(name: e.title, audioUrl: e.audioUrl));
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
      // any we do not already have as draft stops.
      final refreshed =
          await CommunitiesService.get(widget.community.id, userId: userId);
      if (refreshed != null) {
        final existing = _stops.map((s) => s.audioUrl.text.trim()).toSet();
        for (final e in refreshed.episodes) {
          if (!existing.contains(e.audioUrl)) {
            _stops.add(_DraftStop(name: e.title, audioUrl: e.audioUrl));
          }
        }
      }
    }
    setState(() {
      _busy = false;
      _error = ok ? null : 'Could not import that feed.';
    });
  }

  void _addLink() {
    final title = _linkTitle.text.trim();
    final url = _linkUrl.text.trim();
    if (url.isEmpty) return;
    setState(() {
      _stops.add(_DraftStop(name: title.isEmpty ? 'Stop ${_stops.length + 1}' : title,
          audioUrl: url));
      _linkTitle.clear();
      _linkUrl.clear();
    });
  }

  void _removeStop(int i) {
    setState(() {
      _stops[i].dispose();
      _stops.removeAt(i);
    });
  }

  void _moveUp(int i) {
    if (i == 0) return;
    setState(() {
      final s = _stops.removeAt(i);
      _stops.insert(i - 1, s);
    });
  }

  String? _clientValidate() {
    if (_tourName.text.trim().isEmpty) return 'Give the tour a name.';
    if (_stops.isEmpty) return 'Add at least one stop.';
    for (var i = 0; i < _stops.length; i++) {
      final s = _stops[i];
      if (s.name.text.trim().isEmpty) return 'Stop ${i + 1} needs a name.';
      if (s.audioUrl.text.trim().isEmpty) {
        return '"${s.name.text.trim()}" has no audio.';
      }
      if (_needsLocation &&
          (double.tryParse(s.lat.text.trim()) == null ||
              double.tryParse(s.lng.text.trim()) == null)) {
        return '"${s.name.text.trim()}" needs a location for a $_tourType tour.';
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
      appBar: AppBar(title: const Text('Make a tour from your audio')),
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
                  onPressed: _addLink,
                  icon: const Icon(Icons.add_circle_outline),
                  tooltip: 'Add link',
                ),
              ],
            ),
            const Divider(height: 28),

            // Stops.
            Text('Stops (${_stops.length})',
                style: const TextStyle(fontWeight: FontWeight.bold)),
            if (_needsLocation)
              const Padding(
                padding: EdgeInsets.only(top: 4),
                child: Text(
                    'A walking/biking/driving tour needs a location on every stop.',
                    style: TextStyle(fontSize: 12, color: Colors.black54)),
              ),
            const SizedBox(height: 6),
            ..._stops.asMap().entries.map((e) => _stopCard(e.key, e.value)),
            const SizedBox(height: 16),

            // Rights.
            CheckboxListTile(
              value: _rightsAccepted,
              onChanged: (v) => setState(() => _rightsAccepted = v ?? false),
              controlAffinity: ListTileControlAffinity.leading,
              title: const Text(
                  'I have the right to publish this audio to my members.'),
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

  Widget _stopCard(int i, _DraftStop s) {
    return Card(
      key: ValueKey('stop_$i'),
      margin: const EdgeInsets.symmetric(vertical: 6),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(radius: 14, child: Text('${i + 1}')),
                const SizedBox(width: 8),
                Expanded(
                  child: TextField(
                    controller: s.name,
                    decoration: const InputDecoration(
                        labelText: 'Stop name', isDense: true),
                  ),
                ),
                IconButton(
                  onPressed: i == 0 ? null : () => _moveUp(i),
                  icon: const Icon(Icons.arrow_upward, size: 18),
                  tooltip: 'Move up',
                ),
                IconButton(
                  onPressed: () => _removeStop(i),
                  icon: const Icon(Icons.delete_outline, size: 18),
                  tooltip: 'Remove',
                ),
              ],
            ),
            TextField(
              controller: s.audioUrl,
              decoration:
                  const InputDecoration(labelText: 'Audio URL', isDense: true),
            ),
            Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: s.lat,
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true, signed: true),
                    decoration: const InputDecoration(
                        labelText: 'Latitude', isDense: true),
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
                  ),
                ),
              ],
            ),
            TextField(
              controller: s.text,
              maxLines: 2,
              decoration: const InputDecoration(
                  labelText: 'Notes / text (optional)', isDense: true),
            ),
          ],
        ),
      ),
    );
  }
}
