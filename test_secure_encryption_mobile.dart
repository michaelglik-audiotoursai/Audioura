import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

/// Standalone test program for secure encryption with full entropy
/// Tests the SECURE method (no truncation) for Services coordination
void main() {
  print('=== SECURE ENCRYPTION TEST - FULL ENTROPY METHOD ===');
  testSecureEncryption();
}

void testSecureEncryption() {
  // Hardcoded shared secret for testing (same value Services will use)
  final sharedSecret = BigInt.parse(
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '123456789012345678901234567890123456789012345678901234567890'
    '1234567890'
  );
  
  print('MOBILE TEST: Starting secure encryption test...');
  print('MOBILE TEST: Shared secret bit length: ${sharedSecret.bitLength}');
  
  // SECURE METHOD: Use full shared secret (no truncation)
  final sharedSecretBytes = _bigIntToFullBytes(sharedSecret);
  print('MOBILE TEST: Shared secret byte length: ${sharedSecretBytes.length}');
  print('MOBILE TEST: SECURE METHOD - NO TRUNCATION, FULL ENTROPY');
  
  // Derive AES key using SHA-256 of full shared secret
  final digest = sha256.convert(sharedSecretBytes);
  final aesKey = Uint8List.fromList(digest.bytes.take(16).toList());
  
  print('MOBILE TEST: SHA-256 hash (32 bytes): ${digest.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  print('MOBILE TEST: AES-128 key (16 bytes): ${aesKey.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  
  // Test credentials
  const username = 'testuser123';
  const password = 'testpass456';
  
  print('MOBILE TEST: Encrypting credentials...');
  print('MOBILE TEST: Username: "$username"');
  print('MOBILE TEST: Password: "$password"');
  
  // Encrypt using AES-128-CBC
  final encryptedUsername = _encryptAES(username, aesKey);
  final encryptedPassword = _encryptAES(password, aesKey);
  
  print('MOBILE TEST: Encrypted username: $encryptedUsername');
  print('MOBILE TEST: Encrypted password: $encryptedPassword');
  
  print('');
  print('=== FOR SERVICES TESTING ===');
  print('Copy these values into Services Python test:');
  print('encrypted_username = "$encryptedUsername"');
  print('encrypted_password = "$encryptedPassword"');
  print('');
  print('Expected decryption results:');
  print('username = "$username"');
  print('password = "$password"');
  print('');
  print('✅ MOBILE SECURE ENCRYPTION TEST COMPLETE');
}

/// Convert BigInt to full bytes (SECURE - no truncation)
Uint8List _bigIntToFullBytes(BigInt bigInt) {
  if (bigInt == BigInt.zero) return Uint8List.fromList([0]);
  
  final bytes = <int>[];
  var temp = bigInt;
  
  while (temp > BigInt.zero) {
    bytes.insert(0, (temp & BigInt.from(0xff)).toInt());
    temp = temp >> 8;
  }
  
  return Uint8List.fromList(bytes);
}

/// AES-128-CBC encryption with PKCS7 padding
String _encryptAES(String plaintext, Uint8List key) {
  // Generate random IV (16 bytes)
  final random = Random.secure();
  final iv = Uint8List.fromList(List.generate(16, (i) => random.nextInt(256)));
  
  // Setup AES-CBC cipher
  final cipher = CBCBlockCipher(AESEngine());
  final params = ParametersWithIV(KeyParameter(key), iv);
  cipher.init(true, params);
  
  // Add PKCS7 padding
  final plaintextBytes = utf8.encode(plaintext);
  final paddedPlaintext = _addPKCS7Padding(plaintextBytes, 16);
  
  // Encrypt
  final encrypted = Uint8List(paddedPlaintext.length);
  var offset = 0;
  while (offset < paddedPlaintext.length) {
    offset += cipher.processBlock(paddedPlaintext, offset, encrypted, offset);
  }
  
  // Return Base64(IV + Encrypted)
  final combined = Uint8List.fromList([...iv, ...encrypted]);
  return base64.encode(combined);
}

/// Add PKCS7 padding
Uint8List _addPKCS7Padding(List<int> data, int blockSize) {
  final padding = blockSize - (data.length % blockSize);
  final padded = List<int>.from(data);
  for (int i = 0; i < padding; i++) {
    padded.add(padding);
  }
  return Uint8List.fromList(padded);
}