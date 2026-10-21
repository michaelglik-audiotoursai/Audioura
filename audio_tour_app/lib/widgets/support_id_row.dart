// [LOCAL-729 / D692] The public Support ID row shown in About.
//
// A Support ID is a short PUBLIC ALIAS of the device, e.g. AU-7K3Q, that a buyer
// can quote when asking Audioura for a reimbursement so we can find them without
// any private data. It is NEVER the secret device id.
//
// This widget is deliberately small and dependency-free (no network, no plugins)
// so it renders the same in the app and in a widget test. The caller passes the
// resolved [supportId]; [computeLocalSupportId] gives the deterministic offline
// value the About screen shows until the server confirms the authoritative one.
// The alphabet MUST match the server (support_id.py): A-Z and 2-9 minus the
// easily-confused O/I/L and 0/1.

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

/// The Support ID alphabet — identical to the server's support_id.py.
const String kSupportIdAlphabet = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789';

/// A deterministic AU-XXXX alias of a device id. Pure function, so it is stable
/// across launches and matches the About screen's offline fallback. The server
/// allocates a random one; this is only the pre-confirmation display value.
String computeLocalSupportId(String userId) {
  int h = 0;
  for (final cu in userId.codeUnits) {
    h = (h * 31 + cu) & 0x7fffffff;
  }
  final buf = StringBuffer('AU-');
  for (int i = 0; i < 4; i++) {
    buf.write(kSupportIdAlphabet[h % kSupportIdAlphabet.length]);
    h = h ~/ kSupportIdAlphabet.length;
  }
  return buf.toString();
}

/// True if [value] has the Support ID shape (AU- + 4 alphabet chars).
bool isSupportIdShape(String value) {
  if (!value.startsWith('AU-') || value.length != 7) return false;
  for (final c in value.substring(3).split('')) {
    if (!kSupportIdAlphabet.contains(c)) return false;
  }
  return true;
}

/// The About-screen Support ID row: a label, the value, and a Copy button.
class SupportIdRow extends StatelessWidget {
  const SupportIdRow({super.key, required this.supportId, this.onCopied});

  /// The Support ID to show (already resolved/computed by the caller).
  final String supportId;

  /// Optional callback after a successful copy (e.g. to show a snackbar). When
  /// null, the widget shows its own confirmation snackbar.
  final VoidCallback? onCopied;

  Future<void> _copy(BuildContext context) async {
    await Clipboard.setData(ClipboardData(text: supportId));
    if (onCopied != null) {
      onCopied!();
      return;
    }
    if (!context.mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('Support ID $supportId copied'),
        backgroundColor: Colors.green,
        duration: const Duration(seconds: 2),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.center,
        children: [
          const SizedBox(
            width: 80,
            child: Text(
              'Support ID:',
              style: TextStyle(fontWeight: FontWeight.w600, fontSize: 14),
            ),
          ),
          Expanded(
            child: Text(
              supportId,
              key: const Key('support_id_value'),
              style: const TextStyle(fontSize: 14, fontFamily: 'monospace'),
            ),
          ),
          IconButton(
            key: const Key('support_id_copy'),
            icon: const Icon(Icons.copy, size: 18),
            tooltip: 'Copy Support ID',
            padding: EdgeInsets.zero,
            constraints: const BoxConstraints(),
            onPressed: () => _copy(context),
          ),
        ],
      ),
    );
  }
}
