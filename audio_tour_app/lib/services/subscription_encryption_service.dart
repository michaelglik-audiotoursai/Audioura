import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';
import 'package:flutter_secure_storage/flutter_secure_storage.dart';

class SubscriptionEncryptionService {
  static const _storage = FlutterSecureStorage();
  static const String _keyStorageKey = 'subscription_encryption_key';
  static const String _privateKeyStorageKey = 'dh_private_key';
  static const String _publicKeyStorageKey = 'dh_public_key';
  
  // Diffie-Hellman parameters (RFC 3526 - 2048-bit MODP Group)
  static final BigInt _prime = BigInt.parse(
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
  static final BigInt _generator = BigInt.from(2);
  
  /// Perform Diffie-Hellman key exchange with server
  static Future<Map<String, String>?> performKeyExchange(String serverPublicKeyHex) async {
    try {
      print('🔥 VERSION CHECK: Mobile App v1.2.8+18 - COMPREHENSIVE DEBUG BUILD 🔥');
      print('DH: Starting key exchange with server key: ${serverPublicKeyHex.substring(0, 20)}...');
      
      // Generate private key (256-bit random number)
      final random = Random.secure();
      final privateKey = _generateSecurePrivateKey(random);
      print('DH: Generated private key: ${privateKey.bitLength} bits');
      
      // Generate public key: g^privateKey mod p
      final publicKey = _generator.modPow(privateKey, _prime);
      print('DH: Generated public key: ${publicKey.bitLength} bits');
      
      // Calculate shared secret: serverPublicKey^privateKey mod p
      // Remove 0x prefix if present
      final cleanHex = serverPublicKeyHex.startsWith('0x') ? serverPublicKeyHex.substring(2) : serverPublicKeyHex;
      print('DH: Clean server hex: ${cleanHex.substring(0, 20)}...');
      
      final serverPublicKey = BigInt.parse(cleanHex, radix: 16);
      print('DH: Parsed server key: ${serverPublicKey.bitLength} bits');
      
      final sharedSecret = serverPublicKey.modPow(privateKey, _prime);
      print('DH: Computed shared secret: ${sharedSecret.bitLength} bits');
      
      // DEBUG: Log shared secret details for Services coordination
      print('DEBUG MOBILE: Shared secret BigInt: $sharedSecret');
      print('DEBUG MOBILE: Shared secret bit length: ${sharedSecret.bitLength}');
      
      // SERVICES DEBUG: Log exact calculation inputs
      print('=== SERVICES DEBUG: EXACT CALCULATION VALUES ===');
      print('SERVICES_DEBUG: Server Public Key (hex): ${serverPublicKey.toRadixString(16)}');
      print('SERVICES_DEBUG: Mobile Private Key (hex): ${privateKey.toRadixString(16)}');
      print('SERVICES_DEBUG: Prime P (hex): ${_prime.toRadixString(16)}');
      print('SERVICES_DEBUG: Shared Secret Calculation: serverPublicKey^mobilePrivateKey mod P');
      print('SERVICES_DEBUG: Shared Secret (decimal): $sharedSecret');
      
      // Derive AES key from shared secret using SHA-256 (use full bytes for security)
      final sharedSecretBytes = _bigIntToFullBytes(sharedSecret);
      
      // DEBUG: Log byte conversion details
      print('DEBUG MOBILE: Shared secret byte length: ${sharedSecretBytes.length}');
      print('DEBUG MOBILE: Byte conversion method: _bigIntToFullBytes with NO truncation');
      print('SERVICES_DEBUG: Shared Secret Bytes (${sharedSecretBytes.length} bytes, hex): ${sharedSecretBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      final digest = sha256.convert(sharedSecretBytes);
      
      // DEBUG: Log SHA-256 hash
      print('DEBUG MOBILE: SHA-256 hash (32 bytes): ${digest.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: SHA-256 Full Hash (32 bytes, hex): ${digest.bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      final aesKey = base64.encode(digest.bytes.take(16).toList()); // AES-128
      
      // DEBUG: Log final AES key
      final aesKeyBytes = digest.bytes.take(16).toList();
      print('DEBUG MOBILE: Final AES-128 key (16 bytes): ${aesKeyBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: AES Key (SHA-256 first 16 bytes, hex): ${aesKeyBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: EXACT AES KEY (HEX): ${aesKeyBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('DH: Derived AES key: ${aesKey.substring(0, 8)}...');
      
      // Store keys securely
      await _storage.write(key: _keyStorageKey, value: aesKey);
      await _storage.write(key: _privateKeyStorageKey, value: privateKey.toRadixString(16));
      await _storage.write(key: _publicKeyStorageKey, value: publicKey.toRadixString(16));
      print('DH: Keys stored successfully');
      
      return {
        'client_public_key': publicKey.toRadixString(16),
        'shared_secret_hash': base64.encode(digest.bytes),
      };
    } catch (e, stackTrace) {
      print('Diffie-Hellman key exchange error: $e');
      print('Stack trace: $stackTrace');
      return null;
    }
  }
  
  /// Generate cryptographically secure private key
  static BigInt _generateSecurePrivateKey(Random random) {
    // Generate 256-bit private key
    final bytes = Uint8List(32);
    for (int i = 0; i < 32; i++) {
      bytes[i] = random.nextInt(256);
    }
    return _bytesToBigInt(bytes);
  }
  
  /// Get stored encryption key (SECURE - only from Diffie-Hellman)
  static Future<String?> getStoredKey() async {
    final key = await _storage.read(key: _keyStorageKey);
    
    if (key == null) {
      print('SECURITY: No secure key found - must perform key exchange first');
      return null;
    }
    
    print('SECURITY: Using secure key from Diffie-Hellman exchange');
    return key;
  }
  
  /// Check if encryption key exists
  static Future<bool> hasStoredKey() async {
    final key = await getStoredKey();
    return key != null && key.isNotEmpty;
  }
  
  /// Encrypt credentials using stored AES key
  static Future<Map<String, String>?> encryptCredentials(String username, String password, String domain) async {
    try {
      print('CREDENTIAL_DEBUG: Starting encryption - Username: "$username" (${username.length}), Password: "$password" (${password.length})');
      
      final keyBase64 = await getStoredKey();
      if (keyBase64 == null) {
        throw Exception('No encryption key found');
      }
      
      final key = base64.decode(keyBase64);
      print('CREDENTIAL_DEBUG: AES key: ${key.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: ENCRYPTING WITH AES KEY: ${key.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: USERNAME TO ENCRYPT: "$username"');
      print('SERVICES_DEBUG: PASSWORD TO ENCRYPT: "$password"');
      print('🔥🔥🔥 FINAL_DEBUG: AES=${key.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')} USER=$username PASS=$password 🔥🔥🔥');
      
      final encryptedUsername = _encryptAES(username, key);
      final encryptedPassword = _encryptAES(password, key);
      
      print('CREDENTIAL_DEBUG: Encrypted username: $encryptedUsername');
      print('CREDENTIAL_DEBUG: Encrypted password: $encryptedPassword');
      
      return {
        'encrypted_username': encryptedUsername,
        'encrypted_password': encryptedPassword,
        'domain': domain,
      };
    } catch (e) {
      print('Encryption error: $e');
      return null;
    }
  }
  
  /// Proper AES-128-CBC encryption as required by Services
  static String _encryptAES(String plaintext, Uint8List key) {
    try {
      print('=== ENCRYPTION PROCESS DEBUG ===');
      print('AES_DEBUG: Encrypting plaintext: "$plaintext" (length: ${plaintext.length})');
      
      // SERVICES DEBUG: Input validation
      print('SERVICES_DEBUG: Username/Password length: ${plaintext.length} chars');
      final plaintextBytes = utf8.encode(plaintext);
      print('SERVICES_DEBUG: UTF-8 encoded bytes: ${plaintextBytes.length}');
      print('SERVICES_DEBUG: Plaintext bytes (hex): ${plaintextBytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      // Generate random IV (16 bytes)
      final random = Random.secure();
      final iv = Uint8List.fromList(List.generate(16, (i) => random.nextInt(256)));
      print('AES_DEBUG: Generated IV: ${iv.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: IV (16 bytes, hex): ${iv.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      // Setup AES-CBC cipher
      final cipher = CBCBlockCipher(AESEngine());
      final params = ParametersWithIV(KeyParameter(key), iv);
      cipher.init(true, params);
      
      // Add PKCS7 padding
      final paddedPlaintext = _addPKCS7Padding(plaintextBytes, 16);
      print('AES_DEBUG: Padded plaintext: ${paddedPlaintext.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')} (length: ${paddedPlaintext.length})');
      print('SERVICES_DEBUG: After PKCS7 padding: ${paddedPlaintext.length} bytes');
      print('SERVICES_DEBUG: Padded data (hex): ${paddedPlaintext.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      // Calculate padding info for Services
      final paddingLength = 16 - (plaintextBytes.length % 16);
      print('SERVICES_DEBUG: PKCS7 padding bytes added: $paddingLength');
      print('SERVICES_DEBUG: Padding value: $paddingLength (repeated $paddingLength times)');
      
      // Encrypt
      final encrypted = Uint8List(paddedPlaintext.length);
      var offset = 0;
      while (offset < paddedPlaintext.length) {
        offset += cipher.processBlock(paddedPlaintext, offset, encrypted, offset);
      }
      print('AES_DEBUG: Encrypted bytes: ${encrypted.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: Ciphertext (${encrypted.length} bytes, hex): ${encrypted.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      // Return Base64(IV + Encrypted)
      final combined = Uint8List.fromList([...iv, ...encrypted]);
      print('SERVICES_DEBUG: Combined IV+Ciphertext (${combined.length} bytes, hex): ${combined.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      final result = base64.encode(combined);
      print('AES_DEBUG: Final base64 result: $result');
      print('SERVICES_DEBUG: Final Base64 result: $result');
      return result;
    } catch (e) {
      print('AES encryption error: $e');
      throw Exception('Encryption failed: $e');
    }
  }
  
  /// Add PKCS7 padding
  static Uint8List _addPKCS7Padding(List<int> data, int blockSize) {
    final padding = blockSize - (data.length % blockSize);
    final padded = List<int>.from(data);
    for (int i = 0; i < padding; i++) {
      padded.add(padding);
    }
    return Uint8List.fromList(padded);
  }
  
  /// Convert BigInt to full bytes (no truncation for security)
  static Uint8List _bigIntToFullBytes(BigInt bigInt) {
    if (bigInt == BigInt.zero) return Uint8List.fromList([0]);
    
    final bytes = <int>[];
    var temp = bigInt;
    
    while (temp > BigInt.zero) {
      bytes.insert(0, (temp & BigInt.from(0xff)).toInt());
      temp = temp >> 8;
    }
    
    final result = Uint8List.fromList(bytes);
    
    // DEBUG: Log full byte conversion
    print('DEBUG MOBILE: BigInt to full bytes conversion:');
    print('DEBUG MOBILE: Input BigInt bit length: ${bigInt.bitLength}');
    print('DEBUG MOBILE: Full byte array length: ${result.length} bytes');
    print('DEBUG MOBILE: NO TRUNCATION - using full entropy');
    
    return result;
  }
  
  /// Convert BigInt to bytes with specified length (kept for compatibility)
  static Uint8List _bigIntToBytes(BigInt bigInt, int length) {
    final hex = bigInt.toRadixString(16);
    final paddedHex = hex.padLeft(length * 2, '0');
    final bytes = <int>[];
    
    for (int i = 0; i < paddedHex.length; i += 2) {
      bytes.add(int.parse(paddedHex.substring(i, i + 2), radix: 16));
    }
    
    return Uint8List.fromList(bytes.take(length).toList());
  }
  
  /// Convert bytes to BigInt
  static BigInt _bytesToBigInt(Uint8List bytes) {
    BigInt result = BigInt.zero;
    for (int i = 0; i < bytes.length; i++) {
      result = (result << 8) + BigInt.from(bytes[i]);
    }
    return result;
  }
  
  /// Get stored client public key for credential submission
  static Future<String?> getClientPublicKey() async {
    return await _storage.read(key: _publicKeyStorageKey);
  }
  
  /// Clear stored encryption keys (for testing/reset)
  static Future<void> clearStoredKeys() async {
    await _storage.delete(key: _keyStorageKey);
    await _storage.delete(key: _privateKeyStorageKey);
    await _storage.delete(key: _publicKeyStorageKey);
    print('SECURITY: Cleared all stored keys - will force secure key exchange');
  }
  
  /// Force secure key regeneration (clears old insecure keys)
  static Future<void> forceSecureKeyRegeneration() async {
    print('SECURITY: Forcing secure key regeneration...');
    await clearStoredKeys();
    print('SECURITY: Old keys cleared - next key exchange will use secure method');
  }
  
  /// Get Diffie-Hellman parameters for Services
  static Map<String, String> getDiffieHellmanParameters() {
    return {
      'prime': _prime.toRadixString(16),
      'generator': _generator.toString(),
      'key_size': '2048',
      'group': 'RFC 3526 Group 14'
    };
  }
}