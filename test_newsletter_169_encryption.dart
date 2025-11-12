import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

/// Test encryption for newsletter ID 169 with real credentials
/// Simulates mobile app encrypting 'Misha'/'kapustA77' for Services verification
void main() {
  print('=== NEWSLETTER 169 CREDENTIAL ENCRYPTION TEST ===');
  testNewsletter169Encryption();
}

void testNewsletter169Encryption() {
  // Simulate server public key that would be provided for newsletter 169
  // This represents what Services would send to mobile app
  final serverPublicKeyHex = '0x' + 
    'A1B2C3D4E5F6789012345678901234567890ABCDEF1234567890ABCDEF123456' +
    '7890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF123456' +
    '7890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF123456' +
    '7890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF123456' +
    '7890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF123456' +
    '7890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF123456' +
    '7890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF123456' +
    '7890ABCDEF1234567890ABCDEF1234567890ABCDEF1234567890ABCDEF123456';
  
  print('NEWSLETTER 169: Simulating key exchange with server public key');
  print('Server public key (first 40 chars): ${serverPublicKeyHex.substring(0, 40)}...');
  
  // Perform Diffie-Hellman key exchange (simulating mobile app process)
  final keyExchangeResult = performKeyExchange(serverPublicKeyHex);
  if (keyExchangeResult == null) {
    print('❌ Key exchange failed');
    return;
  }
  
  final clientPublicKey = keyExchangeResult['client_public_key']!;
  final aesKey = keyExchangeResult['aes_key']!;
  
  print('NEWSLETTER 169: Key exchange successful');
  print('Client public key (first 40 chars): ${clientPublicKey.substring(0, 40)}...');
  print('Derived AES key: $aesKey');
  
  // Test credentials for newsletter 169
  const username = 'Misha';
  const password = 'kapustA77';
  const domain = 'newsletter169.example.com';
  const articleId = 'article_169_001';
  const deviceId = 'mobile_device_12345';
  
  print('');
  print('NEWSLETTER 169: Encrypting credentials');
  print('Username: "$username"');
  print('Password: "$password"');
  print('Domain: "$domain"');
  
  // Encrypt credentials using derived AES key
  final aesKeyBytes = base64.decode(aesKey);
  final encryptedUsername = encryptAES(username, aesKeyBytes);
  final encryptedPassword = encryptAES(password, aesKeyBytes);
  
  print('Encrypted username: $encryptedUsername');
  print('Encrypted password: $encryptedPassword');
  
  // Generate JSON that mobile app would send to Services
  final credentialSubmissionJson = {
    'article_id': articleId,
    'mobile_public_key': clientPublicKey,
    'encrypted_username': encryptedUsername,
    'encrypted_password': encryptedPassword,
    'device_id': deviceId,
    'domain': domain,
  };
  
  print('');
  print('=== MOBILE APP JSON FOR SERVICES (NEWSLETTER 169) ===');
  print(JsonEncoder.withIndent('  ').convert(credentialSubmissionJson));
  
  print('');
  print('=== FOR SERVICES AMAZON-Q VERIFICATION ===');
  print('Newsletter ID: 169');
  print('Expected decrypted username: "$username"');
  print('Expected decrypted password: "$password"');
  print('Client public key for DH calculation: $clientPublicKey');
  print('');
  print('Services should:');
  print('1. Use client public key to calculate same shared secret');
  print('2. Derive same AES key: $aesKey');
  print('3. Decrypt credentials to get: "$username" / "$password"');
  print('');
  print('✅ NEWSLETTER 169 ENCRYPTION TEST COMPLETE');
}

/// Perform Diffie-Hellman key exchange (simulating mobile app)
Map<String, String>? performKeyExchange(String serverPublicKeyHex) {
  try {
    // RFC 3526 Group 14 parameters (2048-bit)
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
    
    // Generate mobile private key (256-bit)
    final random = Random.secure();
    final privateKey = generateSecurePrivateKey(random);
    
    // Generate mobile public key: g^privateKey mod p
    final publicKey = generator.modPow(privateKey, prime);
    
    // Parse server public key (remove 0x prefix)
    final cleanHex = serverPublicKeyHex.startsWith('0x') 
        ? serverPublicKeyHex.substring(2) 
        : serverPublicKeyHex;
    final serverPublicKey = BigInt.parse(cleanHex, radix: 16);
    
    // Calculate shared secret: serverPublicKey^privateKey mod p
    final sharedSecret = serverPublicKey.modPow(privateKey, prime);
    
    // Derive AES key using SECURE method (full entropy)
    final sharedSecretBytes = bigIntToFullBytes(sharedSecret);
    final digest = sha256.convert(sharedSecretBytes);
    final aesKey = base64.encode(digest.bytes.take(16).toList());
    
    return {
      'client_public_key': publicKey.toRadixString(16),
      'aes_key': aesKey,
    };
  } catch (e) {
    print('Key exchange error: $e');
    return null;
  }
}

/// Generate cryptographically secure private key
BigInt generateSecurePrivateKey(Random random) {
  final bytes = Uint8List(32);
  for (int i = 0; i < 32; i++) {
    bytes[i] = random.nextInt(256);
  }
  return bytesToBigInt(bytes);
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

/// Convert bytes to BigInt
BigInt bytesToBigInt(Uint8List bytes) {
  BigInt result = BigInt.zero;
  for (int i = 0; i < bytes.length; i++) {
    result = (result << 8) + BigInt.from(bytes[i]);
  }
  return result;
}

/// AES-128-CBC encryption with PKCS7 padding
String encryptAES(String plaintext, Uint8List key) {
  // Generate random IV (16 bytes)
  final random = Random.secure();
  final iv = Uint8List.fromList(List.generate(16, (i) => random.nextInt(256)));
  
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