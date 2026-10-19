// SPDX-FileCopyrightText: 2026 edgecoil
// SPDX-License-Identifier: MIT
plugins {
    id("com.android.application")
}

android {
    namespace = "dev.edgecoil.tunebutton"
    compileSdk = 35
    defaultConfig {
        applicationId = "dev.edgecoil.tunebutton"
        minSdk = 26
        targetSdk = 35
        versionCode = 1
        versionName = "0.1.0"
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    testOptions { unitTests.isReturnDefaultValues = true }
}

dependencies {
    implementation("androidx.work:work-runtime:2.10.5")
    testImplementation("junit:junit:4.13.2")
    testImplementation("org.json:json:20250517")
}
