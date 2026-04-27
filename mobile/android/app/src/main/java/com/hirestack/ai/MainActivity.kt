package com.hirestack.ai

import android.os.Bundle
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import com.hirestack.ai.ui.HireStackApp
import com.hirestack.ai.ui.theme.HireStackTheme
import com.hirestack.ai.ui.theme.LocalThemeMode
import com.hirestack.ai.ui.theme.ThemeMode
import com.hirestack.ai.ui.theme.ThemePrefs
import com.hirestack.ai.ui.theme.rememberThemeModeState
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.foundation.isSystemInDarkTheme
import dagger.hilt.android.AndroidEntryPoint

@AndroidEntryPoint
class MainActivity : ComponentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        // Must be called before super.onCreate(). Honours the
        // Theme.HireStack.Splash declared in AndroidManifest.
        installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        val deepLink = intent?.data?.host // hirestack://add-job → "add-job"
        setContent {
            val themeModeState = rememberThemeModeState()
            val ctx = androidx.compose.ui.platform.LocalContext.current
            LaunchedEffect(themeModeState.value) { ThemePrefs.write(ctx, themeModeState.value) }
            val systemDark = isSystemInDarkTheme()
            val darkTheme = when (themeModeState.value) {
                ThemeMode.System -> systemDark
                ThemeMode.Dark -> true
                ThemeMode.Light -> false
            }
            CompositionLocalProvider(LocalThemeMode provides themeModeState) {
                HireStackTheme(darkTheme = darkTheme) {
                    Surface(modifier = Modifier.fillMaxSize()) {
                        HireStackApp(initialDeepLink = deepLink)
                    }
                }
            }
        }
    }
}
