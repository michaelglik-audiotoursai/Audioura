import 'package:flutter/material.dart';
import '../services/wallet_service.dart';

/// Wallet screen — accessible from Settings (About).
/// Shows balance, plan, spend, transactions, and top-up.
class WalletScreen extends StatefulWidget {
  const WalletScreen({super.key});

  @override
  State<WalletScreen> createState() => _WalletScreenState();
}

class _WalletScreenState extends State<WalletScreen> {
  WalletData? _wallet;
  List<WalletTransaction> _transactions = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadWalletData();
  }

  Future<void> _loadWalletData() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final wallet = await WalletService.getWallet();
      final transactions = await WalletService.getTransactions();
      if (mounted) {
        setState(() {
          _wallet = wallet;
          _transactions = transactions;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  Future<void> _handleTopUp() async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Top Up Credits'),
        content: const Text(
          'Add credits to your wallet.\n\n'
          'You will be asked to confirm this purchase.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(context, true),
            style: ElevatedButton.styleFrom(
              backgroundColor: Colors.green,
              foregroundColor: Colors.white,
            ),
            child: const Text('Top Up'),
          ),
        ],
      ),
    );

    if (confirmed == true) {
      try {
        await WalletService.topUp('credit_topup_10');
        await _loadWalletData();
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(
              content: Text('Credits added successfully'),
              backgroundColor: Colors.green,
            ),
          );
        }
      } catch (e) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(
              content: Text('Top-up failed: $e'),
              backgroundColor: Colors.red,
            ),
          );
        }
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Wallet'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadWalletData,
            tooltip: 'Refresh',
          ),
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(
                  child: Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    children: [
                      Icon(Icons.error_outline,
                          size: 48, color: Colors.red.shade300),
                      const SizedBox(height: 16),
                      Text('Failed to load wallet',
                          style: TextStyle(color: Colors.red.shade700)),
                      const SizedBox(height: 8),
                      ElevatedButton(
                        onPressed: _loadWalletData,
                        child: const Text('Retry'),
                      ),
                    ],
                  ),
                )
              : RefreshIndicator(
                  onRefresh: _loadWalletData,
                  child: ListView(
                    padding: const EdgeInsets.all(16),
                    children: [
                      _buildBalanceCard(),
                      const SizedBox(height: 16),
                      _buildPlanCard(),
                      const SizedBox(height: 16),
                      if (_wallet?.plan == 'pay_per_use') ...[
                        _buildTopUpButton(),
                        const SizedBox(height: 16),
                      ],
                      _buildTransactionList(),
                    ],
                  ),
                ),
    );
  }

  Widget _buildBalanceCard() {
    final wallet = _wallet!;
    if (wallet.plan == 'unlimited') {
      return _buildCostStopCard(wallet);
    }
    if (wallet.plan == 'free') {
      return _buildFreeCard();
    }
    // Pay-Per-Use: show balance prominently
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const Text(
              'Available Balance',
              style: TextStyle(fontSize: 14, color: Colors.grey),
            ),
            const SizedBox(height: 8),
            Text(
              '\$${wallet.balanceUsd.toStringAsFixed(2)}',
              style: TextStyle(
                fontSize: 42,
                fontWeight: FontWeight.bold,
                color: wallet.lowBalance ? Colors.red : Colors.green.shade700,
              ),
            ),
            if (wallet.lowBalance) ...[
              const SizedBox(height: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.orange.shade50,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.orange.shade200),
                ),
                child: const Text(
                  '⚠️ Low balance — top up to continue generating',
                  style: TextStyle(
                      fontSize: 12, color: Color(0xFFE65100)),
                ),
              ),
            ],
            const SizedBox(height: 16),
            Row(
              mainAxisAlignment: MainAxisAlignment.center,
              children: [
                _buildSpendChip(
                    'This period', '\$${wallet.periodSpendUsd.toStringAsFixed(2)}'),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildCostStopCard(WalletData wallet) {
    final progress = wallet.costStopProgress!;
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            const Text(
              'Monthly Allowance',
              style: TextStyle(fontSize: 14, color: Colors.grey),
            ),
            const SizedBox(height: 12),
            Text(
              '\$${progress.usedUsd.toStringAsFixed(2)} / \$${progress.limitUsd.toStringAsFixed(2)}',
              style: const TextStyle(
                fontSize: 28,
                fontWeight: FontWeight.bold,
              ),
            ),
            const SizedBox(height: 12),
            ClipRRect(
              borderRadius: BorderRadius.circular(8),
              child: LinearProgressIndicator(
                value: progress.progressFraction,
                minHeight: 12,
                backgroundColor: Colors.grey.shade200,
                valueColor: AlwaysStoppedAnimation<Color>(
                  progress.progressFraction > 0.85
                      ? Colors.orange
                      : Colors.blue,
                ),
              ),
            ),
            const SizedBox(height: 8),
            Text(
              '${(progress.progressFraction * 100).toStringAsFixed(0)}% used',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade600),
            ),
            if (progress.progressFraction >= 1.0) ...[
              const SizedBox(height: 8),
              Container(
                padding:
                    const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                decoration: BoxDecoration(
                  color: Colors.red.shade50,
                  borderRadius: BorderRadius.circular(16),
                  border: Border.all(color: Colors.red.shade200),
                ),
                child: const Text(
                  'Monthly allowance reached',
                  style: TextStyle(fontSize: 12, color: Colors.red),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildFreeCard() {
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          children: [
            Icon(Icons.account_balance_wallet_outlined,
                size: 48, color: Colors.grey.shade400),
            const SizedBox(height: 12),
            const Text(
              'Free Plan',
              style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
            ),
            const SizedBox(height: 8),
            Text(
              'Upgrade to generate unlimited tours and articles',
              textAlign: TextAlign.center,
              style: TextStyle(color: Colors.grey.shade600),
            ),
            const SizedBox(height: 16),
            ElevatedButton(
              onPressed: () {
                Navigator.push(
                  context,
                  MaterialPageRoute(
                      builder: (context) => const PaywallScreen()),
                );
              },
              style: ElevatedButton.styleFrom(
                backgroundColor: const Color(0xFF2c3e50),
                foregroundColor: Colors.white,
              ),
              child: const Text('View Plans'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildPlanCard() {
    final wallet = _wallet!;
    final planDisplay = _planDisplayName(wallet.plan);
    return Card(
      child: ListTile(
        leading: Icon(_planIcon(wallet.plan), color: _planColor(wallet.plan)),
        title: Text(planDisplay,
            style: const TextStyle(fontWeight: FontWeight.bold)),
        subtitle: Text(_planSubtitle(wallet)),
        trailing: TextButton(
          onPressed: () {
            Navigator.push(
              context,
              MaterialPageRoute(builder: (context) => const PaywallScreen()),
            );
          },
          child: const Text('Change'),
        ),
      ),
    );
  }

  Widget _buildTopUpButton() {
    return SizedBox(
      width: double.infinity,
      child: ElevatedButton.icon(
        onPressed: _handleTopUp,
        icon: const Icon(Icons.add_circle_outline),
        label: const Text('Top Up'),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.green,
          foregroundColor: Colors.white,
          padding: const EdgeInsets.symmetric(vertical: 14),
          textStyle: const TextStyle(fontSize: 16),
        ),
      ),
    );
  }

  Widget _buildTransactionList() {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const Padding(
          padding: EdgeInsets.symmetric(vertical: 8),
          child: Text(
            'Transaction History',
            style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
          ),
        ),
        if (_transactions.isEmpty)
          Card(
            child: Padding(
              padding: const EdgeInsets.all(24),
              child: Center(
                child: Text(
                  'No transactions yet',
                  style: TextStyle(color: Colors.grey.shade600),
                ),
              ),
            ),
          )
        else
          Card(
            child: ListView.separated(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              itemCount: _transactions.length,
              separatorBuilder: (_, __) => const Divider(height: 1),
              itemBuilder: (context, index) =>
                  _buildTransactionRow(_transactions[index]),
            ),
          ),
      ],
    );
  }

  Widget _buildTransactionRow(WalletTransaction txn) {
    final isCredit = txn.chargedUsd < 0;
    return ListTile(
      dense: true,
      leading: Icon(
        txn.cacheHit
            ? Icons.cloud_download_outlined
            : isCredit
                ? Icons.add_circle
                : Icons.remove_circle_outline,
        color: txn.cacheHit
            ? Colors.grey
            : isCredit
                ? Colors.green
                : Colors.blue.shade700,
        size: 20,
      ),
      title: Text(
        txn.description,
        style: TextStyle(
          fontSize: 14,
          color: txn.cacheHit ? Colors.grey.shade600 : null,
        ),
      ),
      subtitle: Text(
        _formatDate(txn.createdAt),
        style: const TextStyle(fontSize: 11),
      ),
      trailing: Text(
        txn.cacheHit
            ? '\$0.00'
            : isCredit
                ? '+\$${txn.chargedUsd.abs().toStringAsFixed(2)}'
                : '−\$${txn.chargedUsd.toStringAsFixed(2)}',
        style: TextStyle(
          fontSize: 14,
          fontWeight: FontWeight.w600,
          color: txn.cacheHit
              ? Colors.grey
              : isCredit
                  ? Colors.green
                  : Colors.black87,
        ),
      ),
    );
  }

  Widget _buildSpendChip(String label, String value) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: Colors.blue.shade50,
        borderRadius: BorderRadius.circular(16),
      ),
      child: Text('$label: $value',
          style: TextStyle(fontSize: 13, color: Colors.blue.shade700)),
    );
  }

  String _planDisplayName(String plan) {
    switch (plan) {
      case 'pay_per_use':
        return 'Pay-Per-Use';
      case 'unlimited':
        return 'Unlimited';
      default:
        return 'Free';
    }
  }

  IconData _planIcon(String plan) {
    switch (plan) {
      case 'pay_per_use':
        return Icons.account_balance_wallet;
      case 'unlimited':
        return Icons.all_inclusive;
      default:
        return Icons.person_outline;
    }
  }

  Color _planColor(String plan) {
    switch (plan) {
      case 'pay_per_use':
        return Colors.green;
      case 'unlimited':
        return Colors.blue;
      default:
        return Colors.grey;
    }
  }

  String _planSubtitle(WalletData wallet) {
    final start = '${wallet.periodStart.month}/${wallet.periodStart.day}';
    final end = '${wallet.periodEnd.month}/${wallet.periodEnd.day}';
    return 'Period: $start – $end';
  }

  String _formatDate(DateTime dt) {
    final now = DateTime.now();
    final diff = now.difference(dt);
    if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
    if (diff.inHours < 24) return '${diff.inHours}h ago';
    if (diff.inDays < 7) return '${diff.inDays}d ago';
    return '${dt.month}/${dt.day}/${dt.year}';
  }
}

/// Low-balance banner widget — embed in other screens
class LowBalanceBanner extends StatelessWidget {
  final VoidCallback onTopUp;

  const LowBalanceBanner({super.key, required this.onTopUp});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 10),
      decoration: BoxDecoration(
        color: Colors.orange.shade50,
        border: Border(
          bottom: BorderSide(color: Colors.orange.shade200),
        ),
      ),
      child: Row(
        children: [
          Icon(Icons.warning_amber_rounded,
              color: Colors.orange.shade700, size: 20),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              'Low balance — top up to keep generating',
              style: TextStyle(
                  fontSize: 13, color: Colors.orange.shade900),
            ),
          ),
          TextButton(
            onPressed: onTopUp,
            style: TextButton.styleFrom(
              backgroundColor: Colors.orange,
              foregroundColor: Colors.white,
              padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
              minimumSize: Size.zero,
              tapTargetSize: MaterialTapTargetSize.shrinkWrap,
            ),
            child: const Text('Top Up', style: TextStyle(fontSize: 12)),
          ),
        ],
      ),
    );
  }
}

