import 'dart:convert';
import '../lib/services/subscription_encryption_service.dart';

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
    // Clear any existing keys to ensure fresh test
    await SubscriptionEncryptionService.clearStoredKeys();
    
    // Perform Diffie-Hellman key exchange
    print('\n=== PERFORMING KEY EXCHANGE ===');
    final keyExchangeResult = await SubscriptionEncryptionService.performKeyExchange(serverPublicKeyHex);
    
    if (keyExchangeResult == null) {
      throw Exception('Key exchange failed');
    }
    
    final mobilePublicKey = keyExchangeResult['client_public_key']!;
    print('Mobile Public Key: $mobilePublicKey');
    
    // Encrypt credentials
    print('\n=== ENCRYPTING CREDENTIALS ===');
    final encryptionResult = await SubscriptionEncryptionService.encryptCredentials(username, password, domain);
    
    if (encryptionResult == null) {
      throw Exception('Credential encryption failed');
    }
    
    // Generate JSON for Services
    final jsonPayload = {
      'encrypted_username': encryptionResult['encrypted_username'],
      'encrypted_password': encryptionResult['encrypted_password'],
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
    print('Mobile Public Key: ${mobilePublicKey.substring(0, 50)}...');
    print('Server Public Key: ${serverPublicKeyHex.substring(0, 50)}...');
    print('Encryption Method: Secure Full Entropy (2048-bit DH + SHA-256 + AES-128-CBC)');
    
  } catch (e) {
    print('ERROR: $e');
  }
}