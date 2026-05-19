// Top-level build file where you can add configuration options common to all sub-projects/modules.
buildscript {
    repositories {
        google()
        mavenCentral()
    }
    dependencies {
        // Android Gradle Plugin
        classpath("com.android.tools.build:gradle:8.3.2")
        // Kotlin Gradle Plugin (1.9.23 Compose Compiler 1.5.11 ile uyumludur)
        classpath("org.jetbrains.kotlin:kotlin-gradle-plugin:1.9.23")
    }
}

tasks.register("clean", Delete::class) {
    delete(rootProject.layout.buildDirectory)
}
