# Mac Mini M4 Setup Guide for iOS Development
## 🍎 Complete Step-by-Step Instructions

### OVERVIEW
This guide sets up your Mac Mini M4 for iOS development of the Audioura mobile app.
**Estimated Time**: 2-3 hours (mostly waiting for Xcode download)

---

## STEP 1: BASIC macOS SETUP (30 minutes)

### Physical Setup:
1. Connect Mac Mini M4 to monitor, keyboard, mouse
2. Power on and wait for startup chime
3. Follow setup wizard:
   - Select language and region
   - Connect to WiFi network
   - Create user account: **micha** (to match Windows)
   - Set password and security questions
   - Sign in with Apple ID: **glikfamily@gmail.com**

### Initial System Configuration:
1. Complete setup wizard (10-15 minutes)
2. Open System Settings (Apple menu → System Settings)
3. Software Update: Install any pending updates
4. Enable automatic updates: General → Software Update → Automatic Updates

---

## STEP 2: INSTALL XCODE COMMAND LINE TOOLS (10 minutes)

### Open Terminal:
1. Press **Cmd + Space** (Spotlight search)
2. Type **"Terminal"** and press Enter
3. Run this command:
```bash
xcode-select --install
```
4. Click **"Install"** when dialog appears (takes 5-10 minutes)
5. Verify installation:
```bash
xcode-select -p
```
Should show: `/Library/Developer/CommandLineTools`

---

## STEP 3: INSTALL HOMEBREW (5 minutes)

### In Terminal, run:
```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

### Add Homebrew to PATH:
```bash
echo 'eval "$(/opt/homebrew/bin/brew shellenv)"' >> ~/.zprofile
source ~/.zprofile
```

### Verify Homebrew:
```bash
brew --version
```

---

## STEP 4: INSTALL XCODE 16 (60-90 minutes)

### Via App Store (Recommended):
1. Open **App Store** (Dock or Spotlight)
2. Search **"Xcode"**
3. Click **"Get"** or **"Install"** (FREE, but 15GB+ download)
4. **Wait 30-90 minutes** for download/installation
5. **Launch Xcode** when complete
6. **Accept license agreements**
7. **Install additional components** when prompted

### Verify Xcode Installation:
```bash
xcode-select -p
```
Should now show: `/Applications/Xcode.app/Contents/Developer`

---

## STEP 5: CONFIGURE APPLE DEVELOPER ACCOUNT (5 minutes)

### **CRITICAL: Use Your Paid Apple Developer License**
**Your Account Details:**
- **Apple ID**: glikfamily@gmail.com
- **Developer Order**: W1583339145
- **Status**: Active (Paid License)
- **Benefits**: Device testing, App Store distribution, full iOS features

### **Sign In to Xcode with Paid Account:**
1. **Launch Xcode** (if not already open)
2. **Xcode menu → Settings** (or Preferences in older versions)
3. **Click "Accounts" tab**
4. **Click "+" button → "Add Apple ID"**
5. **Enter**: `glikfamily@gmail.com`
6. **Enter your Apple ID password**
7. **Sign in successfully**

### **Verify Developer Team Access:**
1. **After signing in**, you should see your account listed
2. **Click on your account** in the list
3. **Verify "Team" shows**: Your paid developer team
4. **Click "Download Manual Profiles"** (if available)
5. **Certificates should download automatically**

### **Configure Project Code Signing:**
1. **Open your iOS project**: `open ~/Development/AudioTours/development/audio_tour_app/ios/Runner.xcworkspace`
2. **Select "Runner" project** in navigator (left panel)
3. **Select "Runner" target** (under project)
4. **Click "Signing & Capabilities" tab**
5. **Team dropdown**: Select your paid developer team (glikfamily@gmail.com)
6. **Bundle Identifier**: Ensure it's `com.audioura.app`
7. **✅ Check "Automatically manage signing"**
8. **Provisioning Profile**: Should show "Xcode Managed Profile"

### **Verify Paid License Benefits:**
- ✅ **No 7-day expiration** on device installs
- ✅ **App Store distribution** capability
- ✅ **Push notifications** enabled
- ✅ **All iOS features** unlocked
- ✅ **Multiple device testing** allowed

---

## STEP 6: INSTALL FLUTTER SDK (15 minutes)

### Download Flutter:
```bash
cd ~/
curl -O https://storage.googleapis.com/flutter_infra_release/releases/stable/macos/flutter_macos_arm64_3.24.5-stable.zip
```

### Extract and Setup:
```bash
# Extract Flutter
unzip flutter_macos_arm64_3.24.5-stable.zip

