# Mobile Demo Recording Guide - AudioTours App
## Complete Setup and Recording Process

### 🔧 **Prerequisites Setup**
- **Windows Computer** with VirtualBox
- **Ubuntu VM** running in VirtualBox
- **Android Phone** with AudioTours app installed (v1.2.8+125)
- **USB Cable** for phone connection

---

## 📱 **Phase 1: Phone Setup (One-time)**

### **Step 1: Enable Developer Options**
1. **Phone Settings** → **About Phone**
2. **Tap "Build Number" 7 times** (enter phone password when prompted)
3. **Confirmation message**: "You are now a developer"

### **Step 2: Enable USB Debugging**
1. **Phone Settings** → **System** → **Developer Options**
2. **Toggle ON "USB Debugging"**
3. **Confirm** when prompted

### **Step 3: Physical Connection**
1. **Connect USB cable** between phone and Windows computer
2. **In VirtualBox**: Devices → USB → **Select your phone** (share with Ubuntu VM)

---

## 🖥️ **Phase 2: Ubuntu VM Setup**

### **Step 1: Verify ADB Connection**
```bash
# Test ADB is working
adb version
# Expected: Android Debug Bridge version 1.0.41

# Check phone connection
adb devices
# Expected: List of devices attached
#           99251FFAZ002YY    device
```

### **Step 2: Handle Authorization (if needed)**
If you see "unauthorized":
1. **Check phone screen** for USB debugging permission dialog
2. **Tap "Allow"** and check "Always allow from this computer"
3. **Re-run**: `adb devices` (should show "device" not "unauthorized")

---

## 🎬 **Phase 3: Recording Methods**

## **Method A: ADB Command Recording (Video Only)**

### **VirtualBox USB Setup:**
1. **In VirtualBox**: Devices → USB → **Select your phone** (e.g., Google Pixel 4)
2. **Verify connection** in Ubuntu with `adb devices`

### **Basic Video Recording:**
```bash
# Start recording (video only, 3-minute limit)
adb shell screenrecord /sdcard/mobile_demo.mp4

# Use AudioTours app on phone for 2-3 minutes
# Recording stops automatically or press Ctrl+C

# Download video to Ubuntu
adb pull /sdcard/mobile_demo.mp4 ~/mobile_demo.mp4

# Copy to Windows accessible location
cp ~/mobile_demo.mp4 /media/sf_audiotours/mobile_demo.mp4
```

---

## **Method B: Windows Microphone Recording**

### **Audio Recording Setup:**
1. **Windows Voice Recorder** or **Sound Recorder** app
2. **Start audio recording** on Windows laptop
3. **Simultaneously start** ADB video recording
4. **Demonstrate AudioTours app** while narrating:
   - Your commentary will be captured by laptop microphone
   - App audio will be captured through laptop microphone from phone speaker
   - Navigate through tours, play audio, show features
5. **Stop both recordings** when demo complete

### **Audio Recording Process:**
```bash
# In Windows: Start Voice Recorder app
# Click Record button

# In Ubuntu: Start video recording
adb shell screenrecord /sdcard/mobile_demo.mp4

# Demonstrate app for 2-3 minutes with commentary
# Stop both recordings

# Transfer video from phone
adb pull /sdcard/mobile_demo.mp4 ~/mobile_demo.mp4
cp ~/mobile_demo.mp4 /media/sf_audiotours/mobile_demo.mp4
```

---

## **Method C: Microsoft Clipchamp Video Editing**

### **Combining Video and Audio:**
1. **Open Microsoft Clipchamp**
2. **Click "Create New Video"**
3. **Import media files**:
   - Your MP4 video from phone recording
   - Your M4A audio from Windows Voice Recorder
4. **Timeline editing**:
   - Drag MP4 to video timeline
   - Drag M4A to audio track
   - Position audio to sync with video moments
   - Adjust volume levels (video vs commentary)
5. **Add intro music** (optional):
   - Use Clipchamp's royalty-free music library
   - Add 3-4 seconds at beginning
   - Fade out before commentary starts
6. **Preview and export** final demo video

