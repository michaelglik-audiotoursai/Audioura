import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../services/platform_logger.dart';
import '../services/log_redactor.dart';

class DebugLogViewerScreen extends StatefulWidget {
  const DebugLogViewerScreen({super.key});

  @override
  State<DebugLogViewerScreen> createState() => _DebugLogViewerScreenState();
}

class _DebugLogViewerScreenState extends State<DebugLogViewerScreen> {
  List<String> _debugLogs = [];

  @override
  void initState() {
    super.initState();
    _loadDebugLogs();
  }

  Future<void> _loadDebugLogs() async {
    if (kIsWeb) {
      // Web platform: Show message about console logs
      setState(() {
        _debugLogs = [
          '[INFO] Web Platform Debug Logs',
          '[INFO] Logs are displayed in browser console (F12)',
          '[INFO] WebLogger prevents storage quota issues',
          '[INFO] Check browser console for real-time logs',
          '[INFO] Press F12 → Console tab to view logs',
        ];
      });
    } else {
      // Mobile platform: Load from SharedPreferences
      final prefs = await SharedPreferences.getInstance();
      setState(() {
        _debugLogs = prefs.getStringList('debug_logs') ?? [];
      });
    }
  }

  Future<void> _copyAllLogs() async {
    if (_debugLogs.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No logs to copy'),
          backgroundColor: Colors.orange,
        ),
      );
      return;
    }
    
    final allLogs = _debugLogs.join('\n');
    await Clipboard.setData(ClipboardData(text: allLogs));
    
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${_debugLogs.length} log entries copied to clipboard'),
        backgroundColor: Colors.green,
        action: SnackBarAction(
          label: 'Share',
          onPressed: () {
            // You can now paste into email, Google Docs, etc.
          },
        ),
      ),
    );
  }

  Future<void> _clearLogs() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('debug_logs');
    setState(() {
      _debugLogs = [];
    });
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Debug logs cleared'),
        backgroundColor: Colors.blue,
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('🔍 Debug Logs'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadDebugLogs,
          ),
          IconButton(
            icon: const Icon(Icons.copy),
            onPressed: _copyAllLogs,
          ),
          IconButton(
            icon: const Icon(Icons.clear),
            onPressed: _clearLogs,
          ),
        ],
      ),
      body: Container(
        color: Colors.black87,
        child: _debugLogs.isEmpty
            ? const Center(
                child: Text(
                  'No debug logs yet.\nPress "Sync User to Database" to generate logs.',
                  textAlign: TextAlign.center,
                  style: TextStyle(
                    color: Colors.green,
                    fontSize: 16,
                  ),
                ),
              )
            : ListView.builder(
                padding: const EdgeInsets.all(8),
                itemCount: _debugLogs.length,
                itemBuilder: (context, index) {
                  return Padding(
                    padding: const EdgeInsets.symmetric(vertical: 2),
                    child: SelectableText(
                      _debugLogs[index],
                      style: const TextStyle(
                        color: Colors.green,
                        fontFamily: 'monospace',
                        fontSize: 12,
                      ),
                    ),
                  );
                },
              ),
      ),
    );
  }
}

// Helper class for adding debug logs from anywhere in the app
class DebugLogHelper {
  static final PlatformLogger _logger = PlatformLogger.instance;
  
  static Future<void> addDebugLog(String message) async {
    // Guard against secret leakage into the persisted, in-app-viewable log.
    // Every message is scrubbed here so a stray `... $password ...` at any
    // call site cannot write a credential/key to disk. See wdvrday4pk.
    await _logger.log(LogRedactor.redact(message));
  }
}