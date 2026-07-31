import 'dart:convert';
import 'package:shared_preferences/shared_preferences.dart';
import '../config/endpoints.dart';

/// Whether to use the mock wallet API instead of the real backend.
/// Set to false when the backend is deployed and ready.
const bool useMockWallet = true;

/// Wallet data model
class WalletData {
  final String plan; // 'free', 'pay_per_use', 'unlimited'
  final double balanceUsd;
  final double periodSpendUsd;
  final DateTime periodStart;
  final DateTime periodEnd;
  final CostStopProgress? costStopProgress;
  final bool lowBalance;

  WalletData({
    required this.plan,
    required this.balanceUsd,
    required this.periodSpendUsd,
    required this.periodStart,
    required this.periodEnd,
    this.costStopProgress,
    required this.lowBalance,
  });

  factory WalletData.fromJson(Map<String, dynamic> json) {
    return WalletData(
      plan: json['plan'] as String,
      balanceUsd: (json['balance_usd'] as num).toDouble(),
      periodSpendUsd: (json['period_spend_usd'] as num).toDouble(),
      periodStart: DateTime.parse(json['period_start'] as String),
      periodEnd: DateTime.parse(json['period_end'] as String),
      costStopProgress: json['cost_stop_progress'] != null
          ? CostStopProgress.fromJson(
              json['cost_stop_progress'] as Map<String, dynamic>)
          : null,
      lowBalance: json['low_balance'] as bool,
    );
  }
}

class CostStopProgress {
  final double usedUsd;
  final double limitUsd;

  CostStopProgress({required this.usedUsd, required this.limitUsd});

  factory CostStopProgress.fromJson(Map<String, dynamic> json) {
    return CostStopProgress(
      usedUsd: (json['used_usd'] as num).toDouble(),
      limitUsd: (json['limit_usd'] as num).toDouble(),
    );
  }

  double get progressFraction =>
      limitUsd > 0 ? (usedUsd / limitUsd).clamp(0.0, 1.0) : 0.0;
}

/// Transaction data model
class WalletTransaction {
  final String id;
  final DateTime createdAt;
  final String operationType;
  final String description;
  final double chargedUsd;
  final bool cacheHit;

  WalletTransaction({
    required this.id,
    required this.createdAt,
    required this.operationType,
    required this.description,
    required this.chargedUsd,
    required this.cacheHit,
  });

  factory WalletTransaction.fromJson(Map<String, dynamic> json) {
    return WalletTransaction(
      id: json['id'] as String,
      createdAt: DateTime.parse(json['created_at'] as String),
      operationType: json['operation_type'] as String,
      description: json['description'] as String,
      chargedUsd: (json['charged_usd'] as num).toDouble(),
      cacheHit: json['cache_hit'] as bool,
    );
  }
}

/// Available plan data model
class AvailablePlan {
  final String planId;
  final String displayName;
  final double priceUsd;
  final String period;
  final List<String> features;

  AvailablePlan({
    required this.planId,
    required this.displayName,
    required this.priceUsd,
    required this.period,
    required this.features,
  });

  factory AvailablePlan.fromJson(Map<String, dynamic> json) {
    return AvailablePlan(
      planId: json['plan_id'] as String,
      displayName: json['display_name'] as String,
      priceUsd: (json['price_usd'] as num).toDouble(),
      period: json['period'] as String,
      features: List<String>.from(json['features'] as List),
    );
  }
}

/// Top-up result
class TopUpResult {
  final String status;
  final double newBalanceUsd;

  TopUpResult({required this.status, required this.newBalanceUsd});

  factory TopUpResult.fromJson(Map<String, dynamic> json) {
    return TopUpResult(
      status: json['status'] as String,
      newBalanceUsd: (json['new_balance_usd'] as num).toDouble(),
    );
  }
}

/// Wallet service — fetches wallet data from the API or mock
class WalletService {
  static Future<String> _getUserId() async {
    final prefs = await SharedPreferences.getInstance();
    return prefs.getString('user_id') ?? 'unknown';
  }

