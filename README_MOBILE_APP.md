# Audio Tour Mobile App

This solution creates a native mobile app for your audio tours that works completely offline.

## Overview

Instead of relying on web technologies that can be unreliable for offline use, this approach packages your audio files into a native Android app using Kivy and Buildozer.

## Requirements

- Python 3.7+
- Kivy (`pip install kivy`)
- Buildozer (for Android packaging)
- Android SDK and NDK (for Android packaging)

## How to Use

### 1. Package Your Tour

Run the packaging script to prepare your tour for mobile app conversion:

```
python package_tour_app.py
```

This will:
- List available tour directories
- Let you select which tour to package
- Copy all audio files to the mobile app directory
- Configure the app with the tour name

### 2. Build the Android APK

To build the Android app:

1. Install buildozer:
   ```
   pip install buildozer
   ```

2. Install required dependencies (on Ubuntu/Debian):
   ```
   sudo apt update
   sudo apt install -y python3-pip build-essential git python3-dev ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev
   ```

3. Navigate to the mobile_app directory:
   ```
   cd mobile_app
   ```

4. Build the APK:
   ```
   buildozer android debug
   ```

5. The APK will be created in the `bin/` directory

### 3. Install on Your Phone

1. Transfer the APK to your phone
2. Install the APK (you may need to enable "Install from Unknown Sources")
3. Open the app to access your audio tour

## Advantages Over Web Approach

- Works 100% offline with no connection issues
- No reliance on browser cache that can be cleared
- Native audio playback with better controls
- Can be distributed through app stores
- No IP address dependency

## Customization

You can customize the app by modifying:
- `main.py` - The main app code
- `buildozer.spec` - App packaging configuration