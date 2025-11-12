# Mobile App Amazon-Q Context Reminder - POST COMPACTION
## Who you are
1. **Mobile App Amazon-Q**: Responsible for Audioura mobile app development working with Services Amazon-Q
2. **CRITICAL LIMITATION**: ❌ **CANNOT BUILD APK** - Windows environment, APK requires Ubuntu VM with `bash build_flutter_clean.sh`
3. **Workflow**: Propose → Get approval → Implement → User builds in Ubuntu
4. **Location**: `C:\\Users\\micha\\eclipse-workspace\\AudioTours\\development\\audio_tour_app\\`
5. **Communication**: Use `c:\\Users\\micha\\eclipse-workspace\\amazon-q-communications\\audiotours\\requirements\\`

## CURRENT PROJECT STATUS - LATEST UPDATE
**Project**: Audioura Mobile App Development
**Version**: v1.2.8+19 (Secure Encryption Implementation)
**Branch**: Newsletters (`git push origin Newsletters`)
**Icon**: Audioura_3.png
**Status**: ✅ **SUBSCRIPTION STAGE 1 COMPLETE**

### 🔐 ENCRYPTION IMPLEMENTATION - VERIFIED SECURE
**Method**: RFC 3526 Diffie-Hellman (2048-bit) → SHA-256 full entropy → AES-128-CBC
**Key Derivation**: `SHA-256(shared_secret_bytes)[:16]`
**Shared Secret**: `mobile_public_key^server_private_key mod P`
**Format**: `Base64(IV + AES-CBC-encrypted-data)`
**Byte Conversion**: `_bigIntToFullBytes()` - no truncation, full entropy

### 🎯 PHASE 2: READY FOR IMPLEMENTATION
**Next Features**:
1. **Article Processing Status**: Show progress after credential submission
2. **Article Download**: Fetch subscription articles after credentials processed
3. **Credential Storage**: Remember credentials per domain using secure storage
4. **Session Management**: Handle expiration and re-authentication
5. **Error Handling**: Invalid credentials, processing failures, network issues
6. **Offline Support**: Cache subscription articles for offline reading

## KEY FILES - CURRENT STATE
- `lib/services/subscription_encryption_service.dart` - **SECURE**: Full entropy DH + AES-128-CBC encryption
- `lib/services/subscription_service.dart` - Key exchange + credential submission
- `lib/widgets/subscription_credential_dialog.dart` - User credential input
- `lib/screens/home_screen.dart` - Article selection + secure key initialization
- `pubspec.yaml` - Version 1.2.8+19

## IMMEDIATE NEXT STEPS
1. **Phase 2 Implementation**: Implement article download and processing status
2. **Credential Storage**: Add secure credential storage per domain
3. **Error Handling**: Improve user experience for failed authentications

## CRITICAL REMINDERS
- ❌ **NEVER attempt APK build in Windows** - Always requires Ubuntu VM
- 🌿 **All commits go to Newsletters branch** - NOT main branch
- 🔐 **Security**: Mobile app uses secure full entropy method (RFC 3526 DH + AES-128-CBC)
- ✅ **Stage 1**: Subscription encryption and credential submission working
- 🔄 **Next**: Implement Phase 2 features (article download, status, storage)

## Post-Compaction Recovery Instructions
**When chat history is compacted, read both @remind_ai.md and @remind_mobile_ai.md to get complete context**

### IMMEDIATE CONTEXT AFTER COMPACTION:
- **STAGE 1**: Subscription encryption complete with secure implementation
- **STATUS**: Credential submission working successfully
- **NEXT PHASE**: Implement article download and processing features
- **CURRENT VERSION**: v1.2.8+19 with secure encryption
- **READY FOR**: Phase 2 development (article processing, storage, error handling)