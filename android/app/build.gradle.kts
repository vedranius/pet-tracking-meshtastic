plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.pawtrack.app"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.pawtrack.app"
        minSdk = 26
        targetSdk = 34
        versionCode = 2
        versionName = "0.1.1"
    }

    signingConfigs {
        // Populated from environment variables in CI (see .github/workflows/android.yml)
        // so every release is signed with the same key and can be installed as an
        // upgrade over the previous one. Falls back to the debug key locally so
        // `./gradlew assembleDebug` (or assembleRelease without the env vars set)
        // still works for local development without needing a real keystore.
        create("release") {
            val storeFilePath = System.getenv("PAWTRACK_KEYSTORE_PATH")
            if (!storeFilePath.isNullOrBlank()) {
                storeFile = file(storeFilePath)
                storePassword = System.getenv("PAWTRACK_KEYSTORE_PASSWORD")
                keyAlias = System.getenv("PAWTRACK_KEY_ALIAS")
                keyPassword = System.getenv("PAWTRACK_KEY_PASSWORD")
            }
        }
    }

    buildTypes {
        release {
            isMinifyEnabled = false
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
            signingConfig = if (System.getenv("PAWTRACK_KEYSTORE_PATH").isNullOrBlank()) {
                signingConfigs.getByName("debug")
            } else {
                signingConfigs.getByName("release")
            }
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    kotlinOptions {
        jvmTarget = "17"
    }

    buildFeatures {
        viewBinding = true
        buildConfig = true // AGP 8+ disables BuildConfig generation by default
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.13.1")
    implementation("androidx.appcompat:appcompat:1.7.0")
    implementation("androidx.activity:activity-ktx:1.9.1")
    implementation("com.google.android.material:material:1.12.0")
    implementation("androidx.lifecycle:lifecycle-service:2.8.4")
    implementation("androidx.webkit:webkit:1.11.0")
    implementation("com.squareup.okhttp3:okhttp:4.12.0")
    implementation("org.json:json:20240303")
}
