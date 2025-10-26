import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import 'dart:io';

import 'news_player_screen.dart';

class MyNewsScreen extends StatefulWidget {
  const MyNewsScreen({super.key});

  @override
  State<MyNewsScreen> createState() => _MyNewsScreenState();
}

class _MyNewsScreenState extends State<MyNewsScreen> {
  List<Map<String, dynamic>> _news = [];

  @override
  void initState() {
    super.initState();
    _loadNews();
  }

  Future<void> _loadNews() async {
    final prefs = await SharedPreferences.getInstance();
    final news = prefs.getStringList('saved_news') ?? [];
    
    setState(() {
      _news = news.map((article) => jsonDecode(article) as Map<String, dynamic>).toList().reversed.toList();
    });
  }
  
  Future<void> _deleteNews(int index) async {
    final article = _news[index];
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
      setState(() {
        _news.removeAt(index);
      });
      
      final prefs = await SharedPreferences.getInstance();
      final news = prefs.getStringList('saved_news') ?? [];
      final reversedIndex = news.length - 1 - index;
      if (reversedIndex >= 0 && reversedIndex < news.length) {
        news.removeAt(reversedIndex);
        await prefs.setStringList('saved_news', news);
      }
      
      try {
        final articleDir = Directory(article['path']);
        if (await articleDir.exists()) {
          await articleDir.delete(recursive: true);
        }
      } catch (e) {
        print('Error deleting article files: $e');
      }
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Deleted "${article['title']}"'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('📰 My News'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _news.isEmpty
          ? const Center(
              child: Text(
                'No articles have been processed for audio edition.\nPlease generate News first.',
                textAlign: TextAlign.center,
                style: TextStyle(fontSize: 18, color: Colors.grey),
              ),
            )
          : ListView.builder(
              itemCount: _news.length,
              itemBuilder: (context, index) {
                final article = _news[index];
                
                return Card(
                  margin: const EdgeInsets.all(8),
                  child: ListTile(
                    leading: const Icon(Icons.article, color: Color(0xFF3498db)),
                    title: Text(article['title']),
                    subtitle: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text('Created: ${DateTime.parse(article['created']).toLocal().toString().split(' ')[0]}'),
                        if (article['original_request'] != null && article['original_request'] != article['title'])
                          Text(
                            'Original: ${article['original_request']}',
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
                          icon: const Icon(Icons.delete, color: Colors.red),
                          onPressed: () => _deleteNews(index),
                        ),
                        const Icon(Icons.play_arrow, color: Color(0xFF3498db)),
                      ],
                    ),
                    onTap: () async {
                      final prefs = await SharedPreferences.getInstance();
                      await prefs.setString('current_article_id', article['title']);
                      await prefs.setString('current_article_path', article['path']);
                      
                      Navigator.push(
                        context,
                        MaterialPageRoute(
                          builder: (context) => NewsPlayerScreen(
                            articlePath: article['path'],
                            articleTitle: article['title'],
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
}