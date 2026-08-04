import java.util.Properties

plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.android)
    alias(libs.plugins.kotlin.compose)
    alias(libs.plugins.kotlin.serialization)
    alias(libs.plugins.detekt)
    alias(libs.plugins.ktlint)
    alias(libs.plugins.ksp)
}

fun String.asBuildConfigString(): String = "\"" + replace("\\", "\\\\").replace("\"", "\\\"") + "\""

val localProperties =
    Properties().apply {
        rootProject
            .file("local.properties")
            .takeIf { it.isFile }
            ?.inputStream()
            ?.use(::load)
    }

val mnemeApiBaseUrl =
    providers
        .gradleProperty("MNEME_API_BASE_URL")
        .orElse(providers.environmentVariable("MNEME_API_BASE_URL"))
        .orElse(localProperties.getProperty("MNEME_API_BASE_URL") ?: "http://10.0.2.2:8000/v1/")
val mnemeDemoToken =
    providers
        .gradleProperty("MNEME_DEMO_TOKEN")
        .orElse(providers.environmentVariable("MNEME_DEMO_TOKEN"))
        .orElse(localProperties.getProperty("MNEME_DEMO_TOKEN") ?: "")

ksp {
    arg("room.schemaLocation", "$projectDir/src/main/schemas")
}

android {
    namespace = "com.mneme.app"
    compileSdk = 36

    defaultConfig {
        applicationId = "com.mneme.app"
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0"

        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        buildConfigField("String", "MNEME_API_BASE_URL", mnemeApiBaseUrl.get().asBuildConfigString())
        buildConfigField("String", "MNEME_DEMO_TOKEN", mnemeDemoToken.get().asBuildConfigString())
    }

    sourceSets {
        getByName("androidTest").assets.srcDir("$projectDir/src/main/schemas")
    }

    buildTypes {
        create("benchmark") {
            initWith(getByName("release"))
            signingConfig = signingConfigs.getByName("debug")
            matchingFallbacks += listOf("release")
            buildConfigField(
                "String",
                "MNEME_API_BASE_URL",
                "http://127.0.0.1:9/v1/".asBuildConfigString(),
            )
            buildConfigField(
                "String",
                "MNEME_DEMO_TOKEN",
                "benchmark-cache-only".asBuildConfigString(),
            )
        }
        release {
            isMinifyEnabled = false
            proguardFiles(
                getDefaultProguardFile("proguard-android-optimize.txt"),
                "proguard-rules.pro",
            )
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
        compose = true
        buildConfig = true
    }

    packaging {
        resources.excludes += "/META-INF/{AL2.0,LGPL2.1}"
    }
}

detekt {
    buildUponDefaultConfig = true
    config.setFrom(files("$rootDir/detekt.yml"))
    parallel = true
}

dependencies {
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.lifecycle.runtime.ktx)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.activity.compose)

    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.ui.graphics)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons.extended)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.room.runtime)
    implementation(libs.androidx.room.ktx)
    implementation(libs.androidx.datastore.preferences)
    implementation(libs.androidx.work.runtime)
    implementation(libs.kotlinx.serialization.core)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.retrofit.core)
    implementation(libs.retrofit.kotlinx.serialization)
    implementation(libs.okhttp)
    ksp(libs.androidx.room.compiler)

    testImplementation(libs.junit)
    testImplementation(libs.okhttp.mockwebserver)

    androidTestImplementation(libs.androidx.junit)
    androidTestImplementation(libs.androidx.espresso.core)
    androidTestImplementation(libs.androidx.test.core.ktx)
    androidTestImplementation(libs.androidx.room.testing)
    androidTestImplementation(libs.okhttp.mockwebserver)
    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)

    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)
}
