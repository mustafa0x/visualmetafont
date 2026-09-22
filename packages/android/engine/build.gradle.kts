plugins {
    id("com.android.library")
}

val source_root = rootProject.projectDir.resolve("../..").canonicalFile

android {
    namespace = "io.github.mustafa0x.digitalkhatt.engine"
    compileSdk = 36
    ndkVersion = "27.1.12297006"

    defaultConfig {
        minSdk = 24
        externalNativeBuild {
            cmake {
                arguments += listOf(
                    "-DDIGITALKHATT_SOURCE_DIR=${source_root.absolutePath}",
                    "-DANDROID_STL=c++_shared",
                    "-DANDROID_SUPPORT_FLEXIBLE_PAGE_SIZES=ON",
                )
                providers.gradleProperty("pcre2Source").orNull?.let { source ->
                    arguments += listOf(
                        "-DFETCHCONTENT_SOURCE_DIR_PCRE2=${file(source).canonicalPath}",
                        "-DFETCHCONTENT_FULLY_DISCONNECTED=ON",
                    )
                }
            }
        }
        ndk { abiFilters += listOf("arm64-v8a", "x86_64") }
    }

    externalNativeBuild {
        cmake {
            path = file("src/main/cpp/CMakeLists.txt")
            version = "3.28.3"
        }
    }

    buildFeatures { prefabPublishing = true }
    prefab {
        create("digitalkhatt") {
            headers = source_root.resolve("lib/digitalkhatt/runtime/include").absolutePath
            libraryName = "libdigitalkhatt"
        }
    }
    sourceSets.getByName("main").assets.directories.add(source_root.resolve("packages/licenses").absolutePath)
}
