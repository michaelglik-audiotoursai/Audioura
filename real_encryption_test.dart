import 'dart:convert';
import 'dart:math';
import 'dart:typed_data';
import 'package:crypto/crypto.dart';
import 'package:pointycastle/export.dart';

void main() {
  // Use fixed keys for reproducible results
  final serverPrivateKey = BigInt.parse('12345');
  final clientPrivateKey = BigInt.parse('67890');
  
  // RFC 3526 Group 14 prime and generator
  final prime = BigInt.parse('FFFFFFFFFFFFFFFFC90FDAA22168C234C4C6628B80DC1CD129024E088A67CC74020BBEA63B139B22514A08798E3404DDEF9519B3CD3A431B302B0A6DF25F14374FE1356D6D51C245E485B576625E7EC6F44C42E9A637ED6B0BFF5CB6F406B7EDEE386BFB5A899FA5AE9F24117C4B1FE649286651ECE45B3DC2007CB8A163BF0598DA48361C55D39A69163FA8FD24CF5F83655D23DCA3AD961C62F356208552BB9ED529077096966D670C354E4ABC9804F1746C08CA18217C32905E462E36CE3BE39E772C180E86039B2783A2EC07A28FB5C55DF06F4C52C9DE2BCBF6955817183995497CEA956AE515D2261898FA051015728E5A8AACAA68FFFFFFFFFFFFFFFF', radix: 16);
  final generator = BigInt.from(2);
  
  // Generate public keys
  final serverPublicKey = generator.modPow(serverPrivateKey, prime);
  final clientPublicKey = generator.modPow(clientPrivateKey, prime);
  
  // Calculate shared secret
  final sharedSecret = serverPublicKey.modPow(clientPrivateKey, prime);
  
  // Use mobile app's secure method
  final sharedSecretBytes = bigIntToFullBytes(sharedSecret);
  final digest = sha256.convert(sharedSecretBytes);
  final aesKey = Uint8List.fromList(digest.bytes.take(16).toList());
  
  // Encrypt with fixed IV for reproducible results
  final fixedIV = Uint8List.fromList([1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16]);
  
  final encryptedUsername = encryptWithFixedIV('Misha', aesKey, fixedIV);
  final encryptedPassword = encryptWithFixedIV('kapustA77', aesKey, fixedIV);
  
  print('Server Public Key: ${serverPublicKey.toRadixString(16)}');
  print('');
  print('JSON:');
  print(JsonEncoder.withIndent('  ').convert({
    'article_id': 'article_169_001',
    'mobile_public_key': clientPublicKey.toRadixString(16),
    'encrypted_username': encryptedUsername,
    'encrypted_password': encryptedPassword,
    'device_id': 'mobile_device_12345',
    'domain': 'newsletter169.example.com'
  }));
  print('');
  print('Server Private Key: ${serverPrivateKey.toRadixString(16)}');
}

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

String encryptWithFixedIV(String plaintext, Uint8List key, Uint8List iv) {
  final cipher = CBCBlockCipher(AESEngine());
  final params = ParametersWithIV(KeyParameter(key), iv);
  cipher.init(true, params);
  
  final plaintextBytes = utf8.encode(plaintext);
  final paddedPlaintext = addPKCS7Padding(plaintextBytes, 16);
  
  final encrypted = Uint8List(paddedPlaintext.length);
  var offset = 0;
  while (offset < paddedPlaintext.length) {
    offset += cipher.processBlock(paddedPlaintext, offset, encrypted, offset);
  }
  
  final combined = Uint8List.fromList([...iv, ...encrypted]);
  return base64.encode(combined);
}

Uint8List addPKCS7Padding(List<int> data, int blockSize) {
  final padding = blockSize - (data.length % blockSize);
  final padded = List<int>.from(data);
  for (int i = 0; i < padding; i++) {
    padded.add(padding);
  }
  return Uint8List.fromList(padded);
}