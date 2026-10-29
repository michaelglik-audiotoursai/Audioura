import 'dart:async';
import 'package:flutter/material.dart';
import 'package:flutter_map/flutter_map.dart';
import 'package:latlong2/latlong.dart';
import 'package:geolocator/geolocator.dart';
import 'package:permission_handler/permission_handler.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'package:path_provider/path_provider.dart';
import 'package:archive/archive.dart';
import 'package:url_launcher/url_launcher.dart';
import 'package:flutter/foundation.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:typed_data';
import 'dart:math';
import '../screens/debug_log_viewer_screen.dart';
import '../services/subscription_service.dart';
import '../services/subscription_encryption_service.dart';
import '../services/device_service.dart';
import '../services/saved_tours_store.dart';
import '../services/translation_service.dart';
import '../services/tour_translation_helper.dart';
import '../services/error_handler_service.dart';
import '../services/failure_reporter.dart';
import '../services/tour_pricing_service.dart';
import '../services/downloaded_tour_meta.dart';
import '../services/tour_download_service.dart';
import '../services/translate_download_manager.dart';
import '../utils/tour_display.dart';
import '../config.dart';
import '../config/endpoints.dart';
import '../utils/share_code.dart';
import '../utils/downloaded_message.dart';
import '../utils/search_dispatch.dart';
import '../utils/place_geocoder.dart';
import '../utils/map_zoom.dart';
import '../services/deep_link_service.dart';
import '../services/communities_service.dart';
import '../services/community_tour_service.dart';
import 'community_page_screen.dart';
import 'communities_hub_screen.dart';
import 'recovery_code_screen.dart';
// import '../services/credential_storage_service.dart';  // TEMPORARILY DISABLED - CAUSING BUILD ERRORS
// import '../services/subscription_article_storage.dart';  // TEMPORARILY DISABLED - CAUSING BUILD ERRORS
import '../widgets/subscription_credential_dialog.dart';
import '../widgets/language_selector.dart';
import '../widgets/rate_tour_dialog.dart';
import '../widgets/why_this_score_sheet.dart';
import '../widgets/reviews_section.dart';
import '../widgets/price_badge.dart';
import '../widgets/community_tour_chip.dart';
import '../widgets/first_layout_tile_layer.dart';
import '../widgets/tour_buy_sheet.dart';
import '../widgets/download_action_plan.dart';
import '../services/tour_preview_player.dart';

/// [LOCAL-793] A resolved place search: where to move the map, and the clean
/// place NAME that was actually matched (shown in the Home banner so a wrong
/// match — e.g. a Paris restaurant for "Saigon Vietnam" — is visible at once,
/// instead of echoing the raw typed text).
class GeoResult {
  final LatLng location;
  final String name;
  const GeoResult({required this.location, required this.name});
}

