// LOCAL-478 — Shared stale-container path healer.
//
// iOS reassigns the app container UUID on reinstall/update (e.g. a TestFlight
// bump 2.3.2 (22) → (23)). Every absolute path that was stored under the old
// container then points outside the current sandbox, so a stored tour path
// like
//
//   /var/mobile/Containers/Data/Application/<OLD-UUID>/Documents/tours/foo
//
// no longer exists. The fix is to re-anchor the path to the CURRENT Documents
// directory while keeping the stable `/tours/...` suffix.
//
// This rule was previously inlined only in the Listen screen
// (`my_tours_screen.dart` `_healTourPaths`, which logs
// `LISTEN: Healed stale container paths in saved_tours`). LOCAL-478 needs the
// same healing in the stop editor, so rather than write a second copy the rule
// lives here and both callers use it. Keeping ONE implementation means the
// editor and the Listen screen can never drift apart.
//
// Pure and synchronous by design (the caller supplies `docsDir`) so it is
// trivially unit-testable without a running app / MethodChannel.

/// Re-anchor [path] onto [docsDir] when it carries a stale iOS container UUID.
///
/// Returns the healed path when [path] contains the `/tours/` marker and is not
/// already rooted at [docsDir]; otherwise returns [path] unchanged.
///
/// This is the exact rule the Listen screen applied to `saved_tours`, lifted
/// out verbatim so callers share one behaviour.
String healTourPath(String path, String docsDir) {
  final idx = path.indexOf('/tours/');
  if (idx != -1 && !path.startsWith(docsDir)) {
    return docsDir + path.substring(idx);
  }
  return path;
}
