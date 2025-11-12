import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

/// Standalone test to verify mobile app encryption matches Services expectations
void main() {
  print('=== MOBILE APP ENCRYPTION TEST ===');
  
  // Test with the shared secret from Services
  final sharedSecret = BigInt.parse('376247706963695395655942410089832014385902292525619568738686307803236121300817324410794408994386117655280655842515751417256970207265621256134942126115810316027345450459417783218550341441497105925164381448417501339371554553966138478663002876245166881627654080154690541380769471364388529300386342332010061414234026059573997842463866452263604972411909941391123343686254395125117539536474863775225819210454953763922120536098726031647823255111006583630959683070231072699651120677353889508319492868795993107305252766924799681465763844483377584228037024984598407941217312092860640036678370991632954542927205910798727860164');
  
  // Derive AES key exactly like mobile app
  final sharedSecretBytes = _bigIntToBytes(sharedSecret, 32);
  print('Shared secret bytes: ${sharedSecretBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  
  final digest = sha256.convert(sharedSecretBytes);
  final aesKey = Uint8List.fromList(digest.bytes.take(16).toList());
  print('AES key: ${aesKey.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  
  // Test encryption with hardcoded values
  final testUsername = 'testuser123';
  final testPassword = 'testpass456';
  
  print('\n=== ENCRYPTING TEST CREDENTIALS ===');
  final encryptedUsername = _encryptAES(testUsername, aesKey);
  final encryptedPassword = _encryptAES(testPassword, aesKey);
  
  print('Test username: "$testUsername"');
  print('Test password: "$testPassword"');
  print('Encrypted username: $encryptedUsername');
  print('Encrypted password: $encryptedPassword');
  
  // Verify decryption works
  print('\n=== VERIFYING DECRYPTION ===');
  final decryptedUsername = _decryptAES(encryptedUsername, aesKey);
  final decryptedPassword = _decryptAES(encryptedPassword, aesKey);
  
  print('Decrypted username: "$decryptedUsername"');
  print('Decrypted password: "$decryptedPassword"');
  
  final usernameMatch = decryptedUsername == testUsername;
  final passwordMatch = decryptedPassword == testPassword;
  
  print('\n=== RESULTS ===');
  print('Username match: $usernameMatch');
  print('Password match: $passwordMatch');
  print('Overall success: ${usernameMatch && passwordMatch}');
  
  if (usernameMatch && passwordMatch) {
    print('\n✅ ENCRYPTION TEST PASSED - Mobile app encryption is working correctly');
    print('Services should be able to decrypt these values:');
    print('- encrypted_username: $encryptedUsername');
    print('- encrypted_password: $encryptedPassword');
  } else {
    print('\n❌ ENCRYPTION TEST FAILED - There is an issue with the encryption/decryption');
  }
}

/// Convert BigInt to bytes with specified length
Uint8List _bigIntToBytes(BigInt bigInt, int length) {
  final hex = bigInt.toRadixString(16);
  final paddedHex = hex.padLeft(length * 2, '0');
  final bytes = <int>[];
  
  for (int i = 0; i < paddedHex.length; i += 2) {
    bytes.add(int.parse(paddedHex.substring(i, i + 2), radix: 16));
  }
  
  return Uint8List.fromList(bytes.take(length).toList());
}

/// AES-128-CBC encryption exactly like mobile app
String _encryptAES(String plaintext, Uint8List key) {
  print('Encrypting: "$plaintext" (length: ${plaintext.length})');
  
  // Generate random IV (16 bytes)
  final random = Random.secure();
  final iv = Uint8List.fromList(List.generate(16, (i) => random.nextInt(256)));
  print('IV: ${iv.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  
  // Setup AES-CBC cipher
  final cipher = CBCBlockCipher(AESEngine());
  final params = ParametersWithIV(KeyParameter(key), iv);
  cipher.init(true, params);
  
  // Add PKCS7 padding
  final plaintextBytes = utf8.encode(plaintext);
  final paddedPlaintext = _addPKCS7Padding(plaintextBytes, 16);
  print('Padded length: ${paddedPlaintext.length}');
  
  // Encrypt
  final encrypted = Uint8List(paddedPlaintext.length);
  var offset = 0;
  while (offset < paddedPlaintext.length) {
    offset += cipher.processBlock(paddedPlaintext, offset, encrypted, offset);
  }
  
  // Return Base64(IV + Encrypted)
  final combined = Uint8List.fromList([...iv, ...encrypted]);
  final result = base64.encode(combined);
  print('Encrypted result: $result');
  return result;
}

/// Decrypt for verification
String _decryptAES(String encryptedBase64, Uint8List key) {
  final combined = base64.decode(encryptedBase64);
  final iv = combined.sublist(0, 16);
  final encrypted = combined.sublist(16);
  
  final cipher = CBCBlockCipher(AESEngine());
  final params = ParametersWithIV(KeyParameter(key), iv);
  cipher.init(false, params);
  
  final decrypted = Uint8List(encrypted.length);
  var offset = 0;
  while (offset < encrypted.length) {
    offset += cipher.processBlock(encrypted, offset, decrypted, offset);
  }
  
  // Remove PKCS7 padding
  final paddingLength = decrypted.last;
  final plaintext = decrypted.sublist(0, decrypted.length - paddingLength);
  
  return utf8.decode(plaintext);
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