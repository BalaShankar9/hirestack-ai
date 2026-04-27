package com.hirestack.ai.ui.theme

import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.darkColorScheme
import androidx.compose.material3.lightColorScheme
import androidx.compose.runtime.Composable

/**
 * Dark-first color scheme that maps the HireStack brand into M3 roles cleanly.
 * Light scheme provided for accessibility / OS-forced light, but app default is dark.
 */
private val DarkColors = darkColorScheme(
    primary = Brand.Indigo,
    onPrimary = Brand.Ink50,
    primaryContainer = Brand.Ink600,
    onPrimaryContainer = Brand.Ink50,

    secondary = Brand.Violet,
    onSecondary = Brand.Ink50,
    secondaryContainer = Brand.Ink600,
    onSecondaryContainer = Brand.Ink50,

    tertiary = Brand.Pink,
    onTertiary = Brand.Ink50,
    tertiaryContainer = Brand.Ink600,
    onTertiaryContainer = Brand.Ink50,

    background = Brand.Ink900,
    onBackground = Brand.Ink50,
    surface = Brand.Ink800,
    onSurface = Brand.Ink50,
    surfaceVariant = Brand.Ink700,
    onSurfaceVariant = Brand.Ink200,
    surfaceContainerLowest = Brand.Ink900,
    surfaceContainerLow = Brand.Ink800,
    surfaceContainer = Brand.Ink700,
    surfaceContainerHigh = Brand.Ink600,
    surfaceContainerHighest = Brand.Ink500,

    outline = Brand.Ink500,
    outlineVariant = Brand.Ink600,

    error = Brand.Danger,
    onError = Brand.Ink50,

    inverseSurface = Brand.Cloud50,
    inverseOnSurface = Brand.Cloud900,
)

private val LightColors = lightColorScheme(
    primary = Brand.Indigo,
    secondary = Brand.Violet,
    tertiary = Brand.Pink,
    background = Brand.Cloud50,
    surface = Brand.Cloud0,
    surfaceVariant = Brand.Cloud100,
    onSurface = Brand.Cloud900,
    onSurfaceVariant = Brand.Cloud700,
    outline = Brand.Cloud200,
    error = Brand.Danger,
)

@Composable
fun HireStackTheme(
    darkTheme: Boolean = true, // brand-default dark
    dynamicColor: Boolean = false, // opt-in Material You; default off to preserve brand
    content: @Composable () -> Unit,
) {
    val context = androidx.compose.ui.platform.LocalContext.current
    val scheme = when {
        dynamicColor && android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.S ->
            if (darkTheme) androidx.compose.material3.dynamicDarkColorScheme(context)
            else androidx.compose.material3.dynamicLightColorScheme(context)
        darkTheme -> DarkColors
        else -> LightColors
    }
    MaterialTheme(
        colorScheme = scheme,
        typography = HireStackTypography,
        shapes = HireStackShapes,
        content = content,
    )
}