# Add Flutter to PATH permanently
echo 'export PATH="$PATH:$HOME/flutter/bin"' >> ~/.zprofile
source ~/.zprofile

# Clean up zip file
rm flutter_macos_arm64_3.24.5-stable.zip
```

### Verify Flutter Installation:
```bash
flutter --version
flutter doctor -v
```

---

## STEP 7: INSTALL ADDITIONAL TOOLS (10 minutes)

### Install CocoaPods (iOS dependency manager):
```bash
sudo gem install cocoapods
```

### Install Rosetta 2 (for Intel compatibility):
```bash
softwareupdate --install-rosetta --agree-to-license
```

---

## STEP 8: FINAL VERIFICATION

### Run Flutter Doctor:
```bash
flutter doctor -v
```

### Expected Output (should show mostly ✅):
```
[✓] Flutter (Channel stable, 3.24.5, on macOS 14.x darwin-arm64)
[✓] Android toolchain - develop for Android devices
[✓] Xcode - develop for iOS and macOS (Xcode 16.x)
[✓] Chrome - develop for the web
[✓] Connected device (1 available)
[✓] Network resources
```

---

## TROUBLESHOOTING

### If Xcode download is slow:
- Use ethernet connection if possible
- Download during off-peak hours
- Consider downloading overnight

### If Flutter doctor shows issues:
```bash
# Common fixes
flutter doctor --android-licenses  # Accept Android licenses
flutter config --enable-web        # Enable web support
```

### If PATH issues occur:
```bash
# Reload shell configuration
source ~/.zprofile
# Or restart Terminal
```

---

## STEP 9: SETUP GITHUB AUTHENTICATION (15 minutes)

### **Your GitHub Credentials**:
- **Username**: `michaelglik-audiotoursai`
- **Password**: `<YOUR_GITHUB_PASSWORD>`
- **Repository**: `https://github.com/michaelglik-audiotoursai/Audioura`

### **Create Personal Access Token on Mac Mini**:

#### **Step 1: Sign into GitHub**:
1. **Open Safari** on Mac Mini
2. **Go to**: `github.com`
3. **Click "Sign in"**
4. **Enter credentials**:
   - **Username**: `michaelglik-audiotoursai`
   - **Password**: `<YOUR_GITHUB_PASSWORD>`
5. **Sign in successfully**

#### **Step 2: Create Personal Access Token**:
1. **Click your profile picture** (top right) → **Settings**
2. **Scroll down** → **Developer settings** (left sidebar, bottom)
3. **Personal access tokens** → **Tokens (classic)**
4. **Click "Generate new token"** → **"Generate new token (classic)"**
5. **Configure token**:
   - **Note**: `Mac Mini M4 Development`
   - **Expiration**: `No expiration` (or 90 days)
   - **Select scopes**: Check **`repo`** (Full control of private repositories)