/// [LOCAL-793] The closest tour to a point and its distance (km), from the
/// recover-empty-view lookup.
class _NearestTour {
  final Map<String, dynamic> tour;
  final double distanceKm;
  const _NearestTour({required this.tour, required this.distanceKm});
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key});

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  MapController _mapController = MapController();
  // [LOCAL-789] Fires when the FlutterMap's laid-out size changes because the
  // header above it changed height (the orange "Showing tours near: …" banner
  // appearing on a place search, or the LOCAL-761 hide-on-scroll bar) — a
  // layout change flutter_map may not emit a size event for in time, which left
  // the map's TOP band grey until the next camera event ~30 s later
  // (Michael, TestFlight 83). A LayoutBuilder around the map pushes the new
  // height here; FirstLayoutTileLayer coalesces it to one tile reload per
  // frame. Broadcast so a late listener still works.
  final StreamController<void> _mapSizeReset =
      StreamController<void>.broadcast();
  double? _lastMapHeight;
  LatLng? _userLocation;
  LatLng? _displayLocation; // Location being displayed (may differ from user location)
  List<Marker> _tourMarkers = [];
  // [LOCAL-690] Listed-community pins for the Home map (community badge).
  List<Marker> _communityMarkers = [];
  // [LOCAL-739 §2] True when the user BELONGS TO or ORGANISES ≥ 1 community —
  // the gate for the Home-map "My communities" chip (members only). A
  // non-member never sees the chip. Loaded alongside the community pins.
  bool _isCommunityMember = false;
  // [LOCAL-756 C] The community IDs this user BELONGS TO (from /communities/mine).
  // Used to decide the Home price line per community tour: a member sees
  // "Included with membership"; a non-member sees the join framing. Separate
  // from the any-community boolean above, which only gates the map chip.
  final Set<int> _joinedCommunityIds = <int>{};
  bool _isLoading = true;
  bool _connectionError = false;
  String _appMode = 'Tours';
  bool _isUsingCustomLocation = false;
  String _customLocationName = '';
  List<Map<String, dynamic>> _locationHistory = [];
  List<Map<String, dynamic>> _newsletters = [];
  String _selectedTypeFilter = 'All';
  List<String> _selectedLanguages = ['en'];
  // [LOCAL-670] Home-page rating filter: 0 = Any, else the minimum shown score
  // (7, 8, or 9). Remembered per device under SharedPreferences 'home_min_rating'
  // and passed to /tours-near as ?min_rating=<n> so the server filters.
  double _minRating = 0.0;
  // [LOCAL-681] The map lists the tours in the area the listener is LOOKING AT:
  // zoom out for more, zoom in for fewer. Michael, 2026-10-14, replacing a
  // "Within N mi" setting: "maybe it should not be in the radius, but in the
  // visible Home page, so user can zoom in and out." Both sort orders apply to
  // this same area. Reloaded (debounced) whenever the map stops moving.
  LatLngBounds? _viewBounds;
  // [LOCAL-683] The tours of the last /tours-near load, for the List view.
  List<Map<String, dynamic>> _loadedTours = [];
  Timer? _viewReloadTimer;
  // A world-wide view would ask for every tour; cap the circle at 500 km.
  static const double _maxViewRadiusKm = 500;
  // [LOCAL-672] Home-page "Top rated" sort: when true, /tours-near is asked for
  // ?sort=top_rated and the server orders by the Bayesian rank_score (verified
  // ratings weighted higher, old/pre-version ratings decayed). Remembered per
  // device under SharedPreferences 'home_top_rated'. Default off (nearest-first).
  //
  // [LOCAL-689] Sort is now tri-state: 'nearest' | 'top_rated' | 'match'. The
  // List view exposes all three (Nearest / Top rated / Best match first); the
  // AppBar sort icon and the Search filter-row keep their original two-way
  // Nearest/Top-rated control via the `_topRated` getter/`_setTopRated` setter
  // below, which read and write this one field. Persisted under 'home_sort_mode'
  // (the legacy 'home_top_rated' bool is still honoured on first load).
  String _sortMode = 'nearest';
  bool get _topRated => _sortMode == 'top_rated';
  // [LOCAL-689] The device's listener id (DeviceService.getUserId), cached so
  // the sync _filterQueryParams can attach ?user_id= for the Match % the server
  // computes. Loaded once in _loadAppMode; empty until then (match simply off).
  String _deviceUserId = '';
  // [LOCAL-677] Home-page Free/Paid/Any filter: '' = Any, 'free', or 'paid'.
  // Remembered per device under SharedPreferences 'home_price_filter' and passed
  // to /tours-near as ?price=free|paid so the server filters.
  String _priceFilter = '';
  // [LOCAL-687] "Show 18+ tours (I am 18 or older)". Remembered per device under
  // SharedPreferences 'home_show_adult'. When on, every list/search/code call
  // carries ?adult=1 so mature tours are returned; off (the default) hides them.
  // not_allowed tours are never returned regardless; pending/rejected are hidden
  // until a human approves (server-side, map-delivery LOCAL-687).
  bool _showAdult = false;
  final List<String> _articleTypes = [
    'All',
    'News and Politics',
    'Business and Investment', 
    'Technology',
    'Lifestyle and Entertainment',
    'Education and Learning',
    'Others'
  ];

  @override
  void initState() {
    super.initState();
    _initializeSecureEncryption();
    _loadAppMode();
    _loadCommunityPins();
    _loadCommunityMembership();
    // [LOCAL-709 / D671] A share link (cold/warm start) or a deferred link
    // parks its code in PendingShareSearch; Home runs it through the SAME
    // dispatch path a pasted code takes. Listen for later arrivals (warm start
    // while Home is already open) and also act on any code already waiting
    // (cold start, or a tab switch into Home after the link arrived).
    PendingShareSearch.instance.code.addListener(_onPendingShareSearch);
    WidgetsBinding.instance.addPostFrameCallback((_) {
      _onPendingShareSearch();
    });
  }

  /// [LOCAL-709] Act on a pending share code, if any: fill the shared search
  /// path and consume it so a rebuild never runs the same code twice. Reuses
  /// [_dispatchSearch] (classify → share-code branch → _resolveShareCode),
  /// i.e. exactly what pasting the code into Search does today.
  Future<void> _onPendingShareSearch() async {
    final code = PendingShareSearch.instance.code.value;
    if (code == null || code.isEmpty) return;
    // Consume immediately so concurrent rebuilds / a second listener tick do
    // not dispatch the same code twice.
    PendingShareSearch.instance.consume();
    if (!mounted) return;
    await _dispatchSearch(code);
  }

  @override
  void dispose() {
    PendingShareSearch.instance.code.removeListener(_onPendingShareSearch);
    _mapSizeReset.close(); // [LOCAL-789]
    super.dispose();
  }

  /// [LOCAL-739 §2] Learn whether the user BELONGS TO or ORGANISES ≥ 1
  /// community, to decide whether the Home-map "My communities" chip shows (it
  /// is members-only). Both reads swallow transport errors and return empty
  /// lists, so an unreachable Communities backend simply hides the chip.
  Future<void> _loadCommunityMembership() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id');
      if (userId == null || userId.isEmpty) return;
      final joined = await CommunitiesService.mine(userId);
      final owned = await CommunityTourService.ownedCommunities(userId);
      if (!mounted) return;
      setState(() {
        _isCommunityMember = CommunityRules.hasAnyCommunity(
          joinedCount: joined.length,
          ownedCount: owned.length,
        );
        // [LOCAL-756 C] Remember the joined community IDs so a community tour's
        // price line can read "Included with membership" for this user.
        _joinedCommunityIds
          ..clear()
          ..addAll(joined.map((c) => c.id));
      });
    } catch (_) {
      // Non-fatal: the chip simply stays hidden.
    }
  }

  /// [LOCAL-690] Load Listed communities and render them as map pins with a
  /// community badge. Failures are swallowed — the map still shows tours.
  Future<void> _loadCommunityPins() async {
    try {
      final pins = await CommunitiesService.mapPins();
      if (!mounted) return;
      setState(() {
        _communityMarkers = pins
            .map((p) => Marker(
                  point: LatLng(p.latitude, p.longitude),
                  width: 44,
                  height: 44,
                  child: GestureDetector(
                    onTap: () => _showCommunityPinSheet(p),
                    child: Stack(
                      alignment: Alignment.center,
                      children: [
                        const Icon(Icons.location_on,
                            color: Colors.deepPurple, size: 40),
                        Positioned(
                          bottom: 10,
                          child: Container(
                            padding: const EdgeInsets.all(2),
                            decoration: const BoxDecoration(
                              color: Colors.white, shape: BoxShape.circle),
                            child: const Icon(Icons.groups,
                                color: Colors.deepPurple, size: 14),
                          ),
                        ),
                      ],
                    ),
                  ),
                ))
            .toList();
      });
    } catch (_) {
      // Non-fatal: communities just won't appear on the map this session.
    }
  }

  /// [LOCAL-704 / D665] The map pin sheet for a Listed community: its name and
  /// its member count ("12 members"), with an Open button to the community
  /// page. The organiser is never counted (server-side).
  void _showCommunityPinSheet(CommunityMapPin p) {
    showModalBottomSheet(
      context: context,
      builder: (ctx) => SafeArea(
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text(p.name,
                  style: const TextStyle(
                      fontSize: 18, fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              Row(
                children: [
                  const Icon(Icons.groups,
                      size: 18, color: Colors.deepPurple),
                  const SizedBox(width: 6),
                  Text(
                    CommunityCopy.memberCountLabel(p.memberCount),
                    key: const Key('pin_sheet_member_count'),
                    style: const TextStyle(
                        fontWeight: FontWeight.w600,
                        color: Colors.deepPurple),
                  ),
                ],
              ),
              const SizedBox(height: 16),
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () {
                    Navigator.pop(ctx);
                    Navigator.push(
                      context,
                      MaterialPageRoute(
                          builder: (_) =>
                              CommunityPageScreen(communityId: p.id)),
                    );
                  },
                  child: const Text('Open community'),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }
  
  Future<void> _initializeSecureEncryption() async {
    try {
      // Check if we have a valid encryption key, don't clear unnecessarily
      final hasKey = await SubscriptionEncryptionService.hasStoredKey();
      await DebugLogHelper.addDebugLog('HOME: Secure encryption initialized - has key: $hasKey');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error initializing secure encryption: $e');
    }
  }
  
  Future<void> _loadAppMode() async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('app_mode') ?? 'Tours';
    _minRating = prefs.getDouble('home_min_rating') ?? 0.0;
    // [LOCAL-689] Tri-state sort. New key wins; else migrate the legacy bool.
    _sortMode = prefs.getString('home_sort_mode') ??
        ((prefs.getBool('home_top_rated') ?? false) ? 'top_rated' : 'nearest');
    _priceFilter = prefs.getString('home_price_filter') ?? '';
    _showAdult = prefs.getBool('home_show_adult') ?? false;  // [LOCAL-687]
    // [LOCAL-689] Cache the listener id for the Match % query param.
    try {
      _deviceUserId = await DeviceService.getUserId();
    } catch (_) {
      _deviceUserId = '';
    }
    await _loadLocationHistory();
    await _loadCustomLocation();

    // [LOCAL-773] Home is disposed during first launch (onboarding/plan
    // screens replace it before this async chain returns). Without this guard
    // the setState below throws "Null check operator used on a null value" in
    // State.setState and the rest of the load (_loadNewsletters /
    // _initializeMap) is skipped. Bail out quietly if we are no longer mounted.
    if (!mounted) return;
    setState(() {
      _appMode = mode;
    });
    
    if (_appMode == 'Audio') {
      await _loadNewsletters();
    } else {
      await _initializeMap();
    }
  }
  
  Future<void> _loadCustomLocation() async {
    final prefs = await SharedPreferences.getInstance();
    final customLat = prefs.getDouble('custom_location_lat');
    final customLng = prefs.getDouble('custom_location_lng');
    final customName = prefs.getString('custom_location_name');
    // [LOCAL-789B] Whether the saved label is a geocoder-RESOLVED place name.
    // Locations saved before LOCAL-793 stored the RAW typed text (e.g. the typo
    // "Hi Chi Minh, Vietnam"), which then showed verbatim in the banner and
    // could sit on a wrong coordinate. New saves set this true (see
    // _saveCustomLocation); a legacy save has it absent/false and is re-resolved
    // once below.
    final resolved = prefs.getBool('custom_location_resolved') ?? false;

    if (customLat != null && customLng != null && customName != null) {
      if (!mounted) return; // [LOCAL-773] setState after await: Home may be gone.
      setState(() {
        _displayLocation = LatLng(customLat, customLng);
        _isUsingCustomLocation = true;
        _customLocationName = customName;
      });
      // [LOCAL-789B] One-time heal of a legacy (pre-LOCAL-793) raw label: send
      // it through the SAME geocoder a Home search uses and, if it resolves to a
      // place, replace the banner text (and the coordinate) with the resolved
      // one and persist it as resolved so this never runs again. On any failure
      // we keep the saved value untouched — the banner is no worse than before.
      if (!resolved) {
        await _reResolveLegacyCustomLocation(customName);
      }
    }
  }

  /// [LOCAL-789B] Re-resolve a legacy custom-location label (saved before
  /// LOCAL-793 as raw typed text) exactly once, so the Home banner shows a real
  /// resolved place name instead of e.g. the typo "Hi Chi Minh, Vietnam".
  /// Non-destructive: if geocoding returns nothing the saved location is left
  /// as-is. Marks the entry resolved on success so it is never re-resolved.
  Future<void> _reResolveLegacyCustomLocation(String savedName) async {
    try {
      final result = await _geocodeLocation(savedName);
      if (!mounted || result == null) return;
      setState(() {
        _displayLocation = result.location;
        _customLocationName = result.name;
      });
      _safeMapMove(result.location, 13.0);
      await _saveCustomLocation(); // persists the resolved name + flag
      await DebugLogHelper.addDebugLog(
          'HOME: re-resolved legacy custom location "$savedName" → '
          '"${result.name}"');
      if (!mounted) return;
      await _loadNearbyTours();
    } catch (e) {
      await DebugLogHelper.addDebugLog(
          'HOME: legacy custom-location re-resolve failed for "$savedName": $e');
    }
  }
  
  Future<void> _saveCustomLocation() async {
    final prefs = await SharedPreferences.getInstance();
    if (_isUsingCustomLocation && _displayLocation != null) {
      await prefs.setDouble('custom_location_lat', _displayLocation!.latitude);
      await prefs.setDouble('custom_location_lng', _displayLocation!.longitude);
      await prefs.setString('custom_location_name', _customLocationName);
      // [LOCAL-789B] Every save here comes from a geocoder-resolved GeoResult
      // name (_useCustomLocation) or a just-re-resolved legacy label, so mark it
      // resolved — a later cold start then trusts the banner text as-is.
      await prefs.setBool('custom_location_resolved', true);
    } else {
      await prefs.remove('custom_location_lat');
      await prefs.remove('custom_location_lng');
      await prefs.remove('custom_location_name');
      await prefs.remove('custom_location_resolved');
    }
  }
  
  Future<void> _loadLocationHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final historyJson = prefs.getStringList('location_history') ?? [];
    _locationHistory = historyJson.map((item) => json.decode(item) as Map<String, dynamic>).toList();
  }
  
  Future<void> _saveLocationHistory() async {
    final prefs = await SharedPreferences.getInstance();
    final historyJson = _locationHistory.map((item) => json.encode(item)).toList();
    await prefs.setStringList('location_history', historyJson);
  }
  
  /// [LOCAL-793] Resolve a typed place name to a coordinate AND the clean
  /// place name that was actually matched.
  ///
  /// Two fixes over the old `limit=1`, take-result[0] call (which opened
  /// "Saigon Vietnam" on a Paris restaurant and a "Hi Chi Minh" typo on a bus
  /// stop):
  ///   1. Ask Nominatim for several results (`limit=8`, `accept-language=en`,
  ///      a real User-Agent per the Nominatim usage policy) and prefer a PLACE
  ///      — a city/town/suburb/administrative area — over any POI
  ///      ([pickBestPlace]). A restaurant can never win when a city matches.
  ///   2. When Nominatim returns NO place (a typo like "Hi Chi Minh", or only
  ///      far POIs), fall back to the server geocoder ([_geocodeViaServer]),
  ///      which uses the paid Serper places index server-side (no API key in
  ///      the app) and copes with typos.
  ///
  /// Returns the resolved [GeoResult] (coordinate + display name for the Home
  /// banner), or null when nothing resolves.
  Future<GeoResult?> _geocodeLocation(String query) async {
    // [LOCAL-789 ADDENDUM] Rewrite a historic place name to its modern one
    // before any geocoding — "Saigon Vietnam" → "Ho Chi Minh City Vietnam" —
    // so Nominatim resolves the city instead of dead-ending on POIs literally
    // named "Saigon" (with the server /geocode not deployed, the old name ends
    // at "Nothing found"). Whole-word, case/diacritic-insensitive.
    final aliased = applyPlaceAliases(query);
    if (aliased != query) {
      await DebugLogHelper.addDebugLog(
          'HOME: place alias "$query" → "$aliased"');
    }
    final nominatim = await _geocodeViaNominatim(aliased);
    if (nominatim != null) return nominatim;
    // No usable PLACE from Nominatim — try the typo-tolerant server geocoder.
    final server = await _geocodeViaServer(aliased);
    if (server != null) return server;
    return null;
  }

  /// Query Nominatim for up to 8 results and pick the best PLACE (falling back
  /// to the best POI only when NO candidate is a place). Returns null on error,
  /// an empty response, or when the only matches are POIs — in the POI-only
  /// case the caller tries the server geocoder, which is better at place names.
  Future<GeoResult?> _geocodeViaNominatim(String query) async {
    try {
      final encodedQuery = Uri.encodeComponent(query);
      final response = await http.get(
        Uri.parse('https://nominatim.openstreetmap.org/search'
            '?q=$encodedQuery&format=json&limit=8&accept-language=en'
            '&addressdetails=0'),
        // Nominatim usage policy: a real, identifying User-Agent with contact.
        headers: const {
          'User-Agent':
              'com.audioura.audiotours/1.0 (support@audioura.com)',
          'Accept-Language': 'en',
        },
      ).timeout(Duration(seconds: 10));

      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        if (data is List && data.isNotEmpty) {
          final candidates = parseNominatim(data);
          // A PLACE is required here; if the only matches are POIs, return null
          // so the server geocoder gets a chance (it handles "Saigon"/typos).
          final hasPlace = candidates.any(isPlace);
          final best = pickBestPlace(candidates, query: query);
          if (best != null && hasPlace) {
            await DebugLogHelper.addDebugLog(
                'HOME: Nominatim place "${best.displayName}" '
                '(${best.klass}/${best.type}) for "$query"');
            return GeoResult(
              location: LatLng(best.lat, best.lon),
              name: best.displayName.isNotEmpty ? best.displayName : query,
            );
          }
          await DebugLogHelper.addDebugLog(
              'HOME: Nominatim returned only POIs for "$query"; '
              'trying server geocoder');
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Nominatim geocoding error: $e');
    }
    return null;
  }

  /// [LOCAL-793] Server-side geocoder fallback. Calls map-delivery `/geocode`,
  /// which resolves a free-text place name (typo-tolerant) using the paid
  /// Serper places index — the key lives on the server, never in the app.
  /// Returns null on any error or when the server finds nothing.
  Future<GeoResult?> _geocodeViaServer(String query) async {
    try {
      final uri = await Endpoints.url(
          Service.mapDelivery, '/geocode?q=${Uri.encodeComponent(query)}');
      final response = await http
          .get(uri, headers: await Endpoints.apiHeaders(Service.mapDelivery))
          .timeout(const Duration(seconds: 12));
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final lat = (data is Map) ? data['lat'] : null;
        final lng = (data is Map) ? (data['lng'] ?? data['lon']) : null;
        if (lat != null && lng != null) {
          final dLat = lat is num ? lat.toDouble() : double.tryParse('$lat');
          final dLng = lng is num ? lng.toDouble() : double.tryParse('$lng');
          if (dLat != null && dLng != null) {
            final name = '${(data as Map)['name'] ??
                data['display_name'] ?? query}';
            await DebugLogHelper.addDebugLog(
                'HOME: Server geocoder resolved "$query" → "$name"');
            return GeoResult(
              location: LatLng(dLat, dLng),
              name: name.isNotEmpty ? name : query,
            );
          }
        }
      } else {
        await DebugLogHelper.addDebugLog(
            'HOME: Server geocoder status ${response.statusCode} for "$query"');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Server geocoding error: $e');
    }
    return null;
  }

  Future<void> _initializeMap() async {
    await DebugLogHelper.addDebugLog('HOME: Starting map initialization');
    
    // Load cached tours first
    await _loadCachedTours();
    
    await _getCurrentLocation();
    await _loadNearbyTours();
    
    if (!mounted) return; // [LOCAL-773] setState after await: Home may be gone.
    setState(() {
      _isLoading = false;
    });
    
    await DebugLogHelper.addDebugLog('HOME: Map initialization completed');
  }

  Future<void> _getCurrentLocation() async {
    try {
      await DebugLogHelper.addDebugLog('HOME: Requesting location permission');
      
      // Check current permission status
      LocationPermission permission = await Geolocator.checkPermission();
      
      if (permission == LocationPermission.denied) {
        permission = await Geolocator.requestPermission();
        if (permission == LocationPermission.denied) {
          await DebugLogHelper.addDebugLog('HOME: Location permission denied');
          if (!mounted) return; // [LOCAL-773] setState after await.
          setState(() {
            _userLocation = LatLng(42.3601, -71.0589);
          });
          return;
        }
      }
      
      if (permission == LocationPermission.deniedForever) {
        await DebugLogHelper.addDebugLog('HOME: Location permission denied forever');
        if (!mounted) return; // [LOCAL-773] setState after await.
        setState(() {
          _userLocation = LatLng(42.3601, -71.0589);
        });
        return;
      }

      await DebugLogHelper.addDebugLog('HOME: Getting current position');
      Position? position;
      try {
        position = await Geolocator.getCurrentPosition(
          desiredAccuracy: LocationAccuracy.high,
        );
      } catch (e) {
        await DebugLogHelper.addDebugLog('HOME: Geolocator error: $e');
        throw e;
      }

      if (position != null) {
        if (mounted) {
          setState(() {
            _userLocation = LatLng(position!.latitude, position.longitude);
          });
        }

        await DebugLogHelper.addDebugLog('HOME: User location: ${position.latitude}, ${position.longitude}');
      } else {
        await DebugLogHelper.addDebugLog('HOME: Position is null, using default location');
        if (mounted) {
          setState(() {
            _userLocation = LatLng(42.3601, -71.0589);
          });
        }
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error getting location: $e');
      if (!mounted) return; // [LOCAL-773] setState after await.
      setState(() {
        _userLocation = LatLng(42.3601, -71.0589);
      });
    }
  }

  Future<void> _loadCachedTours() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final cachedTours = prefs.getString('cached_tours');
      
      if (cachedTours != null) {
        await DebugLogHelper.addDebugLog('HOME: Loading cached tours');
        final tours = json.decode(cachedTours) as List;
        
        // Apply clustering to cached tours too
        final clusteredTours = _clusterTours(tours);
        
        if (!mounted) return; // [LOCAL-773] setState after await.
        setState(() {
          _tourMarkers = clusteredTours.map((cluster) {
            final toursList = cluster['tours'] as List;
            // [LOCAL-757 A] One pure rule decides the marker's look. A cluster
            // holding a community tour is drawn GREEN with the groups icon so a
            // community tour is told apart on the map BEFORE the tap; treats and
            // plain tours keep their pre-LOCAL-757 colour/icon.
            final markerKind = CommunityRules.homeMarkerKind(toursList);
            final isMultiple = toursList.length > 1;
            final isCommunity = markerKind == 'community';

            return Marker(
              point: LatLng(cluster['lat'], cluster['lng']),
              width: 40,
              height: 40,
              child: GestureDetector(
                onTap: () => isMultiple 
                  ? _showMultipleTourDialog(cluster['tours'])
                  : _onTourMarkerTapped(cluster['tours'][0]),
                child: Stack(
                  children: [
                    Container(
                      decoration: BoxDecoration(
                        color: homeMarkerColor(markerKind),
                        shape: BoxShape.circle,
                        border: Border.all(color: Colors.white, width: 2),
                      ),
                      child: Icon(
                        homeMarkerIcon(markerKind),
                        color: Colors.white,
                        size: 20,
                      ),
                    ),
                    // [LOCAL-682] Gold $ badge: this pin holds a paid tour.
                    if (_clusterHasPaid(cluster['tours'] as List)) const _PaidPinBadge(),
                    // [LOCAL-757 A] The green "apps" multi-tour badge is dropped
                    // on a community pin — the pin is already green and would
                    // otherwise be green-on-green; the community look wins.
                    if (isMultiple && !isCommunity)
                      Positioned(
                        right: -2,
                        top: -2,
                        child: Container(
                          width: 20,
                          height: 20,
                          decoration: BoxDecoration(
                            color: Colors.green,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 1),
                          ),
                          child: Icon(
                            Icons.apps,
                            color: Colors.white,
                            size: 12,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            );
          }).toList();
        });
        
        await DebugLogHelper.addDebugLog('HOME: Loaded ${tours.length} cached tours with clustering');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error loading cached tours: $e');
    }
  }

  /// [LOCAL-682] True when any tour on this pin is paid (Michael, 2026-10-14:
  /// paid and free pins looked identical).
  static bool _clusterHasPaid(List toursList) => toursList.any((t) =>
      t is Map &&
      (t['is_paid'] == true ||
          (t['price_tier'] is num && (t['price_tier'] as num) > 0)));

  /// [LOCAL-683] The loaded tours that are actually ON SCREEN (the request
  /// circle reaches the corners, so it returns a few just outside), in the
  /// chosen order. Nearest = nearest to the listener when the map shows their
  /// own location, else to the map centre. Top rated = the server's rank order.
  /// [LOCAL-689] Best match = by the server's personal match_percent descending,
  /// tours with no match (null) sinking to the end.
  List<Map<String, dynamic>> _visibleTours() {
    final view = _viewBounds;
    final list = _loadedTours.where((t) {
      if (t['type'] == 'treat') return false;
      final lat = (t['lat'] as num?)?.toDouble();
      final lng = (t['lng'] as num?)?.toDouble();
      if (lat == null || lng == null) return false;
      return view == null || view.contains(LatLng(lat, lng));
    }).toList();

    // Distance is shown as "mi" in every mode, so always compute _list_km.
    final from = (!_isUsingCustomLocation && _userLocation != null)
        ? _userLocation!
        : (view?.center ?? _userLocation);
    if (from != null) {
      for (final t in list) {
        t['_list_km'] = _calculateDistance(from.latitude, from.longitude,
            (t['lat'] as num).toDouble(), (t['lng'] as num).toDouble());
      }
    }

    if (_sortMode == 'match') {
      // Best match first; a null match_percent (cold start / no history) sorts
      // to the end, then nearest within equal match.
      int pct(Map<String, dynamic> t) {
        final v = t['match_percent'];
        return v is num ? v.toInt() : -1;
      }
      list.sort((a, b) {
        final cmp = pct(b).compareTo(pct(a));
        if (cmp != 0) return cmp;
        final ak = (a['_list_km'] as num?)?.toDouble() ?? double.infinity;
        final bk = (b['_list_km'] as num?)?.toDouble() ?? double.infinity;
        return ak.compareTo(bk);
      });
    } else if (_sortMode == 'top_rated') {
      // Keep the server's rank order (already sorted by /tours-near).
    } else if (from != null) {
      // Nearest first (the default).
      list.sort((a, b) =>
          (a['_list_km'] as double).compareTo(b['_list_km'] as double));
    }
    return list;
  }

  /// [LOCAL-683] "List" — the tours in the visible map area as a list, where
  /// Nearest / Top rated is actually visible (Michael, 2026-10-14). Tapping a
  /// tour opens the same dialog as its map pin.
  void _showVisibleToursList() {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      builder: (sheetContext) => StatefulBuilder(
        builder: (sheetContext, setSheetState) {
          final tours = _visibleTours();
          return DraggableScrollableSheet(
            expand: false,
            initialChildSize: 0.6,
            maxChildSize: 0.95,
            builder: (context, scrollController) => Column(
              children: [
                Padding(
                  padding: const EdgeInsets.fromLTRB(16, 12, 16, 4),
                  child: Row(
                    children: [
                      Expanded(
                        child: Text(
                          '${tours.length} tour${tours.length == 1 ? '' : 's'} in this map area',
                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                        ),
                      ),
                      TextButton(
                        onPressed: () => Navigator.pop(sheetContext),
                        child: const Text('Cancel'),
                      ),
                    ],
                  ),
                ),
                Padding(
                  padding: const EdgeInsets.symmetric(horizontal: 16),
                  child: Wrap(
                    spacing: 8,
                    children: [
                      // [LOCAL-689] Tri-state sort: Nearest / Top rated / Best match.
                      for (final opt in const [
                        ['nearest', 'Nearest first'],
                        ['top_rated', 'Top rated first'],
                        ['match', 'Best match first'],
                      ])
                        ChoiceChip(
                          label: Text(opt[1]),
                          selected: _sortMode == opt[0],
                          onSelected: (_) async {
                            await _setSortMode(opt[0]);
                            setSheetState(() {});
                          },
                        ),
                    ],
                  ),
                ),
                const Divider(),
                Expanded(
                  child: tours.isEmpty
                      ? const Center(
                          child: Padding(
                            padding: EdgeInsets.all(24),
                            child: Text('No tours here. Zoom out the map to see more.',
                                textAlign: TextAlign.center),
                          ),
                        )
                      : ListView.separated(
                          controller: scrollController,
                          itemCount: tours.length,
                          separatorBuilder: (_, __) => const Divider(height: 1),
                          itemBuilder: (context, i) {
                            final t = tours[i];
                            final km = (t['_list_km'] as num?) ?? (t['distance_km'] as num?);
                            return ListTile(
                              title: Text(t['name']?.toString() ?? 'Tour',
                                  maxLines: 2, overflow: TextOverflow.ellipsis),
                              subtitle: Padding(
                                padding: const EdgeInsets.only(top: 4),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Wrap(
                                      spacing: 8,
                                      runSpacing: 4,
                                      crossAxisAlignment: WrapCrossAlignment.center,
                                      children: [
                                        // [LOCAL-689] "Match 82%" leads when present.
                                        if (_matchChip(t) != null) _matchChip(t)!,
                                        TourRatingBadge.fromTour(t,
                                            onTap: () => showWhyThisScoreSheet(
                                                context,
                                                tourId: '${t['id']}',
                                                tour: t)),
                                        // [LOCAL-756 C] Community tour → membership
                                        // price line, not the money "Free" badge.
                                        if (CommunityRules.isCommunityTour(t))
                                          _communityPriceLine(t)!
                                        else
                                          TourPriceBadge.fromTour(t),
                                        if (_isMatureTour(t)) _adultChip(),
                                        if (km != null)
                                          Text('${(km / 1.609344).toStringAsFixed(1)} mi',
                                              style: const TextStyle(fontSize: 12)),
                                      ],
                                    ),
                                    // [LOCAL-756 C] Community sign under the badges.
                                    if (_communitySign(t) != null) ...[
                                      const SizedBox(height: 4),
                                      _communitySign(t)!,
                                    ],
                                    // [LOCAL-689] The two reason phrases (or the
                                    // "swipe a few stops" cold-start line).
                                    if (_matchReasonsLine(t) != null) ...[
                                      const SizedBox(height: 4),
                                      _matchReasonsLine(t)!,
                                    ],
                                  ],
                                ),
                              ),
                              onTap: () {
                                Navigator.pop(sheetContext);
                                _onTourMarkerTapped(t);
                              },
                            );
                          },
                        ),
                ),
              ],
            ),
          );
        },
      ),
    );
  }

  /// [LOCAL-681] The map moved: remember the visible area and reload once the
  /// listener stops panning/zooming (programmatic moves count too, so a search
  /// that moves the map lists that area).
  void _onMapMoved(MapPosition position, bool hasGesture) {
    final bounds = position.bounds;
    if (bounds == null) return;
    _viewBounds = bounds;
    _viewReloadTimer?.cancel();
    _viewReloadTimer = Timer(const Duration(milliseconds: 600), () {
      if (mounted) _loadNearbyTours();
    });
  }

  Future<void> _loadNearbyTours() async {
    // [LOCAL-681] Prefer the visible map area: its centre, and a circle reaching
    // its corners (so nothing on screen is missed). Before the map has reported
    // its area, fall back to the listener's location and ~10 mi.
    final view = _viewBounds;
    final searchLocation = view?.center ?? _displayLocation ?? _userLocation;
    final double radiusKm = view == null
        ? 16.0
        : min(
            _calculateDistance(view.center.latitude, view.center.longitude,
                view.northEast.latitude, view.northEast.longitude),
            _maxViewRadiusKm);
    if (searchLocation == null) {
      await DebugLogHelper.addDebugLog('HOME: Cannot load tours - no location available');
      return;
    }

    try {
      final prefs = await SharedPreferences.getInstance();
      // [LOCAL-670] Pass the chosen minimum rating to the server so it filters
      // (Any = omit the param entirely). The server computes the shown score and
      // drops tours below the bar.
      final uri = await Endpoints.url(Service.mapDelivery, '/tours-near/${searchLocation.latitude}/${searchLocation.longitude}?radius=${radiusKm.toStringAsFixed(1)}${_filterQueryParams()}');
      final url = uri.toString();
      
      await DebugLogHelper.addDebugLog('HOME: Requesting tours from: $url');
      
      final response = await http.get(
        uri,
        headers: await Endpoints.apiHeaders(Service.mapDelivery),
      ).timeout(Duration(seconds: 10));

      await DebugLogHelper.addDebugLog('HOME: Response status: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final tours = data['tours'] as List;
        _loadedTours = tours.whereType<Map>().map((t) => Map<String, dynamic>.from(t)).toList();
        await DebugLogHelper.addDebugLog('HOME: Received ${tours.length} tours from server');

        // Cache the tours
        await prefs.setString('cached_tours', json.encode(tours));
        await DebugLogHelper.addDebugLog('HOME: Cached ${tours.length} tours');

        // Group tours by proximity (within 100m)
        final clusteredTours = _clusterTours(tours);
        
        if (mounted) {
          setState(() {
            _tourMarkers = clusteredTours.map((cluster) {
              try {
                final toursList = cluster['tours'] as List?;
                if (toursList == null || toursList.isEmpty) return null;
                
                final firstTour = toursList[0] as Map<String, dynamic>?;
                if (firstTour == null) return null;
                
                // [LOCAL-757 A] Same pure rule as the cached path: a cluster
                // with a community tour is drawn GREEN with the groups icon.
                final markerKind = CommunityRules.homeMarkerKind(toursList);
                final isMultiple = toursList.length > 1;
                final isCommunity = markerKind == 'community';
                
                return Marker(
                  point: LatLng(cluster['lat'], cluster['lng']),
                  width: 40,
                  height: 40,
                  child: GestureDetector(
                    onTap: () => isMultiple 
                      ? _showMultipleTourDialog(toursList)
                      : _onTourMarkerTapped(firstTour),
                    child: Stack(
                      children: [
                        Container(
                          decoration: BoxDecoration(
                            color: homeMarkerColor(markerKind),
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                          child: Icon(
                            homeMarkerIcon(markerKind),
                            color: Colors.white,
                            size: 20,
                          ),
                        ),
                        // [LOCAL-682] Gold $ badge: this pin holds a paid tour.
                        if (_clusterHasPaid(toursList)) const _PaidPinBadge(),
                        // [LOCAL-757 A] Multi-tour badge dropped on a community
                        // pin (already green + groups icon; avoids green-on-green).
                        if (isMultiple && !isCommunity)
                          Positioned(
                            right: -2,
                            top: -2,
                            child: Container(
                              width: 20,
                              height: 20,
                              decoration: BoxDecoration(
                                color: Colors.green,
                                shape: BoxShape.circle,
                                border: Border.all(color: Colors.white, width: 1),
                              ),
                              child: Icon(
                                Icons.apps,
                                color: Colors.white,
                                size: 12,
                              ),
                            ),
                          ),
                      ],
                    ),
                  ),
                );
              } catch (e) {
                return null;
              }
            }).where((marker) => marker != null).cast<Marker>().toList();
          });
        }

        await DebugLogHelper.addDebugLog('HOME: Loaded ${tours.length} tours for ${_isUsingCustomLocation ? _customLocationName : "current location"}');
      } else {
        await DebugLogHelper.addDebugLog('HOME: Server error: ${response.statusCode}');
        if (mounted && response.statusCode == 401) {
          ErrorHandlerService.showError(context, statusCode: 401, endpoint: '/tours-near');
        }
        if (!mounted) return; // [LOCAL-773] setState after await.
        setState(() { _connectionError = true; });
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error loading tours: $e');
      if (mounted) setState(() { _connectionError = true; });
    }
  }
  
  /// [LOCAL-670] Choose the minimum tour rating to show (Any / 7+ / 8+ / 9+).
  /// Persisted per device under 'home_min_rating' and applied by reloading the
  /// nearby tours with the server-side min_rating filter.
  /// [LOCAL-670/672/677] The three Home filters as query params, shared by
  /// /tours-near and (LOCAL-680) /search-tours so a search honours them too.
  /// Any/Nearest omit their param.
  // [LOCAL-687] True when a tour element carries content_rating 'mature' (the
  // only rating the app ever shows — not_allowed/pending are never delivered).
  bool _isMatureTour(Map<String, dynamic> t) =>
      (t['content_rating']?.toString().toLowerCase() ?? 'general') == 'mature';

  // [LOCAL-687] The small "18+" chip shown beside mature tours in the List view
  // and the tour dialog.
  Widget _adultChip() => Container(
        padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
        decoration: BoxDecoration(
          color: Colors.deepOrange,
          borderRadius: BorderRadius.circular(4),
        ),
        child: const Text('18+',
            style: TextStyle(
                fontSize: 11, color: Colors.white, fontWeight: FontWeight.bold)),
      );

  // ─── [LOCAL-689] Personal "Match %" chip + reasons ─────────────────────────
  // The server attaches match_percent (int|null), match_reasons (two phrases),
  // and match_reason (the single cold-start sentence) to every tour item of
  // /tours-near and /search-tours. These helpers render them identically in the
  // List view and the tour dialog.

  int? _matchPercentOf(Map<String, dynamic> t) {
    final v = t['match_percent'];
    return v is num ? v.toInt() : null;
  }

  List<String> _matchReasonsOf(Map<String, dynamic> t) {
    final r = t['match_reasons'];
    if (r is List) return r.map((e) => e.toString()).toList();
    return const [];
  }

  /// The "Match 82%" chip. Green, like a personal fit. Null → no chip (the
  /// caller shows nothing, or the cold-start line via _matchReasonsLine).
  Widget? _matchChip(Map<String, dynamic> t) {
    final pct = _matchPercentOf(t);
    if (pct == null) return null;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
      decoration: BoxDecoration(
        color: Colors.green.shade600,
        borderRadius: BorderRadius.circular(4),
      ),
      child: Text('Match $pct%',
          style: const TextStyle(
              fontSize: 11, color: Colors.white, fontWeight: FontWeight.bold)),
    );
  }

  /// The two reason phrases joined ("strong on history, which you like; light on
  /// people stories"), or the cold-start sentence when there is no match yet.
  /// Returns null when there is nothing to say (no reasons and no cold line).
  Widget? _matchReasonsLine(Map<String, dynamic> t) {
    final reasons = _matchReasonsOf(t);
    String? text;
    if (reasons.isNotEmpty) {
      text = reasons.join('; ');
    } else if (_matchPercentOf(t) == null && t['match_reason'] is String) {
      text = t['match_reason'] as String;
    }
    if (text == null || text.isEmpty) return null;
    return Text(text,
        style: TextStyle(fontSize: 12, color: Colors.grey.shade700),
        maxLines: 2,
        overflow: TextOverflow.ellipsis);
  }

  String _filterQueryParams() {
    final minRatingParam =
        _minRating > 0 ? '&min_rating=${_minRating.toStringAsFixed(0)}' : '';
    // [LOCAL-689] Tri-state sort → ?sort=top_rated | match (nearest omits it).
    // 'match' also needs ?user_id so the server knows whose preferences to use;
    // we always attach user_id when we have one so every tour carries its
    // Match % regardless of the current sort (the chip shows in all orders).
    final sortParam = _sortMode == 'top_rated'
        ? '&sort=top_rated'
        : (_sortMode == 'match' ? '&sort=match' : '');
    final userParam = _deviceUserId.isNotEmpty
        ? '&user_id=${Uri.encodeComponent(_deviceUserId)}'
        : '';
    final priceParam = _priceFilter.isNotEmpty ? '&price=$_priceFilter' : '';
    // [LOCAL-687] 18+ confirmed → ask the server to include mature tours.
    final adultParam = _showAdult ? '&adult=1' : '';
    return '$minRatingParam$sortParam$userParam$priceParam$adultParam';
  }

  /// [LOCAL-680] One setter per filter, used by the AppBar dialogs and by the
  /// filter row inside the Search dialog. Persist, update, reload the map list.
  Future<void> _setMinRating(double value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setDouble('home_min_rating', value);
    if (!mounted) return;
    setState(() => _minRating = value);
    await _loadNearbyTours();
  }

  /// [LOCAL-672] The two-way Nearest/Top-rated control (AppBar icon, Search
  /// filter-row). Maps onto the tri-state _sortMode: true → 'top_rated',
  /// false → 'nearest'. Does not touch 'match' (that is set from the List view).
  Future<void> _setTopRated(bool value) async {
    await _setSortMode(value ? 'top_rated' : 'nearest');
  }

  /// [LOCAL-689] The tri-state sort used by the List view: 'nearest',
  /// 'top_rated', or 'match' (Best match first). Persisted under
  /// 'home_sort_mode'; the legacy 'home_top_rated' bool is kept in sync so an
  /// older build reading it still gets a sensible Nearest/Top-rated.
  Future<void> _setSortMode(String mode) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('home_sort_mode', mode);
    await prefs.setBool('home_top_rated', mode == 'top_rated');
    if (!mounted) return;
    setState(() => _sortMode = mode);
    await _loadNearbyTours();
  }

  Future<void> _setPriceFilter(String value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('home_price_filter', value);
    if (!mounted) return;
    setState(() => _priceFilter = value);
    await _loadNearbyTours();
  }

  /// [LOCAL-687] The "Show 18+ tours (I am 18 or older)" toggle. Persist per
  /// device and reload so the list immediately gains/loses mature tours.
  Future<void> _setShowAdult(bool value) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setBool('home_show_adult', value);
    if (!mounted) return;
    setState(() => _showAdult = value);
    await _loadNearbyTours();
  }

  /// [LOCAL-680] The sort button used to flip silently between a "sort" and a
  /// "trending up" arrow; Michael could not tell what the arrow meant. It now
  /// opens a dialog that names both orders.
  void _showSortDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Sort tours'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final topRated in [false, true])
              RadioListTile<bool>(
                title: Text(topRated ? 'Top rated first' : 'Nearest first'),
                subtitle: Text(topRated
                    ? 'Best listener ratings first; verified buyers count more'
                    : 'Closest to the map location first'),
                value: topRated,
                groupValue: _topRated,
                onChanged: (value) async {
                  if (value == null) return;
                  Navigator.pop(context);
                  await _setTopRated(value);
                },
              ),
            const Divider(),
            Text('Applies to the tours in the visible map area — zoom out to see more.',
                style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }

  void _showRatingFilterDialog() {
    const options = <String, double>{
      'Any': 0.0,
      '7+': 7.0,
      '8+': 8.0,
      '9+': 9.0,
    };
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Minimum rating'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final entry in options.entries)
              RadioListTile<double>(
                title: Text(entry.key == 'Any' ? 'Any rating' : '${entry.key} stars'),
                value: entry.value,
                groupValue: _minRating,
                onChanged: (value) async {
                  if (value == null) return;
                  Navigator.pop(context);
                  await _setMinRating(value);
                },
              ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }

  /// [LOCAL-677] Choose Free / Paid / Any tours. Persisted per device under
  /// 'home_price_filter' and applied by reloading the nearby tours with the
  /// server-side ?price=free|paid filter.
  void _showPriceFilterDialog() {
    const options = <String, String>{
      'Any': '',
      'Free': 'free',
      'Paid': 'paid',
    };
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Free or paid'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            for (final entry in options.entries)
              RadioListTile<String>(
                title: Text(entry.key == 'Any' ? 'Any tour' : '${entry.key} tours'),
                value: entry.value,
                groupValue: _priceFilter,
                onChanged: (value) async {
                  if (value == null) return;
                  Navigator.pop(context);
                  await _setPriceFilter(value);
                },
              ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
        ],
      ),
    );
  }

  /// [LOCAL-687] The "Show 18+ tours (I am 18 or older)" setting. A single
  /// switch, remembered per device. On → mature tours (strong language,
  /// alcohol/nightlife, gambling) are listed; off (the default) they are hidden.
  /// Nothing rated not_allowed is ever listed, and tours awaiting review stay
  /// hidden until a human approves — this toggle only governs mature tours.
  void _showAdultFilterDialog() {
    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('18+ tours'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              SwitchListTile(
                title: const Text('Show 18+ tours'),
                subtitle: const Text('I am 18 or older'),
                value: _showAdult,
                onChanged: (value) async {
                  setDialogState(() {});
                  Navigator.pop(context);
                  await _setShowAdult(value);
                },
              ),
              const Padding(
                padding: EdgeInsets.symmetric(horizontal: 16),
                child: Text(
                  'Mature tours (strong language, alcohol or nightlife focus, '
                  'gambling) are shown only when this is on.',
                  style: TextStyle(fontSize: 12, color: Colors.black54),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: const Text('Cancel'),
            ),
          ],
        ),
      ),
    );
  }

  /// dialogs (a title, a single text field, Cancel + Search), but a single box
  /// whose hint — "Share code, tour name, or place" — says it takes all three.
  /// On submit it hands the raw text to [classifySearchInput] and runs
  /// [_dispatchSearch]; the FORMAT decides what happens, not which button the
  /// listener happened to press.
  void _showSearchDialog() {
    final TextEditingController controller = TextEditingController();

    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
        // [LOCAL-680] scrollable: with the keyboard up the content no longer
        // fits, and an unscrollable Column let the action buttons overlap the
        // examples (Michael, 2026-10-14). Now the whole body scrolls instead.
        scrollable: true,
        title: const Text('Search'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              decoration: const InputDecoration(
                hintText: 'Share code, tour name, or place',
                labelText: 'Search',
              ),
              autofocus: true,
              onSubmitted: (value) async {
                final query = value.trim();
                if (query.isEmpty) return;
                Navigator.pop(context);
                await _dispatchSearch(query);
              },
            ),
            const SizedBox(height: 12),
            // [LOCAL-680] The three Home filters, also here, so a search can be
            // narrowed without leaving the dialog. Same state as the AppBar icons.
            _buildSearchFilters(setDialogState),
            const SizedBox(height: 12),
            // [LOCAL-680] The one box takes three kinds of input (LOCAL-665), so show
            // one example of each, grouped. Michael, 2026-10-14: the examples were
            // lost when the three dialogs were merged, and they matter more now.
            const _SearchExamples(),
            const SizedBox(height: 16),
            if (_locationHistory.isNotEmpty) ...[
              const Text('Recent Locations:', style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 8),
              // A plain Column: a scrollable dialog cannot host a Flexible list.
              Column(
                mainAxisSize: MainAxisSize.min,
                children: List.generate(_locationHistory.length, (index) {
                    final location = _locationHistory[index];
                    return ListTile(
                      dense: true,
                      leading: const Icon(Icons.history, size: 16),
                      title: Text(location['name'], style: const TextStyle(fontSize: 14)),
                      onTap: () {
                        Navigator.pop(context);
                        _useCustomLocation(
                          LatLng(location['lat'], location['lng']),
                          location['name'],
                        );
                      },
                    );
                }),
              ),
            ],
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () {
              Navigator.pop(context);
              _resetToCurrentLocation();
            },
            child: const Text('Use Current Location'),
          ),
          ElevatedButton(
            onPressed: () async {
              final query = controller.text.trim();
              if (query.isEmpty) return;
              Navigator.pop(context);
              await _dispatchSearch(query);
            },
            child: const Text('Search'),
          ),
        ],
      ),
      ),
    );
  }

  /// [LOCAL-680] Rating / Sort / Price as three labelled dropdowns inside the
  /// Search dialog. [setDialogState] repaints the dialog after a change.
  Widget _buildSearchFilters(StateSetter setDialogState) {
    Widget row<T>(String label, T value, Map<T, String> options,
        Future<void> Function(T) onSet) {
      return Row(
        children: [
          SizedBox(width: 64, child: Text(label, style: const TextStyle(fontSize: 13))),
          Expanded(
            child: DropdownButton<T>(
              isExpanded: true,
              isDense: true,
              value: value,
              items: [
                for (final e in options.entries)
                  DropdownMenuItem<T>(
                    value: e.key,
                    child: Text(e.value, style: const TextStyle(fontSize: 13)),
                  ),
              ],
              onChanged: (v) async {
                if (v == null) return;
                await onSet(v);
                setDialogState(() {});
              },
            ),
          ),
        ],
      );
    }

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        // A stored bar outside the menu would crash DropdownButton; show Any.
        row<double>('Rating', const [7.0, 8.0, 9.0].contains(_minRating) ? _minRating : 0.0,
            <double, String>{0.0: 'Any rating', 7.0: '7+ stars', 8.0: '8+ stars', 9.0: '9+ stars'},
            _setMinRating),
        row<bool>('Sort', _topRated,
            const {false: 'Nearest first', true: 'Top rated first'}, _setTopRated),
        row<String>('Price', _priceFilter,
            const {'': 'Free and paid', 'free': 'Free only', 'paid': 'Paid only'},
            _setPriceFilter),
      ],
    );
  }

  /// [LOCAL-665] Act on one search string by its format, in a fixed order:
  ///   a. share code  → resolve, open the single/multi-tour dialog; if unknown,
  ///      say so and STOP (no fall-through to a place search).
  ///   b. coordinates → move the map there.
  ///   c. otherwise   → run the tour-name search AND the place lookup together.
  Future<void> _dispatchSearch(String query) async {
    final dispatch = classifySearchInput(query);
    switch (dispatch.kind) {
      case SearchKind.shareCode:
        await _dispatchShareCode(dispatch.shareCode!);
        return;
      case SearchKind.coordinates:
        _useCustomLocation(
          LatLng(dispatch.latitude!, dispatch.longitude!),
          '${dispatch.latitude}, ${dispatch.longitude}',
        );
        return;
      case SearchKind.text:
        await _dispatchTextSearch(dispatch);
        return;
    }
  }

  /// [LOCAL-665] (a) A share code: resolve it to tours and open the SAME dialogs
  /// the map uses. An unknown code is a dead end on purpose — we tell the user to
  /// check their server rather than silently searching for a place by that code.
  Future<void> _dispatchShareCode(String code) async {
    final tours = await _resolveShareCode(code);
    if (!mounted) return;
    if (tours.isNotEmpty) {
      _presentFoundTours(tours);
    } else {
      // [LOCAL-690] Not a tour code — try it as a community INVITE code (the
      // join flow, D658 addendum 2 §3). A member → the community page opens to
      // its episodes; a non-member → the page shows "This tour belongs to
      // <Community>. Join to listen" with the passes.
      // [LOCAL-703 / D664] An archived community's code is dead: the server
      // returns 410 community_closed and we tell the listener plainly.
      final res = await CommunitiesService.resolveByCodeResult(code);
      if (!mounted) return;
      if (res.found) {
        Navigator.push(
          context,
          MaterialPageRoute(
              builder: (_) =>
                  CommunityPageScreen(communityId: res.community!.id)),
        );
        return;
      }
      if (res.closed) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text(CommunityCopy.communityClosed),
            backgroundColor: Colors.orange,
            duration: Duration(seconds: 5),
          ),
        );
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No tour or community with that code on this server (check Settings → server)'),
          backgroundColor: Colors.orange,
          duration: Duration(seconds: 5),
        ),
      );
    }
  }

  /// [LOCAL-665] (c) Not a code, not coordinates: run the tour-name search and
  /// the place geocoder CONCURRENTLY, then present the single combined outcome
  /// (resolveTextSearch): tours+place, tours only, place only, or nothing.
  ///
  /// [LOCAL-717 / D677 §3] When the input's LAST character is `*`
  /// ([SearchDispatch.tourNameOnly]) it is a tour-NAME search ONLY: the geocoder
  /// is NEVER called, so a far-away place called "Restaurant" can never win
  /// (Michael's "restaurant*" bug). No tours matched → "No tours named
  /// '<text>…'", never a place relocation.
  Future<void> _dispatchTextSearch(SearchDispatch dispatch) async {
    final query = dispatch.query;
    final nameOnly = dispatch.tourNameOnly;
    // Run the tour-name search and (unless name-only) the place geocoder
    // concurrently. Kept as separate typed futures so the geocoder's
    // [GeoResult] carries the resolved place NAME through to the banner.
    final toursFuture = _searchTours(query);
    final placeFuture = nameOnly
        ? Future<GeoResult?>.value(null)
        : _geocodeLocation(query);
    final tours = await toursFuture;
    final place = await placeFuture;
    if (!mounted) return;

    // [LOCAL-793] Show the RESOLVED place name in the banner, not the raw typed
    // text, so a wrong match ("Saigon Vietnam" → a Paris restaurant) is visible
    // at once. Falls back to the typed query when the geocoder gave no name.
    final placeName = place?.name ?? query;

    final outcome = resolveTextSearch(
      tourCount: tours.length,
      placeFound: place != null,
      nameOnly: nameOnly,
    );

    switch (outcome) {
      case TextSearchOutcome.toursAndPlace:
        await _presentFoundToursWithPlace(tours, place!.location, placeName);
        return;
      case TextSearchOutcome.toursOnly:
        _presentFoundTours(tours);
        return;
      case TextSearchOutcome.placeOnly:
        await _useCustomLocation(place!.location, placeName);
        return;
      case TextSearchOutcome.nothing:
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Nothing found for "$query"')),
        );
        return;
      case TextSearchOutcome.noNamedTours:
        // [LOCAL-717 / D677 §3] A trailing-`*` name search with no matches.
        // Strip the trailing `*` so the message names what the user typed.
        final typed = query.endsWith('*')
            ? query.substring(0, query.length - 1)
            : query;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text("No tours named '$typed…'")),
        );
        return;
    }
  }

  /// [LOCAL-697 / LEAD D662] Tours AND a place both matched the text. A found
  /// PLACE wins: move the map there immediately and show the normal Home view of
  /// that area — exactly as a plain place search does, with NO tours dialog and
  /// NO "relocate?" confirmation (restores the pre-LOCAL-665 behaviour Michael
  /// reported as regressed, Pixel-4 2026-10-15). Because tour NAMES also matched,
  /// a small snackbar offers 'N tours named "<query>" — Show'; tapping Show opens
  /// the usual found-tours dialog. The relocation is awaited so the map has moved
  /// before the snackbar appears.
  Future<void> _presentFoundToursWithPlace(
      List<Map<String, dynamic>> tours, LatLng place, String placeName) async {
    await _useCustomLocation(place, placeName);
    if (!mounted) return;
    final n = tours.length;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('$n tour${n == 1 ? '' : 's'} named "$placeName"'),
        action: SnackBarAction(
          label: 'Show',
          onPressed: () => _presentFoundTours(tours),
        ),
        duration: const Duration(seconds: 6),
      ),
    );
  }
  
  /// [LOCAL-793 live fix] Move the map safely.
  ///
  /// During a relocation the Home screen briefly shows a full-screen loading
  /// spinner (`_isLoading == true`), so `build()` does NOT render the
  /// `FlutterMap` and flutter_map disposes the `MapController`'s internal
  /// controller. A `_mapController.move()` in that window throws
  /// "A FlutterMapInternalController was used after being disposed", which on
  /// the iOS simulator aborted `_useCustomLocation` before it could load the
  /// area's tours or clear `_isLoading` — leaving the map stuck on the spinner
  /// and NO tours shown (surfaced live, 2026-10-28, searching "Ho Chi Minh
  /// City"). The move is in any case redundant while unmounted: when the map
  /// remounts it is recreated with `initialCenter: _displayLocation`, i.e. the
  /// new location. So swallow exactly that transient "disposed" error and let
  /// the flow continue; any other error still surfaces in the debug log.
  void _safeMapMove(LatLng location, double zoom) {
    try {
      _mapController.move(location, zoom);
    } catch (e) {
      // The controller is detached (map not mounted during the loading
      // spinner); the map will re-center via initialCenter on remount.
      DebugLogHelper.addDebugLog('HOME: map move skipped (controller not ready): $e');
    }
  }

  Future<void> _useCustomLocation(LatLng location, String name) async {
    setState(() {
      _displayLocation = location;
      _isUsingCustomLocation = true;
      _customLocationName = name;
      _isLoading = true;
    });
    
    // Add to history (avoid duplicates)
    final locationData = {
      'name': name,
      'lat': location.latitude,
      'lng': location.longitude,
      'timestamp': DateTime.now().toIso8601String(),
    };
    
    _locationHistory.removeWhere((item) => item['name'] == name);
    _locationHistory.insert(0, locationData);
    if (_locationHistory.length > 10) {
      _locationHistory = _locationHistory.take(10).toList();
    }
    await _saveLocationHistory();
    await _saveCustomLocation();
    
    await DebugLogHelper.addDebugLog('HOME: Using custom location: $name');
    
    // Move map to new location
    _safeMapMove(location, 13.0);
    
    // Load tours for new location
    await _loadNearbyTours();

    // [LOCAL-793] Never show a false "0 tours in this map area" when a tour is
    // close by. If nothing loaded into the view, look within ~50 km for the
    // nearest tour and either zoom out to include it or tell the listener how
    // far the nearest tour is (so a search that lands a few km off a city still
    // shows its tours — Michael's "Hi Chi Minh" → "0 tours" bug).
    if (mounted && _loadedTours.isEmpty) {
      await _showNearestToursIfAny(location);
    }
    
    if (!mounted) return; // [LOCAL-773] setState after await.
    setState(() {
      _isLoading = false;
    });
  }

  /// [LOCAL-793] After a relocation left the view empty, find the nearest tour
  /// within [kMaxZoomOutRadiusKm] and act on [decideZoomOut]: zoom out to show
  /// it, or announce "Nearest tours: N km away" with a button to go there.
  Future<void> _showNearestToursIfAny(LatLng center) async {
    final nearest = await _nearestTourWithin(center, kMaxZoomOutRadiusKm);
    if (!mounted) return;
    final decision = decideZoomOut(
      tourInView: false,
      nearestTourKm: nearest?.distanceKm,
    );
    switch (decision.action) {
      case ZoomOutAction.keep:
        return;
      case ZoomOutAction.zoomToShow:
        // Zoom out so the nearby tour is on screen, then reload the view's
        // tours so the pins and the List reflect the wider area.
        _safeMapMove(center, decision.zoom!);
        await _loadNearbyTours();
        return;
      case ZoomOutAction.announceDistance:
        final km = decision.nearestKm!;
        final tour = nearest!.tour;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Nearest tours: $km km away'),
            action: SnackBarAction(
              label: 'Show',
              onPressed: () {
                final lat = (tour['lat'] as num).toDouble();
                final lng = (tour['lng'] as num).toDouble();
                _safeMapMove(LatLng(lat, lng), 13.0);
                _loadNearbyTours();
              },
            ),
            duration: const Duration(seconds: 8),
          ),
        );
        return;
    }
  }

  /// [LOCAL-793] Ask map-delivery for the tours within [radiusKm] of [center]
  /// and return the closest one with its distance, or null when none exist in
  /// that radius. Used only to recover from an empty relocated view.
  Future<_NearestTour?> _nearestTourWithin(LatLng center, double radiusKm) async {
    try {
      final uri = await Endpoints.url(
          Service.mapDelivery,
          '/tours-near/${center.latitude}/${center.longitude}'
          '?radius=${radiusKm.toStringAsFixed(1)}${_filterQueryParams()}');
      final response = await http
          .get(uri, headers: await Endpoints.apiHeaders(Service.mapDelivery))
          .timeout(const Duration(seconds: 10));
      if (response.statusCode != 200) return null;
      final data = json.decode(response.body);
      final tours = (data is Map ? data['tours'] : null) as List?;
      if (tours == null || tours.isEmpty) return null;
      _NearestTour? best;
      for (final t in tours) {
        if (t is! Map) continue;
        final tour = Map<String, dynamic>.from(t);
        final lat = tour['lat'];
        final lng = tour['lng'];
        if (lat is! num || lng is! num) continue;
        final km = _calculateDistance(
            center.latitude, center.longitude, lat.toDouble(), lng.toDouble());
        if (best == null || km < best.distanceKm) {
          best = _NearestTour(tour: tour, distanceKm: km);
        }
      }
      return best;
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: nearest-tour lookup error: $e');
      return null;
    }
  }
  
  void _resetToCurrentLocation() async {
    setState(() {
      _displayLocation = null;
      _isUsingCustomLocation = false;
      _customLocationName = '';
      _isLoading = true;
    });
    
    await _saveCustomLocation();
    await DebugLogHelper.addDebugLog('HOME: Reset to current location');
    
    if (_userLocation != null) {
      _safeMapMove(_userLocation!, 13.0);
      await _loadNearbyTours();
    }
    
    if (!mounted) return; // [LOCAL-773] setState after await.
    setState(() {
      _isLoading = false;
    });
  }

  /// [LEAD 2026-10-09] Found-by-name tours use exactly the map's dialogs (shared code, same look):
  /// one tour → the single-tour dialog, several → the multi-tour dialog.
  void _presentFoundTours(List<Map<String, dynamic>> tours) {
    if (tours.length == 1) {
      _onTourMarkerTapped(tours.first);
    } else {
      _showMultipleTourDialog(tours);
    }
  }

  /// [LOCAL-680] [done] completes when the listener is finished with this tour:
  /// the dialog closed without buying, or Buy & Download finished. The multi-tour
  /// download awaits it to show paid tours one at a time. [cancelLabel] renames
  /// Cancel (the sequence says "Don't download").
  void _onTourMarkerTapped(Map<String, dynamic> item,
      {Completer<void>? done, String cancelLabel = 'Cancel'}) {
    if (item['type'] == 'treat') {
      // Navigate directly to treat detail view
      Navigator.push(
        context,
        MaterialPageRoute(
          builder: (context) => _TreatDetailView(
            treatData: item,
          ),
        ),
      );
    } else {
      // Show download dialog for tours with language selection
      List<String> selectedLanguages = ['en'];
      // [LOCAL-677C / D654] Pay before download. For an UNBOUGHT PAID tour the
      // dialog shows "▶ Preview Stop 1" + "Buy & Download — $X" and NO plain
      // Download. We ask the server once whether THIS tour (the row the listener
      // tapped) is already unlocked for this device; the paid flag comes inline
      // on the item (price_tier / price_label from map-delivery). A free or
      // already-unlocked tour keeps the plain "Download Tour".
      final bool itemIsPaid = item['is_paid'] == true ||
          (item['price_tier'] is num && (item['price_tier'] as num) > 0);
      bool unlockKnown = !itemIsPaid; // free: nothing to ask
      bool unlockUnlocked = !itemIsPaid; // free counts as unlocked
      bool buyBusy = false;
      // [LOCAL-680] Set while Buy & Download runs: its own Navigator.pop must
      // not count as "closed without buying".
      bool buyStarted = false;
      void finish() {
        if (done != null && !done.isCompleted) done.complete();
      }

      showDialog(
        context: context,
        builder: (context) => StatefulBuilder(
          builder: (context, setDialogState) {
            // Fetch the unlock state once for a paid tour (fire and forget; the
            // dialog shows a brief spinner on the Buy row until it resolves).
            if (itemIsPaid && !unlockKnown) {
              TourPricingService.unlockState('${item['id']}').then((st) {
                unlockKnown = true;
                unlockUnlocked = st.unlocked;
                if (context.mounted) setDialogState(() {});
              });
            }
            // [LOCAL-680] A paid tour is bought ONE language at a time (D653:
            // each language is its own $X purchase), so its selector is
            // single-choice. Free / owned tours keep multi-select.
            final bool singleLanguage = itemIsPaid && !unlockUnlocked;
            return AlertDialog(
            // [LOCAL-680] Long titles + reviews pushed the language selector off
            // screen; the body scrolls so every control is reachable.
            scrollable: true,
            title: Text(item['name']),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // [LOCAL-677B] Hide the Distance line when distance_km is null:
                // the share-code (/tour-by-code) and search-results entries carry
                // no distance, and "Distance: null km" is nonsense. Only shown
                // when the server sent a real distance.
                if (shouldShowDistance(item))
                  Text('Distance: ${item['distance_km']} km'),
                Text('Downloads: ${item['popularity']}'),
                SizedBox(height: 6),
                // [LOCAL-670] Rating badge "★ 8.3 · 2 ratings" / "★ 7.5 · New".
                // [LOCAL-677] Price badge "$4.99" / "Free" beside the rating.
                // [LOCAL-689] Personal "Match 82%" chip leads the row when the
                // server computed one for this listener.
                Row(
                  children: [
                    if (_matchChip(item) != null) ...[
                      _matchChip(item)!,
                      const SizedBox(width: 8),
                    ],
                    TourRatingBadge.fromTour(item,
                        onTap: () => showWhyThisScoreSheet(context,
                            tourId: '${item['id']}', tour: item)),
                    const SizedBox(width: 8),
                    // [LOCAL-756 C] A community tour shows its membership price
                    // line here instead of the money "Free"/"$4.99" badge.
                    if (CommunityRules.isCommunityTour(item))
                      _communityPriceLine(item)!
                    else
                      TourPriceBadge.fromTour(item),
                    if (_isMatureTour(item)) ...[
                      const SizedBox(width: 8),
                      _adultChip(),
                    ],
                  ],
                ),
                // [LOCAL-756 C] The community sign (name) under the badges, so
                // the detail sheet shows the listener which community the tour
                // belongs to. Null (nothing shown) for a plain Audioura tour.
                if (_communitySign(item) != null) ...[
                  const SizedBox(height: 4),
                  _communitySign(item)!,
                ],
                // [LOCAL-689] The two reason phrases ("strong on history, which
                // you like; light on people stories") or the cold-start line.
                if (_matchReasonsLine(item) != null) ...[
                  const SizedBox(height: 4),
                  _matchReasonsLine(item)!,
                ],
                if (_tourVersionLabel(item) != null)
                  Text(
                    _tourVersionLabel(item)!,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.blue.shade700,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                // [LOCAL-671] The original language, beside the version/rating
                // badges. Not a translation list — the selector below still lets
                // the listener translate into any language.
                if (_originalLanguageLabel(item) != null)
                  Text(
                    _originalLanguageLabel(item)!,
                    style: TextStyle(
                      fontSize: 12,
                      color: Colors.grey.shade700,
                      fontWeight: FontWeight.w500,
                    ),
                  ),
                SizedBox(height: 10),
                Text(item['request_string']),
                SizedBox(height: 12),
                // [LOCAL-672] Reviews (n): expandable list with the rating
                // distribution bars, sort/filter, "Verified listener" badges,
                // helpful votes and the curator reply.
                ReviewsSection(
                  tourId: '${item['id']}',
                  initialCount: (item['rating_count'] as num?)?.toInt() ?? 0,
                  tourTitle: item['name']?.toString() ?? 'this tour',
                ),
                SizedBox(height: 16),
                Text(singleLanguage ? 'Choose a language:' : 'Select Languages:',
                    style: TextStyle(fontWeight: FontWeight.bold)),
                if (singleLanguage)
                  Text('Each language is a separate purchase.',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade700)),
                // [LOCAL-693B / D660 addendum] No warning at purchase time: a
                // bought tour is like a bought bag — buyers understand that
                // without being warned. The only confirmation lives at DELETION
                // (see DeleteTourPrompt), in a calm voice.
                SizedBox(height: 8),
                LanguageSelector(
                  selectedLanguages: selectedLanguages,
                  onLanguagesChanged: (languages) {
                    setDialogState(() {
                      if (singleLanguage) {
                        // Keep exactly one: the newly tapped chip wins; tapping
                        // the selected chip again leaves it selected.
                        final added = languages
                            .where((l) => !selectedLanguages.contains(l))
                            .toList();
                        if (added.isNotEmpty) selectedLanguages = [added.last];
                      } else {
                        selectedLanguages = languages;
                      }
                    });
                  },
                ),
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text(cancelLabel),
              ),
              // [LOCAL-670] Rate this tour 1–10. On success, refresh the badge
              // in this dialog with the recomputed score.
              // [LOCAL-672] Then offer an optional short text review.
              TextButton(
                onPressed: () async {
                  final result = await showRateTourDialog(
                    context,
                    tourId: '${item['id']}',
                    tourTitle: item['name']?.toString() ?? 'this tour',
                  );
                  if (result != null && result.aggregate != null) {
                    item['rating_score'] = result.aggregate!.score;
                    item['rating_count'] = result.aggregate!.count;
                    item['rating_label'] = result.aggregate!.label;
                    setDialogState(() {});
                    // [LOCAL-672] Offer "Add a short review" right after rating.
                    if (context.mounted) {
                      final status = await showAddReviewDialog(
                        context,
                        tourId: '${item['id']}',
                        tourTitle: item['name']?.toString() ?? 'this tour',
                      );
                      if (status != null && context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(status == 'approved'
                                ? 'Thanks! Your review is live.'
                                : 'Thanks! Your review is being checked.'),
                          ),
                        );
                      }
                    }
                  }
                },
                child: Text('Rate'),
              ),
              // [LOCAL-677C / D654] Pay before download. A free (or already
              // unlocked) tour keeps the plain "Download Tour". An unbought paid
              // tour shows "▶ Preview Stop 1" + "Buy & Download — $X" and NO
              // plain Download — the download starts only after the purchase
              // confirms the unlock.
              ..._buildDownloadActions(
                context: context,
                setDialogState: setDialogState,
                item: item,
                selectedLanguages: selectedLanguages,
                plan: DownloadActionPlan.decide(
                  isPaid: itemIsPaid,
                  unlocked: unlockUnlocked,
                  priceTier: (item['price_tier'] as num?)?.toInt(),
                  priceLabel: item['price_label'] as String?,
                ),
                unlockKnown: unlockKnown,
                buyBusy: buyBusy,
                onBuyBusy: (b) => setDialogState(() => buyBusy = b),
                onBuyStarted: (started) {
                  buyStarted = started;
                },
                onUnlocked: () {
                  if (context.mounted) {
                    setDialogState(() {
                      unlockUnlocked = true;
                    });
                  }
                },
                onFinished: finish,
              ),
            ],
          );
          },
        ),
      ).then((_) {
        // [LOCAL-680] Closing the dialog always stops the preview.
        TourPreviewPlayer.instance.stop();
        if (!buyStarted) finish();
      });
    }
  }

  /// [LOCAL-677C / D654] The download-dialog action buttons for a tour, decided
  /// by [plan]. Free / unlocked: a plain "Download Tour". Unbought paid: a
  /// "▶ Preview Stop 1" button (streams Stop 1, nothing saved) and a
  /// "Buy & Download — $X" button that buys EACH selected paid language, then
  /// downloads only the languages whose unlock the server confirmed.
  List<Widget> _buildDownloadActions({
    required BuildContext context,
    required StateSetter setDialogState,
    required Map<String, dynamic> item,
    required List<String> selectedLanguages,
    required DownloadActionPlan plan,
    required bool unlockKnown,
    required bool buyBusy,
    required void Function(bool) onBuyBusy,
    required void Function(bool) onBuyStarted,
    required void Function() onUnlocked,
    required void Function() onFinished,
  }) {
    if (plan.showPlainDownload) {
      return [
        ElevatedButton(
          onPressed: () {
            Navigator.pop(context);
            _downloadSingleTour(item['id'], selectedLanguages, item);
          },
          child: const Text('Download Tour'),
        ),
      ];
    }

    // Unbought paid tour: Preview + Buy & Download, no plain Download.
    final String priceLabel = plan.priceLabel ?? '\$4.99';
    final int tier = plan.priceTier ?? 3;
    return [
      // [LOCAL-680] Preview → Pause / Resume + Stop while it plays.
      _PreviewControls(tourId: '${item['id']}', enabled: !buyBusy),
      ElevatedButton(
        onPressed: (buyBusy || !unlockKnown || selectedLanguages.isEmpty)
            ? null
            : () async {
                onBuyBusy(true);
                onBuyStarted(true);
                final ok = await _buyAndDownloadPaid(
                  context: context,
                  item: item,
                  tier: tier,
                  priceLabel: priceLabel,
                  language: selectedLanguages.first,
                );
                if (ok) {
                  onUnlocked();
                  onFinished();
                } else {
                  onBuyStarted(false);
                  if (context.mounted) onBuyBusy(false);
                }
              },
        style: ElevatedButton.styleFrom(
          backgroundColor: const Color(0xFF1B6B2E),
          foregroundColor: Colors.white,
        ),
        child: buyBusy
            ? const SizedBox(
                height: 18,
                width: 18,
                child: CircularProgressIndicator(
                    strokeWidth: 2, color: Colors.white),
              )
            : Text('Buy & Download — $priceLabel'),
      ),
    ];
  }

  /// [LOCAL-677C / D654] Buy EACH selected paid language (one purchase each,
  /// D653: 2 × \$4.99 for two), then download only the languages the server
  /// confirmed as unlocked. Stops the preview first. Returns true if at least
  /// the tapped tour was unlocked and downloaded. A 402 on download never
  /// crashes — it leaves the Buy button in place (the tour stays locked).
  Future<bool> _buyAndDownloadPaid({
    required BuildContext context,
    required Map<String, dynamic> item,
    required int tier,
    required String priceLabel,
    required String language,
  }) async {
    await TourPreviewPlayer.instance.stop();
    // [LOCAL-680] Buy exactly ONE language (D653). 'en' / the tour's own
    // language is the tapped row itself; any other language is its translation
    // row, which unlocks separately — so resolve that row and buy IT. Before
    // this, every purchase was charged to the tapped (English) row and the
    // chosen translation then 402'd.
    final int tappedId = item['id'] is int ? item['id'] as int : int.parse('${item['id']}');
    final String itemLang = (item['content_language'] ?? 'en').toString();
    final bool ownRow = language == 'en' || language == itemLang;
    int buyId = tappedId;
    if (!ownRow) {
      final translated = await TourTranslationHelper.translatedRowId(tappedId, language);
      if (translated == null) {
        if (context.mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
                content: Text(
                    '${TourTranslationHelper.availableLanguages[language] ?? language} is not available for this tour right now.')),
          );
        }
        return false;
      }
      buyId = translated;
    }
    if (!context.mounted) return false;
    final langName = TourTranslationHelper.availableLanguages[language] ?? language;
    // The Buy sheet drives the real store (cloud) or the TEST PURCHASE (stub).
    final bought = await TourBuySheet.show(
      context,
      tourId: '$buyId',
      tier: tier,
      priceLabel: priceLabel,
      tourTitle: '${item['name'] ?? 'Tour'} ($langName)',
    );
    if (!bought) return false; // cancelled / failed — Buy button stays.
    if (!context.mounted) return false;

    // Confirm the unlock with the server before downloading. A 402 on the
    // download would otherwise mean we never saved the zip.
    final state = await TourPricingService.unlockState('$buyId');
    if (!state.unlocked) {
      if (context.mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
              content: Text('Purchase not confirmed yet — please try again.')),
        );
      }
      return false;
    }

    if (!context.mounted) return false;
    Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] close root-pushed download dialog
    // Now download only the bought language. 'en' in the list means "the
    // tapped row itself" (_downloadSingleTour's convention); a translation is
    // fetched by the translation path, which now gets 200 because it is unlocked.
    await _downloadSingleTour(tappedId, ownRow ? const ['en'] : [language], item);
    return true;
  }

  /// [LOCAL-677C / D654] The /download-tour URL carrying the device user_id so
  /// the server can decide the pay-before-download gate (unlock / grandfather /
  /// curator). Without this the server would treat the request as anonymous and
  /// 402 even a tour the device already owns. [LOCAL-780] Delegates to the ONE
  /// shared builder so Home and the Generate screen attach user_id identically.
  Future<Uri> _downloadTourUri(int tourId) async =>
      Endpoints.downloadTourUrl(tourId);

  /// [LOCAL-693B / D660 LEAD] Report a FAILED paid download so the server
  /// RESTORES the purchase once. Consumption is decided SERVER-SIDE now (the
  /// server spends the purchase when it finishes streaming the zip), so the app
  /// no longer confirms success. It calls this ONLY when the bytes were received
  /// (HTTP 200) but the zip could not be saved or validated. The server restores
  /// the just-consumed purchase exactly once, within 24h (a second report, or
  /// one past the window, gets 409). [consumesHeader] is the
  /// X-Download-Consumes-Unlock response header: '1' means this download spent a
  /// purchase and is worth reporting; anything else (free / curator /
  /// grandfathered / unpaid) is a no-op. Fully defensive: a failed report never
  /// throws out of here (the caller already rethrows the save error for the
  /// user-facing message); the server reconciles on the next online check.
  Future<void> _reportDownloadFailed(
      int tourId, String? consumesHeader, String reason) async {
    if (consumesHeader != '1') return; // nothing was consumed → nothing to restore
    try {
      final prefs = await SharedPreferences.getInstance();
      final userId = prefs.getString('user_id') ?? '';
      await Endpoints.post(
        Service.mapDelivery,
        '/tour/$tourId/download-failed',
        body: {'user_id': userId, 'reason': reason},
        timeout: const Duration(seconds: 15),
      );
      await DebugLogHelper.addDebugLog(
          'HOME: download-failed reported for tour $tourId (reason=$reason)');
    } catch (e) {
      // A failed report is safe: the server reconciles unlock-state on the next
      // online check. Never surface to the user from here.
      await DebugLogHelper.addDebugLog(
          'HOME: download-failed report failed for $tourId: $e');
    }
  }

  List<Map<String, dynamic>> _clusterTours(List tours) {
    final clusters = <Map<String, dynamic>>[];
    final processed = <bool>[];
    
    for (int i = 0; i < tours.length; i++) {
      processed.add(false);
    }
    
    for (int i = 0; i < tours.length; i++) {
      if (processed[i]) continue;
      
      final cluster = {
        'lat': tours[i]['lat'],
        'lng': tours[i]['lng'],
        'tours': [tours[i]],
      };
      processed[i] = true;
      
      // Find nearby tours (within 100m)
      for (int j = i + 1; j < tours.length; j++) {
        if (processed[j]) continue;
        
        final distance = _calculateDistance(
          tours[i]['lat'], tours[i]['lng'],
          tours[j]['lat'], tours[j]['lng'],
        );
        
        if (distance <= 0.1) { // 100m
          cluster['tours'].add(tours[j]);
          processed[j] = true;
        }
      }
      
      clusters.add(cluster);
    }
    
    return clusters;
  }
  
  double _calculateDistance(double lat1, double lng1, double lat2, double lng2) {
    const double earthRadius = 6371;
    final double dLat = (lat2 - lat1) * (3.14159 / 180);
    final double dLng = (lng2 - lng1) * (3.14159 / 180);
    final double a = sin(dLat / 2) * sin(dLat / 2) +
        cos(lat1 * (3.14159 / 180)) * cos(lat2 * (3.14159 / 180)) *
        sin(dLng / 2) * sin(dLng / 2);
    final double c = 2 * atan2(sqrt(a), sqrt(1 - a));
    return earthRadius * c;
  }
  
  String _getTourTypeIcon(String? type) {
    switch (type) {
      case 'walking_tour': return '🚶';
      case 'museum_tour': return '🏛️';
      case 'shopping_tour': return '🛍️';
      case 'art_tour': return '🎨';
      case 'food_tour': return '🍽️';
      case 'history_tour': return '📚';
      default: return '🗺️';
    }
  }
  
  String _getTourTypeName(String? type) {
    switch (type) {
      case 'walking_tour': return 'Walking';
      case 'museum_tour': return 'Museum';
      case 'shopping_tour': return 'Shopping';
      case 'art_tour': return 'Art';
      case 'food_tour': return 'Food';
      case 'history_tour': return 'History';
      default: return 'Tour';
    }
  }

  // [LOCAL-657] "v{version} · updated {Mon D}" shown next to Downloads, but only
  // when a tour has actually been replaced (version >= 2). Returns null when the
  // label should not appear: version is missing (an old map-delivery that does
  // not send the field), unparseable, or still 1. A missing field must never
  // crash the dialog, so every read is defensive.
  static const List<String> _monthAbbr = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ];

  String? _tourVersionLabel(Map<String, dynamic> tour) {
    final rawVersion = tour['version'];
    int? version;
    if (rawVersion is int) {
      version = rawVersion;
    } else if (rawVersion is num) {
      version = rawVersion.toInt();
    } else if (rawVersion is String) {
      version = int.tryParse(rawVersion);
    }
    if (version == null || version < 2) {
      return null;
    }

    String label = 'v$version';
    final updatedAt = tour['updated_at'];
    if (updatedAt is String && updatedAt.isNotEmpty) {
      final parsed = DateTime.tryParse(updatedAt);
      if (parsed != null && parsed.month >= 1 && parsed.month <= 12) {
        label += ' · updated ${_monthAbbr[parsed.month - 1]} ${parsed.day}';
      }
    }
    return label;
  }

  // [LOCAL-756 C] Whether THIS user belongs to the tour's community. A tour map
  // from /tours-near carries `community_id`; membership is the joined-ID set
  // loaded in _loadCommunityMembership. A non-community tour is never "a member
  // tour" and returns false.
  bool _isMemberOfTour(Map<String, dynamic> tour) {
    final cid = tour['community_id'];
    if (cid is num) return _joinedCommunityIds.contains(cid.toInt());
    if (cid is String) {
      final parsed = int.tryParse(cid);
      return parsed != null && _joinedCommunityIds.contains(parsed);
    }
    return false;
  }

  // [LOCAL-757 B] The COMMUNITY CHIP for a tour — the single green
  // CommunityTourChip widget (groups icon + "Members only · <name>" /
  // "Community tour · <name>") shown wherever Home surfaces a tour (list row,
  // search result, detail sheet, multi-tour dialog) BEFORE the tap. Returns
  // null for a plain Audioura tour so nothing is shown (and no membership is
  // implied). Replaces the small 12-px purple sign LOCAL-756 used — same
  // single source, now green and eye-catching per Michael 2026-10-24.
  Widget? _communitySign(Map<String, dynamic> tour) {
    if (!CommunityRules.isCommunityTour(tour)) return null;
    return CommunityTourChip(tour: tour);
  }

  // [LOCAL-756 C / D706] The PRICE / ACCESS line for a tour on Home. For a
  // community tour this is the membership framing ("Included with membership" /
  // "Members only — join <community>" / "Community tour — join to download"),
  // never "Free"; for a plain Audioura tour, the money price badge is used
  // instead (this returns null so the caller shows the badge).
  // [LOCAL-757 B] Kept in the GREEN community family (not purple) so the price
  // line reads as one colour language with the chip above it.
  Widget? _communityPriceLine(Map<String, dynamic> tour) {
    if (!CommunityRules.isCommunityTour(tour)) return null;
    final line = CommunityRules.homeTourPriceLine(
      tour,
      isMember: _isMemberOfTour(tour),
      moneyPriceLabel: tour['price_label'] as String?,
    );
    return Text(
      line,
      style: const TextStyle(
        fontSize: 12,
        color: kCommunityGreen,
        fontWeight: FontWeight.w600,
      ),
    );
  }

  String _getLanguageName(String? language) {
    switch (language) {
      case 'en': return 'English';
      case 'es': return 'Spanish';
      case 'fr': return 'French';
      case 'de': return 'German';
      case 'ru': return 'Russian';
      case 'zh': return 'Chinese';
      default: return language?.toUpperCase() ?? 'EN';
    }
  }

  // [LOCAL-671] "Original: <Language name>" — the language the tour was WRITTEN
  // in, surfaced by map-delivery as `original_language` on every tour element
  // (an original's own content_language; a translation's SOURCE language, D648).
  // This is NOT a list of available translations — the listener still chooses any
  // target language with the LanguageSelector below. Returns null when the field
  // is missing (an older map-delivery that does not send it) or blank, so the
  // label simply does not appear rather than reading "Original: ".
  String? _originalLanguageLabel(Map<String, dynamic> tour) {
    final raw = tour['original_language'];
    if (raw is! String || raw.trim().isEmpty) {
      return null;
    }
    return 'Original: ${_getLanguageName(raw.trim())}';
  }
  
  String _getTourOriginLabel(Map<String, dynamic> tour) {
    final originalTourId = tour['original_tour_id'];
    final language = tour['language'] ?? 'en';
    
    if (originalTourId != null) {
      return 'Custom';
    } else if (language != 'en') {
      return 'Translation';
    } else {
      return 'Official';
    }
  }
  
  Color _getTourOriginColor(String label) {
    switch (label) {
      case 'Official': return Colors.blue;
      case 'Custom': return Colors.orange;
      case 'Translation': return Colors.green;
      default: return Colors.grey;
    }
  }
  
  void _showMultipleTourDialog(List tours) {
    List<bool> selectedTours = List.filled(tours.length, false);
    List<String> selectedLanguages = ['en'];
    
    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: Text('Select Tours (${tours.length} available)'),
          content: Container(
            width: double.maxFinite,
            height: MediaQuery.of(context).size.height * 0.5,
            child: Column(
              children: [
                LanguageSelector(
                  selectedLanguages: selectedLanguages,
                  onLanguagesChanged: (languages) {
                    setDialogState(() {
                      selectedLanguages = languages;
                    });
                  },
                ),
                SizedBox(height: 16),
                Row(
                  children: [
                    Expanded(
                      child: ElevatedButton(
                        onPressed: () {
                          setDialogState(() {
                            for (int i = 0; i < selectedTours.length; i++) {
                              selectedTours[i] = true;
                            }
                          });
                        },
                        child: Text('Select All'),
                      ),
                    ),
                    SizedBox(width: 8),
                    Expanded(
                      child: OutlinedButton(
                        onPressed: () {
                          setDialogState(() {
                            for (int i = 0; i < selectedTours.length; i++) {
                              selectedTours[i] = false;
                            }
                          });
                        },
                        child: Text('Clear All'),
                      ),
                    ),
                  ],
                ),
                SizedBox(height: 16),
                Expanded(
                  child: ListView.builder(
                    itemCount: tours.length,
                    itemBuilder: (context, index) {
                      final tour = tours[index];
                      return CheckboxListTile(
                        value: selectedTours[index],
                        onChanged: (bool? value) {
                          setDialogState(() {
                            selectedTours[index] = value ?? false;
                          });
                        },
                        title: Row(
                          children: [
                            Text(
                              _getTourTypeIcon(tour['type']),
                              style: TextStyle(fontSize: 16),
                            ),
                            SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                tour['name'],
                                style: TextStyle(fontWeight: FontWeight.bold),
                              ),
                            ),
                            Container(
                              padding: EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                              decoration: BoxDecoration(
                                color: _getTourOriginColor(_getTourOriginLabel(tour)),
                                borderRadius: BorderRadius.circular(4),
                              ),
                              child: Text(
                                _getTourOriginLabel(tour),
                                style: TextStyle(
                                  color: Colors.white,
                                  fontSize: 10,
                                  fontWeight: FontWeight.bold,
                                ),
                              ),
                            ),
                          ],
                        ),
                        subtitle: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            SizedBox(height: 4),
                            Row(
                              children: [
                                Text(
                                  '${_getTourTypeName(tour['type'])} • ${tour['distance_km']} km • ${tour['popularity']} downloads',
                                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                ),
                              ],
                            ),
                            // [LOCAL-677] Price badge in the list row ("$4.99"/"Free").
                            // [LOCAL-756 C] A community tour shows its community
                            // sign + the membership price line instead of "Free".
                            const SizedBox(height: 4),
                            if (CommunityRules.isCommunityTour(tour)) ...[
                              if (_communitySign(tour) != null) ...[
                                Align(
                                  alignment: Alignment.centerLeft,
                                  child: _communitySign(tour)!,
                                ),
                                const SizedBox(height: 2),
                              ],
                              Align(
                                alignment: Alignment.centerLeft,
                                child: _communityPriceLine(tour)!,
                              ),
                            ] else
                              Align(
                                alignment: Alignment.centerLeft,
                                child: TourPriceBadge.fromTour(tour, compact: true),
                              ),
                            if (_tourVersionLabel(tour) != null) ...[
                              SizedBox(height: 2),
                              Text(
                                _tourVersionLabel(tour)!,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Colors.blue.shade700,
                                  fontWeight: FontWeight.w600,
                                ),
                              ),
                            ],
                            // [LOCAL-671] "Original: <Language>" per tour, beside
                            // the version/rating badges. No translation list.
                            if (_originalLanguageLabel(tour) != null) ...[
                              const SizedBox(height: 2),
                              Text(
                                _originalLanguageLabel(tour)!,
                                style: TextStyle(
                                  fontSize: 12,
                                  color: Colors.grey.shade700,
                                  fontWeight: FontWeight.w500,
                                ),
                              ),
                            ],
                            SizedBox(height: 2),
                            Row(
                              children: [
                                Icon(Icons.language, size: 14, color: Colors.blue.shade600),
                                SizedBox(width: 4),
                                Text(
                                  _getLanguageName(tour['language']),
                                  style: TextStyle(fontSize: 12, color: Colors.blue.shade600, fontWeight: FontWeight.w500),
                                ),
                                if (tour['stops_count'] != null) ...[
                                  SizedBox(width: 12),
                                  Icon(Icons.location_on, size: 14, color: Colors.green.shade600),
                                  SizedBox(width: 4),
                                  Text(
                                    '${tour['stops_count']} stops',
                                    style: TextStyle(fontSize: 12, color: Colors.green.shade600, fontWeight: FontWeight.w500),
                                  ),
                                ],
                              ],
                            ),
                          ],
                        ),
                        dense: true,
                      );
                    },
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context),
              child: Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () {
                Navigator.pop(context);
                final selected = <Map<String, dynamic>>[];
                for (int i = 0; i < tours.length; i++) {
                  if (selectedTours[i]) {
                    selected.add(tours[i]);
                  }
                }
                if (selected.isNotEmpty) {
                  _downloadMultipleTours(selected, selectedLanguages);
                }
              },
              child: Text('Download Selected (${selectedTours.where((s) => s).length})'),
            ),
          ],
        ),
      ),
    );
  }
  
  Future<void> _downloadMultipleTours(List<Map<String, dynamic>> tours, [List<String>? languages]) async {
    // Check which tours are already downloaded
    final prefs = await SharedPreferences.getInstance();
    final savedTours = prefs.getStringList('saved_tours') ?? [];
    final existingTours = savedTours.map((tour) => json.decode(tour) as Map<String, dynamic>).toList();
    final existingTourIds = existingTours.map((tour) => tour['tour_id']).toSet();
    
    final toursToDownload = tours.where((tour) => !existingTourIds.contains(tour['id'].toString())).toList();
    final alreadyDownloaded = tours.length - toursToDownload.length;
    
    if (toursToDownload.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('All selected tours are already downloaded'),
          backgroundColor: Colors.green,
        ),
      );
      return;
    }
    
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        content: Row(
          children: [
            CircularProgressIndicator(),
            SizedBox(width: 20),
            Text('Downloading ${toursToDownload.length} tour(s)...'),
          ],
        ),
      ),
    );
    
    // [LOCAL-680] Unbought paid tours cannot be bulk-downloaded (the server
    // answers 402, which used to end in "No new tours downloaded"). Download
    // the rest now; afterwards show each paid tour on its own with Preview /
    // Buy & Download / Don't download (Michael, 2026-10-14).
    final paidToOffer = <Map<String, dynamic>>[];
    final freeOrOwned = <Map<String, dynamic>>[];
    for (final tour in toursToDownload) {
      final isPaid = tour['is_paid'] == true ||
          (tour['price_tier'] is num && (tour['price_tier'] as num) > 0);
      if (isPaid && !(await TourPricingService.unlockState('${tour['id']}')).unlocked) {
        paidToOffer.add(tour);
      } else {
        freeOrOwned.add(tour);
      }
    }

    int successCount = 0;
    int translationSuccessCount = 0;
    final Map<String, List<String>> failuresByTour = {};
    // [LOCAL-717 / D677 §4] Whole-tour download/save failures (e.g. tour 370's
    // 409 resolve). A batch must NEVER drop a tour silently: each failed tour's
    // short title is collected here, named in the snackbar, and logged to
    // DebugLogHelper with the reason. Distinct from failuresByTour, which is
    // per-tour TRANSLATION failures on tours that DID save.
    final List<String> downloadFailures = [];
    // [LOCAL-716] Track the ids of the tours actually downloaded this run. When
    // exactly one was downloaded, the "View" button opens that one tour.
    final List<String> downloadedTourIds = [];
    for (final tour in freeOrOwned) {
      // [LOCAL-717] A readable short title for the message and the log — the
      // tour's own name, else a "Tour <id>" fallback.
      final shortTitle =
          (tour['name'] ?? tour['title'] ?? 'Tour ${tour['id']}').toString();
      try {
        final failures = await _downloadSingleTourSilent(tour['id'], languages, tour);
        // [LOCAL-717 / D677 §4] Count a tour as downloaded ONLY after the save
        // returned without throwing. The resolve/save failure throws, so we
        // never reach here for a dropped tour.
        successCount++;
        downloadedTourIds.add(tour['id'].toString());
        final nonEnglish = (languages ?? []).where((l) => l != 'en').toList();
        translationSuccessCount += nonEnglish.length - failures.length;
        if (failures.isNotEmpty) {
          failuresByTour[shortTitle] = failures;
        }
      } catch (e) {
        // [LOCAL-717 / D677 §4] Report, never hide. Name the tour in the
        // snackbar and log the full reason (HTTP status + body are carried in
        // the thrown Exception's message by _saveTourToMyTours).
        downloadFailures.add(shortTitle);
        await DebugLogHelper.addDebugLog(
            'HOME: DOWNLOAD FAILED for "$shortTitle" (id=${tour['id']}): $e');
        // [LOCAL-785 / D723] Record the download/save/resolve failure to the
        // server (this is the 445/446-class silent failure — a tour that
        // vanished from a batch with only a local log). Background, never throws.
        FailureReporter.instance.report(
          surface: 'download',
          errorCode: 'tour_download_save_failed',
          exceptionType: e.runtimeType.toString(),
          message: 'download/save/resolve failed for "$shortTitle": $e',
          tourId: tour['id'].toString(),
        );
      }
    }

    if (!mounted) return;
    if (Navigator.of(context, rootNavigator: true).canPop()) {
      Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
    }

    // [LOCAL-716] One helper builds the text, with correct singular/plural
    // agreement for every count (tours, translations, already-downloaded).
    final message = downloadedMessage(
      downloaded: successCount,
      translations: translationSuccessCount,
      alreadyDownloaded: alreadyDownloaded,
      failures: failuresByTour,
      downloadFailures: downloadFailures,
    );

    if (!mounted) return;
    if (freeOrOwned.isNotEmpty || paidToOffer.isEmpty) {
      // [LOCAL-716B / D358] The language "View" should open. The user just
      // chose these [languages]; prefer the first non-English one (the
      // translation they downloaded), else fall back to the saved About
      // listening language, else English. The planner uses this only when a
      // tour has SEVERAL translations — with exactly one translation it opens
      // that translation regardless, and with none it opens the original.
      final nonEnglishSelected =
          (languages ?? const <String>[]).where((l) => l != 'en').toList();
      final viewLanguage = nonEnglishSelected.isNotEmpty
          ? nonEnglishSelected.first
          : (prefs.getString('listening_language') ?? 'en');
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          // [LOCAL-716 / LOCAL-716B / LOCAL-719 / D677 addendum 1] "View" goes
          // to the Listen tab and ALWAYS opens a player, in the language just
          // downloaded. With one new tour it opens that tour; with several it
          // opens the FIRST the user selected (that succeeded) — the planner
          // walks `downloadedTourIds` in selection order. The other tours of
          // the batch are highlighted when the user returns to Listen.
          // `downloadedTourIds` holds only tours that saved successfully, in
          // selection order, so a failed first pick is naturally skipped.
          action: successCount > 0 ? SnackBarAction(
            label: 'View',
            onPressed: () => PendingListenOpen.instance.offerBatch(
              downloadedTourIds,
              language: viewLanguage,
            ),
          ) : null,
        ),
      );
    }

    // [LOCAL-680] Now the paid tours, one at a time.
    for (final tour in paidToOffer) {
      if (!mounted) return;
      final done = Completer<void>();
      _onTourMarkerTapped(tour, done: done, cancelLabel: "Don't download");
      await done.future;
    }
  }
  
  Future<void> _downloadTour(int tourId) async {
    await DebugLogHelper.addDebugLog('HOME: Starting tour download for ID: $tourId');
    await DebugLogHelper.addDebugLog('HOME: Using context: ${context.runtimeType}');
    await DebugLogHelper.addDebugLog('HOME: Widget mounted at start: $mounted');
    
    // Check if this exact tour is already downloaded
    final prefs = await SharedPreferences.getInstance();
    final savedTours = prefs.getStringList('saved_tours') ?? [];
    final existingTours = savedTours.map((tour) => json.decode(tour) as Map<String, dynamic>).toList();
    
    // Check for exact match by tour_id
    Map<String, dynamic>? existingTour;
    try {
      existingTour = existingTours.where((tour) => tour['tour_id'] == tourId.toString()).firstOrNull;
    } catch (e) {
      existingTour = null;
    }
    
    if (existingTour != null) {
      await DebugLogHelper.addDebugLog('HOME: Tour $tourId already exists in My Tours');
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('This tour is already downloaded'),
            backgroundColor: Colors.green,
            action: SnackBarAction(
              label: 'Open',
              onPressed: () {
                // [LOCAL-716] Go to Listen and open this one tour (the route
                // '/my_tours' was never registered, so this used to do nothing).
                PendingListenOpen.instance.offer(tourId.toString());
              },
            ),
          ),
        );
      }
      return;
    }
    
    showDialog(
      context: context,
      barrierDismissible: true,
      builder: (context) => AlertDialog(
        title: Text('Downloading Tour'),
        content: Row(
          children: [
            CircularProgressIndicator(),
            SizedBox(width: 20),
            Expanded(
              child: Text('Downloading tour...\nYou can dismiss this dialog and continue using the app.'),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(context);
            },
            child: Text('Dismiss'),
          ),
        ],
      ),
    );

    try {
      final downloadUri = await _downloadTourUri(tourId);
      final url = downloadUri.toString();

      // [LOCAL-781] If a previous attempt downloaded the ZIP but the save failed
      // at /resolve, the bytes were kept — reuse them instead of re-downloading
      // the whole tour from map-delivery (which may re-spend the purchase).
      final List<int>? keptZip = TourDownloadService.peekCachedZip(tourId);
      final http.Response response;
      if (keptZip != null) {
        await DebugLogHelper.addDebugLog(
            'HOME: reusing kept ZIP for $tourId (${keptZip.length} bytes) — '
            'no re-download');
        response = http.Response.bytes(keptZip, 200);
      } else {
        await DebugLogHelper.addDebugLog('HOME: Downloading from: $url');
        response = await http.get(
          downloadUri,
          headers: await Endpoints.apiHeaders(Service.mapDelivery),
        ).timeout(Duration(seconds: 120));
      }

      await DebugLogHelper.addDebugLog('HOME: Download response: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        await DebugLogHelper.addDebugLog('HOME: Tour downloaded successfully (${response.bodyBytes.length} bytes)');

        // [LOCAL-693B / D660 LEAD] The SERVER decides consumption: it spends the
        // purchase when it finishes streaming the zip (last byte). The app's job
        // is only to report FAILURE. If we received the bytes (200) but cannot
        // save/validate the zip, tell the server via POST /tour/<id>/download-
        // failed so it RESTORES the purchase once (within 24h). On success we do
        // nothing — there is no confirm call any more.
        try {
          await _saveTourToMyTours(tourId, response.bodyBytes);
          // [LOCAL-781] Saved — drop any kept ZIP so a later re-download is fresh.
          TourDownloadService.clearCachedZip(tourId);
        } catch (saveError) {
          await DebugLogHelper.addDebugLog(
              'HOME: save/validate failed after bytes received — reporting '
              'download-failed for $tourId: $saveError');
          // [LOCAL-781] Keep the downloaded ZIP so the retry reuses it rather
          // than downloading the whole tour again.
          TourDownloadService.cacheZipForRetry(tourId, response.bodyBytes);
          await _reportDownloadFailed(
              tourId,
              response.headers['x-download-consumes-unlock'],
              'save_or_validate_failed');
          rethrow; // surface to the outer catch for the user-facing error
        }
        await DebugLogHelper.addDebugLog('HOME: MAIN - Back from _saveTourToMyTours');
        
        // Dismiss dialog AFTER save completes
        await DebugLogHelper.addDebugLog('HOME: MAIN - Checking if widget is mounted: $mounted');
        
        // Try to update UI regardless of mounted state
        try {
          if (mounted) {
            await DebugLogHelper.addDebugLog('HOME: MAIN - Widget is mounted, dismissing dialog');
            Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
            await DebugLogHelper.addDebugLog('HOME: MAIN - Dialog dismissed successfully');
          } else {
            await DebugLogHelper.addDebugLog('HOME: MAIN - Widget NOT mounted, trying to find context');
            // Try to find any available context to show success
            final navigatorState = Navigator.of(context, rootNavigator: true);
            if (navigatorState.canPop()) {
              navigatorState.pop();
              await DebugLogHelper.addDebugLog('HOME: MAIN - Dialog dismissed via root navigator');
            }
          }
          
          // Always show success message
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Tour downloaded and added to My Tours!'),
              backgroundColor: Colors.green,
              action: SnackBarAction(
                label: 'View',
                onPressed: () => PendingListenOpen.instance.offer(tourId.toString()),
              ),
            ),
          );
          await DebugLogHelper.addDebugLog('HOME: MAIN - Success message shown');
        } catch (uiError) {
          await DebugLogHelper.addDebugLog('HOME: MAIN - UI update error: $uiError');
          // Download completed successfully even if UI update failed
        }

        // [LOCAL-740 / B5b] A download just finished — offer the recovery code
        // the first time (then once more after the 3rd download if "Later",
        // then never; never the same day as the first-purchase offer). The
        // helper is fully guarded and no-ops when it should not show.
        if (mounted) {
          await maybeOfferRecoveryCodeAfterDownload(context);
        }

        await DebugLogHelper.addDebugLog('HOME: MAIN - Download function completing');
      } else {
        await DebugLogHelper.addDebugLog('HOME: Download failed: ${response.body}');
        throw Exception('Failed to download tour: ${response.statusCode}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Download error: $e');
      await DebugLogHelper.addDebugLog('HOME: Error stack trace: ${e.toString()}');
      
      await DebugLogHelper.addDebugLog('HOME: MAIN - In error handler, mounted: $mounted');
      
      if (mounted) {
        try {
          Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
          await DebugLogHelper.addDebugLog('HOME: MAIN - Error dialog dismissed');
        } catch (navError) {
          await DebugLogHelper.addDebugLog('HOME: MAIN - Error dialog dismiss failed: $navError');
        }
        
        String errorMessage = 'Error downloading tour';
        if (e.toString().contains('Connection closed')) {
          errorMessage = 'Download interrupted - please try again';
        } else if (e.toString().contains('timeout')) {
          errorMessage = 'Download timed out - please check connection';
        } else {
          // [LOCAL-781] A save/resolve failure throws a rich, tour-NAMING
          // message (TourDownloadService.resolveFailureMessage). The old code
          // collapsed every non-network error to the generic "Error downloading
          // tour", so the cloud /resolve 404 never reached the screen (Michael,
          // TestFlight 79: "silently failed"). Surface the real reason now,
          // stripping Dart's "Exception: " prefix.
          final raw = e.toString();
          errorMessage = raw.startsWith('Exception: ')
              ? raw.substring('Exception: '.length)
              : raw;
        }

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(errorMessage),
            duration: Duration(seconds: 8),
          ),
        );
      }
    }
  }
  
  // Resolves the editTourId for a given download ID by calling the resolution endpoint.
  // Used to populate parent_tour_id on translated tours.
  Future<String> _resolveParentEditTourId(int downloadTourId, SharedPreferences prefs) async {
    try {
      final uri = await Endpoints.url(Service.tourIdResolution, '/tour/$downloadTourId/resolve');
      final resp = await http.get(uri, headers: await Endpoints.apiHeaders(Service.tourIdResolution));
      if (resp.statusCode == 200) {
        final data = json.decode(resp.body);
        return (data['edit_tour_id'] ?? '').toString();
      }
    } catch (_) {}
    return '';
  }


  Future<List<String>> _downloadSingleTourSilent(int tourId, [List<String>? languages, Map<String, dynamic>? sourceItem]) async {
    final prefs = await SharedPreferences.getInstance();

    // [LOCAL-677B / D653] Only pull English when it is a selected language.
    final bool wantEnglish = TourTranslationHelper.shouldDownloadEnglish(languages);
    if (wantEnglish) {
      final uri = await _downloadTourUri(tourId);
      final response = await http.get(uri, headers: await Endpoints.apiHeaders(Service.mapDelivery)).timeout(Duration(seconds: 120));
      if (response.statusCode == 200) {
        // [LOCAL-693B / D660 LEAD] Server-side consumption; app reports failure
        // only. If the bytes arrived but the zip cannot be saved/validated,
        // report download-failed so the server restores the purchase once.
        try {
          await _saveTourToMyTours(tourId, response.bodyBytes, sourceItem: sourceItem);
        } catch (saveError) {
          await _reportDownloadFailed(
              tourId,
              response.headers['x-download-consumes-unlock'],
              'save_or_validate_failed');
          rethrow;
        }
      } else {
        throw Exception('Failed to download tour: ${response.statusCode}');
      }
    }

    if (languages == null) return [];
    final nonEnglish = languages.where((l) => l != 'en').toList();
    if (nonEnglish.isEmpty) return [];

    final parentEditTourId = await _resolveParentEditTourId(tourId, prefs);
    return await TourTranslationHelper.downloadTranslatedVersions(
        tourId: tourId,
        languages: nonEnglish,
        parentEditTourId: parentEditTourId,
        sourceItem: sourceItem);
  }

  /// [LOCAL-739 §3] The gate shown when a NON-MEMBER taps Download on a
  /// members-only community tour (found on Home or opened from an emailed
  /// link): "This tour is for members of <community>", with a Join action that
  /// opens the community page and its passes. The community name is fetched for
  /// the message (a generic wording is used if it cannot be resolved). The tour
  /// id is carried into the community page as `pendingDownloadTourId`, so after
  /// the pass is granted that tour downloads automatically and Listen opens —
  /// exactly as after any other download.
  Future<void> _showMembersOnlyTourGate(int communityId, int tourId) async {
    // Resolve the community name for the message (null → generic wording).
    String? name;
    try {
      final c = await CommunitiesService.get(communityId);
      name = c?.name;
    } catch (_) {}
    if (!mounted) return;
    final join = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Members only'),
        content: Text(CommunityRules.membersOnlyTourGate(name)),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Not now'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Join'),
          ),
        ],
      ),
    );
    if (join != true || !mounted) return;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (_) => CommunityPageScreen(
          communityId: communityId,
          pendingDownloadTourId: tourId,
        ),
      ),
    );
  }

  Future<void> _downloadSingleTour(int tourId, [List<String>? languages, Map<String, dynamic>? sourceItem]) async {
    // [LOCAL-794] No app-blocking modal spinner. The English copy (when
    // selected) is small and fast (Michael's log: 0.33 s, 2 MB), and its 402
    // pay/members-only gate needs the screen's context for the Buy prompt /
    // community-page hop — so it is pulled inline here WITHOUT a barrier
    // dialog. The SLOW part (translate + per-language ZIP + save — the 2.5-min
    // gap and the never-ending spinner in the LOCAL-794 reports) is handed to
    // TranslateDownloadManager, which shows the app-wide progress row and lets
    // the user keep using every tab. On completion the manager shows
    // "<Language> version ready — Play" and the Listen page updates itself
    // (SavedToursStore bump), with no modal to get stuck.
    final prefs = await SharedPreferences.getInstance();
    final bool wantEnglish = TourTranslationHelper.shouldDownloadEnglish(languages);
    final List<String> nonEnglishLanguages =
        (languages ?? const <String>[]).where((lang) => lang != 'en').toList();

    // 1) English copy inline (fast; its 402 gate needs UI). On any failure the
    // user is told and nothing is backgrounded.
    if (wantEnglish) {
      try {
        final dlUri = await _downloadTourUri(tourId);
        final response = await http
            .get(dlUri, headers: await Endpoints.apiHeaders(Service.mapDelivery))
            .timeout(const Duration(seconds: 120));
        if (response.statusCode == 200) {
          // [LOCAL-693B / D660 LEAD] Server-side consumption; the app reports
          // only failure. On save/validate failure, report download-failed so
          // the server restores the purchase once.
          try {
            await _saveTourToMyTours(tourId, response.bodyBytes, sourceItem: sourceItem);
          } catch (saveError) {
            await _reportDownloadFailed(
                tourId,
                response.headers['x-download-consumes-unlock'],
                'save_or_validate_failed');
            rethrow;
          }
        } else if (response.statusCode == 402) {
          // [LOCAL-677C / D654] Pay before download. [LOCAL-701 / D663 §3] A
          // COMMUNITY tour refuses membership_required → open the community
          // page (join / buy pass). Both need the screen context, so they stay
          // on this (inline) path, never in the background job.
          int? communityId;
          try {
            final body = json.decode(response.body);
            if (body is Map && body['error'] == 'membership_required') {
              final cid = body['community_id'];
              if (cid is int) {
                communityId = cid;
              } else if (cid is num) {
                communityId = cid.toInt();
              }
            }
          } catch (_) {}
          if (communityId != null) {
            await _showMembersOnlyTourGate(communityId, tourId);
            return;
          }
          if (mounted) {
            ScaffoldMessenger.of(context).showSnackBar(
              const SnackBar(
                content: Text('This tour is paid — buy it to download.'),
                backgroundColor: Colors.orange,
              ),
            );
          }
          return;
        } else {
          throw Exception('Failed to download tour: ${response.statusCode}');
        }
      } catch (e) {
        if (!mounted) return;
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error downloading tour: $e'),
            backgroundColor: Colors.red,
          ),
        );
        return;
      }
    }

    // 2) No translations requested → the English-only download is done. Show
    // the snackbar with View and let Listen refresh itself (already saved).
    if (nonEnglishLanguages.isEmpty) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(downloadedMessage(downloaded: 1, translations: 0)),
          backgroundColor: Colors.green,
          action: SnackBarAction(
            label: 'View',
            onPressed: () => PendingListenOpen.instance.offer(tourId.toString()),
          ),
        ),
      );
      return;
    }

    // 3) Translations → background. One job at a time; the manager owns the
    // progress row, the timeouts on every await, every exit path clearing the
    // row, and the completion "<Language> version ready — Play" SnackBar. We do
    // NOT await it: the user is free to switch tabs immediately.
    final tourName = (sourceItem?['name'] ?? sourceItem?['title'])?.toString();
    final job = TranslateDownloadJob(
      tourId: tourId,
      tourName: tourName,
      languages: nonEnglishLanguages,
      // English was pulled inline above; the job starts at the translate phase.
      phase: TranslateDownloadPhase.translating,
    );
    // Fire-and-forget: the manager drives the UI through the global controller
    // and messenger, so it needs no BuildContext and cannot be orphaned when
    // this screen is disposed (a cause of the never-ending spinner).
    unawaited(TranslateDownloadManager.instance.run(
      job: job,
      downloadEnglish: false, // already done inline
      downloadEnglishStep: () async {},
      resolveParentEditTourId: () => _resolveParentEditTourId(tourId, prefs),
      translate: (parentEditTourId) =>
          TourTranslationHelper.downloadTranslatedVersions(
        tourId: tourId,
        languages: nonEnglishLanguages,
        parentEditTourId: parentEditTourId,
        sourceItem: sourceItem,
      ),
    ));
  }
  
  /// [ST-3] Does this look like a share code rather than a place?
  ///
  /// Michael: "if they enter the code Kostya sends them, we must figure out that it
  /// is not a location but a code for the tour and move to the state as they would
  /// have clicked on a tour in the map."
  ///
  /// A share code is exactly 8 base62 characters (see tour_sharing.py). A place name
  /// essentially never is: real queries carry spaces, commas or accents, and the few
  /// 8-letter single words that exist ("Brooklyn", "Portland") are all lower-case
  /// after the first letter, whereas a generated code mixes case and digits.
  ///
  /// This only decides what to TRY FIRST. A code that does not resolve falls through
  /// to the ordinary location search, so a misread costs one round trip and never a
  /// dead end.
  bool _looksLikeShareCode(String q) {
    // [LOCAL-579] Accept not just a bare code but the full share message a
    // curator sends ("…paste this code: FFush25U") or a share link. The
    // extractor pulls the 8-char token out and applies the SAME digit/internal-
    // capital discriminator ST-3 used, so a place name like "Boston" or
    // "Newton MA" still falls through to the ordinary location search.
    return extractShareCode(q) != null;
  }

  /// [ST-3] Resolve a share code into the same tour shape /tours-near returns.
  /// Returns an empty list when the code is unknown, so the caller falls back to a
  /// location search.
  Future<List<Map<String, dynamic>>> _resolveShareCode(String code) async {
    try {
      // [LOCAL-687] Carry the 18+ flag so a mature shared tour resolves for a
      // confirmed-adult listener; without it the server answers 403
      // age_restricted (handled below) and the listener is told how to enable it.
      // [LOCAL-753 / D707] Carry user_id so a MEMBERS-ONLY community tour
      // resolves through its code for an active member/owner (the server gates
      // it with _is_active_member); a non-member gets the normal 404.
      final params = <String, String>{};
      if (_showAdult) params['adult'] = '1';
      if (_deviceUserId.isNotEmpty) params['user_id'] = _deviceUserId;
      final query = params.isEmpty
          ? ''
          : '?${params.entries.map((e) => '${e.key}=${Uri.encodeComponent(e.value)}').join('&')}';
      final uri = await Endpoints.url(
          Service.mapDelivery,
          '/tour-by-code/${Uri.encodeComponent(code.trim())}$query');
      await DebugLogHelper.addDebugLog('HOME: trying share code: $uri');
      final response = await http.get(
        uri,
        headers: await Endpoints.apiHeaders(Service.mapDelivery),
      ).timeout(Duration(seconds: 10));
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final tours = List<Map<String, dynamic>>.from(data['tours'] ?? []);
        await DebugLogHelper.addDebugLog('HOME: share code resolved ${tours.length} tour(s)');
        return tours;
      }
      // [LOCAL-687] 403 age_restricted: the code points at a mature tour and 18+
      // is off. Tell the listener exactly how to open it, and do NOT fall back to
      // a location search (the code WAS valid — it is gated, not unknown).
      if (response.statusCode == 403) {
        await DebugLogHelper.addDebugLog('HOME: share code is age_restricted (403)');
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
            content: Text('This tour is for adults (18+). Turn on 18+ tours in '
                'Settings to open it.'),
            duration: Duration(seconds: 5),
          ));
        }
        return [];
      }
      // 404 is the normal "that was not a code" answer, not an error worth surfacing.
      await DebugLogHelper.addDebugLog('HOME: share code not found (${response.statusCode})');
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: share code lookup failed: $e');
    }
    return [];
  }

  Future<List<Map<String, dynamic>>> _searchTours(String query) async {
    try {
      // [ST-3] One search box: try the share code first when the input has that
      // shape. The tours come back identical to a /tours-near entry, so everything
      // downstream -- pick, download, translate -- works with no further change.
      // [LOCAL-579] The input may be a bare code, the full share message, or a
      // link — gate on _looksLikeShareCode, then extract the 8-char token.
      if (_looksLikeShareCode(query)) {
        final shareToken = extractShareCode(query);
        if (shareToken != null) {
          final shared = await _resolveShareCode(shareToken);
          if (shared.isNotEmpty) return shared;
          // Not a code after all; fall through and search by location.
        }
      }

      // Convert wildcard pattern to regex
      final regexPattern = query.replaceAll('*', '.*');
      
      final searchLocation = _displayLocation ?? _userLocation;
      if (searchLocation == null) {
        await DebugLogHelper.addDebugLog('HOME: Tour search failed - no location available');
        return [];
      }
      
      final searchUri = await Endpoints.url(Service.mapDelivery, '/search-tours?pattern=${Uri.encodeComponent(regexPattern)}&lat=${searchLocation.latitude}&lng=${searchLocation.longitude}${_filterQueryParams()}');
      final searchUrl = searchUri.toString();
      await DebugLogHelper.addDebugLog('HOME: Searching tours with URL: $searchUrl');
      
      final response = await http.get(
        searchUri,
        headers: await Endpoints.apiHeaders(Service.mapDelivery),
      ).timeout(Duration(seconds: 10));
      
      await DebugLogHelper.addDebugLog('HOME: Tour search response: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final tours = List<Map<String, dynamic>>.from(data['tours'] ?? []);
        await DebugLogHelper.addDebugLog('HOME: Found ${tours.length} tours matching "$query"');
        return tours;
      } else {
        await DebugLogHelper.addDebugLog('HOME: Tour search error: ${response.statusCode} - ${response.body}');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Tour search exception: $e');
    }
    return [];
  }
  
  void _showTourOnMap(Map<String, dynamic> tour) {
    final tourLocation = LatLng(tour['lat'], tour['lng']);
    _mapController.move(tourLocation, 15.0);
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Showing ${tour['name']} on map'),
        action: SnackBarAction(
          label: 'Download',
          onPressed: () => _downloadSingleTour(tour['id']),
        ),
      ),
    );
  }

  // Saves a translated tour directly without backend resolution (translated tours have no edit_tour_id)
  Future<void> _saveTourToMyToursTranslated(int tourId, List<int> zipBytes, String appDirPath, SharedPreferences prefs, String parentEditTourId, String lang) async {
    final archive = ZipDecoder().decodeBytes(zipBytes);
    String tourName = 'Translated Tour $tourId';
    // Try to extract tour name from ZIP manifest
    for (final file in archive) {
      if (file.name.endsWith('manifest.json') || file.name.endsWith('tour.json')) {
        try {
          final data = json.decode(utf8.decode(file.content as List<int>));
          tourName = data['tour_name'] ?? data['name'] ?? tourName;
          break;
        } catch (_) {}
      }
    }
    final safeName = tourName.replaceAll(RegExp(r'[^\w]'), '_').replaceAll(RegExp(r'_+'), '_').toLowerCase();
    final dirName = '${safeName}_${lang}_$tourId';
    final tourDir = Directory('$appDirPath/tours/$dirName');
    await tourDir.create(recursive: true);
    for (final file in archive) {
      if (!file.isFile) continue;
      final outFile = File('${tourDir.path}/${file.name}');
      await outFile.parent.create(recursive: true);
      await outFile.writeAsBytes(file.content as List<int>);
    }
    final actualStops = await _countTourStops(zipBytes);
    final savedTours = prefs.getStringList('saved_tours') ?? [];
    final tourData = {
      'title': tourName,
      'path': tourDir.path,
      'created': DateTime.now().toIso8601String(),
      'stops': actualStops.toString(),
      'original_request': tourName,
      'tour_id': tourId.toString(),
      'editable': false,
      'is_translation': true,
      'parent_tour_id': parentEditTourId.isEmpty ? null : parentEditTourId,
      // [LOCAL-716B] Target language of this translation, so "View" after a
      // "tour + translation" download opens the exact language just downloaded.
      'language': lang,
    };
    savedTours.add(json.encode(tourData));
    await SavedToursStore.save(prefs, savedTours);
    await DebugLogHelper.addDebugLog('HOME: Saved translated tour $tourId as: $tourName');
  }

  Future<void> _saveTourToMyTours(int tourId, List<int> zipBytes, {bool isTranslation = false, Map<String, dynamic>? sourceItem}) async {
    // [LOCAL-713 / D675] Delegates to the SINGLE download+save path
    // (TourDownloadService) so Home and the community page write identical
    // `saved_tours` records — there is one implementation of the on-phone
    // record contract, never a second path.
    assert(!isTranslation,
        '_saveTourToMyTours should not be called with isTranslation: true after M8; '
        'use _saveTourToMyToursTranslated directly via _downloadTranslatedVersions');
    await TourDownloadService.saveTourToMyTours(tourId, zipBytes,
        sourceItem: sourceItem);
  }

  Future<void> _loadNewsletters() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Load cached newsletters first
      await _loadCachedNewsletters();
      
      final newsUri = await Endpoints.url(Service.newsletter, '/newsletters_v2');
      await DebugLogHelper.addDebugLog('HOME: Loading newsletters from $newsUri');
      
      final response = await http.get(
        newsUri,
        headers: await Endpoints.apiHeaders(Service.newsletter),
      ).timeout(Duration(seconds: 10));
      
      await DebugLogHelper.addDebugLog('HOME: Newsletter response status: ${response.statusCode}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final newsletters = List<Map<String, dynamic>>.from(data['newsletters'] ?? []);
        await DebugLogHelper.addDebugLog('HOME: Loaded ${newsletters.length} newsletters from server');
        
        // Cache the newsletters
        await prefs.setString('cached_newsletters', json.encode(newsletters));
        await DebugLogHelper.addDebugLog('HOME: Cached ${newsletters.length} newsletters');
        
        if (!mounted) return; // [LOCAL-773] setState after await.
        setState(() {
          _newsletters = newsletters;
          _isLoading = false;
        });
      } else {
        await DebugLogHelper.addDebugLog('HOME: Newsletter server error: ${response.statusCode}');
        
        if (!mounted) return; // [LOCAL-773] context + setState after await.
        // Only show error if no cached data is available
        if (_newsletters.isEmpty) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(ErrorHandlerService.friendlyMessage(response.statusCode)),
              backgroundColor: Colors.orange,
            ),
          );
        }
        
        setState(() {
          _isLoading = false;
        });
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Newsletter loading error: $e');
      
      if (!mounted) return; // [LOCAL-773] context + setState after await.
      // Only show error if no cached data is available
      if (_newsletters.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('No connection. Showing cached newsletters.'),
            backgroundColor: Colors.orange,
          ),
        );
      }
      
      setState(() {
        _isLoading = false;
      });
    }
  }
  
  Future<void> _loadCachedNewsletters() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final cachedNewsletters = prefs.getString('cached_newsletters');
      
      if (cachedNewsletters != null) {
        await DebugLogHelper.addDebugLog('HOME: Loading cached newsletters');
        final newsletters = List<Map<String, dynamic>>.from(json.decode(cachedNewsletters));
        
        if (!mounted) return; // [LOCAL-773] setState after await.
        setState(() {
          _newsletters = newsletters;
        });
        
        await DebugLogHelper.addDebugLog('HOME: Loaded ${newsletters.length} cached newsletters');
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error loading cached newsletters: $e');
    }
  }
  
  Future<void> _processNewsletterWithUrl(String newsletterUrl, int existingId, String name) async {
    try {
      await DebugLogHelper.addDebugLog('NEWSLETTER: Processing existing newsletter with URL workflow: $newsletterUrl');
      
      // Check if we already have encryption key for this device
      final hasKey = await SubscriptionService.hasEncryptionKey();
      
      if (!hasKey) {
        await DebugLogHelper.addDebugLog('NEWSLETTER: No encryption key found, processing newsletter URL to get key');
        
        final deviceId = await DeviceService.getUserId();
        
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (context) => AlertDialog(
            content: Row(
              children: [
                CircularProgressIndicator(),
                SizedBox(width: 20),
                Expanded(child: Text('Getting encryption key...')),
              ],
            ),
          ),
        );
        
        final processUri = await Endpoints.url(Service.newsletter, '/process_newsletter');
        final requestUrl = processUri.toString();
        final requestBody = {
          'newsletter_url': newsletterUrl,
          'user_id': deviceId,
          'max_articles': 10,
        };
        
        await DebugLogHelper.addDebugLog('NEWSLETTER: Making POST request to: $requestUrl');
        
        final response = await http.post(
          Uri.parse(requestUrl),
          headers: await Endpoints.apiHeaders(Service.newsletter),
          body: json.encode(requestBody),
        ).timeout(Duration(seconds: 60));
        
        Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
        
        if (response.statusCode == 200) {
          final data = json.decode(response.body);
          final deviceEncryptionKey = data['device_encryption_key'];
          
          if (deviceEncryptionKey != null) {
            await SubscriptionService.handleKeyExchange(deviceEncryptionKey);
            await DebugLogHelper.addDebugLog('NEWSLETTER: Encryption key obtained and stored');
          }
        } else if (response.statusCode == 402) {
          await DebugLogHelper.addDebugLog('NEWSLETTER: 402 — source requires subscription (key exchange skipped)');
        }
      } else {
        await DebugLogHelper.addDebugLog('NEWSLETTER: Encryption key already available');
      }
      
      // Now get article details
      await _processNewsletter(existingId, name);
      
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWSLETTER: Exception in _processNewsletterWithUrl: $e');
      
      // Fallback to direct article processing
      await _processNewsletter(existingId, name);
    }
  }
  
  Future<void> _processNewsletterUrl(String newsletterUrl) async {
    try {
      await DebugLogHelper.addDebugLog('NEWSLETTER: Starting newsletter URL processing: $newsletterUrl');
      
      final deviceId = await DeviceService.getUserId();
      
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Expanded(child: Text('Processing newsletter...')),
            ],
          ),
        ),
      );
      
      final processUri = await Endpoints.url(Service.newsletter, '/process_newsletter');
      final requestUrl = processUri.toString();
      final requestBody = {
        'newsletter_url': newsletterUrl,
        'user_id': deviceId,
        'max_articles': 10,
      };
      
      await DebugLogHelper.addDebugLog('NEWSLETTER: Making POST request to: $requestUrl');
      await DebugLogHelper.addDebugLog('NEWSLETTER: Request body: ${json.encode(requestBody)}');
      
      final response = await http.post(
        Uri.parse(requestUrl),
        headers: await Endpoints.apiHeaders(Service.newsletter),
        body: json.encode(requestBody),
      ).timeout(Duration(seconds: 60));
      
      await DebugLogHelper.addDebugLog('NEWSLETTER: Response status: ${response.statusCode}');
      await DebugLogHelper.addDebugLog('NEWSLETTER: Response body: ${response.body}');
      
      Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        
        if (data['status'] == 'success') {
          final newsletterId = data['newsletter_id'];
          final articlesCreated = data['articles_created'] ?? 0;
          final articlesRequiringSubscription = data['articles_requiring_subscription'] ?? 0;
          final deviceEncryptionKey = data['device_encryption_key'];
          
          // Perform key exchange
          final serverPublicKey = data['server_public_key'];
          if (serverPublicKey != null) {
            await SubscriptionService.handleKeyExchange(serverPublicKey);
          }
          
          // Show processing results
          String message = 'Newsletter processed: $articlesCreated articles created';
          if (articlesRequiringSubscription > 0) {
            message += ', $articlesRequiringSubscription require subscription';
          }
          
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text(message),
              backgroundColor: Colors.green,
            ),
          );
          
          // Now get article details  
          await _processNewsletter(newsletterId, 'Newsletter');
        } else {
          throw Exception(data['message'] ?? 'Newsletter processing failed');
        }
      } else if (response.statusCode == 402) {
        // Subscription required — expected outcome, not an error
        String subMessage = 'This source requires a subscription.';
        try {
          final errorData = json.decode(response.body);
          subMessage = errorData['message'] ?? subMessage;
        } catch (_) {}
        await DebugLogHelper.addDebugLog('NEWSLETTER: 402 subscription required: $subMessage');
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text(subMessage), backgroundColor: Colors.orange, duration: const Duration(seconds: 5)),
        );
      } else {
        // Parse server error message for user-friendly display
        String userMessage = ErrorHandlerService.friendlyMessage(response.statusCode);
        try {
          final errorData = json.decode(response.body);
          if (errorData['message'] != null) {
            userMessage = errorData['message'];
          } else if (errorData['error'] != null) {
            userMessage = errorData['error'];
          }
        } catch (parseError) {
          // Keep default message if parsing fails
        }
        throw Exception(userMessage);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWSLETTER: Exception in _processNewsletterUrl: $e');
      
      Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error processing newsletter: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<void> _processNewsletter(int newsletterId, String name) async {
    try {
      await DebugLogHelper.addDebugLog('NEWSLETTER: Starting _processNewsletter with ID: $newsletterId, Name: $name');
      
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Expanded(child: Text('Loading newsletter articles...')),
            ],
          ),
        ),
      );
      
      final articlesUri = await Endpoints.url(Service.newsletter, '/get_articles_by_newsletter_id');
      final requestUrl = articlesUri.toString();
      final requestBody = {'newsletter_id': newsletterId};
      
      await DebugLogHelper.addDebugLog('NEWSLETTER: Making POST request to: $requestUrl');
      await DebugLogHelper.addDebugLog('NEWSLETTER: Request body: ${json.encode(requestBody)}');
      
      final response = await http.post(
        Uri.parse(requestUrl),
        headers: await Endpoints.apiHeaders(Service.newsletter),
        body: json.encode(requestBody),
      ).timeout(Duration(seconds: 30));
      
      await DebugLogHelper.addDebugLog('NEWSLETTER: Response status: ${response.statusCode}');
      await DebugLogHelper.addDebugLog('NEWSLETTER: Response body: ${response.body}');
      
      Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final articles = List<Map<String, dynamic>>.from(data['articles'] ?? []);
        
        // Handle Diffie-Hellman key exchange if server public key present
        final serverPublicKey = data['server_public_key'];
        if (serverPublicKey != null) {
          await SubscriptionService.handleKeyExchange(serverPublicKey);
        } else {
          // Check if there are subscription articles without server_public_key
          final hasSubscriptionArticles = articles.any((article) => article['subscription_required'] == true);
          if (hasSubscriptionArticles) {
            await DebugLogHelper.addDebugLog('NEWSLETTER: ERROR - Articles require subscription but no server_public_key provided by Services');
            await DebugLogHelper.addDebugLog('NEWSLETTER: Services must include server_public_key when returning subscription articles');
            
            // Show user-friendly message about subscription feature status
            if (mounted) {
              ScaffoldMessenger.of(context).showSnackBar(
                SnackBar(
                  content: Text('Subscription articles detected but encryption keys not available. Subscription features temporarily unavailable.'),
                  backgroundColor: Colors.orange,
                  duration: Duration(seconds: 4),
                ),
              );
            }
          }
        }
        
        await DebugLogHelper.addDebugLog('NEWSLETTER: Successfully parsed ${articles.length} articles');
        
        if (articles.isEmpty) {
          await DebugLogHelper.addDebugLog('NEWSLETTER: No articles found in newsletter');
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text('No articles found in this newsletter edition')),
          );
          return;
        }
        
        await DebugLogHelper.addDebugLog('NEWSLETTER: Showing article selection dialog');
        _showArticleSelectionDialog(articles, newsletterId, name);
      } else {
        final errorBody = response.body;
        await DebugLogHelper.addDebugLog('NEWSLETTER: Server error - Status: ${response.statusCode}, Body: $errorBody');
        
        String errorMessage;
        try {
          final errorData = json.decode(errorBody);
          errorMessage = errorData['error'] ?? 'Failed to load articles';
          await DebugLogHelper.addDebugLog('NEWSLETTER: Parsed error message: $errorMessage');
        } catch (parseError) {
          errorMessage = ErrorHandlerService.friendlyMessage(response.statusCode);
          await DebugLogHelper.addDebugLog('NEWSLETTER: Could not parse error response: $parseError');
        }
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Error: $errorMessage'),
            backgroundColor: Colors.red,
          ),
        );
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('NEWSLETTER: Exception in _processNewsletter: $e');
      await DebugLogHelper.addDebugLog('NEWSLETTER: Exception type: ${e.runtimeType}');
      
      Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error loading articles: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<void> _processSelectedArticles(List<Map<String, dynamic>> selectedArticles, int newsletterId, [List<String>? languages]) async {
    try {
      final prefs = await SharedPreferences.getInstance();
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Expanded(child: Text('Downloading ${selectedArticles.length} articles in ${languages?.length ?? 1} language(s)...\nTotal: ${selectedArticles.length * (languages?.length ?? 1)} downloads')),
            ],
          ),
        ),
      );
      
      final savedNews = prefs.getStringList('saved_news') ?? [];
      await DebugLogHelper.addDebugLog('ARTICLE_PROCESS: Starting with ${savedNews.length} existing articles in storage');
      
      final existingArticleIds = <String>{};
      
      // Get existing article IDs to avoid duplicates
      for (final newsJson in savedNews) {
        try {
          final news = json.decode(newsJson) as Map<String, dynamic>;
          final articleId = news['article_id'];
          if (articleId != null) {
            existingArticleIds.add(articleId);
          }
        } catch (e) {
          // Continue if parsing fails
        }
      }
      
      int addedCount = 0;
      int failedCount = 0;
      List<String> failureReasons = [];
      
      // Remove duplicates from selected articles and filter out existing ones
      final uniqueSelected = <String, Map<String, dynamic>>{};
      for (final article in selectedArticles) {
        final articleId = article['article_id'];
        if (!existingArticleIds.contains(articleId)) {
          uniqueSelected[articleId] = article;
        }
      }
      
      for (final article in uniqueSelected.values) {
        try {
          final articleId = article['article_id'];
          final title = article['title'];
          final subscriptionDomain = article['subscription_domain'];
          
          await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Starting download for article: $articleId ($title)');
          
          // Handle translation if languages specified - Services handles this internally
          if (languages != null && languages.isNotEmpty) {
            final nonEnglishLanguages = languages.where((lang) => lang != 'en').toList();
            if (nonEnglishLanguages.isNotEmpty) {
              await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Language selection: ${nonEnglishLanguages.join(", ")} - Services will handle translation internally');
              // Services will handle translation when we download with language parameter
            }
          }
          
          // Download for all selected languages
          await _downloadAndSaveArticle(articleId, title, article, languages);
          addedCount++;
        } catch (e) {
          failedCount++;
          final title = article['title'] ?? 'Unknown Article';
          failureReasons.add('$title: Network error - ${e.toString()}');
        }
      }
      
      // CRITICAL: Reload saved_news after all downloads complete
      final finalSavedNews = prefs.getStringList('saved_news') ?? [];
      await DebugLogHelper.addDebugLog('ARTICLE_PROCESS: Completed with ${finalSavedNews.length} total articles in storage');
      
      Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
      
      // Show detailed results with error handling
      final totalDownloads = addedCount * (languages?.length ?? 1);
      String message = '$totalDownloads articles added to Listen page';
      Color backgroundColor = Colors.green;
      
      if (failedCount > 0) {
        message += ', $failedCount failed';
        backgroundColor = Colors.orange;
        
        // Show detailed error dialog
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: Text('Download Results'),
            content: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('✅ $totalDownloads articles downloaded successfully'),
                if (failedCount > 0) ...[
                  SizedBox(height: 8),
                  Text('❌ $failedCount articles failed:', style: TextStyle(fontWeight: FontWeight.bold)),
                  SizedBox(height: 4),
                  ...failureReasons.map((reason) => Padding(
                    padding: EdgeInsets.only(left: 8, bottom: 4),
                    child: Text('• $reason', style: TextStyle(fontSize: 12)),
                  )),
                ],
              ],
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context),
                child: Text('OK'),
              ),
            ],
          ),
        );
      }
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(message),
          backgroundColor: backgroundColor,
        ),
      );
      
      // Refresh newsletters to show the new one
      await _loadNewsletters();
    } catch (e) {
      Navigator.of(context, rootNavigator: true).pop(); // [LOCAL-762] dismiss root-pushed progress dialog
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error processing articles: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<void> _downloadAndSaveArticle(String articleId, String title, Map<String, dynamic> article, [List<String>? languages]) async {
    final prefs = await SharedPreferences.getInstance();
    final deviceId = await DeviceService.getUserId();
    final subscriptionDomain = article['subscription_domain'];
    
    // Download for each selected language
    final languagesToDownload = languages ?? ['en'];
    int englishFileSize = 0;
    
    for (final language in languagesToDownload) {
      await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Downloading article $articleId in language: $language');
      
      // Use Endpoints.newsDownloadUrl which handles cloud (/news-download) vs local (/download)
      var downloadUri = await Endpoints.newsDownloadUrl(articleId, deviceId);
      if (language != 'en') {
        // Add language query parameter
        final params = Map<String, String>.from(downloadUri.queryParameters);
        params['language'] = language;
        downloadUri = downloadUri.replace(queryParameters: params);
        await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Adding language parameter: $language');
      }
      
      await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Download URL: $downloadUri');
      
      final downloadResponse = await http.get(
        downloadUri,
        headers: await Endpoints.apiHeaders(Service.news),
      ).timeout(Duration(seconds: 30));
      
      await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Response status for $language: ${downloadResponse.statusCode}');
      
      if (downloadResponse.statusCode == 402) {
        // Subscription required — log and skip cleanly (not an error to retry)
        String subMsg = 'Subscription required';
        try { subMsg = json.decode(downloadResponse.body)['message'] ?? subMsg; } catch (_) {}
        await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: 402 — $subMsg');
        continue;
      }
      if (downloadResponse.statusCode != 200) {
        await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Download failed for $language: ${downloadResponse.statusCode}');
        continue; // Skip this language, try next
      }
      
      await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Successfully downloaded article in $language (${downloadResponse.bodyBytes.length} bytes)');
      
      // Store English file size for comparison
      if (language == 'en') {
        englishFileSize = downloadResponse.bodyBytes.length;
      }
      
      // CRITICAL: Check if Services returned translated content
      if (language != 'en' && downloadResponse.bodyBytes.length > 0) {
        if (englishFileSize > 0 && downloadResponse.bodyBytes.length == englishFileSize) {
          await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: ❌ SERVICES TRANSLATION FAILED - $language article has identical size to English ($englishFileSize bytes)');
          await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Skipping duplicate article creation for $language');
          continue; // Skip creating duplicate article
        } else {
          await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: ✅ SERVICES TRANSLATION SUCCESS - $language article size: ${downloadResponse.bodyBytes.length} bytes (different from English: $englishFileSize bytes)');
        }
      }
      
      await _saveArticleToDevice(articleId, title, article, downloadResponse.bodyBytes, language);
    }
  }
  
  Future<void> _saveArticleToDevice(String articleId, String title, Map<String, dynamic> article, List<int> zipBytes, String language) async {
    final prefs = await SharedPreferences.getInstance();
    final subscriptionDomain = article['subscription_domain'];
    
    final savedNews = prefs.getStringList('saved_news') ?? [];
    final isSubscriptionArticle = subscriptionDomain != null && subscriptionDomain.isNotEmpty;
    
    final truncatedTitle = title.length > 50 ? title.substring(0, 50) : title;
    final safeName = truncatedTitle.replaceAll(RegExp(r'[^a-zA-Z0-9_-]'), '_');
    
    // Create unique path for each language
    final languageSuffix = language != 'en' ? '_$language' : '';
    String articleDirPath;
    
    if (kIsWeb) {
      articleDirPath = isSubscriptionArticle ? 'web_subscription/${safeName}_${articleId}$languageSuffix' : 'web_news/${safeName}_${articleId}$languageSuffix';
      final zipBase64 = base64Encode(zipBytes);
      await prefs.setString('${isSubscriptionArticle ? "subscription" : "article"}_zip_${safeName}_${articleId}$languageSuffix', zipBase64);
      
      final archive = ZipDecoder().decodeBytes(zipBytes);
      for (final file in archive) {
        if (file.isFile) {
          final fileBase64 = base64Encode(file.content as List<int>);
          await prefs.setString('${isSubscriptionArticle ? "subscription" : "article"}_file_${safeName}_${articleId}${languageSuffix}_${file.name}', fileBase64);
        }
      }
    } else {
      final appDir = await getApplicationDocumentsDirectory();
      final articleDir = Directory('${appDir.path}/${isSubscriptionArticle ? "subscription" : "news"}/${safeName}_${articleId}$languageSuffix');
      await articleDir.create(recursive: true);
      articleDirPath = articleDir.path;
      
      final zipFile = File('$articleDirPath/article.zip');
      await zipFile.writeAsBytes(zipBytes);
      
      final archive = ZipDecoder().decodeBytes(zipBytes);
      for (final file in archive) {
        if (file.isFile) {
          final extractedFile = File('$articleDirPath/${file.name}');
          await extractedFile.create(recursive: true);
          await extractedFile.writeAsBytes(file.content as List<int>);
        }
      }
    }
    
    final displayTitle = language != 'en' ? '$title ($language)' : title;
    
    await DebugLogHelper.addDebugLog('ARTICLE_SAVE: Creating article with ID: ${articleId}$languageSuffix, Title: $displayTitle');
    
    final articleData = {
      'title': displayTitle,
      'path': articleDirPath,
      'created': DateTime.now().toIso8601String(),
      'original_request': title,
      'article_id': '${articleId}$languageSuffix',
      'article_type': article['article_type'] ?? 'Others',
      'language': language,
      'is_web_storage': kIsWeb,
    };
    
    if (isSubscriptionArticle) {
      articleData['subscription_domain'] = subscriptionDomain;
      articleData['is_subscription'] = true;
    }
    
    savedNews.add(json.encode(articleData));
    await prefs.setStringList('saved_news', savedNews);
    
    // CRITICAL: Verify article was actually saved
    final verifyNews = prefs.getStringList('saved_news') ?? [];
    await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Verified storage - now ${verifyNews.length} articles total');
    
    await DebugLogHelper.addDebugLog('ARTICLE_DOWNLOAD: Saved article "$displayTitle" to Listen page');
  }
  
  void _showArticleSelectionDialog(List<Map<String, dynamic>> articles, int newsletterId, String newsletterName) async {
    List<bool> selectedArticles = List.filled(articles.length, false);
    String dialogFilter = 'All';
    String searchQuery = '';
    TextEditingController searchController = TextEditingController();
    Set<String> subscribedDomains = <String>{}; // Track domains with credentials
    Map<String, bool> articleStorageStatus = {}; // Track local storage status
    List<String> selectedLanguages = ['en']; // Language selection for articles
    
    // Phase 3: Check for stored credentials and local storage (DISABLED - BUILD ERROR)
    for (final article in articles) {
      final articleId = article['article_id'] ?? '';
      final subscriptionDomain = article['subscription_domain'] ?? '';
      
      // if (subscriptionDomain.isNotEmpty) {
      //   final hasCredentials = await CredentialStorageService.hasCredentials(subscriptionDomain);
      //   if (hasCredentials) {
      //     subscribedDomains.add(subscriptionDomain);
      //   }
      // }
      
      // Check if article is stored locally (DISABLED - BUILD ERROR)
      // final isStoredLocally = await SubscriptionService.isArticleStoredLocally(articleId);
      // articleStorageStatus[articleId] = isStoredLocally;
      articleStorageStatus[articleId] = false; // Temporary: assume not stored locally
    }
    
    showDialog(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          List<Map<String, dynamic>> filteredArticles = List.from(articles);
          
          // Apply type filter
          if (dialogFilter != 'All') {
            filteredArticles = filteredArticles.where((article) {
              final articleType = article['article_type'] ?? 'Others';
              return articleType == dialogFilter;
            }).toList();
          }
          
          // Apply search filter
          if (searchQuery.isNotEmpty) {
            filteredArticles = filteredArticles.where((article) {
              final title = (article['title'] ?? '').toLowerCase();
              final author = (article['author'] ?? '').toLowerCase();
              final searchLower = searchQuery.toLowerCase();
              
              // Simple search in title and author
              bool matches = title.contains(searchLower) || author.contains(searchLower);
              
              // Handle exclude terms (words starting with -)
              final terms = searchQuery.split(' ');
              for (final term in terms) {
                if (term.startsWith('-') && term.length > 1) {
                  final excludeTerm = term.substring(1).toLowerCase();
                  if (title.contains(excludeTerm) || author.contains(excludeTerm)) {
                    matches = false;
                    break;
                  }
                }
              }
              
              return matches;
            }).toList();
          }
          
          final keyboardHeight = MediaQuery.of(context).viewInsets.bottom;
          final screenHeight = MediaQuery.of(context).size.height;
          final availableHeight = screenHeight - keyboardHeight - 200; // Reserve space for title and actions
          
          return Dialog(
            child: Container(
              width: MediaQuery.of(context).size.width * 0.9,
              height: MediaQuery.of(context).size.height * 0.8,
              child: Column(
                children: [
                  // Header
                  Container(
                    padding: EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.blue.shade50,
                      borderRadius: BorderRadius.vertical(top: Radius.circular(8)),
                    ),
                    child: Column(
                      children: [
                        Text(
                          'Select Articles',
                          style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                        ),
                        SizedBox(height: 8),
                        Text(
                          'Found ${articles.length} articles from $newsletterName',
                          style: TextStyle(fontSize: 14, color: Colors.grey.shade600),
                        ),
                      ],
                    ),
                  ),
                  
                  // Select All / Clear All buttons
                  Container(
                    padding: EdgeInsets.all(16),
                    child: Column(
                      children: [
                        LanguageSelector(
                          selectedLanguages: selectedLanguages,
                          onLanguagesChanged: (languages) {
                            setDialogState(() {
                              selectedLanguages = languages;
                            });
                          },
                        ),
                        SizedBox(height: 16),
                        Row(
                          children: [
                            Expanded(
                              child: ElevatedButton(
                                onPressed: () {
                                  setDialogState(() {
                                    for (int i = 0; i < selectedArticles.length; i++) {
                                      selectedArticles[i] = true;
                                    }
                                  });
                                },
                                child: Text('Select All'),
                              ),
                            ),
                            SizedBox(width: 16),
                            Expanded(
                              child: OutlinedButton(
                                onPressed: () {
                                  setDialogState(() {
                                    for (int i = 0; i < selectedArticles.length; i++) {
                                      selectedArticles[i] = false;
                                    }
                                  });
                                },
                                child: Text('Clear All'),
                              ),
                            ),
                          ],
                        ),
                      ],
                    ),
                  ),
                  
                  // Article list
                  Expanded(
                    child: ListView.builder(
                      padding: EdgeInsets.symmetric(horizontal: 16),
                      itemCount: articles.length,
                      itemBuilder: (context, index) {
                        final article = articles[index];
                        final title = article['title'] ?? 'Untitled Article';
                        final author = article['author'] ?? 'Unknown Author';
                        final subscriptionRequired = article['subscription_required'] ?? false;
                        final subscriptionDomain = article['subscription_domain'] ?? '';
                        final isSubscribed = subscribedDomains.contains(subscriptionDomain);
                        final articleId = article['article_id'] ?? '';
                        final isStoredLocally = articleStorageStatus[articleId] ?? false;
                        
                        // Phase 2: Detect previously authenticated articles
                        final isPreviouslyAuthenticated = title.startsWith('AUTHENTICATED ARTICLE:');
                        final isSubscriptionArticle = subscriptionRequired || isPreviouslyAuthenticated;
                        
                        if (subscriptionRequired && !isSubscribed) {
                          // Show subscription required for NEW subscription articles only
                          return Container(
                            margin: EdgeInsets.only(bottom: 12),
                            padding: EdgeInsets.all(16),
                            decoration: BoxDecoration(
                              color: Colors.red.shade50,
                              border: Border.all(color: Colors.red.shade200),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  children: [
                                    Icon(Icons.error, color: Colors.red, size: 16),
                                    SizedBox(width: 8),
                                    Text(
                                      'SUBSCRIPTION REQUIRED',
                                      style: TextStyle(
                                        color: Colors.red.shade700,
                                        fontWeight: FontWeight.bold,
                                        fontSize: 12,
                                      ),
                                    ),
                                  ],
                                ),
                                SizedBox(height: 8),
                                SizedBox(
                                  width: double.infinity,
                                  child: ElevatedButton(
                                    onPressed: () async {
                                      // Ensure domain is available for previously authenticated articles
                                      final dialogDomain = subscriptionDomain.isNotEmpty ? subscriptionDomain : 'bostonglobe.com';
                                      
                                      final response = await showDialog<CredentialResponse>(
                                        context: context,
                                        builder: (context) => SubscriptionCredentialDialog(
                                          articleId: article['article_id'] ?? '',
                                          domain: dialogDomain,
                                          articleTitle: title,
                                          newsletterId: newsletterId, // Pass newsletter_id for consistent decryption
                                        ),
                                      );
                                      
                                      // Phase 2: Update visual status after successful credential submission
                                      if (response != null && response.status == 'success') {
                                        setDialogState(() {
                                          subscribedDomains.add(dialogDomain);
                                        });
                                        
                                        // Show success message
                                        ScaffoldMessenger.of(context).showSnackBar(
                                          SnackBar(
                                            content: Text('Credentials accepted for $dialogDomain'),
                                            backgroundColor: Colors.green,
                                            duration: Duration(seconds: 2),
                                          ),
                                        );
                                      }
                                    },
                                    style: ElevatedButton.styleFrom(
                                      backgroundColor: Colors.red,
                                      foregroundColor: Colors.white,
                                      padding: EdgeInsets.symmetric(horizontal: 16, vertical: 8),
                                    ),
                                    child: Text('Enter Credentials'),
                                  ),
                                ),
                                SizedBox(height: 8),
                                Text(
                                  title,
                                  style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                  maxLines: 2,
                                  overflow: TextOverflow.ellipsis,
                                ),
                                SizedBox(height: 4),
                                Text(
                                  'By: $author • Domain: $subscriptionDomain',
                                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                                ),
                              ],
                            ),
                          );
                        } else if (isPreviouslyAuthenticated) {
                          // Previously authenticated article - green with premium indicator
                          return Container(
                            margin: EdgeInsets.only(bottom: 12),
                            decoration: isStoredLocally ? BoxDecoration(
                              color: Colors.green.shade50,
                              border: Border.all(color: Colors.green.shade200),
                              borderRadius: BorderRadius.circular(8),
                            ) : null,
                            child: CheckboxListTile(
                              value: selectedArticles[index],
                              onChanged: (bool? value) {
                                setDialogState(() {
                                  selectedArticles[index] = value ?? false;
                                });
                              },
                              title: Row(
                                children: [
                                  Icon(Icons.verified, color: Colors.green, size: 16),
                                  SizedBox(width: 8),
                                  if (isStoredLocally) ...[
                                    Icon(Icons.download_done, color: Colors.blue, size: 14),
                                    SizedBox(width: 4),
                                  ],
                                  Expanded(
                                    child: Text(
                                      title,
                                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Colors.green.shade700),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                              subtitle: Text(
                                'By: $author • Premium Content (Authenticated)${isStoredLocally ? ' • Stored locally' : ''}',
                                style: TextStyle(fontSize: 12, color: Colors.green.shade600),
                              ),
                              controlAffinity: ListTileControlAffinity.leading,
                            ),
                          );
                        } else if (isSubscriptionArticle && isSubscribed) {
                          // Newly subscribed article - green with open lock, show if stored locally
                          return Container(
                            margin: EdgeInsets.only(bottom: 12),
                            decoration: isStoredLocally ? BoxDecoration(
                              color: Colors.green.shade50,
                              border: Border.all(color: Colors.green.shade200),
                              borderRadius: BorderRadius.circular(8),
                            ) : null,
                            child: CheckboxListTile(
                              value: selectedArticles[index],
                              onChanged: (bool? value) {
                                setDialogState(() {
                                  selectedArticles[index] = value ?? false;
                                });
                              },
                              title: Row(
                                children: [
                                  Icon(Icons.lock_open, color: Colors.green, size: 16),
                                  SizedBox(width: 8),
                                  if (isStoredLocally) ...[
                                    Icon(Icons.download_done, color: Colors.blue, size: 14),
                                    SizedBox(width: 4),
                                  ],
                                  Expanded(
                                    child: Text(
                                      title,
                                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Colors.green.shade700),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                              subtitle: Text(
                                'By: $author • Subscribed to $subscriptionDomain${isStoredLocally ? ' • Stored locally' : ''}',
                                style: TextStyle(fontSize: 12, color: Colors.green.shade600),
                              ),
                              controlAffinity: ListTileControlAffinity.leading,
                            ),
                          );
                        } else {
                          // Free article - show if stored locally
                          return Container(
                            margin: EdgeInsets.only(bottom: 12),
                            decoration: isStoredLocally ? BoxDecoration(
                              color: Colors.blue.shade50,
                              border: Border.all(color: Colors.blue.shade200),
                              borderRadius: BorderRadius.circular(8),
                            ) : null,
                            child: CheckboxListTile(
                              value: selectedArticles[index],
                              onChanged: (bool? value) {
                                setDialogState(() {
                                  selectedArticles[index] = value ?? false;
                                });
                              },
                              title: Row(
                                children: [
                                  Icon(Icons.thumb_up, color: Colors.black, size: 16),
                                  SizedBox(width: 8),
                                  if (isStoredLocally) ...[
                                    Icon(Icons.download_done, color: Colors.blue, size: 14),
                                    SizedBox(width: 4),
                                  ],
                                  Expanded(
                                    child: Text(
                                      title,
                                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                                      maxLines: 2,
                                      overflow: TextOverflow.ellipsis,
                                    ),
                                  ),
                                ],
                              ),
                              subtitle: Text(
                                'By: $author${isStoredLocally ? ' • Stored locally' : ''}',
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                              ),
                              controlAffinity: ListTileControlAffinity.leading,
                            ),
                          );
                        }
                      },
                    ),
                  ),
                  
                  // Bottom buttons
                  Container(
                    padding: EdgeInsets.all(16),
                    decoration: BoxDecoration(
                      color: Colors.grey.shade50,
                      borderRadius: BorderRadius.vertical(bottom: Radius.circular(8)),
                    ),
                    child: Row(
                      children: [
                        Expanded(
                          child: TextButton(
                            onPressed: () => Navigator.pop(context),
                            child: Text('Cancel'),
                          ),
                        ),
                        SizedBox(width: 16),
                        Expanded(
                          child: ElevatedButton(
                            onPressed: () {
                              final selected = <Map<String, dynamic>>[];
                              for (int i = 0; i < articles.length; i++) {
                                if (selectedArticles[i]) {
                                  selected.add(articles[i]);
                                }
                              }
                              
                              Navigator.pop(context);
                              
                              if (selected.isEmpty) {
                                ScaffoldMessenger.of(context).showSnackBar(
                                  SnackBar(content: Text('No articles selected')),
                                );
                                return;
                              }
                              
                              _processSelectedArticles(selected, newsletterId, selectedLanguages);
                            },
                            child: Text('Add Selected (${selectedArticles.where((s) => s).length})'),
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    if (_isLoading) {
      return Scaffold(
        appBar: AppBar(
          title: Text('🏠 Home'),
          backgroundColor: Color(0xFF2c3e50),
          foregroundColor: Colors.white,
        ),
        body: Center(child: CircularProgressIndicator()),
      );
    }
    
    if (_appMode == 'Audio') {
      return _buildNewsletterView();
    }

    return Scaffold(
      appBar: AppBar(
        title: Text('🏠 Home'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          // [LOCAL-670] Rating filter: Any / 7+ / 8+ / 9+. The chosen bar is
          // remembered per device and passed to /tours-near as min_rating.
          IconButton(
            icon: Icon(_minRating > 0 ? Icons.star : Icons.star_border),
            onPressed: _showRatingFilterDialog,
            tooltip: _minRating > 0
                ? 'Rating filter: ${_minRating.toStringAsFixed(0)}+'
                : 'Rating filter: Any',
          ),
          // [LOCAL-672] "Top rated" sort toggle. On → /tours-near is ordered by
          // the Bayesian rank_score (verified ratings weighted higher). Off →
          // nearest-first (the default). Remembered per device.
          // [LOCAL-680] Opens a dialog naming both orders instead of toggling
          // silently; highlighted (amber) while "Top rated first" is on.
          IconButton(
            icon: Icon(Icons.sort,
                color: _topRated ? Colors.amber : null),
            onPressed: _showSortDialog,
            tooltip: _topRated ? 'Sorted: Top rated first' : 'Sorted: Nearest first',
          ),
          // [LOCAL-677] Free/Paid/Any filter. The chosen option is remembered
          // per device and passed to /tours-near as ?price=free|paid.
          IconButton(
            icon: Icon(_priceFilter == 'free'
                ? Icons.money_off
                : _priceFilter == 'paid'
                    ? Icons.sell
                    : Icons.sell_outlined),
            onPressed: _showPriceFilterDialog,
            tooltip: _priceFilter == 'free'
                ? 'Showing: Free tours'
                : _priceFilter == 'paid'
                    ? 'Showing: Paid tours'
                    : 'Free/Paid: Any',
          ),
          // [LOCAL-687] "Show 18+ tours" toggle. On → every list/search/code call
          // carries ?adult=1 so mature tours appear; off (default) hides them.
          // Highlighted (amber) while on. Remembered per device.
          IconButton(
            icon: Icon(_showAdult ? Icons.no_adult_content : Icons.shield_outlined,
                color: _showAdult ? Colors.amber : null),
            onPressed: _showAdultFilterDialog,
            tooltip: _showAdult ? '18+ tours: shown' : '18+ tours: hidden',
          ),
          // [LOCAL-665] One search button for everything. Michael: the two old
          // buttons (flag = tours, arrow-glass = location) were easy to confuse.
          // Now a single box tells a share code, a tour name and a place apart by
          // their format and dispatches accordingly (_showSearchDialog).
          IconButton(
            icon: Icon(Icons.search),
            onPressed: _showSearchDialog,
            tooltip: 'Search',
          ),
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: () async {
              await DebugLogHelper.addDebugLog('HOME: Manual refresh triggered');
              await _loadNearbyTours();
            },
          ),
        ],
      ),
      body: Column(
        children: [
          Container(
            padding: EdgeInsets.all(16),
            color: _isUsingCustomLocation ? Colors.orange.shade50 : Colors.blue.shade50,
            child: Column(
              children: [
                if (_isUsingCustomLocation) ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.location_on, color: Colors.orange.shade700, size: 20),
                      SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          'Showing tours near: $_customLocationName',
                          textAlign: TextAlign.center,
                          style: TextStyle(
                            fontSize: 14,
                            fontWeight: FontWeight.bold,
                            color: Colors.orange.shade800,
                          ),
                        ),
                      ),
                      TextButton(
                        onPressed: _resetToCurrentLocation,
                        child: Text('Reset', style: TextStyle(fontSize: 12)),
                      ),
                    ],
                  ),
                  SizedBox(height: 4),
                ],
                Text(
                  _isUsingCustomLocation 
                    ? 'Select to download for your trip'
                    : 'Most popular tours and treats in your area\nSelect to download',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    fontSize: 16,
                    fontWeight: FontWeight.w500,
                    color: _isUsingCustomLocation ? Colors.orange.shade800 : Colors.blue.shade800,
                  ),
                ),
                // [LOCAL-739 §2] A "My communities" chip on the Home map, shown
                // ONLY to a user who belongs to or organises ≥ 1 community. A
                // non-member never sees it. Opens the single Communities page.
                if (_isCommunityMember) ...[
                  const SizedBox(height: 8),
                  Align(
                    alignment: Alignment.center,
                    child: ActionChip(
                      key: const Key('home_my_communities_chip'),
                      avatar: const Icon(Icons.groups,
                          size: 18, color: Colors.deepPurple),
                      label: const Text('My communities'),
                      onPressed: () {
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                              builder: (_) => const CommunitiesHubScreen()),
                        );
                      },
                    ),
                  ),
                ],
              ],
            ),
          ),
          Expanded(
            child: LayoutBuilder(
              // [LOCAL-789] The map sits in a Column under a variable-height
              // header (the orange "Showing tours near: …" banner appears the
              // moment a place search sets _isUsingCustomLocation, and the
              // LOCAL-761 hide-on-scroll bar comes and goes). When the header
              // grows AFTER the first layout the Expanded map SHRINKS, but on a
              // real device the flutter_map size event could lag — so the tile
              // range stayed computed for the old, taller viewport and the
              // newly-exposed TOP band drew grey until the next camera event
              // ~30 s later. Here we detect the laid-out HEIGHT changing and
              // push onto _mapSizeReset; FirstLayoutTileLayer turns that into a
              // single post-frame tile reload against the now-correct size. No
              // timers — the trigger is the layout itself.
              builder: (context, constraints) {
                final h = constraints.maxHeight;
                if (_lastMapHeight != null &&
                    h.isFinite &&
                    (h - _lastMapHeight!).abs() > 0.5 &&
                    !_mapSizeReset.isClosed) {
                  _mapSizeReset.add(null);
                }
                if (h.isFinite) _lastMapHeight = h;
                return FlutterMap(
              mapController: _mapController,
              options: MapOptions(
                initialCenter: _displayLocation ?? _userLocation ?? LatLng(42.3601, -71.0589),
                initialZoom: 13.0,
                // [LOCAL-681] The visible area decides which tours are listed.
                onPositionChanged: _onMapMoved,
                onMapReady: () {
                  _viewBounds = _mapController.camera.visibleBounds;
                  _loadNearbyTours();
                },
              ),
              children: [
                // [LOCAL-763] The OSM tile layer, wrapped so it reloads its
                // tiles the instant the map's layout size is known. Fixes the
                // blank-map-until-zoom bug on the Home map now that it lives in
                // the LOCAL-761 IndexedStack + nested-Navigator tab shell (see
                // first_layout_tile_layer.dart for the full root-cause note).
                // [LOCAL-789] externalReset reloads the tiles again whenever the
                // map's laid-out height changes (banner/scroll-bar), so the top
                // never stays grey; user agent is the real app id (OSM throttles
                // generic com.example agents, slowing tiles).
                FirstLayoutTileLayer(
                  // [LOCAL-789B] Pass the shared controller so the layer reloads
                  // tiles after the size settles via an imperceptible camera
                  // nudge (zoom ± 1e-4) — the pinch-equivalent — instead of a
                  // key rebuild that disposed the TileLayer's network client and
                  // cancelled every in-flight tile (the fully-grey-on-entry bug).
                  mapController: _mapController,
                  externalReset: _mapSizeReset.stream,
                  builder: (reset) => TileLayer(
                    urlTemplate: 'https://tile.openstreetmap.org/{z}/{x}/{y}.png',
                    userAgentPackageName: 'com.audioura.audiotours',
                    reset: reset,
                  ),
                ),
                
                MarkerLayer(markers: _tourMarkers),

                // [LOCAL-690] Listed communities on the Home map, each with a
                // community badge (D658 addendum 2 §4). Private/waiver
                // communities are never returned by /communities/map.
                MarkerLayer(markers: _communityMarkers),
                
                // User location marker (always show if available)
                if (_userLocation != null && !_isUsingCustomLocation)
                  MarkerLayer(
                    markers: [
                      Marker(
                        point: _userLocation!,
                        width: 30,
                        height: 30,
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.red,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                          child: Icon(
                            Icons.person,
                            color: Colors.white,
                            size: 16,
                          ),
                        ),
                      ),
                    ],
                  ),
                
                // Custom location marker
                if (_isUsingCustomLocation && _displayLocation != null)
                  MarkerLayer(
                    markers: [
                      Marker(
                        point: _displayLocation!,
                        width: 35,
                        height: 35,
                        child: Container(
                          decoration: BoxDecoration(
                            color: Colors.orange,
                            shape: BoxShape.circle,
                            border: Border.all(color: Colors.white, width: 2),
                          ),
                          child: Icon(
                            Icons.search,
                            color: Colors.white,
                            size: 18,
                          ),
                        ),
                      ),
                    ],
                  ),
              ],
                );
              },
            ),
          ),
        ],
      ),
      // [LOCAL-683] "List" above the location button.
      floatingActionButton: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          FloatingActionButton.extended(
            heroTag: 'home_list',
            onPressed: _showVisibleToursList,
            icon: const Icon(Icons.list),
            label: const Text('List'),
          ),
          const SizedBox(height: 12),
          FloatingActionButton(
        heroTag: 'home_location',
        onPressed: () async {
          if (_isUsingCustomLocation) {
            _resetToCurrentLocation();
          } else {
            final position = await Geolocator.getCurrentPosition();
            final newLocation = LatLng(position.latitude, position.longitude);
            if (!mounted) return; // [LOCAL-773] setState after await.
            _mapController.move(newLocation, 15.0);
            setState(() {
              _userLocation = newLocation;
            });
          }
        },
        backgroundColor: _isUsingCustomLocation ? Colors.orange : null,
        child: Icon(_isUsingCustomLocation ? Icons.home : Icons.my_location),
      ),
        ],
      ),
    );
  }
  
  Widget _buildNewsletterView() {
    return Scaffold(
      appBar: AppBar(
        title: Text(_selectedTypeFilter == 'All' 
          ? '📧 Newsletters' 
          : '📧 Newsletters (${_selectedTypeFilter})'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          PopupMenuButton<String>(
            icon: Icon(Icons.filter_list),
            onSelected: (String value) {
              setState(() {
                _selectedTypeFilter = value;
              });
            },
            itemBuilder: (BuildContext context) {
              return _articleTypes.map((String type) {
                return PopupMenuItem<String>(
                  value: type,
                  child: Row(
                    children: [
                      Icon(
                        _selectedTypeFilter == type ? Icons.check : Icons.radio_button_unchecked,
                        size: 16,
                      ),
                      SizedBox(width: 8),
                      Text(type),
                    ],
                  ),
                );
              }).toList();
            },
          ),
          IconButton(
            icon: Icon(Icons.add),
            onPressed: _showNewsletterUrlDialog,
            tooltip: 'Process Newsletter URL',
          ),
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: () async {
              await DebugLogHelper.addDebugLog('HOME: Manual newsletter refresh triggered');
              await _loadNewsletters();
            },
          ),
        ],
      ),
      body: _newsletters.isEmpty
          ? Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  Icon(
                    Icons.email_outlined,
                    size: 64,
                    color: Colors.grey,
                  ),
                  SizedBox(height: 16),
                  Text(
                    'No newsletters available',
                    style: TextStyle(
                      fontSize: 18,
                      color: Colors.grey,
                    ),
                  ),
                  SizedBox(height: 8),
                  Text(
                    'Add newsletter URLs in the Generate section',
                    style: TextStyle(
                      fontSize: 14,
                      color: Colors.grey.shade600,
                    ),
                  ),
                ],
              ),
            )
          : RefreshIndicator(
              onRefresh: _loadNewsletters,
              child: _buildNewsletterSections(),
            ),
    );
  }
  
  Future<List<Map<String, dynamic>>> _getFilteredNewsletters() async {
    final now = DateTime.now();
    final oneMonthAgo = now.subtract(Duration(days: 30));
    
    await DebugLogHelper.addDebugLog('HOME: Filtering ${_newsletters.length} newsletters - date filter: after ${oneMonthAgo.toIso8601String()}');
    
    // Filter by type and date, limit to 12 latest
    final filtered = <Map<String, dynamic>>[];
    
    for (final newsletter in _newsletters) {
      // Filter by type
      if (_selectedTypeFilter != 'All') {
        final newsletterType = newsletter['type'] ?? 'Others';
        if (newsletterType != _selectedTypeFilter) {
          await DebugLogHelper.addDebugLog('HOME: Newsletter ${newsletter['name']} filtered out by type: $newsletterType != $_selectedTypeFilter');
          continue;
        }
      }
      
      // Filter by date (last 30 days)
      final createdAt = newsletter['created_at'];
      if (createdAt != null) {
        try {
          final date = DateTime.parse(createdAt);
          final isAfterFilter = date.isAfter(oneMonthAgo);
          if (!isAfterFilter) {
            await DebugLogHelper.addDebugLog('HOME: Newsletter ${newsletter['name']} filtered out by date: $createdAt is before $oneMonthAgo');
            continue;
          }
        } catch (e) {
          await DebugLogHelper.addDebugLog('HOME: Newsletter ${newsletter['name']} date parse error: $e, including anyway');
        }
      } else {
        await DebugLogHelper.addDebugLog('HOME: Newsletter ${newsletter['name']} has no created_at, including anyway');
      }
      
      filtered.add(newsletter);
    }
    
    await DebugLogHelper.addDebugLog('HOME: After filtering: ${filtered.length} newsletters remain');
    
    // Sort by date (newest first) and limit to 12
    filtered.sort((a, b) {
      try {
        final dateA = DateTime.parse(a['created_at'] ?? '');
        final dateB = DateTime.parse(b['created_at'] ?? '');
        return dateB.compareTo(dateA); // This should put newest first
      } catch (e) {
        return 0;
      }
    });
    
    final result = filtered.take(12).toList();
    await DebugLogHelper.addDebugLog('HOME: Final result: ${result.length} newsletters after sorting and limiting to 12');
    
    // Log the newsletter IDs for debugging
    for (final newsletter in result) {
      await DebugLogHelper.addDebugLog('HOME: Newsletter in final list: ID=${newsletter['newsletter_id']}, Name=${newsletter['name']}, Date=${newsletter['created_at']}');
    }
    
    return result;
  }
  
  Widget _buildNewsletterSections() {
    return FutureBuilder<List<Map<String, dynamic>>>(
      future: _getFilteredNewsletters(),
      builder: (context, snapshot) {
        if (!snapshot.hasData) {
          return Center(child: CircularProgressIndicator());
        }
        
        final newsletters = snapshot.data!;
    if (newsletters.isEmpty) {
      return Center(
        child: Column(
          mainAxisAlignment: MainAxisAlignment.center,
          children: [
            Icon(Icons.email_outlined, size: 64, color: Colors.grey),
            SizedBox(height: 16),
            Text('No newsletters available', style: TextStyle(fontSize: 18, color: Colors.grey)),
            SizedBox(height: 8),
            Text('Add newsletter URLs in the Generate section', style: TextStyle(fontSize: 14, color: Colors.grey.shade600)),
          ],
        ),
      );
    }
    
    final now = DateTime.now();
    final today = DateTime(now.year, now.month, now.day);
    final weekAgo = now.subtract(Duration(days: 7));
    
    final todayNewsletters = <Map<String, dynamic>>[];
    final weekNewsletters = <Map<String, dynamic>>[];
    final monthNewsletters = <Map<String, dynamic>>[];
    
    for (final newsletter in newsletters) {
      try {
        final createdAt = DateTime.parse(newsletter['created_at'] ?? '');
        final createdDate = DateTime(createdAt.year, createdAt.month, createdAt.day);
        
        // Treat future dates as today (handles timezone/clock differences)
        if (createdDate.isAtSameMomentAs(today) || createdAt.isAfter(now)) {
          todayNewsletters.add(newsletter);
        } else if (createdAt.isAfter(weekAgo)) {
          weekNewsletters.add(newsletter);
        } else {
          monthNewsletters.add(newsletter);
        }
      } catch (e) {
        monthNewsletters.add(newsletter);
      }
    }
    
        return ListView(
          padding: EdgeInsets.all(16),
          children: [
            if (todayNewsletters.isNotEmpty) ..._buildSection('Today', todayNewsletters),
            if (weekNewsletters.isNotEmpty) ..._buildSection('This Week', weekNewsletters),
            if (monthNewsletters.isNotEmpty) ..._buildSection('This Month', monthNewsletters),
          ],
        );
      },
    );
  }
  
  List<Widget> _buildSection(String title, List<Map<String, dynamic>> newsletters) {
    return [
      Padding(
        padding: EdgeInsets.symmetric(vertical: 8),
        child: Text(
          title,
          style: TextStyle(
            fontSize: 18,
            fontWeight: FontWeight.bold,
            color: Color(0xFF2c3e50),
          ),
        ),
      ),
      ...newsletters.map((newsletter) => _buildNewsletterCard(newsletter)),
      SizedBox(height: 16),
    ];
  }
  
  Widget _buildNewsletterCard(Map<String, dynamic> newsletter) {
    final name = newsletter['name'] ?? 'Unknown Newsletter';
    final url = newsletter['url'] ?? '';
    final createdAt = newsletter['created_at'] ?? '';
    final newsletterId = newsletter['newsletter_id'] ?? 0;
    final articleCount = newsletter['article_count'] ?? 0;
    

    
    String dateStr = '';
    if (createdAt.isNotEmpty) {
      try {
        final date = DateTime.parse(createdAt);
        dateStr = '${date.month}/${date.day}/${date.year}';
      } catch (e) {
        dateStr = 'Unknown date';
      }
    }
    
    return Card(
      margin: EdgeInsets.only(bottom: 12),
      elevation: 2,
      child: ListTile(
        contentPadding: EdgeInsets.all(16),
        leading: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: Color(0xFF3498db),
            borderRadius: BorderRadius.circular(8),
          ),
          child: Icon(Icons.newspaper, color: Colors.white, size: 24),
        ),
        title: Text(
          name,
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            SizedBox(height: 4),
            Row(
              children: [
                Icon(Icons.calendar_today, size: 14, color: Colors.blue.shade600),
                SizedBox(width: 4),
                Text(
                  dateStr,
                  style: TextStyle(color: Colors.blue.shade600, fontSize: 12, fontWeight: FontWeight.w500),
                ),
                SizedBox(width: 12),
                Icon(Icons.article, size: 14, color: Colors.green.shade600),
                SizedBox(width: 4),
                Text(
                  '$articleCount articles',
                  style: TextStyle(color: Colors.green.shade600, fontSize: 12, fontWeight: FontWeight.w500),
                ),
              ],
            ),
            SizedBox(height: 4),
            Text(
              url,
              style: TextStyle(color: Colors.grey.shade600, fontSize: 11),
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
          ],
        ),
        trailing: Container(
          width: 48,
          height: 48,
          decoration: BoxDecoration(
            color: Color(0xFF27ae60),
            shape: BoxShape.circle,
          ),
          child: IconButton(
            icon: Icon(Icons.play_arrow, color: Colors.white, size: 24),
            onPressed: () {
              _processNewsletterWithUrl(url, newsletterId, name);
            },
          ),
        ),
        onTap: () {
          _processNewsletterWithUrl(url, newsletterId, name);
        },
      ),
    );
  }
  
  Widget _buildSubscriptionArticleTile(Map<String, dynamic> article, String title, String author, String date, String articleType, String subscriptionDomain) {
    return ListTile(
      leading: Container(
        width: 40,
        height: 40,
        decoration: BoxDecoration(
          color: Colors.orange.shade100,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(color: Colors.orange.shade300),
        ),
        child: Icon(Icons.lock, color: Colors.orange.shade700, size: 20),
      ),
      title: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                decoration: BoxDecoration(
                  color: Colors.orange,
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  'SUBSCRIPTION REQUIRED',
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
            ],
          ),
          SizedBox(height: 4),
          Text(
            title,
            style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
            maxLines: 2,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
      subtitle: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                padding: EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                decoration: BoxDecoration(
                  color: _getTypeColor(articleType),
                  borderRadius: BorderRadius.circular(4),
                ),
                child: Text(
                  articleType,
                  style: TextStyle(
                    color: Colors.white,
                    fontSize: 10,
                    fontWeight: FontWeight.bold,
                  ),
                ),
              ),
              SizedBox(width: 8),
              Expanded(
                child: Text(
                  'By: $author',
                  style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                ),
              ),
            ],
          ),
          Text(
            'Domain: $subscriptionDomain',
            style: TextStyle(fontSize: 12, color: Colors.orange.shade700, fontWeight: FontWeight.w500),
          ),
          Text(
            'Date: $date',
            style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
          ),
        ],
      ),
      trailing: ElevatedButton(
        onPressed: () => _showCredentialDialog(article, subscriptionDomain, title),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.orange,
          foregroundColor: Colors.white,
          padding: EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        ),
        child: Text(
          'Enter\nCredentials',
          style: TextStyle(fontSize: 10),
          textAlign: TextAlign.center,
        ),
      ),
      dense: true,
    );
  }
  
  void _showCredentialDialog(Map<String, dynamic> article, String domain, String title, [Function(String)? onCredentialSuccess]) async {
    final response = await showDialog<CredentialResponse>(
      context: context,
      builder: (context) => SubscriptionCredentialDialog(
        articleId: article['article_id'] ?? '',
        domain: domain,
        articleTitle: title,
        newsletterId: null, // No newsletter_id available in this context
      ),
    );
    
    // Phase 2: Update article status from "Subscription Required" to "Subscribed"
    if (response != null && response.status == 'success' && onCredentialSuccess != null) {
      onCredentialSuccess(domain);
    }
  }
  
  void _showNewsletterUrlDialog() {
    final TextEditingController controller = TextEditingController();
    
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Process Newsletter URL'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextField(
              controller: controller,
              decoration: InputDecoration(
                hintText: 'https://mailchi.mp/bostonglobe/...',
                labelText: 'Newsletter URL',
                helperText: 'Enter the full newsletter URL to process',
              ),
              maxLines: 3,
              autofocus: true,
            ),
            SizedBox(height: 16),
            Container(
              padding: EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.blue.shade50,
                borderRadius: BorderRadius.circular(4),
                border: Border.all(color: Colors.blue.shade200),
              ),
              child: Row(
                children: [
                  Icon(Icons.info, color: Colors.blue.shade600, size: 16),
                  SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'This will process the newsletter and generate encryption keys for subscription articles.',
                      style: TextStyle(
                        fontSize: 12,
                        color: Colors.blue.shade700,
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () async {
              final url = controller.text.trim();
              if (url.isEmpty) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text('Please enter a newsletter URL'),
                    backgroundColor: Colors.red,
                  ),
                );
                return;
              }
              
              Navigator.pop(context);
              await _processNewsletterUrl(url);
            },
            child: Text('Process'),
          ),
        ],
      ),
    );
  }
  
  // Count actual stops from tour ZIP content
  Future<int> _countTourStops(List<int> zipBytes) async {
    try {
      final archive = ZipDecoder().decodeBytes(zipBytes);
      
      // Look for tour.json file which contains tour structure
      for (final file in archive) {
        if (file.name == 'tour.json' && file.isFile) {
          final jsonContent = String.fromCharCodes(file.content as List<int>);
          final tourData = json.decode(jsonContent);
          
          // Count stops from tour data structure
          if (tourData['stops'] != null && tourData['stops'] is List) {
            return (tourData['stops'] as List).length;
          }
          
          // Fallback: count audio files (each stop has an MP3)
          int audioCount = 0;
          for (final audioFile in archive) {
            if (audioFile.name.endsWith('.mp3') && audioFile.isFile) {
              audioCount++;
            }
          }
          if (audioCount == 0) await DebugLogHelper.addDebugLog('HOME: Falling back to default stop count of 10 (no tour.json stops, no MP3s)');
          return audioCount > 0 ? audioCount : 10; // Default to 10 if no audio files
        }
      }
      
      // Fallback: count MP3 files
      int audioCount = 0;
      for (final file in archive) {
        if (file.name.endsWith('.mp3') && file.isFile) {
          audioCount++;
        }
      }
      
      if (audioCount == 0) await DebugLogHelper.addDebugLog('HOME: Falling back to default stop count of 10 (no MP3s found in ZIP)');
      return audioCount > 0 ? audioCount : 10; // Default to 10 if no audio files found
    } catch (e) {
      await DebugLogHelper.addDebugLog('HOME: Error counting tour stops: $e');
      return 10; // Default fallback
    }
  }
  
  Color _getTypeColor(String type) {
    switch (type) {
      case 'News and Politics':
        return Colors.red.shade600;
      case 'Business and Investment':
        return Colors.green.shade600;
      case 'Technology':
        return Colors.blue.shade600;
      case 'Lifestyle and Entertainment':
        return Colors.purple.shade600;
      case 'Education and Learning':
        return Colors.orange.shade600;
      default:
        return Colors.grey.shade600;
    }
  }
}

