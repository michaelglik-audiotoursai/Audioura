import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

/// Standalone test program for SECURE encryption with full entropy (FIXED)
/// Tests the corrected implementation that Services Amazon-Q requested
void main() {
  print('=== MOBILE SECURE ENCRYPTION TEST - FIXED IMPLEMENTATION ===');
  testSecureEncryptionFixed();
}

void testSecureEncryptionFixed() {
  // Hardcoded shared secret for testing (2048-bit for full entropy)
  final sharedSecret = BigInt.parse('28948022309329048855892746252171976963363056481941560715954676764349967630336681010609640529444940815536843274168395390471154239097247229931393532337616161');
  
  print('MOBILE SECURE TEST: Starting FIXED secure encryption test...');
  print('MOBILE SECURE TEST: Shared secret bit length: ${sharedSecret.bitLength}');
  
  // SECURE METHOD: Use full shared secret (no truncation) - FIXED
  final sharedSecretBytes = _bigIntToFullBytes(sharedSecret);
  print('MOBILE SECURE TEST: Shared secret byte length: ${sharedSecretBytes.length}');
  print('MOBILE SECURE TEST: SECURE METHOD - NO TRUNCATION, FULL ENTROPY');
  
  // Derive AES key using SHA-256 of full shared secret
  final digest = sha256.convert(sharedSecretBytes);
  final aesKey = Uint8List.fromList(digest.bytes.take(16).toList());
  
  print('MOBILE SECURE TEST: SHA-256 hash (32 bytes): ${digest.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  print('MOBILE SECURE TEST: AES-128 key (16 bytes): ${aesKey.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  
  // Verify we get the expected secure key (Services expects this exact key)
  final expectedKey = 'b627c9429ce1627a56c55493f335f3a6';
  final actualKey = aesKey.map((b) => b.toRadixString(16).padLeft(2, '0')).join('');
  
  print('');
  print('KEY VERIFICATION:');
  print('Expected secure AES key: $expectedKey');
  print('Actual AES key:          $actualKey');
  print('Keys match: ${actualKey == expectedKey}');
  
  if (actualKey != expectedKey) {
    print('❌ CRITICAL ERROR: Mobile not generating expected secure key');
    print('❌ This means the secure method is not implemented correctly');
    return;
  }
  
  print('✅ SUCCESS: Mobile generating correct secure AES key');
  print('✅ This confirms the secure method is working correctly');
  
  // Test credentials
  const username = 'testuser123';
  const password = 'testpass456';
  
  print('');
  print('CREDENTIAL ENCRYPTION:');
  print('MOBILE SECURE TEST: Username: "$username"');
  print('MOBILE SECURE TEST: Password: "$password"');
  
  // Encrypt using AES-128-CBC with secure key
  final encryptedUsername = _encryptAES(username, aesKey);
  final encryptedPassword = _encryptAES(password, aesKey);
  
  print('MOBILE SECURE TEST: Encrypted username: $encryptedUsername');
  print('MOBILE SECURE TEST: Encrypted password: $encryptedPassword');
  
  print('');
  print('=== FOR SERVICES TESTING (SECURE METHOD) ===');
  print('Services Amazon-Q: Copy these values into your Python test:');
  print('');
  print('encrypted_username = "$encryptedUsername"');
  print('encrypted_password = "$encryptedPassword"');
  print('');
  print('Expected decryption results:');
  print('username = "$username"');
  print('password = "$password"');
  print('expected_aes_key = "$expectedKey"');
  print('');
  print('If Services gets these exact results, the secure method is working!');
  print('');
  print('✅ MOBILE SECURE ENCRYPTION TEST COMPLETE');
  print('✅ Ready for Services compatibility verification');
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
  
  final result = Uint8List.fromList(bytes);
  
  // Debug: Confirm we're using full bytes
  print('SECURE DEBUG: BigInt to full bytes conversion:');
  print('SECURE DEBUG: Input BigInt bit length: ${bigInt.bitLength}');
  print('SECURE DEBUG: Output byte array length: ${result.length} bytes');
  print('SECURE DEBUG: NO TRUNCATION - using full entropy');
  
  return result;
}

/// AES-128-CBC encryption with PKCS7 padding (same as production)
String _encryptAES(String plaintext, Uint8List key) {
  print('AES DEBUG: Encrypting "$plaintext" with secure key');
  
  // Generate random IV (16 bytes)
  final random = Random.secure();
  final iv = Uint8List.fromList(List.generate(16, (i) => random.nextInt(256)));
  print('AES DEBUG: Generated IV: ${iv.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  
  // Setup AES-CBC cipher
  final cipher = CBCBlockCipher(AESEngine());
  final params = ParametersWithIV(KeyParameter(key), iv);
  cipher.init(true, params);
  
  // Add PKCS7 padding
  final plaintextBytes = utf8.encode(plaintext);
  final paddedPlaintext = _addPKCS7Padding(plaintextBytes, 16);
  print('AES DEBUG: Padded plaintext length: ${paddedPlaintext.length} bytes');
  
  // Encrypt
  final encrypted = Uint8List(paddedPlaintext.length);
  var offset = 0;
  while (offset < paddedPlaintext.length) {
    offset += cipher.processBlock(paddedPlaintext, offset, encrypted, offset);
  }
  
  // Return Base64(IV + Encrypted)
  final combined = Uint8List.fromList([...iv, ...encrypted]);
  final result = base64.encode(combined);
  print('AES DEBUG: Final encrypted result: $result');
  
  return result;
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