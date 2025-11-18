import 'package:flutter/material.dart';
import '../services/subscription_service.dart';
import '../services/credential_storage_service.dart';
import '../services/subscription_article_storage.dart';
import 'debug_log_viewer_screen.dart';

class SubscriptionManagementScreen extends StatefulWidget {
  const SubscriptionManagementScreen({super.key});

  @override
  State<SubscriptionManagementScreen> createState() => _SubscriptionManagementScreenState();
}

class _SubscriptionManagementScreenState extends State<SubscriptionManagementScreen> {
  Map<String, dynamic> _subscriptionStats = {};
  List<String> _storedDomains = [];
  List<SubscriptionArticleMetadata> _storedArticles = [];
  bool _isLoading = true;

  @override
  void initState() {
    super.initState();
    _loadSubscriptionData();
  }

  Future<void> _loadSubscriptionData() async {
    try {
      await DebugLogHelper.addDebugLog('SUB_MGMT: Loading subscription management data');
      
      setState(() {
        _isLoading = true;
      });

      // Load subscription statistics
      final stats = await SubscriptionService.getSubscriptionStats();
      final domains = await CredentialStorageService.getStoredDomains();
      final articles = await SubscriptionArticleStorage.getAllStoredArticles();

      setState(() {
        _subscriptionStats = stats;
        _storedDomains = domains;
        _storedArticles = articles;
        _isLoading = false;
      });

      await DebugLogHelper.addDebugLog('SUB_MGMT: Loaded ${domains.length} domains and ${articles.length} articles');
    } catch (e) {
      await DebugLogHelper.addDebugLog('SUB_MGMT: Error loading subscription data: $e');
      setState(() {
        _isLoading = false;
      });
    }
  }

