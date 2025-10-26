class ApiConfig {
  static const String _mockBaseUrl = 'http://localhost:5004';
  static const String _prodBaseUrl = 'http://localhost:5002';
  
  static bool _useMockServer = false;
  
  static String get baseUrl => _useMockServer ? _mockBaseUrl : _prodBaseUrl;
  
  static void useMockServer(bool use) {
    _useMockServer = use;
  }
  
  static bool get isMockMode => _useMockServer;
}