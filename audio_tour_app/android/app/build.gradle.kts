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
            // Signature schemes. The AGP shipped with Flutter 3.41.6 defaulted
            // this release config to v2-ONLY, which tap-installs on a Pixel 4
            // (Android 13) failed with the generic "App wasn't installed" — even
            // on a clean device, even though Play Protect logged ALLOW and the
            // integrity check passed. A one-variable test (same bytes, same key,
            // re-signed with v3+v4) tap-installed successfully, isolating the
            // missing v3/v4 signatures as the cause. v4 produces the .idsig used
            // by the streaming/incremental installer path that Files-by-Google
            // uses. Enable v2+v3+v4; v1 is intentionally left off (AGP omits it
            // for minSdk>=24 and it is not needed on API 24+).
            enableV1Signing = false
            enableV2Signing = true
            enableV3Signing = true
            enableV4Signing = true
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