  /// Get wallet data for the current user
  static Future<WalletData> getWallet() async {
    if (useMockWallet) return _MockWalletBackend.getWallet();

    final userId = await _getUserId();
    final response = await Endpoints.get(
      Service.orchestrator,
      '/wallet/$userId',
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode == 200) {
      return WalletData.fromJson(jsonDecode(response.body));
    }
    throw Exception('Failed to fetch wallet: ${response.statusCode}');
  }

  /// Get transaction history
  static Future<List<WalletTransaction>> getTransactions({int limit = 50}) async {
    if (useMockWallet) return _MockWalletBackend.getTransactions(limit: limit);

    final userId = await _getUserId();
    final response = await Endpoints.get(
      Service.orchestrator,
      '/wallet/$userId/transactions?limit=$limit',
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((e) => WalletTransaction.fromJson(e)).toList();
    }
    throw Exception('Failed to fetch transactions: ${response.statusCode}');
  }

  /// Get available plans
  static Future<List<AvailablePlan>> getAvailablePlans() async {
    if (useMockWallet) return _MockWalletBackend.getAvailablePlans();

    final response = await Endpoints.get(
      Service.orchestrator,
      '/plans/available',
      timeout: const Duration(seconds: 10),
    );
    if (response.statusCode == 200) {
      final List<dynamic> data = jsonDecode(response.body);
      return data.map((e) => AvailablePlan.fromJson(e)).toList();
    }
    throw Exception('Failed to fetch plans: ${response.statusCode}');
  }

  /// Top up balance (Pay-Per-Use)
  static Future<TopUpResult> topUp(String productId) async {
    if (useMockWallet) return _MockWalletBackend.topUp(productId);

    final userId = await _getUserId();
    final response = await Endpoints.post(
      Service.orchestrator,
      '/wallet/$userId/topup',
      body: {'product_id': productId},
      timeout: const Duration(seconds: 15),
    );
    if (response.statusCode == 200) {
      return TopUpResult.fromJson(jsonDecode(response.body));
    }
    throw Exception('Top-up failed: ${response.statusCode}');
  }
}

/// Mock wallet backend for development/demo
class _MockWalletBackend {
  // Switch between mock scenarios by changing this value
  static String _mockPlan = 'pay_per_use'; // 'free', 'pay_per_use', 'unlimited'
  static double _mockBalance = 7.45;

  static Future<WalletData> getWallet() async {
    await Future.delayed(const Duration(milliseconds: 300));
    final now = DateTime.now();
    final periodStart = DateTime(now.year, now.month, 1);
    final periodEnd = DateTime(now.year, now.month + 1, 0);

    switch (_mockPlan) {
      case 'free':
        return WalletData(
          plan: 'free',
          balanceUsd: 0.0,
          periodSpendUsd: 0.0,
          periodStart: periodStart,
          periodEnd: periodEnd,
          costStopProgress: null,
          lowBalance: false,
        );
      case 'unlimited':
        return WalletData(
          plan: 'unlimited',
          balanceUsd: 0.0,
          periodSpendUsd: 18.75,
          periodStart: periodStart,
          periodEnd: periodEnd,
          costStopProgress: CostStopProgress(usedUsd: 18.75, limitUsd: 25.0),
          lowBalance: false,
        );
      default: // pay_per_use
        return WalletData(
          plan: 'pay_per_use',
          balanceUsd: _mockBalance,
          periodSpendUsd: 2.55,
          periodStart: periodStart,
          periodEnd: periodEnd,
          costStopProgress: null,
          lowBalance: _mockBalance < 2.0,
        );
    }
  }

