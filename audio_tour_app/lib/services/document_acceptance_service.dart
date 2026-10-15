// [LOCAL-691] Legal documents + acceptance capture.
//
// Pure constants and helpers (document slugs, versions, audioura.com URLs) are
// kept dependency-free so they are unit-testable without a network. The
// networked client records/reads acceptance via Service.userDb, mirroring
// CommunitiesService.
//
//   POST /document-acceptance  {user_id, document, version}
//   GET  /document-acceptance?user_id=...[&document=...]
//
// The published pages live on audioura.com at /terms, /privacy, /refunds,
// /content-policy, /guide-terms, /organiser-terms. They 404 until Michael
// publishes them — that is expected; the app shows the links anyway.

import 'dart:convert';
import '../config/endpoints.dart';

/// The version of the legal documents this build ships against. Stamped on
/// every acceptance so we can prove WHICH text the user agreed to and re-prompt
/// when a new version ships. Matches the `version:` in the legal/ drafts.
const String kLegalDocsVersion = '2026-10-14-draft1';

/// The canonical document slugs (match the server's KNOWN_DOCUMENTS and the
/// legal/ Markdown files).
class LegalDoc {
  static const String terms = 'terms';
  static const String privacy = 'privacy';
  static const String refunds = 'refunds';
  static const String guideTerms = 'guide_terms';
  static const String organiserTerms = 'organiser_terms';
  static const String contentPolicy = 'content_policy';
}

/// Pure helper: the public audioura.com page path for a document slug. These
/// are the routes the About links open; they 404 until published.
String legalDocPath(String document) {
  switch (document) {
    case LegalDoc.terms:
      return '/terms';
    case LegalDoc.privacy:
      return '/privacy';
    case LegalDoc.refunds:
      return '/refunds';
    case LegalDoc.guideTerms:
      return '/guide-terms';
    case LegalDoc.organiserTerms:
      return '/organiser-terms';
    case LegalDoc.contentPolicy:
      return '/content-policy';
    default:
      return '/';
  }
}

/// Pure helper: the full public URL for a document on audioura.com.
String legalDocUrl(String document) =>
    'https://www.audioura.com${legalDocPath(document)}';

/// Human-facing title for a document slug (for link labels / sheets).
String legalDocTitle(String document) {
  switch (document) {
    case LegalDoc.terms:
      return 'Terms';
    case LegalDoc.privacy:
      return 'Privacy';
    case LegalDoc.refunds:
      return 'Refunds';
    case LegalDoc.guideTerms:
      return 'Guide Terms';
    case LegalDoc.organiserTerms:
      return 'Organiser Terms';
    case LegalDoc.contentPolicy:
      return 'Content policy';
    default:
      return 'Legal';
  }
}

/// The thin network client over Service.userDb.
class DocumentAcceptanceService {
  /// Record that [userId] accepted [document] at [version] (default: this
  /// build's version). Returns true when the server stored it (new or already
  /// present — both are success). Returns false on a network/validation error,
  /// so a caller gating an action can require a true result.
  static Future<bool> record(
    String userId,
    String document, {
    String version = kLegalDocsVersion,
  }) async {
    try {
      final r = await Endpoints.post(
        Service.userDb,
        '/document-acceptance',
        body: {
          'user_id': userId,
          'document': document,
          'version': version,
        },
      );
      return r.statusCode == 200;
    } catch (_) {
      return false;
    }
  }

  /// List the documents (and versions) [userId] has accepted. Empty on error.
  static Future<List<AcceptanceRecord>> list(String userId,
      {String? document}) async {
    try {
      final q = document != null ? '&document=$document' : '';
      final r = await Endpoints.get(
          Service.userDb, '/document-acceptance?user_id=$userId$q');
      if (r.statusCode != 200) return const [];
      final j = jsonDecode(r.body) as Map<String, dynamic>;
      final list = (j['acceptances'] as List?) ?? const [];
      return list
          .whereType<Map<String, dynamic>>()
          .map(AcceptanceRecord.fromJson)
          .toList(growable: false);
    } catch (_) {
      return const [];
    }
  }

  /// True when [userId] has accepted [document] at [version] (default: this
  /// build's version). Lets a screen skip re-prompting a user who already
  /// agreed to the current text.
  static Future<bool> hasAccepted(
    String userId,
    String document, {
    String version = kLegalDocsVersion,
  }) async {
    final records = await list(userId, document: document);
    return records.any((a) => a.document == document && a.version == version);
  }
}

/// One acceptance row. Defensive JSON parsing — missing fields never throw.
class AcceptanceRecord {
  final String document;
  final String version;
  final String? acceptedAt;

  const AcceptanceRecord({
    required this.document,
    required this.version,
    this.acceptedAt,
  });

  factory AcceptanceRecord.fromJson(Map<String, dynamic> j) => AcceptanceRecord(
        document: (j['document'] ?? '').toString(),
        version: (j['version'] ?? '').toString(),
        acceptedAt: j['accepted_at']?.toString(),
      );
}
