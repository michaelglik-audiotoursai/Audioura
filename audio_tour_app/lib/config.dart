class Config {
  // Default server IP. Production server is .218.
  // Earlier code used .217 as default which only worked because
  // SharedPreferences override was set by the user.
  static const String defaultServerIp = '192.168.0.136';

  // [LOCAL-737 / D708] The single source of truth for the deployment track
  // value the app uses when stamping/reading tour provenance. Beta, Storied and
  // Subscribed are separate stacks that SHARE one GCloud Postgres; each writes
  // its own `track` so same-name tours never collide across tracks (bug 432).
  //
  // validTracks: every value the DB/API contract accepts. Nowhere in the app
  // should a two-value ['beta','storied'] list be hardcoded — read this.
  static const List<String> validTracks = ['beta', 'storied', 'subscribed'];

  // appTrack: the track THIS build belongs to. Baked in at build time via
  // --dart-define=APP_TRACK=subscribed for the Subscribed build; defaults to
  // 'beta' so Beta/Storied builds are byte-for-byte unchanged. A build that is
  // not 'subscribed' keeps using the existing cloud_track (Stable/Preview)
  // selector. Any unknown value falls back to 'beta'.
  static const String _rawAppTrack =
      String.fromEnvironment('APP_TRACK', defaultValue: 'beta');
  static String get appTrack =>
      validTracks.contains(_rawAppTrack) ? _rawAppTrack : 'beta';

  // True when this is the Subscribed build (its own stack + track='subscribed').
  static bool get isSubscribedBuild => appTrack == 'subscribed';

  // Normalise any raw track value to a known track, defaulting to 'beta'.
  static String normalizeTrack(String? track) =>
      validTracks.contains(track) ? track! : 'beta';
}