  Future<void> _performCleanup() async {
    try {
      await DebugLogHelper.addDebugLog('SUB_MGMT: Starting subscription cleanup');
      
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (context) => AlertDialog(
          content: Row(
            children: [
              CircularProgressIndicator(),
              SizedBox(width: 20),
              Text('Cleaning up expired articles...'),
            ],
          ),
        ),
      );

      final cleanupResults = await SubscriptionService.performCleanup();
      Navigator.pop(context);

      final expiredArticles = cleanupResults['expired_articles_removed'] ?? 0;
      
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Cleanup completed: $expiredArticles expired articles removed'),
          backgroundColor: Colors.green,
        ),
      );

      // Reload data
      await _loadSubscriptionData();
    } catch (e) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Cleanup failed: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _removeDomain(String domain) async {
    try {
      await DebugLogHelper.addDebugLog('SUB_MGMT: Removing domain: $domain');
      
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Remove Domain'),
          content: Text('Remove stored credentials for $domain?\n\nThis will also remove all locally stored articles from this domain.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
              child: Text('Remove'),
            ),
          ],
        ),
      );

      if (confirmed == true) {
        // Remove credentials
        await CredentialStorageService.removeCredentials(domain);
        
        // Remove articles from this domain
        final domainArticles = await SubscriptionArticleStorage.getArticlesByDomain(domain);
        for (final article in domainArticles) {
          await SubscriptionArticleStorage.removeArticle(article.articleId);
        }

        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('Removed credentials and articles for $domain'),
            backgroundColor: Colors.green,
          ),
        );

        // Reload data
        await _loadSubscriptionData();
      }
    } catch (e) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error removing domain: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  Future<void> _clearAllData() async {
    try {
      final confirmed = await showDialog<bool>(
        context: context,
        builder: (context) => AlertDialog(
          title: Text('Clear All Subscription Data'),
          content: Text('This will remove ALL stored credentials and subscription articles.\n\nThis action cannot be undone.'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(context, false),
              child: Text('Cancel'),
            ),
            ElevatedButton(
              onPressed: () => Navigator.pop(context, true),
              style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
              child: Text('Clear All'),
            ),
          ],
        ),
      );

      if (confirmed == true) {
        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (context) => AlertDialog(
            content: Row(
              children: [
                CircularProgressIndicator(),
                SizedBox(width: 20),
                Text('Clearing all data...'),
              ],
            ),
          ),
        );

        await CredentialStorageService.clearAllCredentials();
        await SubscriptionArticleStorage.clearAllArticles();
        
        Navigator.pop(context);
        
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('All subscription data cleared'),
            backgroundColor: Colors.green,
          ),
        );

        // Reload data
        await _loadSubscriptionData();
      }
    } catch (e) {
      Navigator.pop(context);
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text('Error clearing data: $e'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: Text('🔐 Subscription Management'),
        backgroundColor: Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: Icon(Icons.cleaning_services),
            onPressed: _performCleanup,
            tooltip: 'Clean up expired articles',
          ),
          IconButton(
            icon: Icon(Icons.refresh),
            onPressed: _loadSubscriptionData,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: _isLoading
          ? Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadSubscriptionData,
              child: ListView(
                padding: EdgeInsets.all(16),
                children: [
                  _buildStatsCard(),
                  SizedBox(height: 16),
                  _buildDomainsSection(),
                  SizedBox(height: 16),
                  _buildArticlesSection(),
                  SizedBox(height: 16),
                  _buildActionsSection(),
                ],
              ),
            ),
    );
  }

  Widget _buildStatsCard() {
    final articleStats = _subscriptionStats['articles'] as Map<String, dynamic>? ?? {};
    final credentialStats = _subscriptionStats['credentials'] as Map<String, dynamic>? ?? {};

    return Card(
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Subscription Statistics',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _buildStatItem(
                    'Stored Articles',
                    '${articleStats['total_articles'] ?? 0}',
                    Icons.article,
                    Colors.blue,
                  ),
                ),
                Expanded(
                  child: _buildStatItem(
                    'Active Domains',
                    '${credentialStats['active_domains'] ?? 0}',
                    Icons.domain,
                    Colors.green,
                  ),
                ),
              ],
            ),
            SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _buildStatItem(
                    'Storage Used',
                    '${articleStats['total_size_mb'] ?? 0} MB',
                    Icons.storage,
                    Colors.orange,
                  ),
                ),
                Expanded(
                  child: _buildStatItem(
                    'Storage Limit',
                    '${articleStats['storage_limit_mb'] ?? 500} MB',
                    Icons.cloud_queue,
                    Colors.grey,
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatItem(String label, String value, IconData icon, Color color) {
    return Container(
      padding: EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: color.withOpacity(0.3)),
      ),
      child: Column(
        children: [
          Icon(icon, color: color, size: 24),
          SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              fontSize: 16,
              fontWeight: FontWeight.bold,
              color: color,
            ),
          ),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey.shade600,
            ),
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }

  Widget _buildDomainsSection() {
    return Card(
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Stored Credentials (${_storedDomains.length})',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            if (_storedDomains.isEmpty)
              Center(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: Text(
                    'No stored credentials',
                    style: TextStyle(color: Colors.grey.shade600),
                  ),
                ),
              )
            else
              ...(_storedDomains.map((domain) => ListTile(
                    leading: Container(
                      width: 40,
                      height: 40,
                      decoration: BoxDecoration(
                        color: Colors.green.shade100,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Icon(Icons.lock_open, color: Colors.green.shade700),
                    ),
                    title: Text(domain),
                    subtitle: Text('Active credentials'),
                    trailing: IconButton(
                      icon: Icon(Icons.delete, color: Colors.red),
                      onPressed: () => _removeDomain(domain),
                    ),
                  ))),
          ],
        ),
      ),
    );
  }

  Widget _buildArticlesSection() {
    final groupedArticles = <String, List<SubscriptionArticleMetadata>>{};
    for (final article in _storedArticles) {
      groupedArticles.putIfAbsent(article.domain, () => []).add(article);
    }

    return Card(
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Stored Articles (${_storedArticles.length})',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            if (_storedArticles.isEmpty)
              Center(
                child: Padding(
                  padding: EdgeInsets.all(20),
                  child: Text(
                    'No stored articles',
                    style: TextStyle(color: Colors.grey.shade600),
                  ),
                ),
              )
            else
              ...groupedArticles.entries.map((entry) => ExpansionTile(
                    title: Text(entry.key),
                    subtitle: Text('${entry.value.length} articles'),
                    children: entry.value.map((article) => ListTile(
                          leading: Icon(Icons.article, color: Colors.blue),
                          title: Text(
                            article.title,
                            maxLines: 2,
                            overflow: TextOverflow.ellipsis,
                          ),
                          subtitle: Text(
                            'Downloaded: ${article.downloaded.day}/${article.downloaded.month}/${article.downloaded.year}',
                          ),
                          trailing: Text(
                            '${(article.sizeBytes / (1024 * 1024)).toStringAsFixed(1)} MB',
                            style: TextStyle(fontSize: 12, color: Colors.grey.shade600),
                          ),
                        )).toList(),
                  )),
          ],
        ),
      ),
    );
  }

  Widget _buildActionsSection() {
    return Card(
      child: Padding(
        padding: EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'Management Actions',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
            ),
            SizedBox(height: 12),
            ListTile(
              leading: Icon(Icons.cleaning_services, color: Colors.blue),
              title: Text('Clean Up Expired Articles'),
              subtitle: Text('Remove articles older than 30 days'),
              onTap: _performCleanup,
            ),
            ListTile(
              leading: Icon(Icons.clear_all, color: Colors.red),
              title: Text('Clear All Subscription Data'),
              subtitle: Text('Remove all credentials and articles'),
              onTap: _clearAllData,
            ),
          ],
        ),
      ),
    );
  }
}