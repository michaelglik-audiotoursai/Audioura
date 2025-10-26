import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:io';
import 'package:http/http.dart' as http;
import 'package:speech_to_text/speech_to_text.dart';
import 'package:permission_handler/permission_handler.dart';
import '../screens/debug_log_viewer_screen.dart';

import 'tour_player_screen.dart';
import 'news_player_screen.dart';
import 'edit_tour_screen.dart';

class MyToursScreen extends StatefulWidget {
  const MyToursScreen({super.key});

  @override
  State<MyToursScreen> createState() => _MyToursScreenState();
}

class _MyToursScreenState extends State<MyToursScreen> {
  List<Map<String, dynamic>> _tours = [];
  List<Map<String, dynamic>> _news = [];
  List<Map<String, dynamic>> _filteredNews = [];
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

  @override
  void initState() {
    super.initState();
    _loadAppMode();
    _setupVoiceCommands();
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
    
    final permission = await Permission.microphone.request();
    if (!permission.isGranted) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Microphone permission required')),
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
    
    // Convert and remove duplicates based on article_id
    final newsMap = <String, Map<String, dynamic>>{};
    for (final articleJson in news) {
      try {
        final article = jsonDecode(articleJson) as Map<String, dynamic>;
        final articleId = article['article_id'] ?? '';
        if (articleId.isNotEmpty && !newsMap.containsKey(articleId)) {
          newsMap[articleId] = article;
        }
      } catch (e) {
        print('Error parsing article: $e');
      }
    }
    
    setState(() {
      _news = newsMap.values.toList().reversed.toList();
      _applyNewsFilter();
    });
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
      final stopwatch = Stopwatch()..start();
      final response = await http.post(
        Uri.parse('http://192.168.0.217:5008/parse_voice_search'),
        headers: {'Content-Type': 'application/json'},
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
    
    setState(() {
      _tours = tours.map((tour) => jsonDecode(tour) as Map<String, dynamic>).toList().reversed.toList();
    });
    
    // Save available tours list for voice navigation
    final tourInfoList = _tours.map((tour) => '${tour['title']}|${tour['path']}').toList();
    await prefs.setStringList('available_tours', tourInfoList);
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
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete Tour'),
        content: Text('Delete "${tour['title']}"?'),
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
      // First update the UI immediately
      setState(() {
        _tours.removeAt(index);
      });
      
      // Then update SharedPreferences
      final prefs = await SharedPreferences.getInstance();
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
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete All Tours'),
        content: Text('Delete all ${_tours.length} tours? This cannot be undone.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          TextButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete All', style: TextStyle(color: Colors.red)),
          ),
        ],
      ),
    );
    
    if (confirmed == true) {
      final prefs = await SharedPreferences.getInstance();
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
          : NotificationListener<ScrollNotification>(
              onNotification: (ScrollNotification scrollInfo) {
                // Disable pull-to-refresh when scrolling up to prevent interference
                return true;
              },
              child: ListView.builder(
                itemCount: _filteredNews.length,
                itemBuilder: (context, index) {
                final article = _filteredNews[index];
                final articleType = article['article_type'] ?? 'Others';
                
                return Card(
                  margin: const EdgeInsets.all(8),
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
                    title: FutureBuilder<String>(
                      future: _getDisplayTitle(article),
                      builder: (context, snapshot) {
                        return Text(snapshot.data ?? article['title']);
                      },
                    ),
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
              itemCount: _tours.length,
              itemBuilder: (context, index) {
                final tour = _tours[index];
                
                return Card(
                  margin: const EdgeInsets.all(8),
                  child: ListTile(
                    leading: const Icon(Icons.tour, color: Color(0xFF3498db)),
                    title: Text(tour['title']),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('${tour['stops'] ?? '10'} stops • Created: ${DateTime.parse(tour['created']).toLocal().toString().split(' ')[0]}'),
                        if (tour['original_request'] != null && tour['original_request'] != tour['title'])
                          Text(
                            'Original: ${tour['original_request']}',
                            style: const TextStyle(fontSize: 12, color: Colors.grey),
                            maxLines: 1,
                            overflow: TextOverflow.ellipsis,
                          ),
                      ],
                    ),
                    trailing: Row(
                      mainAxisSize: MainAxisSize.min,
                      children: [
                        IconButton(
                          icon: const Icon(Icons.edit, color: Colors.orange),
                          onPressed: () => _editTour(tour),
                          tooltip: 'Edit Tour',
                        ),
                        IconButton(
                          icon: const Icon(Icons.delete, color: Colors.red),
                          onPressed: () => _deleteTour(index),
                        ),
                        const Icon(Icons.play_arrow, color: Color(0xFF3498db)),
                      ],
                    ),
                    onTap: () async {
                      // Save current tour info for voice navigation
                      final prefs = await SharedPreferences.getInstance();
                      await prefs.setString('current_tour_id', tour['title']);
                      await prefs.setString('current_tour_path', tour['path']);
                      await prefs.setInt('current_stop', 0);
                      
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => TourPlayerScreen(
                            tourPath: tour['path'],
                            tourTitle: tour['title'],
                          ),
                        ),
                      );
                    },
                  ),
                );
              },
            ),
    );
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
  
  Future<String> _getDisplayTitle(Map<String, dynamic> article) async {
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