  static Future<List<WalletTransaction>> getTransactions({int limit = 50}) async {
    await Future.delayed(const Duration(milliseconds: 200));
    final now = DateTime.now();
    return [
      WalletTransaction(
        id: 'txn_001',
        createdAt: now.subtract(const Duration(hours: 2)),
        operationType: 'tour_generate',
        description: 'Tour: French Riviera biking',
        chargedUsd: 0.35,
        cacheHit: false,
      ),
      WalletTransaction(
        id: 'txn_002',
        createdAt: now.subtract(const Duration(hours: 5)),
        operationType: 'tour_download',
        description: 'Downloaded — no charge',
        chargedUsd: 0.00,
        cacheHit: true,
      ),
      WalletTransaction(
        id: 'txn_003',
        createdAt: now.subtract(const Duration(days: 1)),
        operationType: 'tour_generate',
        description: 'Tour: Historic Boston walking',
        chargedUsd: 0.45,
        cacheHit: false,
      ),
      WalletTransaction(
        id: 'txn_004',
        createdAt: now.subtract(const Duration(days: 1, hours: 3)),
        operationType: 'tour_translate',
        description: 'Translation: Uffizi Gallery → French',
        chargedUsd: 0.25,
        cacheHit: false,
      ),
      WalletTransaction(
        id: 'txn_005',
        createdAt: now.subtract(const Duration(days: 2)),
        operationType: 'news_generate',
        description: 'News article: Boston Globe',
        chargedUsd: 0.15,
        cacheHit: false,
      ),
      WalletTransaction(
        id: 'txn_006',
        createdAt: now.subtract(const Duration(days: 2, hours: 4)),
        operationType: 'tour_download',
        description: 'Downloaded — no charge',
        chargedUsd: 0.00,
        cacheHit: true,
      ),
      WalletTransaction(
        id: 'txn_007',
        createdAt: now.subtract(const Duration(days: 3)),
        operationType: 'tour_generate',
        description: 'Tour: Cambridge bookshop trail',
        chargedUsd: 0.40,
        cacheHit: false,
      ),
      WalletTransaction(
        id: 'txn_008',
        createdAt: now.subtract(const Duration(days: 3, hours: 6)),
        operationType: 'topup',
        description: 'Credit top-up',
        chargedUsd: -10.00,
        cacheHit: false,
      ),
      WalletTransaction(
        id: 'txn_009',
        createdAt: now.subtract(const Duration(days: 4)),
        operationType: 'tour_generate',
        description: 'Tour: Nice Matisse Museum',
        chargedUsd: 0.55,
        cacheHit: false,
      ),
      WalletTransaction(
        id: 'txn_010',
        createdAt: now.subtract(const Duration(days: 5)),
        operationType: 'tour_download',
        description: 'Downloaded — no charge',
        chargedUsd: 0.00,
        cacheHit: true,
      ),
    ];
  }

  static Future<List<AvailablePlan>> getAvailablePlans() async {
    await Future.delayed(const Duration(milliseconds: 200));
    return [
      AvailablePlan(
        planId: 'free',
        displayName: 'Free',
        priceUsd: 0.0,
        period: 'forever',
        features: [
          'Browse pre-made tours',
          'Limited tour downloads',
        ],
      ),
      AvailablePlan(
        planId: 'pay_per_use',
        displayName: 'Pay-Per-Use',
        priceUsd: 2.0,
        period: 'month',
        features: [
          'Unlimited tour generation',
          'Unlimited news articles',
          'Pay only for what you use',
          'Credits never expire',
        ],
      ),
      AvailablePlan(
        planId: 'unlimited',
        displayName: 'Unlimited',
        priceUsd: 50.0,
        period: 'month',
        features: [
          'Unlimited tour generation',
          'Unlimited news articles',
          'No per-use charges',
          'Priority processing',
          'All future features included',
        ],
      ),
    ];
  }

  static Future<TopUpResult> topUp(String productId) async {
    await Future.delayed(const Duration(milliseconds: 500));
    _mockBalance += 10.0;
    return TopUpResult(status: 'success', newBalanceUsd: _mockBalance);
  }

  /// For testing: switch the mock plan
  static void setMockPlan(String plan) {
    _mockPlan = plan;
  }

  /// For testing: set mock balance
  static void setMockBalance(double balance) {
    _mockBalance = balance;
  }
}

/// Test helpers for widget tests — only effective when useMockWallet = true
class WalletTestHelper {
  /// Set mock plan for testing. One of: 'free', 'pay_per_use', 'unlimited'
  static void setMockPlan(String plan) {
    _MockWalletBackend.setMockPlan(plan);
  }

  /// Set mock balance for testing
  static void setMockBalance(double balance) {
    _MockWalletBackend.setMockBalance(balance);
  }

  /// Reset to defaults
  static void reset() {
    _MockWalletBackend.setMockPlan('pay_per_use');
    _MockWalletBackend.setMockBalance(7.45);
  }
}
