# Add project specific ProGuard rules here.
-keep class com.hirestack.ai.** { *; }
-keep class kotlinx.serialization.** { *; }
-keep class io.github.jan.supabase.** { *; }

# Moshi
-keep class com.squareup.moshi.** { *; }
-keep @com.squareup.moshi.JsonClass class * { *; }

# Retrofit
-dontwarn retrofit2.**
-keep class retrofit2.** { *; }

# OkHttp
-dontwarn okhttp3.**
-dontwarn okio.**