class _TreatDetailView extends StatelessWidget {
  final Map<String, dynamic> treatData;

  const _TreatDetailView({
    required this.treatData,
  });

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: Colors.black,
      appBar: AppBar(
        backgroundColor: Colors.black,
        foregroundColor: Colors.white,
        title: Text(treatData['name'] ?? 'Treat'),
        actions: [
          if (treatData['link_to_vendor'] != null)
            IconButton(
              icon: Icon(Icons.open_in_browser),
              onPressed: () async {
                final url = treatData['link_to_vendor'];
                try {
                  final uri = Uri.parse(url);
                  await launchUrl(
                    uri,
                    mode: LaunchMode.externalApplication,
                  );
                } catch (e) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(content: Text('Error opening link: $e')),
                  );
                }
              },
            ),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: Center(
              child: treatData['image_base64'] != null
                  ? InteractiveViewer(
                      child: Image.memory(
                        base64Decode(treatData['image_base64']),
                        fit: BoxFit.contain,
                      ),
                    )
                  : Icon(
                      Icons.local_cafe,
                      size: 100,
                      color: Colors.white54,
                    ),
            ),
          ),
          if (treatData['request_string'] != null && treatData['request_string'].isNotEmpty)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              color: Colors.black87,
              child: Text(
                treatData['request_string'],
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

/// [LOCAL-680] Examples under the Search box, one group per kind of input.
/// '*' semantics match the server (_search_like_pattern): no star = contains;
/// stars anchor the match.
class _SearchExamples extends StatelessWidget {
  const _SearchExamples();

  static const List<List<String>> _groups = [
    ['Place', 'Boston  ·  Nice, France  ·  42.36, -71.06'],
    ['Tour name', 'Boston* starts with  ·  *Boston ends with  ·  *Boston* contains'],
    ['Share code', 'Ab12Cd34  (8 letters and digits, or paste the whole share message)'],
  ];

  @override
  Widget build(BuildContext context) {
    final small = Theme.of(context).textTheme.bodySmall;
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text('Examples', style: small?.copyWith(fontWeight: FontWeight.bold)),
        const SizedBox(height: 4),
        for (final g in _groups)
          Padding(
            padding: const EdgeInsets.only(bottom: 2),
            child: Text.rich(
              TextSpan(children: [
                TextSpan(text: '${g[0]}: ', style: const TextStyle(fontWeight: FontWeight.w600)),
                TextSpan(text: g[1]),
              ]),
              style: small,
            ),
          ),
      ],
    );
  }
}


