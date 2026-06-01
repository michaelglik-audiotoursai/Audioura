class Config {
  // Default server IP. Production server is .218.
  // Earlier code used .217 as default which only worked because
  // SharedPreferences override was set by the user.
  static const String defaultServerIp = '192.168.0.218';
}
