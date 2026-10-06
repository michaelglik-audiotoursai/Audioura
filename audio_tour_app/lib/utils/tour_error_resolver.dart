// [LOCAL-581] Tour-generation error resolver — extracted for testability.
//
// Michael, 2026-10-05 (app 2.4.1+27, local stack): the server returned an
// actionable message —
//   "We could not find enough verified material about "Griffin Museum of
//    Photography" to build a tour. Try a broader request — for example a
//    walking tour of the surrounding neighbourhood."
// — but the app showed the generic "Unable to generate tour. Please try
// again." The server's own words must reach the user; the generic string is a
// fallback only.
//
// This file holds the PURE decision logic (no Flutter, no I/O) so it can be
// unit-tested directly and reused by the status-poll error branch in
// tour_generator_screen.dart. It turns a job-status map into:
//   • the user-facing message (server precedence, then generic fallback),
//   • an optional suggestion {label, request, tour_type} (LOCAL-580 contract),
//   • whether a plain "Try again" can possibly succeed, or the user must
//     Edit the request first (error_code venue_no_verifiable_content).

/// The generic text shown ONLY when the server sent nothing usable.
const String kGenericTourError = 'Unable to generate tour. Please try again.';

/// Error codes (LOCAL-580 contract) that cannot succeed on a plain retry —
/// the request itself must change first, so the action is "Edit request".
const Set<String> kNonRetryableErrorCodes = {
  'venue_no_verifiable_content',
};

/// [LOCAL-598] The action button a refusal should offer. The subscription-
/// levels refusals (subscription_levels.py, returned as 429/401 with an
/// error_code) each map to one of these so the UI can show a button that
/// matches the code — never a dead-end "Unable to generate tour".
enum TourRefusalAction {
  /// Buy a pack (L3/L4) — the user is out of fresh/pack/ops allowance, or at a
  /// level that cannot generate what they asked for.
  buyPack,

  /// Join the L2 seat queue — shown DISABLED ("coming soon") until LOCAL-596's
  /// queue endpoints exist. Reserved for a future wiring.
  joinQueue,

  /// Open "Your plan" — the refusal is about plan state (renewal due, or a
  /// device-id problem the plan screen explains), not a buyable allowance.
  yourPlan,

  /// Change the request itself (fewer stops, or a by-reference-only level that
  /// can't research the asked-for place) — a plain retry won't help.
  editRequest,

  /// No specific action — show the message only.
  none,
}

/// The subscription-levels error_codes (subscription_levels.py) and the action
/// each one should offer. Generation-failure codes (actionable_failure.py) are
/// NOT in this map — they are handled by the suggestion/canRetry path. A code
/// not in this map yields [TourRefusalAction.none].
const Map<String, TourRefusalAction> kRefusalActions = {
  // Out of allowance -> buy a pack.
  'plan_limit_daily': TourRefusalAction.buyPack,
  'plan_limit_monthly': TourRefusalAction.buyPack,
  'pack_exhausted': TourRefusalAction.buyPack,
  'level_cannot_generate': TourRefusalAction.buyPack,
  // Request itself is the problem -> edit it.
  'stops_over_plan': TourRefusalAction.editRequest,
  'by_reference_unavailable': TourRefusalAction.editRequest,
  // Plan state -> open the plan screen.
  'renewal_due': TourRefusalAction.yourPlan,
  'user_id_required': TourRefusalAction.yourPlan,
};

/// Resolve a subscription-levels refusal (429/401 body) into the action button
/// it should offer. Pure: body map in, action out. Unknown/absent code ->
/// [TourRefusalAction.none]. This is the D6 mapping the UI branches on.
TourRefusalAction refusalActionFor(Map<String, dynamic> body) {
  final code = _nonEmpty(body['error_code']);
  if (code == null) return TourRefusalAction.none;
  return kRefusalActions[code] ?? TourRefusalAction.none;
}

/// Human-facing label for a refusal action button.
String refusalActionLabel(TourRefusalAction action) {
  switch (action) {
    case TourRefusalAction.buyPack:
      return 'Buy a pack';
    case TourRefusalAction.joinQueue:
      return 'Join the queue';
    case TourRefusalAction.yourPlan:
      return 'Your plan';
    case TourRefusalAction.editRequest:
      return 'Edit request';
    case TourRefusalAction.none:
      return '';
  }
}

/// A suggestion the server offers alongside a failure (LOCAL-580 contract):
/// a one-tap alternative request. `label` is the button text, `request` is the
/// tour request to submit, `tourType` an optional tour_type hint.
class TourErrorSuggestion {
  final String label;
  final String request;
  final String? tourType;

  const TourErrorSuggestion({
    required this.label,
    required this.request,
    this.tourType,
  });

