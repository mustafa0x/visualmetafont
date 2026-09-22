plugins {
    id("com.android.library")
}

android {
    namespace = "io.github.mustafa0x.digitalkhatt.consumer"
    compileSdk = 36
    ndkVersion = "27.1.12297006"

    defaultConfig {
        minSdk = 24
        externalNativeBuild {
            cmake { arguments += "-DANDROID_STL=c++_shared" }
        }
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.28.3"
        }
    }
    buildFeatures { prefab = true }
}

dependencies {
    implementation(files("../engine/build/outputs/aar/engine-release.aar"))
}
