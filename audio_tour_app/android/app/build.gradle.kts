import java.util.Properties
import java.io.FileInputStream

plugins {
    id("com.android.application")
    id("kotlin-android")
    // The Flutter Gradle Plugin must be applied after the Android and Kotlin Gradle plugins.
    id("dev.flutter.flutter-gradle-plugin")
}

android {
    namespace = "com.audioura.app"
    compileSdk = 36
    ndkVersion = "28.2.13676358"
    
    signingConfigs {
        getByName("debug") {
            keyAlias = "androiddebugkey"
            keyPassword = "android"
            storeFile = file("debug.keystore")
            storePassword = "android"
        }
        create("release") {
            val keystorePropertiesFile = rootProject.file("key.properties")
            if (keystorePropertiesFile.exists()) {
                val keystoreProperties = Properties()
                keystoreProperties.load(FileInputStream(keystorePropertiesFile))
                keyAlias = keystoreProperties["keyAlias"] as String
                keyPassword = keystoreProperties["keyPassword"] as String
                storeFile = file(keystoreProperties["storeFile"] as String)
                storePassword = keystoreProperties["storePassword"] as String
            } else {
                // Fall back to debug signing if key.properties not found (dev builds)
                keyAlias = "androiddebugkey"
                keyPassword = "android"
                storeFile = file("debug.keystore")
                storePassword = "android"
            }
            // Signature schemes: v2 + v3 (v1/JAR is not needed for minSdk>=24;
            // AGP omits it by default). Play Store re-signs on delivery, so
            // testers are unaffected regardless.
            //
            // NOTE on the "App wasn't installed" saga: signing was investigated
            // and RULED OUT as the cause. The real cause is device-side — on a
            // Pixel 4 / Android 13, Play Protect runs a ~6s Just-in-Time scan on
            // sideloaded APKs (PlayProtectDialogsActivity) that races and
            // outlives the PackageInstaller session ("Session ID is no longer
            // active"), so tap-install intermittently fails even though the
            // verdict is ALLOW. It is non-deterministic and not a build defect:
            // the same APK installs reliably via `adb install -r` and via the
            // Play Store. See ClickUp wdvrdaxxmb for the full logcat evidence.
            enableV2Signing = true
            enableV3Signing = true
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_11
        targetCompatibility = JavaVersion.VERSION_11
        isCoreLibraryDesugaringEnabled = true
    }

    kotlinOptions {
        jvmTarget = "11"
    }

    defaultConfig {
        // TODO: Specify your own unique Application ID (https://developer.android.com/studio/build/application-id.html).
        applicationId = "com.audioura.audiotours"
        // You can update the following values to match your application needs.
        // For more information, see: https://flutter.dev/to/review-gradle-config.
        minSdk = 24
        targetSdk = flutter.targetSdkVersion
        versionCode = flutter.versionCode
        versionName = flutter.versionName
    }

    buildTypes {
        release {
            signingConfig = signingConfigs.getByName("release")
        }
        debug {
            signingConfig = signingConfigs.getByName("debug")
        }
    }
}

dependencies {
    coreLibraryDesugaring("com.android.tools:desugar_jdk_libs:2.0.4")
    implementation("com.google.android.play:integrity:1.4.0")
}

flutter {
    source = "../.."
}
