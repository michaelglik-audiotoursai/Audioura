// [LOCAL-691] Legal-page acceptance — pure helper + widget presence tests.
//
// Covers the Flutter side without a running app or network:
//   * document slugs match the server's canonical set;
//   * legalDocPath / legalDocUrl map each slug to the audioura.com route the
//     About links open (/terms, /privacy, /content-policy, ...);
//   * legalDocTitle labels;
//   * kLegalDocsVersion is the stamped acceptance version;
//   * AcceptanceRecord.fromJson is defensive (missing fields never throw);
//   * the shared TermsAgreeLine widget renders the "By buying you agree to the
//     Terms" line with a tappable "Terms" link (the Buy / pass sheets' line).

import 'package:flutter/material.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:audio_tour_app_dev/services/document_acceptance_service.dart';
import 'package:audio_tour_app_dev/widgets/tour_buy_sheet.dart';

void main() {
  group('legal document slugs', () {
    test('canonical slugs match the server KNOWN_DOCUMENTS', () {
      expect(LegalDoc.terms, 'terms');
      expect(LegalDoc.privacy, 'privacy');
      expect(LegalDoc.refunds, 'refunds');
      expect(LegalDoc.guideTerms, 'guide_terms');
      expect(LegalDoc.organiserTerms, 'organiser_terms');
      expect(LegalDoc.contentPolicy, 'content_policy');
    });
  });

  group('legalDocPath / legalDocUrl', () {
    test('each document maps to its audioura.com route', () {
      expect(legalDocPath(LegalDoc.terms), '/terms');
      expect(legalDocPath(LegalDoc.privacy), '/privacy');
      expect(legalDocPath(LegalDoc.refunds), '/refunds');
      expect(legalDocPath(LegalDoc.guideTerms), '/guide-terms');
      expect(legalDocPath(LegalDoc.organiserTerms), '/organiser-terms');
      expect(legalDocPath(LegalDoc.contentPolicy), '/content-policy');
    });

    test('url is the full https audioura.com URL', () {
      expect(legalDocUrl(LegalDoc.terms), 'https://www.audioura.com/terms');
      expect(legalDocUrl(LegalDoc.contentPolicy),
          'https://www.audioura.com/content-policy');
    });

    test('unknown slug falls back to /', () {
      expect(legalDocPath('nope'), '/');
    });
  });

  group('legalDocTitle', () {
    test('human labels', () {
      expect(legalDocTitle(LegalDoc.terms), 'Terms');
      expect(legalDocTitle(LegalDoc.privacy), 'Privacy');
      expect(legalDocTitle(LegalDoc.contentPolicy), 'Content policy');
      expect(legalDocTitle(LegalDoc.guideTerms), 'Guide Terms');
      expect(legalDocTitle(LegalDoc.organiserTerms), 'Organiser Terms');
    });
  });

  group('kLegalDocsVersion', () {
    test('is the stamped acceptance version', () {
      expect(kLegalDocsVersion, '2026-10-14-draft1');
    });
  });

  group('AcceptanceRecord.fromJson', () {
    test('parses a full record', () {
      final r = AcceptanceRecord.fromJson({
        'document': 'guide_terms',
        'version': '2026-10-14-draft1',
        'accepted_at': '2026-10-14T20:00:00+00:00',
      });
      expect(r.document, 'guide_terms');
      expect(r.version, '2026-10-14-draft1');
      expect(r.acceptedAt, '2026-10-14T20:00:00+00:00');
    });

    test('missing fields never throw', () {
      final r = AcceptanceRecord.fromJson({});
      expect(r.document, '');
      expect(r.version, '');
      expect(r.acceptedAt, isNull);
    });
  });

  group('TermsAgreeLine widget', () {
    testWidgets('shows the agree line with a tappable Terms link',
        (tester) async {
      await tester.pumpWidget(const MaterialApp(
        home: Scaffold(body: TermsAgreeLine()),
      ));
      expect(find.textContaining('By buying you agree to the'), findsOneWidget);
      expect(find.text('Terms'), findsOneWidget);
      // The Terms link is tappable (an InkWell is present).
      expect(find.byType(InkWell), findsWidgets);
    });
  });
}
