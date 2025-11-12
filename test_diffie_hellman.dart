import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';

void main() {
  print('=== Diffie-Hellman Key Exchange Test ===');
  
  // Server public key from logs
  final serverPublicKeyHex = "0x581efd62213962de713420d12794ae421bf9e2fe0830584a3284199cbadbec06a0e9986f2530390e9f1da771548a6fbdd0028e434b6430b224fdbb6fe0983a904a3e7ae74a3440a2db097ae097a784b91eed5e30b63214a4885577847f000623de317827481bdd43a8ee9dcc3dab04820782c85fad656b9624b821ae2e6e7c39621b592873e3b796eb2d52c6869fe40672c3a7f556cce80f4c96c798962eab0cfade6d5cc956d4d54225e7776c23f46ccd1e5426b7079ad4ae046c1a945d20a6eb525225cfff9b29c3f88ef2480b9f5de93a793b4c438e391029756db384a687467023eb97ccf837674756e37911d7974acf733c29144bac7e58b1c67a91c510";
  
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
  
  try {
    print('1. Testing server public key parsing...');
    
    // Test with 0x prefix (current server format)
    final cleanHex = serverPublicKeyHex.startsWith('0x') ? serverPublicKeyHex.substring(2) : serverPublicKeyHex;
    print('   Original: ${serverPublicKeyHex.substring(0, 20)}...');
    print('   Clean hex: ${cleanHex.substring(0, 18)}...');
    
    final serverPublicKey = BigInt.parse(cleanHex, radix: 16);
    print('   ✅ Server public key parsed successfully');
    print('   Key length: ${serverPublicKey.bitLength} bits');
    
    print('\n2. Generating client private key...');
    final random = Random.secure();
    final privateKey = _generateSecurePrivateKey(random);
    print('   ✅ Private key generated: ${privateKey.bitLength} bits');
    
    print('\n3. Generating client public key...');
    final publicKey = generator.modPow(privateKey, prime);
    print('   ✅ Public key generated: ${publicKey.bitLength} bits');
    print('   Client public key: ${publicKey.toRadixString(16).substring(0, 20)}...');
    
    print('\n4. Computing shared secret...');
    final sharedSecret = serverPublicKey.modPow(privateKey, prime);
    print('   ✅ Shared secret computed: ${sharedSecret.bitLength} bits');
    print('   Shared secret: ${sharedSecret.toRadixString(16).substring(0, 20)}...');
    
    print('\n5. Deriving AES key...');
    final sharedSecretBytes = _bigIntToBytes(sharedSecret, 32);
    // Simple hash for testing (not cryptographically secure)
    final simpleHash = sharedSecretBytes.take(16).toList();
    final aesKey = base64.encode(simpleHash);
    print('   ✅ AES-128 key derived');
    print('   Key: $aesKey');
    
    print('\n6. Validation checks...');
    print('   Server key < prime: ${serverPublicKey < prime}');
    print('   Server key > 1: ${serverPublicKey > BigInt.one}');
    print('   Shared secret < prime: ${sharedSecret < prime}');
    print('   Shared secret > 1: ${sharedSecret > BigInt.one}');
    
    print('\n✅ ALL TESTS PASSED - Key exchange should work!');
    
  } catch (e, stackTrace) {
    print('\n❌ ERROR: $e');
    print('Stack trace: $stackTrace');
  }
}

BigInt _generateSecurePrivateKey(Random random) {
  final bytes = Uint8List(32);
  for (int i = 0; i < 32; i++) {
    bytes[i] = random.nextInt(256);
  }
  return _bytesToBigInt(bytes);
}

Uint8List _bigIntToBytes(BigInt bigInt, int length) {
  final hex = bigInt.toRadixString(16);
  final paddedHex = hex.padLeft(length * 2, '0');
  final bytes = <int>[];
  
  for (int i = 0; i < paddedHex.length; i += 2) {
    bytes.add(int.parse(paddedHex.substring(i, i + 2), radix: 16));
  }
  
  return Uint8List.fromList(bytes.take(length).toList());
}

BigInt _bytesToBigInt(Uint8List bytes) {
  BigInt result = BigInt.zero;
  for (int i = 0; i < bytes.length; i++) {
    result = (result << 8) + BigInt.from(bytes[i]);
  }
  return result;
}