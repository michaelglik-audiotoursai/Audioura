# Detailed Instructions for Building and Installing the Audio Tour App

## Prerequisites

- Python 3.7 or newer
- Android phone with USB debugging enabled
- USB cable to connect your phone to your computer

## Step 1: Prepare Your Tour

1. Run the packaging script from your AudioTours development directory:
   ```
   cd c:\Users\micha\eclipse-workspace\AudioTours\development
   python package_tour_app.py
   ```

2. Select the tour you want to package when prompted

## Step 2: Install Buildozer and Dependencies

### On Windows:

1. Install buildozer from any directory (it's a global Python package):
   ```
   pip install buildozer
   ```

2. Install required dependencies:
   - Install [WSL (Windows Subsystem for Linux)](https://docs.microsoft.com/en-us/windows/wsl/install)
   - Install Ubuntu from Microsoft Store
   - Open Ubuntu terminal and run:
     ```
     sudo apt update
     sudo apt install -y python3-pip build-essential git python3-dev ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev
     ```

### On macOS:

1. Install buildozer:
   ```
   pip install buildozer
   ```

2. Install dependencies using Homebrew:
   ```
   brew install pkg-config sdl2 sdl2_image sdl2_ttf sdl2_mixer
   ```

### On Linux (Ubuntu/Debian):

1. Install buildozer:
   ```
   pip install buildozer
   ```

2. Install dependencies:
   ```
   sudo apt update
   sudo apt install -y python3-pip build-essential git python3-dev ffmpeg libsdl2-dev libsdl2-image-dev libsdl2-mixer-dev libsdl2-ttf-dev libportmidi-dev libswscale-dev libavformat-dev libavcodec-dev zlib1g-dev
   ```

## Step 3: Build the APK

1. Navigate to the mobile_app directory:
   ```
   cd c:\Users\micha\eclipse-workspace\AudioTours\development\mobile_app
   ```

2. If using Windows, you need to run buildozer from WSL:
   - Copy the mobile_app directory to your WSL home directory:
     ```
     cp -r /mnt/c/Users/micha/eclipse-workspace/AudioTours/development/mobile_app ~/
     ```
   - Navigate to the copied directory in WSL:
     ```
     cd ~/mobile_app
     ```

3. Run buildozer to create the APK:
   ```
   buildozer android debug
   ```
   
   This will:
   - Download Android SDK and NDK (first time only)
   - Build the app
   - Create an APK file in the `bin/` directory

## Step 4: Install the App on Your Phone

### Method 1: Direct USB Installation

1. Connect your Android phone to your computer with USB cable
2. Enable USB debugging on your phone (in Developer options)
3. Install the APK directly:
   ```
   buildozer android deploy run
   ```

### Method 2: Manual Installation

1. Locate the APK file in the bin directory:
   - Windows WSL: `~/mobile_app/bin/[appname]-[version]-debug.apk`
   - Native Linux/macOS: `mobile_app/bin/[appname]-[version]-debug.apk`

2. Transfer the APK to your phone using:
   - Email
   - USB file transfer
   - Cloud storage (Google Drive, Dropbox)
   - ADB command: `adb install [path-to-apk]`

3. On your phone:
   - Open the APK file
   - Allow installation from unknown sources if prompted
   - Follow the installation prompts
   - Open the app from your app drawer

## Troubleshooting

### Common Issues:

1. **"buildozer command not found"**
   - Make sure you installed buildozer with pip
   - Check if Python scripts directory is in your PATH

2. **Build errors in WSL**
   - Make sure you have enough disk space
   - Try running `buildozer android clean` before building again

3. **App crashes on startup**
   - Check that all audio files were copied correctly
   - Verify the app has storage permissions

4. **"Unknown sources" error when installing**
   - Go to Settings > Security > Unknown sources and enable it
   - On newer Android versions, you'll be prompted during installation