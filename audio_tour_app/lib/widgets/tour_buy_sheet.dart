// [LOCAL-677] Curator paid tours — the Buy / TEST PURCHASE sheet.
//
// Shows the price and a Buy button for a locked paid tour. On a real store
// (cloud) it drives IapService.buyTour; in LOCAL stub mode it shows a clearly
// labelled "TEST PURCHASE" sheet that completes a fake purchase through
// IapService.testPurchaseTour (IAP_VERIFY_MODE=stub), so the whole buy→unlock
// flow can be exercised end to end on Michael's phone before the Apple/Google
// products exist. Returns true when the tour was unlocked.

import 'package:flutter/material.dart';
import 'package:url_launcher/url_launcher.dart';

import '../services/iap_service.dart';
import '../services/device_service.dart';
import '../services/document_acceptance_service.dart';

class TourBuySheet {
  /// Present the buy sheet for [tourId] at [tier] / [priceLabel]. Returns true
  /// if the purchase completed and the tour is now unlocked.
  static Future<bool> show(
    BuildContext context, {
    required String tourId,
    required int tier,
    required String priceLabel,
    String? tourTitle,
  }) async {
    final isStub = await IapService.instance.purchasesModeIsStub(); // [LOCAL-734] ask the server, per platform
    if (!context.mounted) return false;

    return await showModalBottomSheet<bool>(
          context: context,
          isScrollControlled: true,
          builder: (ctx) => _BuySheetBody(
            tourId: tourId,
            tier: tier,
            priceLabel: priceLabel,
            tourTitle: tourTitle,
            isStub: isStub,
          ),
        ) ??
        false;
  }
}

class _BuySheetBody extends StatefulWidget {
  final String tourId;
  final int tier;
  final String priceLabel;
  final String? tourTitle;
  final bool isStub;

  const _BuySheetBody({
    required this.tourId,
    required this.tier,
    required this.priceLabel,
    required this.tourTitle,
    required this.isStub,
  });

  @override
  State<_BuySheetBody> createState() => _BuySheetBodyState();
}

class _BuySheetBodyState extends State<_BuySheetBody> {
  bool _busy = false;
  String? _error;

  Future<void> _buy() async {
    setState(() {
      _busy = true;
      _error = null;
    });
    final IapResult result = widget.isStub
        ? await IapService.instance.testPurchaseTour(widget.tier, widget.tourId)
        : await IapService.instance.buyTour(widget.tier, widget.tourId);
    if (!mounted) return;
    if (result.status == IapResultStatus.granted) {
      // [LOCAL-691] Buying agrees to the Terms — record the acceptance.
      final userId = await DeviceService.getUserId();
      await DocumentAcceptanceService.record(userId, LegalDoc.terms);
      if (!mounted) return;
      Navigator.of(context).pop(true);
      return;
    }
    setState(() {
      _busy = false;
      _error = result.status == IapResultStatus.cancelled
          ? null // user cancelled — no error banner
          : (result.message ?? 'The purchase could not be completed.');
    });
    if (result.status == IapResultStatus.cancelled && mounted) {
      Navigator.of(context).pop(false);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bottom = MediaQuery.of(context).viewInsets.bottom;
    return Padding(
      padding: EdgeInsets.fromLTRB(20, 20, 20, 20 + bottom),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (widget.isStub)
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(8),
              margin: const EdgeInsets.only(bottom: 12),
              decoration: BoxDecoration(
                color: Colors.amber.shade100,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.amber.shade700),
              ),
              child: Row(
                children: [
                  Icon(Icons.science, color: Colors.amber.shade900, size: 18),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'TEST PURCHASE — no real charge. This completes a fake '
                      'purchase on the local server so the unlock flow can be '
                      'tested end to end.',
                      style: TextStyle(
                          fontSize: 12, color: Colors.amber.shade900),
                    ),
                  ),
                ],
              ),
            ),
          Text(
            widget.tourTitle == null
                ? 'Unlock this tour'
                : 'Unlock “${widget.tourTitle}”',
            style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
          const SizedBox(height: 8),
          const Text(
            'Stop 1 is a free preview. Buy to unlock the rest of the tour. '
            'A bought tour stays yours.',
            style: TextStyle(fontSize: 13, color: Colors.black87),
          ),
          const SizedBox(height: 12),
          const TermsAgreeLine(),
          const SizedBox(height: 16),
          if (_error != null) ...[
            Text(_error!, style: TextStyle(color: Colors.red.shade700, fontSize: 13)),
            const SizedBox(height: 12),
          ],
          SizedBox(
            width: double.infinity,
            child: ElevatedButton(
              onPressed: _busy ? null : _buy,
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF1B6B2E),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(vertical: 14),
              ),
              child: _busy
                  ? const SizedBox(
                      height: 20,
                      width: 20,
                      child: CircularProgressIndicator(
                          strokeWidth: 2, color: Colors.white),
                    )
                  : Text(
                      widget.isStub
                          ? 'Test purchase (${widget.priceLabel})'
                          : 'Buy for ${widget.priceLabel}',
                      style: const TextStyle(
                          fontSize: 16, fontWeight: FontWeight.w600),
                    ),
            ),
          ),
          const SizedBox(height: 8),
          SizedBox(
            width: double.infinity,
            child: TextButton(
              onPressed: _busy ? null : () => Navigator.of(context).pop(false),
              child: const Text('Not now'),
            ),
          ),
        ],
      ),
    );
  }
}

/// [LOCAL-691] A small "By buying you agree to the Terms" line with a tappable
/// Terms link. Shared by the tour Buy sheet and the community-pass sheet.
class TermsAgreeLine extends StatelessWidget {
  const TermsAgreeLine({super.key});

  @override
  Widget build(BuildContext context) {
    return Wrap(
      crossAxisAlignment: WrapCrossAlignment.center,
      children: [
        const Text(
          'By buying you agree to the ',
          style: TextStyle(fontSize: 12, color: Colors.black54),
        ),
        InkWell(
          onTap: () async {
            final uri = Uri.parse(legalDocUrl(LegalDoc.terms));
            if (await canLaunchUrl(uri)) {
              await launchUrl(uri, mode: LaunchMode.externalApplication);
            }
          },
          child: const Text(
            'Terms',
            style: TextStyle(
              fontSize: 12,
              color: Color(0xFF3A3AC0),
              decoration: TextDecoration.underline,
            ),
          ),
        ),
        const Text('.', style: TextStyle(fontSize: 12, color: Colors.black54)),
      ],
    );
  }
}
