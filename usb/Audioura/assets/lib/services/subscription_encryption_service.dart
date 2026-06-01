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
      // Generate private key (256-bit random number)
      final random = Random.secure();
      final privateKey = _generateSecurePrivateKey(random);
      
      // Generate public key: g^privateKey mod p
      final publicKey = _generator.modPow(privateKey, _prime);
      
      // Calculate shared secret: serverPublicKey^privateKey mod p
      final cleanHex = serverPublicKeyHex.startsWith('0x') ? serverPublicKeyHex.substring(2) : serverPublicKeyHex;
      final serverPublicKey = BigInt.parse(cleanHex, radix: 16);
      final sharedSecret = serverPublicKey.modPow(privateKey, _prime);
      
      // Derive AES key from shared secret using SHA-256 (use full bytes for security)
      final sharedSecretBytes = _bigIntToFullBytes(sharedSecret);
      final digest = sha256.convert(sharedSecretBytes);
      final aesKey = base64.encode(digest.bytes.take(16).toList()); // AES-128
      
      // Store keys securely
      print('ENCRYPTION_DEBUG: About to store keys');
      print('ENCRYPTION_DEBUG: Storage instance: $_storage');
      print('ENCRYPTION_DEBUG: Storage key constant: $_keyStorageKey');
      print('ENCRYPTION_DEBUG: AES key to store: $aesKey');
      
      await _storage.write(key: _keyStorageKey, value: aesKey);
      print('ENCRYPTION_DEBUG: AES key write completed');
      
      await _storage.write(key: _privateKeyStorageKey, value: privateKey.toRadixString(16));
      await _storage.write(key: _publicKeyStorageKey, value: publicKey.toRadixString(16));
      print('ENCRYPTION_DEBUG: All keys write completed');
      
      // Immediately verify storage with same instance
      final verifyKey = await _storage.read(key: _keyStorageKey);
      print('ENCRYPTION_DEBUG: Immediate verification - key exists: ${verifyKey != null}');
      if (verifyKey != null) {
        print('ENCRYPTION_DEBUG: Immediate verification - key matches: ${verifyKey == aesKey}');
        print('ENCRYPTION_DEBUG: Immediate verification - key length: ${verifyKey.length}');
      } else {
        print('ENCRYPTION_DEBUG: CRITICAL - Key not found immediately after storage!');
      }
      
      // Test hasStoredKey() immediately
      final hasKeyResult = await hasStoredKey();
      print('ENCRYPTION_DEBUG: hasStoredKey() immediately after storage: $hasKeyResult');
      
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
    try {
      print('ENCRYPTION_DEBUG: Attempting to read key from storage with key: $_keyStorageKey');
      final key = await _storage.read(key: _keyStorageKey);
      print('ENCRYPTION_DEBUG: Retrieved key from storage: ${key != null ? "[KEY_EXISTS]" : "[NULL]"}');
      
      if (key != null) {
        print('ENCRYPTION_DEBUG: Key length: ${key.length}');
        print('ENCRYPTION_DEBUG: Key preview: ${key.length > 10 ? key.substring(0, 10) + "..." : key}');
      }
      
      return key;
    } catch (e) {
      print('ENCRYPTION_DEBUG: Error reading key from storage: $e');
      return null;
    }
  }
  
  /// Check if encryption key exists
  static Future<bool> hasStoredKey() async {
    try {
      print('ENCRYPTION_DEBUG: hasStoredKey() called');
      print('ENCRYPTION_DEBUG: Using storage key: $_keyStorageKey');
      
      // Direct storage read for debugging
      final directKey = await _storage.read(key: _keyStorageKey);
      print('ENCRYPTION_DEBUG: Direct storage read result: ${directKey != null ? "[KEY_EXISTS]" : "[NULL]"}');
      
      final key = await getStoredKey();
      final result = key != null && key.isNotEmpty;
      print('ENCRYPTION_DEBUG: hasStoredKey() returning: $result');
      
      return result;
    } catch (e) {
      print('ENCRYPTION_DEBUG: hasStoredKey() error: $e');
      return false;
    }
  }
  
  /// Test method to verify class is accessible
  static Future<String> testMethod() async {
    print('ENCRYPTION_TEST: testMethod called successfully');
    return 'test_success';
  }
  
  /// Encrypt credentials using stored AES key
  static Future<Map<String, String>?> encryptCredentials(String username, String password, String domain) async {
    print('ENCRYPTION_METHOD_ENTRY: encryptCredentials called');
    try {
      print('CREDENTIAL_DEBUG: Starting encryption - Username: "$username" (${username.length}), Password: "$password" (${password.length})');
      
      print('CREDENTIAL_DEBUG: About to call getStoredKey()');
      final keyBase64 = await getStoredKey();
      print('CREDENTIAL_DEBUG: getStoredKey() returned: ${keyBase64 != null ? "[KEY_EXISTS]" : "[NULL]"}');
      
      if (keyBase64 == null) {
        print('CREDENTIAL_DEBUG: ERROR - No encryption key found');
        print('CREDENTIAL_DEBUG: Checking if key was stored during key exchange...');
        
        // Check if key exists with direct storage access
        final directCheck = await _storage.read(key: _keyStorageKey);
        print('CREDENTIAL_DEBUG: Direct storage check: ${directCheck != null ? "[KEY_EXISTS]" : "[NULL]"}');
        
        return null; // Return null instead of throwing exception
      }
      
      print('CREDENTIAL_DEBUG: Retrieved key from storage: $keyBase64');
      
      final key = base64.decode(keyBase64);
      print('CREDENTIAL_DEBUG: AES key: ${key.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: ENCRYPTING WITH AES KEY: ${key.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      print('SERVICES_DEBUG: USERNAME TO ENCRYPT: "$username"');
      print('SERVICES_DEBUG: PASSWORD TO ENCRYPT: "$password"');
      
      print('CREDENTIAL_DEBUG: About to encrypt username');
      final encryptedUsername = _encryptAES(username, key);
      print('CREDENTIAL_DEBUG: Username encrypted successfully');
      
      print('CREDENTIAL_DEBUG: About to encrypt password');
      final encryptedPassword = _encryptAES(password, key);
      print('CREDENTIAL_DEBUG: Password encrypted successfully');
      
      print('CREDENTIAL_DEBUG: Encryption completed successfully');
      return {
        'encrypted_username': encryptedUsername,
        'encrypted_password': encryptedPassword,
        'domain': domain,
      };
    } catch (e, stackTrace) {
      print('CREDENTIAL_DEBUG: ENCRYPTION ERROR: $e');
      print('CREDENTIAL_DEBUG: Stack trace: $stackTrace');
      return null;
    }
  }
  
  /// Proper AES-128-CBC encryption as required by Services
  static String _encryptAES(String plaintext, Uint8List key) {
    try {
      print('CREDENTIAL_DEBUG: _encryptAES called with plaintext length: ${plaintext.length}, key length: ${key.length}');
      
      // Generate random IV (16 bytes)
      final random = Random.secure();
      final iv = Uint8List.fromList(List.generate(16, (i) => random.nextInt(256)));
      print('CREDENTIAL_DEBUG: Generated IV: ${iv.map((b) => b.toRadixString(16).padLeft(2, '0')).join('')}');
      
      // Setup AES-CBC cipher
      final cipher = CBCBlockCipher(AESEngine());
      final params = ParametersWithIV(KeyParameter(key), iv);
      cipher.init(true, params);
      print('CREDENTIAL_DEBUG: AES cipher initialized');
      
      // Add PKCS7 padding
      final plaintextBytes = utf8.encode(plaintext);
      final paddedPlaintext = _addPKCS7Padding(plaintextBytes, 16);
      print('CREDENTIAL_DEBUG: Plaintext padded from ${plaintextBytes.length} to ${paddedPlaintext.length} bytes');
      
      // Encrypt
      final encrypted = Uint8List(paddedPlaintext.length);
      var offset = 0;
      while (offset < paddedPlaintext.length) {
        offset += cipher.processBlock(paddedPlaintext, offset, encrypted, offset);
      }
      print('CREDENTIAL_DEBUG: Encryption completed, encrypted length: ${encrypted.length}');
      
      // Return Base64(IV + Encrypted)
      final combined = Uint8List.fromList([...iv, ...encrypted]);
      final result = base64.encode(combined);
      print('CREDENTIAL_DEBUG: Base64 encoding completed, result length: ${result.length}');
      return result;
    } catch (e, stackTrace) {
      print('CREDENTIAL_DEBUG: _encryptAES ERROR: $e');
      print('CREDENTIAL_DEBUG: _encryptAES Stack trace: $stackTrace');
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
    
    return Uint8List.fromList(bytes);
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
  }
  
  /// Force secure key regeneration (clears old insecure keys)
  static Future<void> forceSecureKeyRegeneration() async {
    await clearStoredKeys();
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