  @override
  bool operator ==(Object other) =>
      other is TourErrorSuggestion &&
      other.label == label &&
      other.request == request &&
      other.tourType == tourType;

  @override
  int get hashCode => Object.hash(label, request, tourType);

  @override
  String toString() =>
      'TourErrorSuggestion(label: $label, request: $request, tourType: $tourType)';
}

/// The resolved, display-ready outcome of a failed tour job.
class ResolvedTourError {
  /// The message to show the user. Never empty: falls back to
  /// [kGenericTourError] when the server sent nothing usable.
  final String message;

  /// True when the server (not the fallback) supplied the message. Lets the
  /// UI know the text is actionable server copy, for logging/telemetry.
  final bool isServerMessage;

  /// Extra lines to show under the message (legacy user_error.suggestions).
  final List<String> suggestions;

  /// The one-tap alternative, when the server offered one. Null otherwise —
  /// the UI must simply not show the button (no crash on a missing field).
  final TourErrorSuggestion? suggestion;

  /// The server's machine-readable error_code, when present.
  final String? errorCode;

  /// False when the error_code says a plain retry cannot succeed
  /// (e.g. venue_no_verifiable_content) — the UI labels the action
  /// "Edit request" and returns the user to the form instead of re-submitting.
  final bool canRetry;

  const ResolvedTourError({
    required this.message,
    required this.isServerMessage,
    required this.suggestions,
    required this.suggestion,
    required this.errorCode,
    required this.canRetry,
  });
}

/// Resolve a job-status map (the body of GET /status/:id when status is
/// `error`/`failed`) into a [ResolvedTourError].
///
/// Message precedence (first non-empty wins):
///   1. `error`                     — the server's own, most specific text.
///   2. `message`                   — LOCAL-580 top-level user message.
///   3. `user_error.message`        — legacy structured user error.
///   4. `user_message`              — legacy flat user message.
///   5. [kGenericTourError]         — fallback only when the server sent
///                                    nothing (isServerMessage = false).
///
/// The suggestion comes from `suggestion {label, request, tour_type}` when all
/// required fields are present; a malformed or missing suggestion yields null
/// (never a crash). `error_code` drives [ResolvedTourError.canRetry].
ResolvedTourError resolveTourError(Map<String, dynamic> status) {
  // --- message precedence ---
  String? message;
  final rawError = _nonEmpty(status['error']);
  final rawMessage = _nonEmpty(status['message']);
  final userError = status['user_error'];
  final rawUserErrorMsg = userError is Map
      ? _nonEmpty(userError['message'])
      : null;
  final rawUserMessage = _nonEmpty(status['user_message']);

  if (rawError != null) {
    message = rawError;
  } else if (rawMessage != null) {
    message = rawMessage;
  } else if (rawUserErrorMsg != null) {
    message = rawUserErrorMsg;
  } else if (rawUserMessage != null) {
    message = rawUserMessage;
  }

  final isServerMessage = message != null;

  // --- legacy suggestion lines (user_error.suggestions) ---
  final suggestions = <String>[];
  if (userError is Map && userError['suggestions'] is List) {
    for (final s in (userError['suggestions'] as List)) {
      final line = _nonEmpty(s);
      if (line != null) suggestions.add(line);
    }
  }

  // --- one-tap suggestion (LOCAL-580 contract) ---
  final suggestion = _parseSuggestion(status['suggestion']);

  // --- error_code / retryability ---
  final errorCode = _nonEmpty(status['error_code']);
  final canRetry =
      errorCode == null || !kNonRetryableErrorCodes.contains(errorCode);

  return ResolvedTourError(
    message: message ?? kGenericTourError,
    isServerMessage: isServerMessage,
    suggestions: suggestions,
    suggestion: suggestion,
    errorCode: errorCode,
    canRetry: canRetry,
  );
}

/// Parse the optional `suggestion` object. Requires at least a non-empty
/// `request`; `label` falls back to a sensible default if absent so a partial
/// payload still produces a usable button rather than crashing. Anything not a
/// map, or without a request, yields null (button hidden).
TourErrorSuggestion? _parseSuggestion(dynamic raw) {
  if (raw is! Map) return null;
  final request = _nonEmpty(raw['request']);
  if (request == null) return null;
  final label = _nonEmpty(raw['label']) ?? 'Try this instead';
  final tourType = _nonEmpty(raw['tour_type']);
  return TourErrorSuggestion(
    label: label,
    request: request,
    tourType: tourType,
  );
}

/// Returns the trimmed string value of [v], or null when it is null, not a
/// stringifiable scalar we want, or blank after trimming.
String? _nonEmpty(dynamic v) {
  if (v == null) return null;
  final s = v.toString().trim();
  return s.isEmpty ? null : s;
}
