@echo off
echo Setting up Flutter Audio Tour App...

echo Step 1: Check Flutter installation
flutter doctor

echo.
echo Step 2: Create Flutter app
cd c:\Users\micha\eclipse-workspace\AudioTours\development
flutter create audio_tour_app
cd audio_tour_app

echo.
echo Step 3: Add dependencies to pubspec.yaml
echo This will be done manually after creation

echo.
echo Step 4: Get dependencies
flutter pub get

echo.
echo Step 5: Run app
echo flutter run

pause