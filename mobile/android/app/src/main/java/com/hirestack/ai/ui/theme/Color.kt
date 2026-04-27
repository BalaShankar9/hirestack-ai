package com.hirestack.ai.ui.theme

import androidx.compose.ui.graphics.Brush
import androidx.compose.ui.graphics.Color

/**
 * HireStack brand palette — phone-first re-imagining, not a web clone.
 * Dark-first because the AI/career space reads premium in dark, and OLED
 * phones get a battery win. A high-contrast light scheme is provided for
 * accessibility but the splash + nav default to dark.
 */
object Brand {
    // Core brand
    val Indigo = Color(0xFF6366F1)
    val Violet = Color(0xFF8B5CF6)
    val Pink = Color(0xFFEC4899)
    val Cyan = Color(0xFF06B6D4)
    val Emerald = Color(0xFF10B981)
    val Amber = Color(0xFFF59E0B)
    val Rose = Color(0xFFF43F5E)

    // Surfaces (dark)
    val Ink900 = Color(0xFF07070D)   // app background
    val Ink800 = Color(0xFF0E0E1A)   // surface
    val Ink700 = Color(0xFF161629)   // surface variant / cards
    val Ink600 = Color(0xFF1F1F38)   // outline
    val Ink500 = Color(0xFF2C2C4A)   // outline-variant
    val Ink400 = Color(0xFF6B6B8A)   // muted text
    val Ink200 = Color(0xFFB7B7D1)   // body text on dark
    val Ink50  = Color(0xFFF5F5FB)   // primary text on dark

    // Surfaces (light)
    val Cloud0  = Color(0xFFFFFFFF)
    val Cloud50 = Color(0xFFF7F7FB)
    val Cloud100 = Color(0xFFEDEDF5)
    val Cloud200 = Color(0xFFD9D9E6)
    val Cloud700 = Color(0xFF3A3A55)
    val Cloud900 = Color(0xFF111122)

    // Status
    val Success = Emerald
    val Warning = Amber
    val Danger = Rose
    val Info = Cyan
}

/**
 * Branded gradients used by hero cards, score rings, and the launcher backdrop.
 * Compose Brush is cheap to construct each frame; no need to memoize.
 */
object BrandGradient {
    val HeroDark = Brush.linearGradient(
        colors = listOf(Color(0xFF1E1B4B), Color(0xFF312E81), Color(0xFF4C1D95)),
    )
    val Aurora = Brush.linearGradient(
        colors = listOf(Brand.Indigo, Brand.Violet, Brand.Pink),
    )
    val Cool = Brush.linearGradient(
        colors = listOf(Brand.Cyan, Brand.Indigo),
    )
    val Warm = Brush.linearGradient(
        colors = listOf(Brand.Amber, Brand.Pink),
    )
    val Mint = Brush.linearGradient(
        colors = listOf(Brand.Emerald, Brand.Cyan),
    )
    val Subtle = Brush.verticalGradient(
        colors = listOf(Brand.Ink800, Brand.Ink900),
    )
}
