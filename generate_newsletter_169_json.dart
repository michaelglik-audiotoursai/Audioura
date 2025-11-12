import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

/// Generate actual encrypted JSON for newsletter 169 with Misha/kapustA77
void main() {
  print('=== GENERATING NEWSLETTER 169 JSON WITH REAL ENCRYPTED VALUES ===');
  
  // Fixed values for consistent testing
  final serverPrivateKey = BigInt.parse('123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890123456789012345678901234567890');
  final clientPrivateKey = BigInt.parse('987654321098765432109876543210987654321098765432109876543210987654321098765432109876543210987654321098765432109876543210987654321098765432109876543210987654321098765432109876543210987654321098765432109876543210987654321098765432109876543210987654321098765432109876543210');
  
  // RFC 3526 Group 14 parameters
  final prime = BigInt.parse(
    'FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD1'
    '29024E088A67CC74020BBEA63B139B22514A08798E3404DD'
    'EF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245'
    'E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7ED'
    'EE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3D'
    'C2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F'
    '83655D23DCA3AD961C62F356208552BB9ED529077096966D'
    '670C354E4ABC9804F1746C08CA18217C32905E462E36CE3B'
    'E39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9'
    'DE2BCBF6955817183995497CEA956AE515D2261898FA0510'
    '15728E5A8AACAA68FFFFFFFFFFFFFFFF',
    radix: 16);
  final generator = BigInt.from(2);
  
  // Generate public keys
  final serverPublicKey = generator.modPow(serverPrivateKey, prime);
  final clientPublicKey = generator.modPow(clientPrivateKey, prime);
  
  // Calculate shared secret (both sides get same result)
  final sharedSecret = serverPublicKey.modPow(clientPrivateKey, prime);
  
  print('Shared secret bit length: ${sharedSecret.bitLength}');
  
  // Derive AES key using SECURE method (full entropy)
  final sharedSecretBytes = bigIntToFullBytes(sharedSecret);
  final digest = sha256.convert(sharedSecretBytes);
  final aesKeyBytes = Uint8List.fromList(digest.bytes.take(16).toList());
  
  print('AES key: ${aesKeyBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
  
  // Encrypt credentials with fixed IV for reproducible results
  const username = 'Misha';
  const password = 'kapustA77';
  
  // Use fixed IV for consistent results (in real app, this would be random)
  final fixedIV = Uint8List.fromList([
    0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0,
    0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88
  ]);
  
  final encryptedUsername = encryptAESWithFixedIV(username, aesKeyBytes, fixedIV);
  final encryptedPassword = encryptAESWithFixedIV(password, aesKeyBytes, fixedIV);
  
  // Generate the complete JSON
  final credentialJson = {
    'article_id': 'article_169_001',
    'mobile_public_key': clientPublicKey.toRadixString(16),
    'encrypted_username': encryptedUsername,
    'encrypted_password': encryptedPassword,
    'device_id': 'mobile_device_12345',
    'domain': 'newsletter169.example.com'
  };
  
  print('');
  print('=== NEWSLETTER 169 JSON FOR SERVICES AMAZON-Q ===');
  print(JsonEncoder.withIndent('  ').convert(credentialJson));
  
  print('');
  print('=== VERIFICATION INFO FOR SERVICES ===');
  print('Server private key: ${serverPrivateKey.toRadixString(16)}');
  print('Expected decrypted username: "$username"');
  print('Expected decrypted password: "$password"');
  print('Expected AES key: ${aesKeyBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
}

/// Convert BigInt to full bytes (SECURE - no truncation)
Uint8List bigIntToFullBytes(BigInt bigInt) {
  if (bigInt == BigInt.zero) return Uint8List.fromList([0]);
  
  final bytes = <int>[];
  var temp = bigInt;
  
  while (temp > BigInt.zero) {
    bytes.insert(0, (temp & BigInt.from(0xff)).toInt());
    temp = temp >> 8;
  }
  
  return Uint8List.fromList(bytes);
}

/// AES-128-CBC encryption with fixed IV (for reproducible results)
String encryptAESWithFixedIV(String plaintext, Uint8List key, Uint8List iv) {
  // Setup AES-CBC cipher
  final cipher = CBCBlockCipher(AESEngine());
  final params = ParametersWithIV(KeyParameter(key), iv);
  cipher.init(true, params);
  
  // Add PKCS7 padding
  final plaintextBytes = utf8.encode(plaintext);
  final paddedPlaintext = addPKCS7Padding(plaintextBytes, 16);
  
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
Uint8List addPKCS7Padding(List<int> data, int blockSize) {
  final padding = blockSize - (data.length % blockSize);
  final padded = List<int>.from(data);
  for (int i = 0; i < padding; i++) {
    padded.add(padding);
  }
  return Uint8List.fromList(padded);
}