6. **Click "Generate token"**
7. **COPY THE TOKEN IMMEDIATELY** (starts with `ghp_`) — use `<YOUR_GITHUB_PAT_FROM_DOTENV>` from your `.env` file
8. **Save token** in TextEdit temporarily (you won't see it again!)

#### **Step 3: Configure Git on Mac**:
```bash
# Set up Git identity with your exact credentials
git config --global user.name "michaelglik-audiotoursai"
git config --global user.email "glikfamily@gmail.com"

# Configure credential helper to store token
git config --global credential.helper store
```

---

## STEP 10: CLONE AUDIOURA PROJECT FROM GITHUB (15 minutes)

### Setup Development Directory:
```bash
# Create development directory (equivalent to Windows eclipse-workspace)
mkdir -p ~/Development
cd ~/Development
```

### Clone Audioura Repository:

#### **Clone Repository with Personal Access Token**:
```bash
# Clone the Audioura repository
git clone https://github.com/michaelglik-audiotoursai/Audioura.git AudioTours

# When prompted for credentials:
# Username for 'https://github.com': michaelglik-audiotoursai
# Password for 'https://michaelglik-audiotoursai@github.com': [<YOUR_GITHUB_PAT_FROM_DOTENV>]

# Navigate to project
cd AudioTours

# Verify repository structure
ls -la
# Should see: development/, .git/, README.md
```

#### **Switch to Development Branch**:
```bash
# Check available branches
git branch -a

# Switch to Newsletters branch (current development)
git checkout Newsletters

# Verify you're on correct branch
git branch  # Should show * Newsletters

# Pull latest changes
git pull origin Newsletters

# Verify project structure
ls -la development/
# Should see: audio_tour_app/, *.py files, docker-compose.yml, remind_*.md
```

### Verify Project Structure:
```bash
# Check directory structure
ls -la ~/Development/AudioTours/

# If files are in root instead of development/ subdirectory, fix the structure:
cd ~/Development/AudioTours

# Create development subdirectory if missing
mkdir -p development

# Move all files except .git into development/ (if needed)
find . -maxdepth 1 -not -name '.' -not -name '.git' -not -name 'development' -exec mv {} development/ \;

# Verify correct structure after fix
ls -la  # Should show: .git/ and development/
ls -la development/  # Should show: audio_tour_app/, *.py files, docker-compose.yml, remind_*.md
```

---

## STEP 11: FLUTTER PROJECT SETUP (10 minutes)

### **Navigate to Flutter App Directory**:
```bash
cd ~/Development/AudioTours/development/audio_tour_app

# Verify Flutter app structure
ls -la
```

### **Install Flutter Dependencies**:
```bash
flutter pub get
```

### **Install iOS Dependencies (CocoaPods)**:
```bash
cd ios
pod install
cd ..
```

### **Verify Flutter Setup**:
```bash
flutter doctor -v
flutter analyze
```

---

## STEP 11: iOS PROJECT CONFIGURATION (15 minutes)

### **Open iOS Project in Xcode:**
```bash
cd ~/Development/AudioTours/development/audio_tour_app
open ios/Runner.xcworkspace
```

### **Configure Code Signing with Paid License:**
1. **In Xcode**: Select "Runner" project in navigator (left panel)
2. **Select "Runner" target** (under Runner project)
3. **Click "Signing & Capabilities" tab**
4. **CRITICAL SETTINGS**:
   - **Team**: Select your paid developer team (glikfamily@gmail.com)
   - **Bundle Identifier**: `com.audioura.app`
   - **✅ Check "Automatically manage signing"**
   - **Provisioning Profile**: Should show "Xcode Managed Profile"
   - **Signing Certificate**: Should show "Apple Development"

### **Benefits of Paid License Setup:**
- ✅ **Unlimited device testing** (no 7-day expiration)
- ✅ **App Store distribution** ready
- ✅ **Push notifications** capability
- ✅ **Advanced iOS features** unlocked
- ✅ **Professional provisioning** profiles

---

## STEP 12: NETWORK CONFIGURATION FOR SERVICES (10 minutes)

### Find Windows Machine IP:
**On Windows machine**, run in Command Prompt:
```cmd
ipconfig
```
**Look for IPv4 Address** (example: 192.168.1.100)

### Update Flutter App Configuration:
```bash
open ~/Development/AudioTours/development/audio_tour_app/lib/config/api_config.dart
```

### Replace localhost with Windows IP:
```dart
// Change from:
static const String baseUrl = 'http://localhost:5002';

// To (replace with your actual Windows IP):
static const String baseUrl = 'http://192.168.1.100:5002';
```

---

## STEP 13: CREATE BUILD SCRIPT (5 minutes)

### Create Automated Build Script:
```bash
cat > ~/Development/build_audioura.sh << 'EOF'
#!/bin/bash
echo "🍎 Audioura iOS Build Script"
echo "============================="

cd ~/Development/AudioTours/development/audio_tour_app

echo "🧹 Cleaning previous build..."
flutter clean
flutter pub get
cd ios && pod install && cd ..

echo "🔨 Building iOS (debug)..."
flutter build ios --debug --no-codesign

echo "📱 Building Android APK..."
flutter build apk --release

echo "✅ Build complete!"
EOF

chmod +x ~/Development/build_audioura.sh
```

---

## STEP 14: CONNECT IPHONE 16 FOR TESTING (10 minutes)

### Enable iPhone 16 Developer Mode:
1. **Connect iPhone 16** to Mac Mini via USB-C cable
2. **Trust computer** when prompted on iPhone
3. **On iPhone**: Settings → Privacy & Security → Developer Mode → **ON**
4. **Restart iPhone** when prompted
5. **Confirm Developer Mode** activation

### Verify Device Connection:
```bash
flutter devices
```

### Install App on iPhone:
```bash
flutter install -d ios
# Or run with live reload
flutter run -d ios
```

---

## STEP 15: FINAL VERIFICATION & SUCCESS CRITERIA

### Complete Setup Checklist:
- [ ] **Basic macOS setup** complete
- [ ] **Xcode 16** installed and launches without errors
- [ ] **Flutter SDK** installed and in PATH
- [ ] **Apple Developer Account** configured in Xcode
- [ ] **Git repository** cloned successfully
- [ ] **On Newsletters branch** (`git branch` shows `* Newsletters`)
- [ ] **Flutter dependencies** installed (`flutter pub get` successful)
- [ ] **iOS dependencies** installed (`pod install` successful)
- [ ] **Bundle identifier** set to `com.audioura.app`
- [ ] **Code signing** configured with Apple Developer team
- [ ] **Network configuration** updated with Windows IP
- [ ] **Build script** created and executable
- [ ] **iPhone 16** connected and in Developer Mode
- [ ] **Flutter doctor** shows no critical iOS issues
- [ ] **Test build** completes successfully
- [ ] **App installs** on iPhone 16

### Final Verification Commands:
```bash
# Verify Git setup
cd ~/Development/AudioTours
git branch  # Should show * Newsletters
git remote -v  # Should show GitHub repository

# Verify Flutter setup
cd development/audio_tour_app
flutter doctor -v
flutter devices  # Should show iPhone 16

# Test build process
bash ~/Development/build_audioura.sh
```

---

## TROUBLESHOOTING COMMON ISSUES

### Git Issues:
```bash
# If authentication fails
git config --global user.name "michaelglik-audiotoursai"
git config --global user.email "glikfamily@gmail.com"

# If clone fails with authentication error
# Use Personal Access Token (not password) as the git password
# Username: michaelglik-audiotoursai
# Password: [<YOUR_GITHUB_PAT_FROM_DOTENV>]

# If you need to update stored credentials
git config --global --unset credential.helper
git config --global credential.helper store
```

### Flutter Issues:
```bash
# If Flutter not found
echo 'export PATH="$PATH:$HOME/flutter/bin"' >> ~/.zprofile
source ~/.zprofile

# If build fails
flutter clean
flutter pub get
cd ios && pod install && cd ..
```

### iOS Build Issues:
```bash
# If code signing fails
# Open Xcode → Runner → Signing & Capabilities
# Verify Apple Developer team is selected
# Ensure Bundle ID matches: com.audioura.app

# If pod install fails
cd ios
rm -rf Pods Podfile.lock
pod install --repo-update
cd ..
```

### Network Issues:
```bash
# If services unreachable
# Verify Windows IP address: ipconfig on Windows
# Update api_config.dart with correct IP
# Check Windows firewall allows connections on ports 5002, 5005, 5006, 5007, 5012
```

---

**SETUP COMPLETE!** 🎉

Your Mac Mini is now configured for complete iOS development of the Audioura mobile app.

### Important Notes:
- **File Paths**: Windows `c:\Users\micha\eclipse-workspace\AudioTours\` ↔ Mac `~/Development/AudioTours/`
- **Apple Developer**: glikfamily@gmail.com, Order W1583339145, Team 4HGRU6TKGQ
- **App**: Audioura, Bundle ID `com.audioura.app`
- **Branch**: Newsletters
