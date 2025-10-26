@echo off
echo === Updating Flutter app with Flutter Map ===

echo.
echo === Creating Flutter Map implementation ===
cd c:\Users\micha\eclipse-workspace\AudioTours\development
python implement_flutter_map.py

echo.
echo === Copying files to Flutter app directory ===
copy home_page_flutter_map.dart c:\Users\micha\eclipse-workspace\AudioTours\development\audio_tour_app\lib\

echo.
echo === Done! ===
echo ✅ Created Flutter Map home page implementation
echo ✅ Copied to your Flutter app directory
echo.
echo Next steps:
echo 1. Update pubspec.yaml dependencies (remove mapbox_gl, add flutter_map)
echo 2. Replace your existing home page with home_page_flutter_map.dart
echo 3. Add location permissions to AndroidManifest.xml
echo 4. Run flutter pub get
echo 5. Test the app
pause