/// Paywall / upgrade screen — plan comparison + purchase
class PaywallScreen extends StatefulWidget {
  const PaywallScreen({super.key});

  @override
  State<PaywallScreen> createState() => _PaywallScreenState();
}

class _PaywallScreenState extends State<PaywallScreen> {
  List<AvailablePlan> _plans = [];
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadPlans();
  }

  Future<void> _loadPlans() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final plans = await WalletService.getAvailablePlans();
      if (mounted) {
        setState(() {
          _plans = plans;
          _isLoading = false;
        });
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _error = e.toString();
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Choose a Plan'),
        backgroundColor: const Color(0xFF2c3e50),
        foregroundColor: Colors.white,
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
              ? Center(child: Text('Error: $_error'))
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    const Padding(
                      padding: EdgeInsets.only(bottom: 16),
                      child: Text(
                        'Pick the plan that fits how you explore',
                        style: TextStyle(fontSize: 16),
                        textAlign: TextAlign.center,
                      ),
                    ),
                    ..._plans.map(_buildPlanCard),
                    const SizedBox(height: 24),
                    Center(
                      child: TextButton(
                        onPressed: _restorePurchases,
                        child: const Text('Restore Purchases'),
                      ),
                    ),
                  ],
                ),
    );
  }

  Widget _buildPlanCard(AvailablePlan plan) {
    final isHighlighted = plan.planId == 'pay_per_use';
    return Card(
      elevation: isHighlighted ? 4 : 1,
      margin: const EdgeInsets.only(bottom: 12),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(12),
        side: isHighlighted
            ? const BorderSide(color: Colors.green, width: 2)
            : BorderSide.none,
      ),
      child: Padding(
        padding: const EdgeInsets.all(20),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Text(
                  plan.displayName,
                  style: const TextStyle(
                      fontSize: 20, fontWeight: FontWeight.bold),
                ),
                if (isHighlighted) ...[
                  const SizedBox(width: 8),
                  Container(
                    padding:
                        const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                    decoration: BoxDecoration(
                      color: Colors.green.shade100,
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Text('Popular',
                        style: TextStyle(
                            fontSize: 11,
                            color: Colors.green,
                            fontWeight: FontWeight.bold)),
                  ),
                ],
              ],
            ),
            const SizedBox(height: 4),
            Text(
              plan.priceUsd == 0
                  ? 'Free forever'
                  : '\$${plan.priceUsd.toStringAsFixed(2)} / ${plan.period}',
              style: TextStyle(fontSize: 16, color: Colors.grey.shade700),
            ),
            const SizedBox(height: 12),
            ...plan.features.map((f) => Padding(
                  padding: const EdgeInsets.only(bottom: 6),
                  child: Row(
                    children: [
                      const Icon(Icons.check_circle,
                          size: 16, color: Colors.green),
                      const SizedBox(width: 8),
                      Expanded(
                          child:
                              Text(f, style: const TextStyle(fontSize: 14))),
                    ],
                  ),
                )),
            const SizedBox(height: 12),
            if (plan.planId != 'free')
              SizedBox(
                width: double.infinity,
                child: ElevatedButton(
                  onPressed: () => _subscribe(plan),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: isHighlighted
                        ? Colors.green
                        : const Color(0xFF2c3e50),
                    foregroundColor: Colors.white,
                  ),
                  child: Text('Subscribe to ${plan.displayName}'),
                ),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _subscribe(AvailablePlan plan) async {
    // In production this would go through RevenueCat / StoreKit.
    // For now, show a placeholder.
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(
            'Purchase flow for ${plan.displayName} — requires App Store configuration'),
        backgroundColor: Colors.blue,
      ),
    );
  }

  Future<void> _restorePurchases() async {
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Restoring purchases…'),
        backgroundColor: Colors.blue,
      ),
    );
    // In production: RevenueCat.restorePurchases()
    await Future.delayed(const Duration(seconds: 1));
    if (mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('No previous purchases found'),
          backgroundColor: Colors.grey,
        ),
      );
    }
  }
}
