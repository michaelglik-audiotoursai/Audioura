// [LOCAL-730 / D694, Privacy "Location and places"] The Treats screen.
//
// Treats are chosen from the PLACES IN THE USER'S TOURS, or a place typed on
// Home — NEVER from the phone's location. The point selection lives entirely in
// [TreatsSourceResolver], which has no path to the device GPS; this screen does
// not import `geolocator` and must never read it. Phone-location Treats are a
// FUTURE opt-in (D694), built only on demand with a policy update first — see
// _kLocationTreatsOptInEnabled below (a build-time flag, OFF).

import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'package:url_launcher/url_launcher.dart';
import 'dart:convert';
import '../config/endpoints.dart';
import '../services/treats_source_resolver.dart';

/// [LOCAL-730 / D694] Opt-in hook for "Show Treats near me (uses your
/// location)", hidden behind a build-time feature flag that is OFF. While it is
/// false the switch is never shown and no GPS is read. Flipping it on is NOT
/// enough to ship the feature: D694 requires a Privacy Policy update first.
/// Kept as a flag (vs. deleted) so the opt-in has a single, documented home.
const bool _kLocationTreatsOptInEnabled =
    bool.fromEnvironment('TREATS_LOCATION_OPT_IN', defaultValue: false);

class TreatsScreen extends StatefulWidget {
  const TreatsScreen({super.key});

  @override
  State<TreatsScreen> createState() => _TreatsScreenState();
}

