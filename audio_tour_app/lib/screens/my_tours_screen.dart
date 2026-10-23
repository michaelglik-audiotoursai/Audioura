import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:speech_to_text/speech_to_text.dart';
import 'package:path_provider/path_provider.dart';
import '../screens/debug_log_viewer_screen.dart';
import '../services/tour_translation_helper.dart';
import '../config/endpoints.dart';
import '../utils/tour_path_healer.dart';
import '../utils/view_after_download.dart';
import '../widgets/share_tour_sheet.dart';
import '../services/community_downloads.dart';
import '../widgets/rate_tour_dialog.dart';
import '../widgets/delete_tour_prompt.dart';
import 'package:url_launcher/url_launcher.dart';

import 'tour_player_screen.dart';
import 'news_player_screen.dart';
import 'edit_tour_screen.dart';
import 'tour_map_screen.dart';
import 'my_communities_screen.dart';
import '../services/tour_pricing_service.dart';
import '../services/entitlements_service.dart';
import '../services/device_service.dart';
import '../services/score_explanation_service.dart';
import '../services/document_acceptance_service.dart';
import '../services/deep_link_service.dart';

/// LOCAL-484 — build the subtitle line shown under each tour on the Listen
/// (My Tours) list.
///
/// The count segment ("N stops • ") is only emitted when the tour actually
/// stored a stop count. Previously the widget used `tour['stops'] ?? '10'`,
/// which asserted a fabricated "10 stops" for any tour that never stored a
/// count. An absent number is honest; a wrong one is not — so when the count
/// is unknown we show only the created date.
///
/// Kept as a top-level pure function so the "no count → no '10 stops'"
/// behaviour is unit-testable without the widget (AC #3).
String tourSubtitleLine(Map<String, dynamic> tour) {
  final created =
      DateTime.parse(tour['created']).toLocal().toString().split(' ')[0];

  final rawStops = tour['stops'];
  final stops = rawStops?.toString().trim() ?? '';
  if (stops.isEmpty) {
    return 'Created: $created';
  }
  return '$stops stops • Created: $created';
}

/// [LOCAL-666] "v{version} · updated {Mon D}" shown on the My Tours (Listen) list
/// under each tour, mirroring the found-tour dialogs (LOCAL-657). Returns null —
/// so the list shows nothing extra — when the label should not appear: version is
/// missing (an old server/an older saved entry stored none), unparseable, or still
/// 1. For a translation the version is the SOURCE tour's version (the server pins
/// it via source_version), so the Russian copy of v10 reads "v10" here too.
///
/// Kept a top-level pure function (like tourSubtitleLine) so the "no version → no
/// label" and "v1 → no label" behaviour is unit-testable without the widget, and
/// every field read is defensive so a missing/garbled value never throws.
const List<String> _kMonthAbbr = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
];

String? tourVersionLabel(Map<String, dynamic> tour) {
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
      label += ' · updated ${_kMonthAbbr[parsed.month - 1]} ${parsed.day}';
    }
  }
  return label;
}

class MyToursScreen extends StatefulWidget {
  const MyToursScreen({super.key});

  @override
  State<MyToursScreen> createState() => _MyToursScreenState();
}

class _MyToursScreenState extends State<MyToursScreen> {
  List<Map<String, dynamic>> _tours = [];
  List<Map<String, dynamic>> _news = [];
  List<Map<String, dynamic>> _filteredNews = [];
  Map<String, String> _displayTitles = {}; // Pre-loaded display titles
  String _appMode = 'Tours';
  String _selectedTypeFilter = 'All';
  final List<String> _articleTypes = [
    'All',
    'News and Politics',
    'Business and Investment', 
    'Technology',
    'Lifestyle and Entertainment',
    'Education and Learning',
    'Others'
  ];
  bool _isSelectionMode = false;
  List<bool> _selectedArticles = [];
  String _searchQuery = '';
  TextEditingController _searchController = TextEditingController();
  SpeechToText _speechToText = SpeechToText();
  bool _speechEnabled = false;
  bool _isListening = false;
  int _currentVisibleIndex = 0;
  double _previousScrollPosition = 0.0;
  Map<int, bool> _tourHasMap = {};

  // [LOCAL-677] Curator paid tours. _canSell is the device's Curator entitlement
  // (plans.can_sell) — the Price control is shown only to a curator. _priceByTour
  // caches the current price state, _salesByTour the unlock (sales) count, both
  // keyed by the tour's numeric id string, loaded lazily per tour.
  bool _canSell = false;
  final Map<String, TourPrice> _priceByTour = {};
  final Map<String, int> _salesByTour = {};

  final ScrollController _scrollController = ScrollController();

  // [LOCAL-716B / D358] The displayed index of a tour to briefly highlight
  // after "View" when several tours were downloaded (or a single-tour open
  // missed and fell back). Null when nothing is highlighted. A timer clears it
  // after ~2s so the row flashes, then returns to normal.
  int? _highlightIndex;
  Timer? _highlightTimer;
  
  Future<void> _manualRefresh() async {
    await DebugLogHelper.addDebugLog('LISTEN: Manual refresh triggered');
    if (!mounted) return;
    await _loadAppMode();
  }
  
  @override
  void initState() {
    super.initState();
    _loadAppMode();
    _setupVoiceCommands();
    _setupScrollListener();
    _loadCuratorStatus();
  }

  @override
  void dispose() {
    // [LOCAL-716B] Cancel the highlight flash timer and release the scroll
    // controller so the newest-tour highlight path leaves nothing running.
    _highlightTimer?.cancel();
    _scrollController.dispose();
    super.dispose();
  }

  /// [LOCAL-677] Learn whether this device is a Curator (plans.can_sell). Only a
  /// curator sees the Price control. Fails safe to false (no control shown).
  Future<void> _loadCuratorStatus() async {
    try {
      final ent = await EntitlementsService.me();
      if (mounted) setState(() => _canSell = ent.canSell);
    } catch (_) {/* not a curator / offline → no price control */}
  }

  /// [LOCAL-677] The numeric tour id of a saved tour, or null for a local-only
  /// tour that was never persisted server-side (can't be priced/sold).
  ///
  /// [LOCAL-680] Prefers `server_tour_id`, stamped at download (LOCAL-677B):
  /// `tour_id` holds the EDIT id, which is non-numeric for a downloaded tour, so
  /// Rate said "no numeric tour ID" on a bought tour (Michael, 2026-10-14).
  String? _numericTourId(Map<String, dynamic> tour) {
    for (final key in const ['server_tour_id', 'tour_id']) {
      final raw = tour[key]?.toString();
      if (raw != null && int.tryParse(raw) != null) return raw;
    }
    return null;
  }

  /// [LOCAL-677] Lazily load a tour's price + sales count for the curator view.
  Future<void> _loadPriceAndSales(String tourId) async {
    final price = await TourPricingService.price(tourId);
    final sales = await TourPricingService.salesCount(tourId);
    if (!mounted) return;
    setState(() {
      _priceByTour[tourId] = price;
      _salesByTour[tourId] = sales;
    });
  }

