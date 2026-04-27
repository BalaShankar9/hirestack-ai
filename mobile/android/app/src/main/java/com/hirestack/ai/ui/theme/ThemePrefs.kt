package com.hirestack.ai.ui.theme

import android.content.Context
import androidx.compose.runtime.Composable
import androidx.compose.runtime.MutableState
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.ui.platform.LocalContext

enum class ThemeMode { System, Dark, Light }

private const val PREFS = "hirestack_prefs"
private const val KEY_THEME = "theme_mode"

object ThemePrefs {
    fun read(context: Context): ThemeMode {
        val raw = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE).getString(KEY_THEME, null)
        return runCatching { ThemeMode.valueOf(raw ?: ThemeMode.System.name) }.getOrDefault(ThemeMode.System)
    }

    fun write(context: Context, mode: ThemeMode) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_THEME, mode.name)
            .apply()
    }
}

val LocalThemeMode = compositionLocalOf<MutableState<ThemeMode>> {
    error("ThemeMode not provided")
}

@Composable
fun rememberThemeModeState(): MutableState<ThemeMode> {
    val context = LocalContext.current
    return remember { mutableStateOf(ThemePrefs.read(context)) }
}
