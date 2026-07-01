import 'dart:convert';
import 'dart:io' show Platform;
import 'package:crypto/crypto.dart';
import 'package:flutter/services.dart';
import '../screens/debug_log_viewer_screen.dart';

/// Platform attestation service.
/// Android: Play Integrity API token via MethodChannel.
/// iOS: App Attest assertion via MethodChannel.
/// Returns null if attestation is unavailable (dev/emulator/unsupported).
/// Log-only mode: token is attached but gateway doesn't enforce (observes only).
class AppAttestationService {
  static const _channel = MethodChannel('com.audioura.app/attestation');

  /// Returns a platform-appropriate attestation token tied to [requestBody].
  /// Nonce = SHA-256 of the request body, preventing replay attacks.
  /// Never throws — logs failures and returns null so the request can proceed.
  static Future<String?> getToken(Map<String, dynamic> requestBody) async {
    try {
      final nonce = _generateNonce(requestBody);
      if (Platform.isAndroid) {
        return await _getPlayIntegrityToken(nonce);
      } else if (Platform.isIOS) {
        return await _getAppAttestToken(nonce);
      }
    } catch (e) {
      await DebugLogHelper.addDebugLog('ATTEST: Failed to get token: $e');
    }
    return null;
  }

  /// SHA-256 of the JSON-encoded request body, used as nonce.
  static String _generateNonce(Map<String, dynamic> requestBody) {
    final bodyString = jsonEncode(requestBody);
    final bytes = utf8.encode(bodyString);
    return sha256.convert(bytes).toString();
  }

  /// Android: Play Integrity API token via MethodChannel.
  /// The native Android side (MainActivity.kt) calls the Play Integrity API
  /// and returns the integrity token string.
  static Future<String?> _getPlayIntegrityToken(String nonce) async {
    try {
      final token = await _channel.invokeMethod<String>('getPlayIntegrityToken', {'nonce': nonce});
      if (token != null && token.isNotEmpty) {
        await DebugLogHelper.addDebugLog('ATTEST: Play Integrity token generated (${token.length} bytes)');
        return token;
      }
      await DebugLogHelper.addDebugLog('ATTEST: Play Integrity returned empty/null (device may not support it)');
    } on MissingPluginException {
      await DebugLogHelper.addDebugLog('ATTEST: Play Integrity MethodChannel not registered (native side not implemented yet)');
    } on PlatformException catch (e) {
      await DebugLogHelper.addDebugLog('ATTEST: Play Integrity platform error: ${e.message}');
    }
    return null;
  }

  /// iOS: App Attest assertion via MethodChannel.
  /// The native Swift side (AppAttestHandler.swift) calls DCAppAttestService
  /// and returns a base64-encoded assertion.
  /// MethodChannel contract:
  ///   Channel: 'com.audioura.app/attestation'
  ///   Method: 'getAssertion'
  ///   Args: {'nonce': String}
  ///   Returns: String (base64-encoded assertion) or null
  static Future<String?> _getAppAttestToken(String nonce) async {
    try {
      final token = await _channel.invokeMethod<String>('getAssertion', {'nonce': nonce});
      if (token != null && token.isNotEmpty) {
        await DebugLogHelper.addDebugLog('ATTEST: App Attest assertion generated (${token.length} bytes)');
        return token;
      }
      await DebugLogHelper.addDebugLog('ATTEST: App Attest returned empty/null');
    } on MissingPluginException {
      await DebugLogHelper.addDebugLog('ATTEST: App Attest MethodChannel not registered (native side not implemented yet)');
    } on PlatformException catch (e) {
      await DebugLogHelper.addDebugLog('ATTEST: App Attest platform error: ${e.message}');
    }
    return null;
  }
}