  /// [LOCAL-677] The curator's price + Sales line for a sellable tour. Triggers
  /// a lazy load the first time it is built. Shows nothing for a tour with no
  /// numeric id. "Price: $4.99 · Sales: 3" or "Price: Free · Sales: 0".
  Widget _buildCuratorPriceLine(Map<String, dynamic> tour) {
    final tourId = _numericTourId(tour);
    if (tourId == null) return const SizedBox.shrink();
    if (!_priceByTour.containsKey(tourId)) {
      // Kick off the lazy load once, after this frame (avoid setState in build).
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted && !_priceByTour.containsKey(tourId)) {
          _priceByTour[tourId] = const TourPrice(
              isPaid: false,
              priceTier: null,
              priceUsd: null,
              priceLabel: 'Free',
              productId: null); // placeholder to avoid a reload loop
          _loadPriceAndSales(tourId);
        }
      });
      return const SizedBox.shrink();
    }
    final price = _priceByTour[tourId]!;
    final sales = _salesByTour[tourId] ?? 0;
    return Padding(
      padding: const EdgeInsets.only(top: 2),
      child: Text(
        'Price: ${price.priceLabel} · Sales: $sales',
        style: TextStyle(
          fontSize: 12,
          color: price.isPaid ? const Color(0xFF1B6B2E) : Colors.grey.shade700,
          fontWeight: FontWeight.w600,
        ),
      ),
    );
  }

  /// [LOCAL-688] Request the ONE free re-score of this tour after an edit.
  /// Confirms first (it is one per content version), then POSTs to map-delivery
  /// with the device user_id; the server enforces ownership (403) and the
  /// one-per-version limit (409). The outcome is surfaced as a clear message.
  Future<void> _requestRescore(Map<String, dynamic> tour) async {
    final tourId = _numericTourId(tour);
    if (tourId == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('This tour has no numeric ID yet and cannot be re-scored.'),
      ));
      return;
    }

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('Request a re-score'),
        content: const Text(
          'We\'ll grade this version of your tour again and publish the fresh '
          'Audioura score. You get one free re-score per edit — edit the tour '
          'again for another.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(ctx, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('Request'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;

    final userId = await DeviceService.getUserId();
    final result = await ScoreExplanationService.requestRescore(tourId, userId);
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(result.message)),
    );
  }

  /// [LOCAL-677] Curator Price control: pick a tier (or Free) for THIS tour.
  /// Uses the server's price_tiers config (no hard-coded prices) and
  /// TourPricingService.setPrice, which enforces curator + ownership server-side
  /// (a 403 is surfaced as a clear message). On success the row refreshes.
  Future<void> _showPriceDialog(Map<String, dynamic> tour) async {
    final tourId = _numericTourId(tour);
    if (tourId == null) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('This tour has no numeric ID yet and cannot be priced.'),
      ));
      return;
    }

    // [LOCAL-686] The picker offers ONLY the round-dollar ladder (in_picker).
    final ladder = await TourPricingService.pickerLadder();
    final current = await TourPricingService.price(tourId);
    if (!mounted) return;

    if (ladder.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(const SnackBar(
        content: Text('Prices are unavailable right now. Please try again.'),
      ));
      return;
    }

    // The LEAD quick-pick recommendation (D-pending): $3, $5, $10, $20, $50.
    // Map each to its ladder tier (the ladder is round dollars, so these exist).
    const quickPickUsd = [3.0, 5.0, 10.0, 20.0, 50.0];
    final quickPicks = <PriceTier>[
      for (final usd in quickPickUsd)
        ...ladder.where((t) => t.priceUsd == usd).take(1),
    ];

    int? chosen = current.priceTier; // null = Free
    final customController = TextEditingController();
    // [LOCAL-691] First time a guide prices a tour (any paid tier) they must
    // accept the Guide Terms. We seed this true if they already accepted the
    // current version, so returning guides are not re-prompted.
    bool guideTermsAccepted = false;
    final priceUserId = await DeviceService.getUserId();
    guideTermsAccepted = await DocumentAcceptanceService.hasAccepted(
        priceUserId, LegalDoc.guideTerms);
    if (!mounted) return;
    // If the tour already has a non-quick-pick price, seed the custom field with
    // it so the guide sees their current price and can tweak it.
    if (current.priceTier != null &&
        !quickPicks.any((t) => t.tier == current.priceTier)) {
      final cur = ladder.where((t) => t.tier == current.priceTier);
      if (cur.isNotEmpty) {
        customController.text = cur.first.priceUsd.toStringAsFixed(0);
      }
    }

    await showDialog(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setDialog) {
          // The label under the custom field: 'Your price: $X' = nearest step.
          String customSnapLabel = '';
          final typed = double.tryParse(customController.text.trim());
          if (typed != null) {
            final snapped = TourPricingService.snapToLadder(typed, ladder);
            if (snapped != null) customSnapLabel = 'Your price: ${snapped.label}';
          }

          Widget priceChip(String label, int? tier) {
            final selected = chosen == tier;
            return ChoiceChip(
              label: Text(label),
              selected: selected,
              onSelected: (_) => setDialog(() {
                chosen = tier;
                // Picking a chip clears any custom entry (one source of truth).
                customController.clear();
              }),
            );
          }

          return AlertDialog(
            title: const Text('Set a price'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Padding(
                    padding: EdgeInsets.only(bottom: 8),
                    child: Text(
                      'Stop 1 is a free preview; the rest unlocks on purchase.',
                      style: TextStyle(fontSize: 12, color: Colors.black54),
                    ),
                  ),
                  // Quick picks + Free as chips at the top of the control.
                  Wrap(
                    spacing: 8,
                    runSpacing: 4,
                    children: [
                      priceChip('Free', null),
                      for (final t in quickPicks) priceChip(t.label, t.tier),
                    ],
                  ),
                  const SizedBox(height: 16),
                  const Text('Or set your own price',
                      style: TextStyle(fontWeight: FontWeight.w600)),
                  const SizedBox(height: 4),
                  TextField(
                    controller: customController,
                    keyboardType: const TextInputType.numberWithOptions(
                        decimal: true),
                    decoration: const InputDecoration(
                      labelText: r'Your price ($2–$200)',
                      prefixText: r'$',
                      isDense: true,
                    ),
                    onChanged: (val) => setDialog(() {
                      // Typing a custom price snaps to the nearest ladder step
                      // and selects that tier; the chip selection clears.
                      final amt = double.tryParse(val.trim());
                      if (amt != null) {
                        final snapped =
                            TourPricingService.snapToLadder(amt, ladder);
                        chosen = snapped?.tier;
                      }
                    }),
                  ),
                  if (customSnapLabel.isNotEmpty)
                    Padding(
                      padding: const EdgeInsets.only(top: 6),
                      child: Text(
                        customSnapLabel,
                        style: const TextStyle(
                          fontWeight: FontWeight.bold,
                          color: Color(0xFF1B6B2E),
                        ),
                      ),
                    ),
                  // [LOCAL-691] Required Guide Terms acceptance for a paid price.
                  if (chosen != null) ...[
                    const SizedBox(height: 8),
                    CheckboxListTile(
                      contentPadding: EdgeInsets.zero,
                      dense: true,
                      value: guideTermsAccepted,
                      onChanged: (v) =>
                          setDialog(() => guideTermsAccepted = v ?? false),
                      title: Wrap(
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          const Text('I accept the ',
                              style: TextStyle(fontSize: 13)),
                          InkWell(
                            onTap: () async {
                              final uri =
                                  Uri.parse(legalDocUrl(LegalDoc.guideTerms));
                              if (await canLaunchUrl(uri)) {
                                await launchUrl(uri,
                                    mode: LaunchMode.externalApplication);
                              }
                            },
                            child: const Text('Guide Terms',
                                style: TextStyle(
                                  fontSize: 13,
                                  color: Color(0xFF3A3AC0),
                                  decoration: TextDecoration.underline,
                                )),
                          ),
                        ],
                      ),
                    ),
                  ],
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(ctx),
                child: const Text('Cancel'),
              ),
              ElevatedButton(
                onPressed: (chosen != null && !guideTermsAccepted)
                    ? null
                    : () async {
                  // [LOCAL-691] Record Guide Terms acceptance before pricing.
                  if (chosen != null) {
                    await DocumentAcceptanceService.record(
                        priceUserId, LegalDoc.guideTerms);
                  }
                  Navigator.pop(ctx);
                  final res = await TourPricingService.setPrice(tourId, chosen);
                  if (!mounted) return;
                  if (res.ok) {
                    await _loadPriceAndSales(tourId);
                    if (!mounted) return;
                    ScaffoldMessenger.of(context).showSnackBar(SnackBar(
                      content: Text(chosen == null
                          ? 'Tour is now free.'
                          : 'Price set.'),
                    ));
                  } else {
                    final msg = res.code == 'not_owner'
                        ? 'You can only price a tour you created.'
                        : res.code == 'not_curator'
                            ? 'Only a Curator can set a price.'
                            : (res.message ?? 'Could not set the price.');
                    ScaffoldMessenger.of(context)
                        .showSnackBar(SnackBar(content: Text(msg)));
                  }
                },
                child: const Text('Save'),
              ),
            ],
          );
        },
      ),
    );
  }
  
  void _setupScrollListener() {
    // SCROLL LISTENER DISABLED - not essential for core functionality
    unawaited(DebugLogHelper.addDebugLog('SCROLL: Listener disabled - not needed for core functionality')); // sync callback, cannot await
  }
  
  void _setupVoiceCommands() async {
    _speechEnabled = await _speechToText.initialize();
  }
  
  Future<void> _handleVoiceSearchCommand(String voiceCommand) async {
    // Convert voice command to search pattern
    final searchPattern = await _convertVoiceToSearch(voiceCommand);
    
    // Apply the search directly as filter
    setState(() {
      _searchQuery = searchPattern;
      _searchController.text = searchPattern;
    });
    
    await _applyNewsFilter();
    
    // Add debug log
    await DebugLogHelper.addDebugLog('LISTEN: Voice search "$voiceCommand" → "$searchPattern" → ${_filteredNews.length} results');
    
    // Show simple feedback
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(_filteredNews.isNotEmpty 
          ? 'Found ${_filteredNews.length} articles for "$voiceCommand"'
          : 'No articles found for "$voiceCommand"'),
        backgroundColor: _filteredNews.isNotEmpty ? Colors.green : Colors.orange,
      ),
    );
  }
  

  
  Future<void> _startVoiceSearch() async {
    if (!_speechEnabled) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Speech recognition not available')),
      );
      return;
    }
    
    setState(() {
      _isListening = true;
    });
    
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => AlertDialog(
        title: Text('🎤 Listening...'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            CircularProgressIndicator(),
            SizedBox(height: 16),
            Text('Say something like:'),
            Text('"Find articles about Boston"', style: TextStyle(fontSize: 12, fontStyle: FontStyle.italic)),
            Text('"Show me podcast articles"', style: TextStyle(fontSize: 12, fontStyle: FontStyle.italic)),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              _stopListening();
              Navigator.pop(context);
            },
            child: Text('Cancel'),
          ),
        ],
      ),
    );
    
    await _speechToText.listen(
      onResult: (result) {
        if (result.finalResult) {
          Navigator.pop(context);
          _handleVoiceSearchCommand(result.recognizedWords);
        }
      },
      listenFor: Duration(seconds: 10),
    );
  }
  
  void _stopListening() {
    _speechToText.stop();
    setState(() {
      _isListening = false;
    });
  }
  
  Future<void> _playArticle(int index) async {
    final article = _filteredNews[index];
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('current_article_id', article['title']);
    await prefs.setString('current_article_path', article['path']);
    await prefs.setInt('current_filtered_article_index', index);
    
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => NewsPlayerScreen(
          articlePath: article['path'],
          articleTitle: article['title'],
        ),
      ),
    );
  }
  
  Future<void> _loadAppMode() async {
    final prefs = await SharedPreferences.getInstance();
    final mode = prefs.getString('app_mode') ?? 'Tours';
    final savedFilter = prefs.getString('listen_page_filter') ?? 'All';
    setState(() {
      _appMode = mode;
      _selectedTypeFilter = savedFilter;
    });
    
    if (_appMode == 'Audio') {
      _loadNews();
    } else {
      _loadTours();
    }
  }
  
  Future<void> _loadNews() async {
    final prefs = await SharedPreferences.getInstance();
    final news = prefs.getStringList('saved_news') ?? [];
    
    await DebugLogHelper.addDebugLog('LISTEN: Loading ${news.length} articles from storage');
    
    // Convert articles without duplicate removal - keep all language variants
    final articles = <Map<String, dynamic>>[];
    for (final articleJson in news) {
      try {
        final article = jsonDecode(articleJson) as Map<String, dynamic>;
        articles.add(article);
      } catch (e) {
        await DebugLogHelper.addDebugLog('LISTEN: Error parsing article: $e');
      }
    }
    
    await DebugLogHelper.addDebugLog('LISTEN: Successfully loaded ${articles.length} articles (all languages)');
    
    setState(() {
      _news = articles.reversed.toList();
    });
    
    // Pre-load all display titles to avoid async operations during scroll
    await _preloadDisplayTitles();
    
    // Always apply filter to ensure _filteredNews is properly populated
    await _applyNewsFilter();
  }
  
  void _toggleSelectionMode() {
    setState(() {
      _isSelectionMode = !_isSelectionMode;
      if (!_isSelectionMode) {
        _selectedArticles = List.filled(_filteredNews.length, false);
      }
    });
  }
  
  void _selectAll() {
    setState(() {
      _selectedArticles = List.filled(_filteredNews.length, true);
    });
  }
  
  Future<void> _deleteSelectedArticles() async {
    final selectedIndices = <int>[];
    for (int i = 0; i < _selectedArticles.length; i++) {
      if (_selectedArticles[i]) {
        selectedIndices.add(i);
      }
    }
    
    if (selectedIndices.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('No articles selected')),
      );
      return;
    }
    
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('Delete Articles'),
        content: Text('Delete ${selectedIndices.length} selected articles?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      final prefs = await SharedPreferences.getInstance();
      final savedNews = prefs.getStringList('saved_news') ?? [];
      
      // Delete from newest to oldest to maintain indices
      selectedIndices.sort((a, b) => b.compareTo(a));
      
      // Collect article IDs to delete
      final articlesToDelete = <String>[];
      for (final index in selectedIndices) {
        final article = _filteredNews[index];
        final articleId = article['article_id'];
        if (articleId != null) {
          articlesToDelete.add(articleId);
        }
      }
      
      // Delete files and remove from saved_news by article_id
      for (int i = savedNews.length - 1; i >= 0; i--) {
        try {
          final article = jsonDecode(savedNews[i]) as Map<String, dynamic>;
          final articleId = article['article_id'];
          
          if (articlesToDelete.contains(articleId)) {
            // Delete files
            try {
              final articleDir = Directory(article['path']);
              if (await articleDir.exists()) {
                await articleDir.delete(recursive: true);
              }
            } catch (e) {
              print('Error deleting article files: $e');
            }
            
            // Remove from saved_news
            savedNews.removeAt(i);
          }
        } catch (e) {
          print('Error processing article for deletion: $e');
        }
      }
      
      await prefs.setStringList('saved_news', savedNews);
      
      // Reload news and reapply filters
      await _loadNews();
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Deleted ${selectedIndices.length} articles'),
          backgroundColor: Colors.red,
        ),
      );
      
      setState(() {
        _isSelectionMode = false;
      });
      
      // Add debug log
      await DebugLogHelper.addDebugLog('LISTEN: Bulk deleted ${selectedIndices.length} articles');
    }
  }
  
  Future<void> _applyNewsFilter() async {
    var filtered = _news;
    
    // Apply type filter
    if (_selectedTypeFilter != 'All') {
      filtered = filtered.where((article) {
        final articleType = article['article_type'] ?? 'Others';
        return articleType == _selectedTypeFilter;
      }).toList();
      await DebugLogHelper.addDebugLog('LISTEN: Filtered by type "$_selectedTypeFilter" - ${filtered.length} articles');
    }
    
    // Apply search filter
    if (_searchQuery.isNotEmpty) {
      final searchTerms = _parseSearchQuery(_searchQuery);
      final searchFiltered = <Map<String, dynamic>>[];
      
      for (final article in filtered) {
        if (await _matchesSearchQuery(article, searchTerms)) {
          searchFiltered.add(article);
        }
      }
      
      filtered = searchFiltered;
    }
    
    setState(() {
      _filteredNews = filtered;
      // Initialize selection array
      _selectedArticles = List.filled(_filteredNews.length, false);
      _isSelectionMode = false;
    });
    
    // Save filter state for persistence
    _saveFilterState();
  }
  
  Future<void> _saveFilterState() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('listen_page_filter', _selectedTypeFilter);
    
    // Save filtered articles for voice navigation
    final filteredArticleIds = _filteredNews.map((article) => (article['article_id'] ?? '') as String).toList();
    await prefs.setStringList('filtered_article_ids', filteredArticleIds);
  }
  
  Map<String, List<String>> _parseSearchQuery(String query) {
    final includeTerms = <String>[];
    final excludeTerms = <String>[];
    final includePhrases = <String>[];
    final excludePhrases = <String>[];
    
    if (query.trim().isEmpty) {
      return {
        'includeTerms': includeTerms,
        'excludeTerms': excludeTerms,
        'includePhrases': includePhrases,
        'excludePhrases': excludePhrases,
      };
    }
    
    final regex = RegExp(r'(-?"[^"]*"|-?\S+)');
    final matches = regex.allMatches(query);
    
    for (final match in matches) {
      String term = match.group(0)!;
      bool isExclude = term.startsWith('-');
      
      if (isExclude) {
        term = term.substring(1);
      }
      
      if (term.startsWith('"') && term.endsWith('"')) {
        // Quoted phrase
        final phrase = term.substring(1, term.length - 1).toLowerCase();
        if (isExclude) {
          excludePhrases.add(phrase);
        } else {
          includePhrases.add(phrase);
        }
      } else {
        // Single term
        final cleanTerm = term.toLowerCase();
        if (isExclude) {
          excludeTerms.add(cleanTerm);
        } else {
          includeTerms.add(cleanTerm);
        }
      }
    }
    
    return {
      'includeTerms': includeTerms,
      'excludeTerms': excludeTerms,
      'includePhrases': includePhrases,
      'excludePhrases': excludePhrases,
    };
  }
  
  Future<String> _convertVoiceToSearch(String voiceCommand) async {
    await DebugLogHelper.addDebugLog('VOICE: Attempting AI conversion for "$voiceCommand"');
    
    try {
      // Gate off in cloud mode — voice AI service not deployed to cloud yet
      final prefs = await SharedPreferences.getInstance();
      if ((prefs.getString('server_mode') ?? 'local') == 'cloud') {
        await DebugLogHelper.addDebugLog('VOICE: AI voice search not available in cloud mode — using pattern fallback');
        return voiceCommand; // Fall through to local pattern matching
      }

      final stopwatch = Stopwatch()..start();
      final response = await http.post(
        await Endpoints.url(Service.voice, '/parse_voice_search'),
        headers: await Endpoints.apiHeaders(Service.voice),
        body: json.encode({'voice_command': voiceCommand}),
      ).timeout(Duration(seconds: 3));
      
      stopwatch.stop();
      await DebugLogHelper.addDebugLog('VOICE: AI service responded in ${stopwatch.elapsedMilliseconds}ms with status ${response.statusCode}');
      
      if (response.statusCode == 200) {
        final data = json.decode(response.body);
        final aiResult = data['search_pattern'] ?? voiceCommand;
        await DebugLogHelper.addDebugLog('VOICE: AI SUCCESS - "$voiceCommand" → "$aiResult"');
        return aiResult;
      } else {
        await DebugLogHelper.addDebugLog('VOICE: AI HTTP ERROR ${response.statusCode}: ${response.body}');
      }
    } catch (e) {
      if (e.toString().contains('TimeoutException')) {
        await DebugLogHelper.addDebugLog('VOICE: AI TIMEOUT after 3 seconds - using pattern fallback');
      } else if (e.toString().contains('SocketException')) {
        await DebugLogHelper.addDebugLog('VOICE: AI CONNECTION FAILED (no internet/service down) - using pattern fallback');
      } else {
        await DebugLogHelper.addDebugLog('VOICE: AI ERROR: $e - using pattern fallback');
      }
    }
    
    // Fallback pattern matching
    final fallbackResult = _fallbackVoiceConversion(voiceCommand);
    await DebugLogHelper.addDebugLog('VOICE: PATTERN FALLBACK - "$voiceCommand" → "$fallbackResult"');
    return fallbackResult;
  }
  
  String _fallbackVoiceConversion(String voiceCommand) {
    final command = voiceCommand.toLowerCase();
    
    // Extract main search terms
    String searchTerms = '';
    
    // Pattern 1: Various ways to express search intent
    final patterns = [
      r'(?:articles?\s+about|find\s+articles?\s+about|show\s+me\s+articles?\s+about)\s+([^,]+?)(?:\s+but|\s+without|\$)',
      r'(?:articles?\s+mentioned?|articles?\s+mentioning)\s+([^,]+?)(?:\s+but|\s+without|\$)',
      r'(?:find|show\s+me|search\s+for)\s+([^,]+?)(?:\s+articles?|\s+but|\s+without|\$)',
      r'(?:about|with|containing|mentioned?|mentioning)\s+([^,]+?)(?:\s+but|\s+without|\$)'
    ];
    
    for (final pattern in patterns) {
      final match = RegExp(pattern).firstMatch(command);
      if (match != null) {
        searchTerms = match.group(1)!.trim();
        break;
      }
    }
    
    // If no pattern matched, extract key words
    if (searchTerms.isEmpty) {
      // Remove common words and extract meaningful terms
      final words = command.split(' ');
      final stopWords = {
        'the', 'a', 'an', 'me', 'i', 'you', 'it', 'they', 'them', 'their', 'this', 'that', 'these', 'those',
        'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by', 'from', 'up', 'down',
        'find', 'search', 'look', 'show', 'get', 'give', 'bring', 'fetch', 'retrieve', 'locate',
        'articles', 'article', 'news', 'stories', 'story', 'posts', 'post', 'content', 'items', 'item',
        'having', 'containing', 'about', 'regarding', 'concerning', 'related', 'mentioning', 'mentioned', 'mention',
        'discussing', 'discuss', 'covering', 'cover', 'featuring', 'feature',
        'all', 'any', 'some', 'every', 'each', 'both', 'much', 'many', 'most', 'more', 'less', 'few',
        'word', 'words', 'term', 'terms', 'topic', 'topics', 'subject', 'subjects', 'thing', 'things'
      };
      final meaningfulWords = words.where((word) => !stopWords.contains(word.toLowerCase())).toList();
      searchTerms = meaningfulWords.join(' ');
    }
    
    // Handle plurals - remove 's' from end
    searchTerms = searchTerms.replaceAllMapped(RegExp(r'\b(\w+)s\b'), (match) {
      final word = match.group(1)!;
      return word.length > 3 ? word : match.group(0)!; // Only remove 's' from longer words
    });
    
    // Handle exclusions
    if (command.contains('but not') || command.contains('without')) {
      final excludeMatch = RegExp(r'(?:but\s+not|without)\s+([^,]+?)(?:\s+and|\$)').firstMatch(command);
      if (excludeMatch != null) {
        searchTerms += ' -${excludeMatch.group(1)!.trim()}';
      }
    }
    
    return searchTerms.isNotEmpty ? searchTerms : voiceCommand;
  }
  
  Future<bool> _matchesSearchQuery(Map<String, dynamic> article, Map<String, List<String>> searchTerms) async {
    if (searchTerms['includeTerms']!.isEmpty && 
        searchTerms['excludeTerms']!.isEmpty &&
        searchTerms['includePhrases']!.isEmpty && 
        searchTerms['excludePhrases']!.isEmpty) {
      return true;
    }
    
    try {
      // Read article content from text file
      final articlePath = article['path'];
      final textFile = File('$articlePath/audiotours_search_content.txt');
      
      if (!await textFile.exists()) {
        // Fallback to title search if no text file
        final title = (article['title'] ?? '').toLowerCase();
        final contentLower = title;
        
        // Apply search logic to title only
        for (final term in searchTerms['includeTerms']!) {
          if (!contentLower.contains(term)) return false;
        }
        for (final phrase in searchTerms['includePhrases']!) {
          if (!contentLower.contains(phrase)) return false;
        }
        for (final term in searchTerms['excludeTerms']!) {
          if (contentLower.contains(term)) return false;
        }
        for (final phrase in searchTerms['excludePhrases']!) {
          if (contentLower.contains(phrase)) return false;
        }
        return true;
      }
      
      final content = await textFile.readAsString();
      final contentLower = content.toLowerCase();
      
      // Check include terms (all must be present)
      for (final term in searchTerms['includeTerms']!) {
        if (!contentLower.contains(term)) {
          return false;
        }
      }
      
      // Check include phrases (all must be present)
      for (final phrase in searchTerms['includePhrases']!) {
        if (!contentLower.contains(phrase)) {
          return false;
        }
      }
      
      // Check exclude terms (none must be present)
      for (final term in searchTerms['excludeTerms']!) {
        if (contentLower.contains(term)) {
          return false;
        }
      }
      
      // Check exclude phrases (none must be present)
      for (final phrase in searchTerms['excludePhrases']!) {
        if (contentLower.contains(phrase)) {
          return false;
        }
      }
      
      return true;
    } catch (e) {
      return false;
    }
  }

  Future<void> _loadTours() async {
    final prefs = await SharedPreferences.getInstance();
    final tours = prefs.getStringList('saved_tours') ?? [];

    await DebugLogHelper.addDebugLog('LISTEN: Loading ${tours.length} tours from storage');

    final parsed = <Map<String, dynamic>>[];
    for (final tourJson in tours) {
      try {
        final tour = jsonDecode(tourJson) as Map<String, dynamic>;
        if (tour['title'] is! String || tour['path'] is! String || tour['created'] is! String) {
          await DebugLogHelper.addDebugLog('LISTEN: Skipping tour with invalid field types: ${tour.keys.toList()}');
          continue;
        }
        parsed.add(tour);
      } catch (e) {
        await DebugLogHelper.addDebugLog('LISTEN: Skipping corrupt tour entry: $e');
      }
    }

    await DebugLogHelper.addDebugLog('LISTEN: Loaded ${parsed.length} valid tours (${tours.length - parsed.length} skipped)');

    if (parsed.length != tours.length) {
      await prefs.setStringList('saved_tours', parsed.map((t) => json.encode(t)).toList());
      await DebugLogHelper.addDebugLog('LISTEN: Pruned ${tours.length - parsed.length} corrupt entries from saved_tours');
    }

    await _healTourPaths();

    final healedList = prefs.getStringList('saved_tours') ?? [];
    final healedParsed = <Map<String, dynamic>>[];
    for (final t in healedList) {
      try { healedParsed.add(Map<String, dynamic>.from(json.decode(t) as Map)); } catch (_) {}
    }
    setState(() { _tours = healedParsed.reversed.toList(); });

    // [LOCAL-716] If we arrived here from a download's "View" button for a
    // single tour, open that tour now that the list is loaded.
    _consumePendingListenOpen();

    final tourInfoList = _tours.map((tour) => '${tour['title']}|${tour['path']}').toList();
    await prefs.setStringList('available_tours', tourInfoList);
    unawaited(_detectMapTours());
  }

  Future<void> _healTourPaths() async {
    final docsDir = (await getApplicationDocumentsDirectory()).path;
    final prefs = await SharedPreferences.getInstance();
    final savedRaw = prefs.getStringList('saved_tours') ?? [];
    bool anyHealed = false;
    final healedRaw = <String>[];
    for (final raw in savedRaw) {
      try {
        final tour = Map<String, dynamic>.from(json.decode(raw) as Map);
        final oldPath = tour['path'] as String? ?? '';
        // LOCAL-478: shared rule — same healing the stop editor now uses.
        final newPath = healTourPath(oldPath, docsDir);
        if (newPath != oldPath) {
          tour['path'] = newPath;
          healedRaw.add(json.encode(tour));
          anyHealed = true;
        } else {
          healedRaw.add(raw);
        }
      } catch (_) {
        healedRaw.add(raw);
      }
    }
    if (anyHealed) {
      await prefs.setStringList('saved_tours', healedRaw);
      await DebugLogHelper.addDebugLog('LISTEN: Healed stale container paths in saved_tours');
    }
  }

  Future<void> _detectMapTours() async {
    final results = <int, bool>{};
    for (int i = 0; i < _tours.length; i++) {
      final path = _tours[i]['path'] as String? ?? '';
      final file = File('$path/audio_1.txt');
      bool hasCoords = false;
      try {
        if (await file.exists()) {
          final content = await file.readAsString();
          hasCoords = RegExp(r'Coordinates:\s*[-\d.]+\s*,\s*[-\d.]+').hasMatch(content);
        }
      } catch (_) {}
      results[i] = hasCoords;
    }
    if (mounted) setState(() => _tourHasMap = results);
  }
  
  Future<void> _deleteNews(int index) async {
    final article = _filteredNews[index];  // Use filtered list
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Article'),
        content: Text('Delete "${article['title']}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      final prefs = await SharedPreferences.getInstance();
      final savedNews = prefs.getStringList('saved_news') ?? [];
      final articleId = article['article_id'];
      
      // Delete files and remove from saved_news by article_id
      for (int i = savedNews.length - 1; i >= 0; i--) {
        try {
          final savedArticle = jsonDecode(savedNews[i]) as Map<String, dynamic>;
          if (savedArticle['article_id'] == articleId) {
            // Delete files
            try {
              final articleDir = Directory(article['path']);
              if (await articleDir.exists()) {
                await articleDir.delete(recursive: true);
              }
            } catch (e) {
              print('Error deleting article files: $e');
            }
            
            // Remove from saved_news
            savedNews.removeAt(i);
            break;
          }
        } catch (e) {
          print('Error processing article for deletion: $e');
        }
      }
      
      await prefs.setStringList('saved_news', savedNews);
      
      // Reload news and reapply filters
      await _loadNews();
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Deleted "${article['title']}"'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }
  
  Future<void> _deleteTour(int index) async {
    final tour = _tours[index];
    // [LOCAL-693 / D660 + LOCAL-693B / D660 addendum] A PAID tour on the phone is
    // the listener's forever, but every download is a purchase: deleting it means
    // buying again to get it back. No warning at purchase; the one calm
    // confirmation lives HERE. A paid tour shows "Delete paid tour?" with the
    // D660-addendum sentence; a free tour shows the plain confirmation. Pure
    // decision in DeleteTourPrompt (unit-tested); paid from saved metadata.
    final prompt = DeleteTourPrompt.decide(
      tourTitle: (tour['title'] ?? 'this tour').toString(),
      isPaid: DeleteTourPrompt.isPaidTour(tour),
    );
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(prompt.title),
        content: Text(prompt.body),
        actions: [
          // Cancel is the default (listed first, no destructive styling).
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(prompt.cancelLabel),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(prompt.confirmLabel,
                style: const TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      // First update the UI immediately
      setState(() {
        _tours.removeAt(index);
      });
      
      // Then update SharedPreferences
      final prefs = await SharedPreferences.getInstance();
      // [D675 §6] A deleted tour is never auto-downloaded again.
      await recordDeletedTours(prefs, [Map<String, dynamic>.from(tour)]);
      final tours = prefs.getStringList('saved_tours') ?? [];
      
      // Make sure we're removing the correct tour from the list
      // since the list is reversed in _loadTours
      final reversedIndex = tours.length - 1 - index;
      if (reversedIndex >= 0 && reversedIndex < tours.length) {
        tours.removeAt(reversedIndex);
        await prefs.setStringList('saved_tours', tours);
        
        // Update available tours list for voice navigation
        final tourInfoList = tours.map((tourJson) {
          final tour = jsonDecode(tourJson) as Map<String, dynamic>;
          return '${tour['title']}|${tour['path']}';
        }).toList();
        await prefs.setStringList('available_tours', tourInfoList);
      }
      
      // Delete tour files
      try {
        final tourDir = Directory(tour['path']);
        if (await tourDir.exists()) {
          await tourDir.delete(recursive: true);
        }
      } catch (e) {
        print('Error deleting tour files: $e');
      }
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Deleted "${tour['title']}"'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  /// [LOCAL-670] Rate a downloaded tour 1–10 from its ⋮ menu. The rating keys on
  /// the numeric tour_id; a tour with no numeric id (local-only) can't be rated,
  /// so we tell the user rather than silently failing.
  Future<void> _showRateDialog(Map<String, dynamic> tour) async {
    final tourId = _numericTourId(tour);
    if (tourId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('This tour cannot be rated yet (no numeric tour ID).'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    final result = await showRateTourDialog(
      context,
      tourId: tourId.toString(),
      tourTitle: tour['title']?.toString() ?? 'this tour',
    );
    if (result != null && mounted) {
      final agg = result.aggregate;
      final msg = agg != null
          ? 'Thanks! Tour rating now ${agg.badgeText}.'
          : 'Thanks! ${result.myRatingText}.';
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(msg)),
      );
    }
  }

  Future<void> _showTranslateDialog(Map<String, dynamic> tour) async {
    final tourId = _numericTourId(tour) ?? tour['tour_id'];
    if (tourId == null || tourId.toString().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('This tour cannot be translated (no tour ID).'), backgroundColor: Colors.orange),
      );
      return;
    }

    // Parse tour_id to int (translation service requires numeric ID)
    final numericId = int.tryParse(tourId.toString());
    if (numericId == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('This tour uses a non-numeric ID and cannot be translated yet.'), backgroundColor: Colors.orange),
      );
      return;
    }

    final availableLanguages = TourTranslationHelper.availableLanguages;

    final selected = <String>{};

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) => AlertDialog(
          title: const Text('Translate Tour'),
          content: SizedBox(
            width: double.maxFinite,
            child: Column(
              mainAxisSize: MainAxisSize.min,
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Select languages for: ${tour['title']}', style: const TextStyle(fontSize: 13)),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  runSpacing: 4,
                  children: availableLanguages.entries.map((entry) => FilterChip(
                    label: Text(entry.value),
                    selected: selected.contains(entry.key),
                    onSelected: (val) => setDialogState(() {
                      if (val) { selected.add(entry.key); } else { selected.remove(entry.key); }
                    }),
                  )).toList(),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(context).pop(false),
              child: const Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: selected.isEmpty ? null : () => Navigator.of(context).pop(true),
              child: const Text('Translate'),
            ),
          ],
        ),
      ),
    );

    if (confirmed != true || selected.isEmpty) return;

    // Show progress
    if (mounted) {
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => const AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Expanded(child: Text('Translating tour...')),
            ],
          ),
        ),
      );
    }

    final parentEditTourId = tour['edit_tour_id']?.toString() ?? tourId.toString();
    final failures = await TourTranslationHelper.downloadTranslatedVersions(
      tourId: numericId,
      languages: selected.toList(),
      parentEditTourId: parentEditTourId,
    );

    if (mounted) Navigator.of(context).pop(); // dismiss progress

    if (mounted) {
      if (failures.isEmpty) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Translated to ${selected.length} language(s) successfully!'), backgroundColor: Colors.green),
        );
      } else {
        final failedNames = failures.map((code) => TourTranslationHelper.availableLanguages[code] ?? code).join(', ');
        showDialog(
          context: context,
          builder: (context) => AlertDialog(
            title: const Text('Translation Not Available'),
            content: Text('$failedNames wasn\'t available for this older tour, so the English version was saved.'),
            actions: [
              TextButton(onPressed: () => Navigator.of(context).pop(), child: const Text('OK')),
            ],
          ),
        );
      }
      _loadTours(); // refresh list to show new translated entries
    }
  }
  
  Future<void> _reportTour(Map<String, dynamic> tour) async {
    final tourTitle = tour['title'] ?? 'Unknown Tour';
    final tourId = tour['tour_id'] ?? 'unknown';
    
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Report This Tour'),
        content: Text(
          'Report "$tourTitle" as objectionable content?\n\n'
          'This sends the report to our review team in the app.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(true),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.orange,
              foregroundColor: Colors.white,
            ),
            child: const Text('Report'),
          ),
        ],
      ),
    );

    if (confirmed != true) return;

    // [LOCAL-724 item 5] Send the report to the server (one row per report in
    // tour_reports via map-delivery POST /report-tour). On any failure, fall
    // back to the old mailto: so a report is never simply lost.
    final numericId = _numericTourId(tour) ?? tour['tour_id'];
    try {
      final reportUri = await Endpoints.url(Service.mapDelivery, '/report-tour');
      final resp = await http
          .post(
            reportUri,
            headers: {
              'Content-Type': 'application/json',
              ...await Endpoints.apiHeaders(Service.mapDelivery),
            },
            body: jsonEncode({
              'tour_id': numericId,
              'tour_name': tourTitle,
            }),
          )
          .timeout(const Duration(seconds: 15));
      if (resp.statusCode == 201 || resp.statusCode == 200) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Thanks — your report was sent to our review team.'),
              backgroundColor: Colors.green,
            ),
          );
        }
        return;
      }
      // Non-2xx: fall through to the mailto fallback below.
    } catch (_) {
      // Network/offline: fall through to the mailto fallback below.
    }

    // Fallback: open an email (the pre-LOCAL-724 behaviour).
    final subject = Uri.encodeComponent('Content Report: $tourTitle');
    final body = Uri.encodeComponent(
      'I would like to report the following tour content:\n\n'
      'Tour: $tourTitle\n'
      'Tour ID: $tourId\n\n'
      'Reason for report:\n[Please describe the issue]\n\n'
      '---\nSent from Audioura App',
    );
    final mailtoUri = Uri.parse('mailto:info@audioura.com?subject=$subject&body=$body');

    try {
      if (await canLaunchUrl(mailtoUri)) {
        await launchUrl(mailtoUri);
      } else {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('Could not open email client. Please email info@audioura.com directly.'), backgroundColor: Colors.orange),
          );
        }
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Error: $e'), backgroundColor: Colors.red),
        );
      }
    }
  }

  /// [LOCAL-579] Share this tour by code. Resolves the tour's numeric id and
  /// delegates to the shared flow (progress → POST /tour/share → result sheet
  /// with the 8-char code, Copy, and OS Share…). The share service rejects
  /// non-numeric ids and surfaces server/offline errors as a SnackBar.
  void _shareTour(Map<String, dynamic> tour) {
    final title = (tour['title'] ?? 'this tour').toString();
    // [LOCAL-710 / D672] Hand the sharing flow what the tour record holds: the
    // downloaded tour's path (first stop's name + address), the stored stop
    // count, the paid snapshot (price_tier / price_label) and a community name.
    final rawStops = tour['stops']?.toString().trim();
    final stopCount = (rawStops != null && rawStops.isNotEmpty)
        ? int.tryParse(rawStops)
        : null;
    final priceTier = tour['price_tier'];
    final isPaid = tour['is_paid'] == true || priceTier != null;
    final price = tour['price_label']?.toString();
    final communityName = tour['community_name']?.toString();
    // [LOCAL-711 / D673] The server-written short title, when the tour record
    // carries one (map-delivery now returns it; the downloaded tour stores it).
    // Empty/absent => the sharing flow falls back to shortTourTitle(title).
    final serverShortTitle = tour['short_title']?.toString();
    shareTour(
      context,
      audioTourId: _numericTourId(tour) ?? tour['tour_id'],
      tourName: title,
      tourPath: tour['path']?.toString(),
      stopCount: stopCount,
      isPaid: isPaid,
      price: (isPaid && price != null && price != 'Free') ? price : null,
      communityName:
          (communityName != null && communityName.trim().isNotEmpty)
              ? communityName
              : null,
      shortTitle: serverShortTitle,
    );
  }

  void _editTour(Map<String, dynamic> tour) {
    Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => EditTourScreen(
          tourData: tour,
        ),
      ),
    ).then((_) {
      // Reload tours when returning from edit screen
      _loadTours();
    });
  }
  
  Future<void> _deleteAllTours() async {
    // [LOCAL-740 / B3] The "delete all" path must carry the paid-tour warning
    // too — before, it showed a plain "Delete all N tours?" with no mention of
    // re-purchase even when the batch held tours the listener paid for. The
    // pure decision lives in DeleteTourPrompt (unit-tested).
    final prompt = DeleteTourPrompt.decideDeleteAll(
      tours: _tours.map((t) => Map<String, dynamic>.from(t)).toList(),
    );
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: Text(prompt.title),
        content: Text(prompt.body),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: Text(prompt.cancelLabel),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: Text(prompt.confirmLabel,
                style: const TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      final prefs = await SharedPreferences.getInstance();
      // [D675 §6] Remember every deleted tour so the community sync skips them.
      await recordDeletedTours(prefs, _tours.map((t) => Map<String, dynamic>.from(t)));
      await prefs.remove('saved_tours');
      await prefs.remove('available_tours'); // Clear voice navigation list too
      
      // Delete all tour files
      for (final tour in _tours) {
        try {
          final tourDir = Directory(tour['path']);
          if (await tourDir.exists()) {
            await tourDir.delete(recursive: true);
          }
        } catch (e) {
          print('Error deleting tour files: $e');
        }
      }
      
      _loadTours();
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('All tours deleted'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    if (_appMode == 'Audio') {
      return _buildNewsView();
    } else {
      return _buildToursView();
    }
  }
  
  Widget _buildNewsView() {
    return Scaffold(
      appBar: AppBar(
        title: Text(_isSelectionMode 
          ? '${_selectedArticles.where((s) => s).length} selected'
          : _buildAppBarTitle()),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: _isSelectionMode ? [
          IconButton(
            icon: Icon(Icons.select_all),
            onPressed: _selectAll,
            tooltip: 'Select All',
          ),
          IconButton(
            icon: Icon(Icons.delete),
            onPressed: _deleteSelectedArticles,
            tooltip: 'Delete Selected',
          ),
          IconButton(
            icon: Icon(Icons.close),
            onPressed: _toggleSelectionMode,
            tooltip: 'Cancel',
          ),
        ] : [
          IconButton(
            icon: Icon(Icons.search),
            onPressed: () {
              showDialog(
                context: context,
                builder: (context) => AlertDialog(
                  title: Text('Search Articles'),
                  content: Column(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      TextField(
                        controller: _searchController,
                        decoration: InputDecoration(
                          hintText: 'microsoft profit -future',
                          helperText: 'Include: terms, Exclude: -terms, Phrases: "exact phrase"',
                        ),
                        autofocus: true,
                      ),
                    ],
                  ),
                  actions: [
                    TextButton(
                      onPressed: () {
                        _searchController.clear();
                        setState(() {
                          _searchQuery = '';
                        });
                        _applyNewsFilter();
                        Navigator.pop(context);
                      },
                      child: Text('Clear'),
                    ),
                    ElevatedButton(
                      onPressed: () {
                        setState(() {
                          _searchQuery = _searchController.text;
                        });
                        _applyNewsFilter();
                        Navigator.pop(context);
                      },
                      child: Text('Search'),
                    ),
                  ],
                ),
              );
            },
          ),
          PopupMenuButton<String>(
            icon: Icon(Icons.filter_list),
            onSelected: (String value) {
              setState(() {
                _selectedTypeFilter = value;
              });
              _applyNewsFilter();
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
            icon: Icon(_isListening ? Icons.mic_off : Icons.mic),
            onPressed: _isListening ? _stopListening : _startVoiceSearch,
            tooltip: _isListening ? 'Stop Listening' : 'Voice Search',
          ),
          IconButton(
            icon: Icon(Icons.help_outline),
            onPressed: () {
              showDialog(
                context: context,
                builder: (context) => AlertDialog(
                  title: Text('🎤 Voice Commands Help'),
                  content: Column(
                    mainAxisSize: MainAxisSize.min,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text('Voice Search Examples:', style: TextStyle(fontWeight: FontWeight.bold)),
                      SizedBox(height: 8),
                      Text('• "Find articles about Boston"'),
                      Text('• "Show me podcast articles"'),
                      Text('• "Articles mentioning Microsoft"'),
                      Text('• "Technology articles but not Apple"'),
                      SizedBox(height: 12),
                      Text('Search Tips:', style: TextStyle(fontWeight: FontWeight.bold)),
                      SizedBox(height: 8),
                      Text('• Include terms: "profit growth"'),
                      Text('• Exclude terms: "profit -loss"'),
                      Text('• Exact phrases: ""artificial intelligence""'),
                    ],
                  ),
                  actions: [
                    TextButton(
                      onPressed: () => Navigator.pop(context),
                      child: Text('Got it'),
                    ),
                  ],
                ),
              );
            },
            tooltip: 'Voice Commands Help',
          ),
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: () => _manualRefresh(),
            tooltip: 'Refresh',
          ),
          if (_filteredNews.isNotEmpty)
            IconButton(
              icon: Icon(Icons.checklist),
              onPressed: _toggleSelectionMode,
              tooltip: 'Select Articles',
            ),
        ],
      ),
      body: _filteredNews.isEmpty
          ? Center(
              child: Text(
                _news.isEmpty 
                  ? 'No articles have been processed for audio edition.\nPlease generate News first.'
                  : 'No articles found for "$_selectedTypeFilter" category.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, color: Colors.grey),
              ),
            )
          : ListView.builder(
              // controller: _scrollController, // Disabled - not essential
              itemCount: _filteredNews.length,
              itemBuilder: (context, index) {
                final article = _filteredNews[index];
                final articleType = article['article_type'] ?? 'Others';
                final isCurrentlyVisible = index == _currentVisibleIndex;
                
                return Card(
                  margin: const EdgeInsets.all(8),
                  // color: isCurrentlyVisible ? Colors.yellow.shade100 : null, // Disabled - not essential
                  child: ListTile(
                    leading: _isSelectionMode ? Checkbox(
                      value: _selectedArticles[index],
                      onChanged: (bool? value) {
                        setState(() {
                          _selectedArticles[index] = value ?? false;
                        });
                      },
                    ) : Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        Icon(Icons.article, color: Color(0xFF3498db)),
                        Container(
                          padding: EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                          decoration: BoxDecoration(
                            color: _getTypeColor(articleType),
                            borderRadius: BorderRadius.circular(8),
                          ),
                          child: Text(
                            _getTypeAbbreviation(articleType),
                            style: TextStyle(
                              color: Colors.white,
                              fontSize: 8,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ],
                    ),
                    title: Text(_displayTitles[article['article_id']] ?? article['title']),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('$articleType • Created: ${DateTime.parse(article['created']).toLocal().toString().split(' ')[0]}'),
                        if (article['original_request'] != null && article['original_request'] != article['title'])
                          Text(
                            'Original: ${article['original_request']}',
                            style: const TextStyle(fontSize: 12, color: Colors.grey),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                      ],
                    ),
                    trailing: _isSelectionMode ? null : Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.delete, color: Colors.red),
                          onPressed: () => _deleteNews(index),
                        ),
                        const Icon(Icons.play_arrow, color: Color(0xFF3498db)),
                      ],
                    ),
                    onTap: () async {
                      if (_isSelectionMode) {
                        setState(() {
                          _selectedArticles[index] = !_selectedArticles[index];
                        });
                      } else {
                        final prefs = await SharedPreferences.getInstance();
                        await prefs.setString('current_article_id', article['title']);
                        await prefs.setString('current_article_path', article['path']);
                        
                        // Save current article index in filtered list for voice navigation
                        await prefs.setInt('current_filtered_article_index', index);
                        
                        Navigator.push(
                          context,
                          MaterialPageRoute(
                            builder: (context) => NewsPlayerScreen(
                              articlePath: article['path'],
                              articleTitle: article['title'],
                            ),
                          ),
                        );
                      }
                    },
                  ),
                );
              },
            ),
    );
  }
  
  Widget _buildToursView() {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🎵 Listen'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          // [LOCAL-690] Joined communities live beside My tours in the Listen
          // tab; each carries its origin (the community + organiser).
          IconButton(
            icon: const Icon(Icons.groups),
            tooltip: 'My communities',
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const MyCommunitiesScreen()),
              );
            },
          ),
          if (_tours.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.delete_sweep),
              onPressed: _deleteAllTours,
            ),
        ],
      ),
      body: _tours.isEmpty
          ? const Center(
              child: Text(
                'No tours yet.\nGenerate your first tour!',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, color: Colors.grey),
              ),
            )
          : ListView.builder(
              controller: _scrollController,
              itemCount: _tours.length,
              itemBuilder: (context, index) {
                final tour = _tours[index];
                // [LOCAL-716B] A freshly-downloaded tour flashes briefly after
                // "View" (the highlight path). The colour clears itself after
                // ~2s via _highlightTimer.
                final bool highlighted = _highlightIndex == index;

                return Card(
                  margin: const EdgeInsets.all(8),
                  color: highlighted ? Colors.amber.shade100 : null,
                  shape: highlighted
                      ? RoundedRectangleBorder(
                          side: BorderSide(
                              color: Colors.amber.shade700, width: 2),
                          borderRadius: BorderRadius.circular(4),
                        )
                      : null,
                  child: ListTile(
                    leading: const Icon(Icons.tour, color: Color(0xFF3498db)),
                    title: Text(tour['title']),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(tourSubtitleLine(tour)),
                        // [LOCAL-666] Same "v{n} · updated {Mon D}" label the found-tour
                        // dialogs show (LOCAL-657), now on the My Tours list for English
                        // AND translated tours (a translation shows its source version).
                        // Only when version >= 2; defensive, so a tour saved without the
                        // fields simply shows nothing extra.
                        if (tourVersionLabel(tour) != null)
                          Text(
                            tourVersionLabel(tour)!,
                            style: TextStyle(
                              fontSize: 12,
                              color: Colors.blue.shade700,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        if (tour['original_request'] != null && tour['original_request'] != tour['title'])
                          Text(
                            'Original: ${tour['original_request']}',
                            style: const TextStyle(fontSize: 12, color: Colors.grey),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                        // [LOCAL-677] Curator-only: the tour's price + a Sales
                        // (unlocks) count. Only for a curator's sellable (numeric,
                        // non-translation) tour. Loaded lazily the first time the
                        // row builds; no money totals (that's a later task).
                        if (_canSell && !TourTranslationHelper.isTranslation(tour))
                          _buildCuratorPriceLine(tour),
                        // Track/release provenance is intentionally NOT shown as
                        // a chip here — a visible "Stable"/"Preview" label on the
                        // list confuses testers. It's available on demand via the
                        // "Version" item in the ⋮ menu instead. See wdvrdaxxmb.
                      ],
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        if (_tourHasMap[index] == true)
                          IconButton(
                            icon: const Icon(Icons.map, color: Color(0xFF27ae60), size: 20),
                            tooltip: 'View Map',
                            constraints: const BoxConstraints(minWidth: 36),
                            onPressed: () => Navigator.push(
                              context,
                              MaterialPageRoute(
                                builder: (context) => TourMapScreen(
                                  tourPath: tour['path'],
                                  tourTitle: tour['title'],
                                ),
                              ),
                            ),
                          ),
                        PopupMenuButton<String>(
                          icon: const Icon(Icons.more_vert, size: 20),
                          constraints: const BoxConstraints(minWidth: 36),
                          onSelected: (value) {
                            switch (value) {
                              case 'rate': _showRateDialog(tour); break;
                              case 'share': _shareTour(tour); break;
                              case 'translate': _showTranslateDialog(tour); break;
                              case 'edit': _editTour(tour); break;
                              case 'delete': _deleteTour(index); break;
                              case 'report': _reportTour(tour); break;
                              case 'version': _showVersionDialog(tour); break;
                              case 'price': _showPriceDialog(tour); break;
                              case 'rescore': _requestRescore(tour); break;
                            }
                          },
                          itemBuilder: (context) => [
                            const PopupMenuItem(value: 'rate', child: ListTile(leading: Icon(Icons.star_outline, color: Color(0xFFE2A400)), title: Text('Rate this tour'), dense: true)),
                            const PopupMenuItem(value: 'share', child: ListTile(leading: Icon(Icons.ios_share, color: Color(0xFF3498db)), title: Text('Share'), dense: true)),
                            if (!TourTranslationHelper.isTranslation(tour))
                              const PopupMenuItem(value: 'translate', child: ListTile(leading: Icon(Icons.translate, color: Color(0xFF8e44ad)), title: Text('Translate'), dense: true)),
                            // [LOCAL-677] Curator-only Price control (tier picker /
                            // Free). Shown only to a device with can_sell, and only
                            // for a tour with a numeric id (sellable). The server
                            // still enforces ownership.
                            if (_canSell && !TourTranslationHelper.isTranslation(tour) && _numericTourId(tour) != null)
                              const PopupMenuItem(value: 'price', child: ListTile(leading: Icon(Icons.sell, color: Color(0xFF1B6B2E)), title: Text('Price'), dense: true)),
                            const PopupMenuItem(value: 'edit', child: ListTile(leading: Icon(Icons.edit, color: Colors.orange), title: Text('Edit'), dense: true)),
                            // [LOCAL-688] One free re-score after an edit, on the
                            // guide's OWN original tour (numeric id). The server
                            // enforces ownership and the one-per-version limit.
                            if (!TourTranslationHelper.isTranslation(tour) && _numericTourId(tour) != null)
                              const PopupMenuItem(value: 'rescore', child: ListTile(leading: Icon(Icons.refresh, color: Color(0xFFE2A400)), title: Text('Request re-score'), dense: true)),
                            const PopupMenuItem(value: 'delete', child: ListTile(leading: Icon(Icons.delete, color: Colors.red), title: Text('Delete'), dense: true)),
                            const PopupMenuItem(value: 'report', child: ListTile(leading: Icon(Icons.flag_outlined, color: Colors.grey), title: Text('Report'), dense: true)),
                            const PopupMenuItem(value: 'version', child: ListTile(leading: Icon(Icons.info_outline, color: Colors.blueGrey), title: Text('Version'), dense: true)),
                          ],
                        ),
                        const Icon(Icons.play_arrow, color: Color(0xFF3498db)),
                      ],
                    ),
                    onTap: () async {
                      // Save current tour info for voice navigation
                      await _openTourPlayer(tour);
                    },
                  ),
                );
              },
            ),
    );
  }

  /// [LOCAL-716] Open a saved tour's player — the SINGLE place the Listen list
  /// opens a tour. A tap on a tour row calls it, and so does the pending-open
  /// path (a download's "View" button for one tour). Extracted verbatim from
  /// the row tap so both routes open exactly the same screen with exactly the
  /// same arguments.
  Future<void> _openTourPlayer(Map<String, dynamic> tour) async {
    // Save current tour info for voice navigation
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('current_tour_id', tour['title']);
    await prefs.setString('current_tour_path', tour['path']);
    await prefs.setInt('current_stop', 0);
    await prefs.setString('current_tour_type', tour['type'] ?? '');

    if (!mounted) return;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (context) => TourPlayerScreen(
          tourPath: tour['path'],
          tourTitle: tour['title'],
          tourId: tour['tour_id']?.toString(),
          // [LOCAL-677B] The NUMERIC server id the pricing/
          // unlock endpoints key on, stamped at download. This
          // is what the player needs to ask /unlock-state (the
          // editable tour_id above is non-numeric, which is why
          // the player never asked — the Bounce). Falls back to
          // the local snapshot inside the player when absent.
          serverTourId: tour['server_tour_id']?.toString(),
          originalLanguage: tour['original_language']?.toString(),
          track: tour['track'] as String?,
          buildNumber: tour['build_number'] is int
              ? tour['build_number'] as int
              : (tour['build_number'] is String
                  ? int.tryParse(tour['build_number'])
                  : null),
        ),
      ),
    );
  }

  /// [LOCAL-716 / LOCAL-716B / LOCAL-719 / D677 addendum 1] After the tours
  /// load, honour a pending "View" request from a download snackbar.
  ///
  /// "View" ALWAYS opens a player. The pure [planViewAfterDownload] decides
  /// WHICH from the loaded entries alone:
  ///   * it walks the offered server ids IN SELECTION ORDER and opens the FIRST
  ///     that has a saved entry — one tour for a single download, the first the
  ///     user selected (that succeeded) for a batch;
  ///   * for that tour it opens the copy in the language just downloaded (the
  ///     single translation, the listening-language translation when there are
  ///     several, or the original when there are none);
  ///   * only when NO offered id matches any saved entry (or none were offered)
  ///     does it fall back to highlighting the newest downloaded tour — and on
  ///     a miss we LOG it first (never the old silent return).
  ///
  /// The request is consumed up front so it fires at most once per load.
  void _consumePendingListenOpen() {
    final req = PendingListenOpen.instance.request.value;
    if (req == null) return;
    final wantedIds = req.tourIds;
    final language = req.language;
    // Consume up front: this request is for THIS load; a miss must not leave it
    // armed for a later unrelated rebuild.
    PendingListenOpen.instance.consume();

    // "Just show Listen" (nothing to open): highlight the newest and stop.
    if (wantedIds.isEmpty) {
      _highlightNewestTour();
      return;
    }

    final plan = planViewAfterDownload(
      entries: _tours,
      downloadedTourIds: wantedIds,
      listeningLanguage: language,
    );

    if (plan.action == ViewAfterDownloadAction.openEntry &&
        plan.entryIndex != null &&
        plan.entryIndex! >= 0 &&
        plan.entryIndex! < _tours.length) {
      final match = _tours[plan.entryIndex!];
      // Open after this frame so the list has built and a BuildContext exists.
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (mounted) _openTourPlayer(match);
      });
      return;
    }

    // No silent miss (D358): none of the offered ids matched a saved entry. Log
    // which ids missed and what we had, then fall back to the highlight path so
    // the user is never left staring at an unchanged list with nothing opened.
    unawaited(DebugLogHelper.addDebugLog(
        'LISTEN: View miss — offered ids ${wantedIds.toList()} (lang=$language) matched no '
        'saved entry among ${_tours.length} tours '
        '[${_tours.map((t) => 'tid=${t['tour_id']},sid=${t['server_tour_id']},psid=${t['parent_server_tour_id']},tr=${t['is_translation']},lang=${t['language']}').join(' | ')}]'));
    _highlightNewestTour();
  }

  /// [LOCAL-716B / D358] Scroll to and briefly highlight the NEWEST downloaded
  /// tour. `_tours` is stored newest-first (the saved list reversed, new entries
  /// appended), so the newest sits near the top — but we locate it by its
  /// `created` timestamp via [newestEntryIndex] rather than trusting position,
  /// as LOCAL-716 only CLAIMED "the first new one is at the top". The highlight
  /// clears itself after ~2s.
  void _highlightNewestTour() {
    if (_tours.isEmpty) return;
    final newest = newestEntryIndex(_tours);
    if (newest == null) return;

    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) return;
      // Scroll the newest row into view. Each Card is ~96px tall; this is an
      // estimate that lands the row on screen (exactness is not required — the
      // highlight makes it obvious which one is new).
      if (_scrollController.hasClients) {
        final target = (newest * 96.0)
            .clamp(0.0, _scrollController.position.maxScrollExtent);
        _scrollController.animateTo(
          target,
          duration: const Duration(milliseconds: 400),
          curve: Curves.easeInOut,
        );
      }
      setState(() => _highlightIndex = newest);
      _highlightTimer?.cancel();
      _highlightTimer = Timer(const Duration(seconds: 2), () {
        if (mounted) setState(() => _highlightIndex = null);
      });
    });
  }
  String _buildAppBarTitle() {
    String title = '📰 Listen';
    
    if (_selectedTypeFilter != 'All') {
      title += ' (${_selectedTypeFilter})';
    }
    
    if (_searchQuery.isNotEmpty) {
      final shortQuery = _searchQuery.length > 15 
        ? '${_searchQuery.substring(0, 15)}...' 
        : _searchQuery;
      title += ' \ud83d\udd0d "$shortQuery"';
    }
    
    return title;
  }
  
  /// Version/provenance details for a tour, shown on demand from the ⋮ menu
  /// (NOT as a chip on the list — a visible Stable/Preview label confuses
  /// testers). Shows generation date, release (track + build number when
  /// present), and services version once the tour record carries it. See
  /// wdvrdaxxmb.
  void _showVersionDialog(Map<String, dynamic> tour) {
    // Generation date
    String generated = 'Unknown';
    final created = tour['created'];
    if (created is String && created.isNotEmpty) {
      try {
        generated = DateTime.parse(created).toLocal().toString().split('.').first;
      } catch (_) {
        generated = created;
      }
    }

    // Release = track label (+ build number when the record has one).
    final track = tour['track'] as String?;
    final rawBuild = tour['build_number'];
    final buildNumber = rawBuild is int
        ? rawBuild
        : (rawBuild is String ? int.tryParse(rawBuild) : null);
    final release = Endpoints.trackLabel(track, buildNumber: buildNumber);

    // Services version — only present once the services side stores it on the
    // tour record. Absent for now; show a placeholder until then.
    final rawSvc = tour['services_version'];
    final servicesVersion =
        (rawSvc != null && rawSvc.toString().isNotEmpty) ? rawSvc.toString() : 'Not available yet';

    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Version'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _versionRow('Generated', generated),
            const SizedBox(height: 8),
            _versionRow('Release', release),
            const SizedBox(height: 8),
            _versionRow('Services version', servicesVersion),
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

  Widget _versionRow(String label, String value) {
    return Row(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        SizedBox(
          width: 120,
          child: Text(label, style: const TextStyle(fontWeight: FontWeight.w600)),
        ),
        Expanded(child: Text(value)),
      ],
    );
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
  
  Future<void> _preloadDisplayTitles() async {
    final Map<String, String> titles = {};
    
    for (final article in _news) {
      final articleId = article['article_id'] ?? '';
      if (articleId.isNotEmpty) {
        try {
          final shortTitleFile = File('${article['path']}/audiotours_short_title.txt');
          if (await shortTitleFile.exists()) {
            final shortTitle = await shortTitleFile.readAsString();
            titles[articleId] = shortTitle.trim();
          }
        } catch (e) {
          // Ignore errors and fall back to original title
        }
      }
    }
    
    setState(() {
      _displayTitles = titles;
    });
  }
  
  Future<String> _getDisplayTitle(Map<String, dynamic> article) async {
    // Keep this method for compatibility but it's no longer used in ListView
    try {
      final shortTitleFile = File('${article['path']}/audiotours_short_title.txt');
      if (await shortTitleFile.exists()) {
        final shortTitle = await shortTitleFile.readAsString();
        return shortTitle.trim();
      }
    } catch (e) {
      // Ignore errors and fall back to original title
    }
    return article['title'];
  }
  
  String _getTypeAbbreviation(String type) {
    switch (type) {
      case 'News and Politics':
        return 'POL';
      case 'Business and Investment':
        return 'BIZ';
      case 'Technology':
        return 'TECH';
      case 'Lifestyle and Entertainment':
        return 'LIFE';
      case 'Education and Learning':
        return 'EDU';
      default:
        return 'OTH';
    }
  }
}