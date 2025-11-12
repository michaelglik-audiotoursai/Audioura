import 'dart:convert';
import 'dart:math';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

void main() async {
  print('=== SERVICES COMPATIBILITY TEST ===');
  print('Testing mobile app encryption with Services public key');
  
  // Services provided public key
  final serverPublicKeyHex = '89811725cc73276ebb6b09499464b2868ae2233682287511741b3089cc10849dcdabf14cb29ca64f5481f9f739f2b8734fed7c4a4751623564272b357f2e01d390483e773531afce14f0e3ce29bdd30fe7881ef1efb5967c912b6daec87a2f609ac986ccb1361ec4cb27aeaba04ca7468e4343c341f00b7558d3b3081d4678065a31fc37d84279b084284b694598a1f3a14f3e85119adc4680aa97612dbb6cfd5993155051d548230256fff863eae66c5e29a213373addbe1795a7798eda58b22e0de337533dc6e6464cb28c84ed08e1a05f785539048a96c2e923a326396ca499c6c1bc90eb2a08fa5f7fa3a';
  
  // Test credentials
  final username = 'Misha';
  final password = 'kapustA77';
  final articleId = '169';
  final domain = 'vew.marketing.select.com';
  final deviceId = 'test-device-12345';
  
  try {
    // Initialize encryption service (same as mobile app)
    final encryptionService = SubscriptionEncryptionService();
    
    // Generate client key pair
    await encryptionService.generateClientKeyPair();
    
    // Set server public key
    await encryptionService.setServerPublicKey(serverPublicKeyHex);
    
    // Get mobile public key for JSON
    final mobilePublicKey = await encryptionService.getMobilePublicKey();
    
    // Encrypt credentials
    final encryptedUsername = await encryptionService.encryptCredential(username);
    final encryptedPassword = await encryptionService.encryptCredential(password);
    
    // Generate JSON for Services
    final jsonPayload = {
      'encrypted_username': encryptedUsername,
      'encrypted_password': encryptedPassword,
      'device_id': deviceId,
      'article_id': articleId,
      'mobile_public_key': mobilePublicKey,
      'domain': domain
    };
    
    print('\n=== GENERATED JSON FOR SERVICES ===');
    print(jsonEncode(jsonPayload));
    
    print('\n=== VERIFICATION INFO ===');
    print('Username: $username');
    print('Password: $password');
    print('Mobile Public Key: $mobilePublicKey');
    print('Server Public Key: ${serverPublicKeyHex.substring(0, 50)}...');
    
  } catch (e) {
    print('ERROR: $e');
  }
}

// Mobile app's actual encryption service (secure method)
class SubscriptionEncryptionService {
  static final BigInt _p = BigInt.parse('0xFFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF', 16);
  static final BigInt _g = BigInt.from(2);
  
  BigInt? _privateKey;
  BigInt? _publicKey;
  BigInt? _sharedSecret;
  
  Future<void> generateClientKeyPair() async {
    final random = Random.secure();
    _privateKey = _generateRandomBigInt(256, random);
    _publicKey = _g.modPow(_privateKey!, _p);
  }
  
  Future<void> setServerPublicKey(String serverPublicKeyHex) async {
    final serverPublicKey = BigInt.parse(serverPublicKeyHex, radix: 16);
    _sharedSecret = serverPublicKey.modPow(_privateKey!, _p);
  }
  
  Future<String> getMobilePublicKey() async {
    return _publicKey!.toRadixString(16);
  }
  
  Future<String> encryptCredential(String credential) async {
    final sharedSecretBytes = _bigIntToFullBytes(_sharedSecret!, 256);
    final keyBytes = sha256.convert(sharedSecretBytes).bytes.take(16).toList();
    
    final iv = _generateRandomBytes(16);
    final cipher = CBCBlockCipher(AESEngine());
    final params = ParametersWithIV(KeyParameter(Uint8List.fromList(keyBytes)), Uint8List.fromList(iv));
    cipher.init(true, params);
    
    final paddedData = _addPKCS7Padding(utf8.encode(credential), 16);
    final encrypted = _processBlocks(cipher, paddedData);
    
    final combined = iv + encrypted;
    return base64.encode(combined);
  }
  
  Uint8List _bigIntToFullBytes(BigInt bigInt, int length) {
    final bytes = Uint8List(length);
    var temp = bigInt;
    for (int i = length - 1; i >= 0; i--) {
      bytes[i] = (temp & BigInt.from(0xff)).toInt();
      temp = temp >> 8;
    }
    return bytes;
  }
  
  BigInt _generateRandomBigInt(int bitLength, Random random) {
    final byteLength = (bitLength + 7) ~/ 8;
    final bytes = List<int>.generate(byteLength, (_) => random.nextInt(256));
    return BigInt.parse(bytes.map((b) => b.toRadixString(16).padLeft(2, '0')).join(), radix: 16);
  }
  
  List<int> _generateRandomBytes(int length) {
    final random = Random.secure();
    return List<int>.generate(length, (_) => random.nextInt(256));
  }
  
  Uint8List _addPKCS7Padding(List<int> data, int blockSize) {
    final padding = blockSize - (data.length % blockSize);
    return Uint8List.fromList(data + List.filled(padding, padding));
  }
  
  Uint8List _processBlocks(BlockCipher cipher, Uint8List data) {
    final output = Uint8List(data.length);
    for (int offset = 0; offset < data.length; offset += cipher.blockSize) {
      cipher.processBlock(data, offset, output, offset);
    }
    return output;
  }
}