### **Clipchamp Workflow:**
- **Video Track**: Phone screen recording (MP4)
- **Audio Track 1**: Your commentary (M4A)
- **Audio Track 2**: Intro music (optional, from Clipchamp library)
- **Timeline Control**: Position audio at exact moments
- **Export**: Professional demo ready for presentation

---

## 🔄 **Phase 4: Troubleshooting**

### **Connection Issues:**
```bash
# Reset ADB if connection fails
adb kill-server
adb start-server
adb devices
```

### **Phone Not Detected:**
1. **Check USB cable** (try different cable/port)
2. **Re-share USB device** in VirtualBox
3. **Check phone notification** for USB debugging permission
4. **Try different USB debugging mode** in Developer Options

### **Audio Sync Issues:**
- **Use Clipchamp timeline** to manually sync audio with video
- **Adjust audio timing** by dragging on timeline
- **Test different microphone positions** for better phone audio capture

---

## 📋 **Phase 5: Demo Workflow**

### **Recommended Demo Sequence:**
1. **App Launch** (show splash screen, version)
2. **Main Interface** (navigate through tabs)
3. **Tour Selection** (browse available tours)
4. **Audio Playback** (play tour audio - crucial for audio app)
5. **Map Integration** (show location features)
6. **Voice Controls** (demonstrate voice commands if working)
7. **Settings/About** (show version info)

### **Audio App Specific Tips:**
- **Play actual tour audio** during recording
- **Show audio controls** (play, pause, skip)
- **Demonstrate volume** and audio quality
- **Include multiple tour types** (walking, museum, etc.)
- **Show audio continues** while navigating

---

## 📁 **File Management**

### **Video File Locations:**
- **Ubuntu VM**: `~/mobile_demo.mp4`
- **Windows Access**: `/media/sf_audiotours/` (shared folder)
- **Final Location**: `c:\Users\micha\eclipse-workspace\AudioTours\development\`

### **File Naming Convention:**
- `mobile_demo_YYYYMMDD_HHMMSS.mp4` (ADB recording)
- `voice_recording_YYYYMMDD.m4a` (Windows Voice Recorder)
- `audiotours_demo_v1.2.8_final.mp4` (Clipchamp export)

---

## ✅ **Success Checklist**

### **Before Recording:**
- [ ] Phone USB debugging enabled
- [ ] ADB connection working (`adb devices` shows device)
- [ ] AudioTours app installed and working
- [ ] Windows Voice Recorder ready
- [ ] VirtualBox USB device shared (Google Pixel 4)

### **During Recording:**
- [ ] Both video and audio recording started simultaneously
- [ ] Clear narration while demonstrating app
- [ ] Phone speaker volume up for laptop microphone to capture
- [ ] 2-3 minute duration (optimal length)
- [ ] Demonstrate key app functionality

### **After Recording:**
- [ ] Video file transferred from phone to Windows
- [ ] Audio file saved from Windows Voice Recorder
- [ ] Both files imported into Clipchamp
- [ ] Audio synchronized with video in timeline
- [ ] Final demo exported and ready for presentation

---

## 🎯 **Quick Reference Commands**

```bash
# Check connection
adb devices

# Record video only (3 min limit)
adb shell screenrecord /sdcard/demo.mp4

# Download video
adb pull /sdcard/demo.mp4 ~/demo.mp4

# Copy to Windows
cp ~/demo.mp4 /media/sf_audiotours/demo.mp4
```

### **Clipchamp Quick Steps:**
1. **Create New Video** in Clipchamp
2. **Import** MP4 (video) and M4A (audio)
3. **Drag to timeline** - video and audio tracks
4. **Sync audio** with video moments
5. **Add intro music** from Clipchamp library (optional)
6. **Export** final demo

---

**Last Updated**: 2025-12-17  
**Tested With**: AudioTours v1.2.8+125, Ubuntu 25.04, Google Pixel 4 with USB debugging, Microsoft Clipchamp  
**Status**: ✅ Working - ADB video recording + Windows microphone + Clipchamp editing workflow functional