/// [LOCAL-680] Stop-1 preview controls for the paid-tour dialog:
/// idle → "Preview Stop 1"; playing → "Pause" + "Stop"; paused → "Resume" + "Stop".
class _PreviewControls extends StatelessWidget {
  final String tourId;
  final bool enabled;
  const _PreviewControls({required this.tourId, required this.enabled});

  @override
  Widget build(BuildContext context) {
    final player = TourPreviewPlayer.instance;
    return ValueListenableBuilder<PreviewState>(
      valueListenable: player.state,
      builder: (context, st, _) {
        final mine = player.currentTourId == tourId;
        final state = mine ? st : PreviewState.idle;
        if (state == PreviewState.idle) {
          return TextButton.icon(
            icon: const Icon(Icons.play_arrow),
            label: const Text('Preview Stop 1'),
            onPressed: !enabled
                ? null
                : () async {
                    try {
                      await player.play(tourId);
                    } catch (_) {
                      if (context.mounted) {
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(content: Text('Preview unavailable right now.')),
                        );
                      }
                    }
                  },
          );
        }
        if (state == PreviewState.loading) {
          return const Padding(
            padding: EdgeInsets.symmetric(horizontal: 12),
            child: SizedBox(
                height: 18, width: 18, child: CircularProgressIndicator(strokeWidth: 2)),
          );
        }
        final playing = state == PreviewState.playing;
        return Row(
          mainAxisSize: MainAxisSize.min,
          children: [
            TextButton.icon(
              icon: Icon(playing ? Icons.pause : Icons.play_arrow),
              label: Text(playing ? 'Pause' : 'Resume'),
              onPressed: playing ? player.pause : player.resume,
            ),
            TextButton.icon(
              icon: const Icon(Icons.stop),
              label: const Text('Stop'),
              onPressed: player.stop,
            ),
          ],
        );
      },
    );
  }
}


/// [LOCAL-682] Small gold "$" in the pin's bottom-right corner (the top-right is
/// the multi-tour badge).
class _PaidPinBadge extends StatelessWidget {
  const _PaidPinBadge();

  @override
  Widget build(BuildContext context) {
    return Positioned(
      right: -2,
      bottom: -2,
      child: Container(
        width: 18,
        height: 18,
        alignment: Alignment.center,
        decoration: BoxDecoration(
          color: const Color(0xFFFFC107),
          shape: BoxShape.circle,
          border: Border.all(color: Colors.white, width: 1.5),
        ),
        child: const Text(
          '\$',
          style: TextStyle(
            fontSize: 12,
            fontWeight: FontWeight.w900,
            color: Color(0xFF5D4037),
            height: 1.0,
          ),
        ),
      ),
    );
  }
}