class _TreatsScreenState extends State<TreatsScreen> {
  List<Map<String, dynamic>> _treats = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadTreats();
  }

  Future<void> _loadTreats() async {
    setState(() {
      _isLoading = true;
    });

    try {
      // Resolve the points from the tour places (never the phone's GPS).
      final resolved = await TreatsSourceResolver.production().resolve();

      if (resolved.isEmpty) {
        // Source (d): no tour places and no Home place ⇒ no request at all.
        setState(() {
          _treats = [];
          _isLoading = false;
        });
        return;
      }

      final treats = await _fetchTreatsForPoints(resolved.points);

      setState(() {
        _treats = treats;
        _isLoading = false;
      });
    } catch (e) {
      print('Error loading treats: $e');
      setState(() {
        _isLoading = false;
      });
    }
  }

  /// Ask the server for treats near the resolved [points]. Prefers the batch
  /// POST /treats-near-places (one request, server merges + de-dups); falls
  /// back to the legacy GET /treats-near/<lat>/<lng> for the single-point case
  /// or if the batch endpoint is unavailable (older server).
  Future<List<Map<String, dynamic>>> _fetchTreatsForPoints(
      List<TreatPoint> points) async {
    // Single point ⇒ the legacy GET is enough.
    if (points.length == 1) {
      return _getTreatsNear(points.first);
    }

    // Try the batch endpoint first.
    try {
      final response = await Endpoints.post(
        Service.treats,
        '/treats-near-places',
        body: {
          'points': points.map((p) => p.toJson()).toList(),
        },
      );
      if (response.statusCode == 200) {
        return _parseTreats(response.body);
      }
      // 404/405 ⇒ older server without the batch route: fall back below.
    } catch (e) {
      print('Treats batch request failed, falling back to GET: $e');
    }

    // Fallback: repeated GETs, merged + de-duplicated client-side by treat id.
    final merged = <Object, Map<String, dynamic>>{};
    for (final p in points) {
      final treats = await _getTreatsNear(p);
      for (final t in treats) {
        final key = t['id'] ?? '${t['name']}|${t['link_to_vendor']}';
        merged.putIfAbsent(key, () => t);
      }
    }
    final list = merged.values.toList();
    list.sort((a, b) {
      final da = (a['distance_km'] as num?)?.toDouble() ?? double.infinity;
      final db = (b['distance_km'] as num?)?.toDouble() ?? double.infinity;
      return da.compareTo(db);
    });
    return list.take(5).toList();
  }

  Future<List<Map<String, dynamic>>> _getTreatsNear(TreatPoint p) async {
    final response = await http.get(
      await Endpoints.url(Service.treats, '/treats-near/${p.lat}/${p.lng}'),
      headers: await Endpoints.apiHeaders(Service.treats),
    );
    if (response.statusCode == 200) {
      return _parseTreats(response.body);
    }
    return [];
  }

  List<Map<String, dynamic>> _parseTreats(String body) {
    final data = json.decode(body);
    final treats = data['treats'] as List;
    return treats.cast<Map<String, dynamic>>();
  }

  /// [LOCAL-730 / D694] The "Show Treats near me (uses your location)" opt-in.
  /// Returns null (nothing shown) while the feature flag is OFF — and because it
  /// is OFF, this screen reads no GPS. When the flag is turned on in a future
  /// build (with a Privacy Policy update first, D694), this is the single place
  /// the switch would live. Kept deliberately inert today.
  Widget? _buildLocationOptInSwitch() {
    if (!_kLocationTreatsOptInEnabled) return null; // hidden + no GPS read
    return SwitchListTile(
      title: const Text('Show Treats near me (uses your location)'),
      value: false,
      onChanged: (_) {},
    );
  }

  @override
  Widget build(BuildContext context) {
    final optInSwitch = _buildLocationOptInSwitch();
    return Scaffold(
      appBar: AppBar(
        title: const Text('🍰 Treats'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadTreats,
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _treats.isEmpty
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      const Padding(
                        padding: EdgeInsets.all(32),
                        child: Text(
                          'Treats appear along the stops of your tours — '
                          'download a tour or search a place on Home.',
                          style: TextStyle(fontSize: 16, color: Colors.grey),
                          textAlign: TextAlign.center,
                        ),
                      ),
                      if (optInSwitch != null) optInSwitch,
                    ],
                  ),
                )
              : Column(
                  children: [
                    if (optInSwitch != null) optInSwitch,
                    Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(12),
                        color: Colors.amber.shade100,
                        child: const Text(
                          'Samples for the future',
                          style: TextStyle(fontSize: 13, fontWeight: FontWeight.w500),
                          textAlign: TextAlign.center,
                        ),
                      ),
                    Expanded(
                      child: ListView.builder(
                  itemCount: _treats.length,
                  itemBuilder: (context, index) {
                    final treat = _treats[index];
                    final hasCoords = treat['lat'] != null && treat['lng'] != null;
                    
                    return Card(
                      margin: const EdgeInsets.all(8),
                      child: ListTile(
                        leading: treat['image_base64'] != null
                            ? Container(
                                width: 50,
                                height: 50,
                                decoration: BoxDecoration(
                                  borderRadius: BorderRadius.circular(8),
                                  image: DecorationImage(
                                    image: MemoryImage(
                                      base64Decode(treat['image_base64']),
                                    ),
                                    fit: BoxFit.cover,
                                  ),
                                ),
                              )
                            : Icon(
                                Icons.local_cafe,
                                color: hasCoords ? Colors.green : Colors.grey,
                                size: 32,
                              ),
                        title: GestureDetector(
                          onTap: () async {
                            final url = treat['link_to_vendor'];
                            if (url != null && url.isNotEmpty) {
                              try {
                                final uri = Uri.parse(url);
                                await launchUrl(
                                  uri,
                                  mode: LaunchMode.externalApplication,
                                  webViewConfiguration: const WebViewConfiguration(
                                    enableJavaScript: true,
                                  ),
                                );
                              } catch (e) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text('Error opening link: $e')),
                                );
                              }
                            }
                          },
                          child: Text(
                            treat['name'] ?? 'Unknown Treat',
                            style: TextStyle(
                              color: treat['link_to_vendor'] != null ? Colors.blue : null,
                              decoration: treat['link_to_vendor'] != null ? TextDecoration.underline : null,
                            ),
                          ),
                        ),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (treat['description'] != null)
                              Text(
                                treat['description'],
                                maxLines: 2,
                                overflow: TextOverflow.ellipsis,
                              ),
                            const SizedBox(height: 4),
                            if (hasCoords && treat['distance_km'] != null)
                              Text(
                                '${treat['distance_km'].toStringAsFixed(1)} km away',
                                style: const TextStyle(
                                  color: Colors.blue,
                                  fontWeight: FontWeight.w500,
                                ),
                              )
                            else
                              const Text(
                                'Location not available',
                                style: TextStyle(color: Colors.grey),
                              ),
                          ],
                        ),
                        trailing: const Icon(Icons.arrow_forward_ios),
                        onTap: () {
                          if (treat['image_base64'] != null) {
                            Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (context) => _FullScreenImageView(
                                  imageBase64: treat['image_base64'],
                                  title: treat['name'] ?? 'Treat',
                                  description: treat['description'] ?? '',
                                ),
                              ),
                            );
                          } else {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text('No image available for ${treat['name']}'),
                              ),
                            );
                          }
                        },
                      ),
                    );
                  },
                ),
                    ),
                  ],
                ),
    );
  }
}

class _FullScreenImageView extends StatelessWidget {
  final String imageBase64;
  final String title;
  final String description;

  const _FullScreenImageView({
    required this.imageBase64,
    required this.title,
    required this.description,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(title),
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: InteractiveViewer(
                child: Image.memory(
                  base64Decode(imageBase64),
                  fit: BoxFit.contain,
                ),
              ),
            ),
          ),
          if (description.isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              color: Colors.black87,
              child: Text(
                description,
                style: const TextStyle(
                  color: Colors.white,
                  fontSize: 16,
                ),
                textAlign: TextAlign.center,
              ),
            ),
        ],
      ),
    );
  }
}
