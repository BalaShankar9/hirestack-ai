# =============================================================================
# HireStack AI – ProGuard / R8 rules
# =============================================================================
# Currently the release build has minification disabled (see build.gradle.kts).
# These rules are checked in so flipping `isMinifyEnabled = true` produces a
# working APK without further investigation. Keep this file in sync as new
# reflective dependencies are added.
# -----------------------------------------------------------------------------

# --- Hilt / Dagger -----------------------------------------------------------
-keep class dagger.hilt.** { *; }
-keep class * extends dagger.hilt.android.HiltAndroidApp { *; }
-keep class **_HiltModules* { *; }
-keep,allowobfuscation,allowshrinking @dagger.hilt.android.lifecycle.HiltViewModel class *

# --- Kotlin metadata ---------------------------------------------------------
-keep class kotlin.Metadata { *; }
-keepclassmembers class kotlin.Metadata { public <methods>; }

# --- Moshi (codegen-generated adapters) --------------------------------------
-keep class **JsonAdapter { *; }
-keep class **_JsonAdapter { *; }
-keepclassmembers class * { @com.squareup.moshi.* <methods>; }
-keepclasseswithmembers class * { @com.squareup.moshi.JsonClass <methods>; }
-keep @com.squareup.moshi.JsonClass class * { *; }

# Our DTOs all live here – keep them and their members.
-keep class com.hirestack.ai.data.network.** { *; }

# --- Retrofit / OkHttp -------------------------------------------------------
-keepattributes Signature, *Annotation*, EnclosingMethod, InnerClasses
-keep class retrofit2.** { *; }
-keepclassmembers,allowshrinking,allowobfuscation interface * {
    @retrofit2.http.* <methods>;
}
-dontwarn org.codehaus.mojo.animal_sniffer.IgnoreJRERequirement
-dontwarn javax.annotation.**
-dontwarn okhttp3.**
-dontwarn okio.**

# --- kotlinx.serialization (Supabase + Ktor use this) ------------------------
-keepattributes RuntimeVisibleAnnotations,AnnotationDefault
-keep,includedescriptorclasses class com.hirestack.ai.**$$serializer { *; }
-keepclassmembers class com.hirestack.ai.** { *** Companion; }
-keepclasseswithmembers class com.hirestack.ai.** {
    kotlinx.serialization.KSerializer serializer(...);
}

# --- Ktor (used by Supabase gotrue-kt) ---------------------------------------
-keep class io.ktor.** { *; }
-dontwarn io.ktor.**

# --- Supabase ----------------------------------------------------------------
-keep class io.github.jan.supabase.** { *; }
-dontwarn io.github.jan.supabase.**

# --- Coil --------------------------------------------------------------------
-dontwarn coil3.**

# --- DataStore ---------------------------------------------------------------
-keep class androidx.datastore.preferences.** { *; }

# --- Compose ----------------------------------------------------------------
-dontwarn androidx.compose.**
