import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import 'dart:convert';
import '../screens/debug_log_viewer_screen.dart';

/// API Tester to check which endpoints are available
class ApiTester {
  /// Test all possible API endpoints
  static Future<void> testAllEndpoints() async {
    final prefs = await SharedPreferences.getInstance();
    final serverIp = prefs.getString('server_ip') ?? '192.168.0.217';
    
    await DebugLogHelper.addDebugLog('API TESTER: Testing all endpoints on $serverIp');
    
    // List of endpoints to test
    final endpoints = [
      '/health',
      '/status',
      '/api',
      '/api/v1',
      '/user',
      '/tours',
      '/sql',
      '/execute_sql',
      '/update_tour',
      '/db/update_tour',
      '/jdbc',
      '/jdbc/execute',
      '/pg',
      '/pg/query',
      '/direct',
      '/direct/sql',
      '/direct/update',
    ];
    
    // Test each endpoint with GET request
    for (final endpoint in endpoints) {
      try {
        final response = await http.get(
          Uri.parse('http://$serverIp:5003$endpoint'),
        ).timeout(const Duration(seconds: 2));
        
        await DebugLogHelper.addDebugLog('GET $endpoint: ${response.statusCode} - ${_truncateResponse(response.body)}');
      } catch (e) {
        await DebugLogHelper.addDebugLog('GET $endpoint: ERROR - $e');
      }
    }
    
    // Test direct SQL POST to port 5002 (the tour generation API)
    try {
      final sqlData = {
        'sql': "SELECT 1 as test"
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5002/sql'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(sqlData),
      ).timeout(const Duration(seconds: 2));
      
      await DebugLogHelper.addDebugLog('POST /sql on port 5002: ${response.statusCode} - ${_truncateResponse(response.body)}');
    } catch (e) {
      await DebugLogHelper.addDebugLog('POST /sql on port 5002: ERROR - $e');
    }
    
    // Test direct connection to PostgreSQL
    await testDirectPostgres(serverIp);
  }
  
  /// Test direct connection to PostgreSQL
  static Future<void> testDirectPostgres(String serverIp) async {
    try {
      final pgData = {
        'host': serverIp,
        'port': 5432,
        'database': 'audiotours',
        'user': 'postgres',
        'password': 'postgres',
        'query': "UPDATE tour_requests SET status = 'completed', finished_at = '${DateTime.now().toIso8601String()}' WHERE tour_id = 'tour_1981b2356dc'"
      };
      
      final response = await http.post(
        Uri.parse('http://$serverIp:5003/postgres/direct'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode(pgData),
      ).timeout(const Duration(seconds: 5));
      
      await DebugLogHelper.addDebugLog('DIRECT POSTGRES: ${response.statusCode} - ${_truncateResponse(response.body)}');
    } catch (e) {
      await DebugLogHelper.addDebugLog('DIRECT POSTGRES: ERROR - $e');
    }
  }
  
  /// Truncate long responses
  static String _truncateResponse(String response) {
    if (response.length > 100) {
      return '${response.substring(0, 100)}...';
    }
    return response;
  }
}