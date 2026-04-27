package com.hirestack.ai.ui.components

import androidx.compose.material3.SnackbarDuration
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.SnackbarResult
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.compositionLocalOf
import androidx.compose.runtime.staticCompositionLocalOf
import androidx.compose.ui.hapticfeedback.HapticFeedback
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.launch

/* ------------------------------------------------------------------ */
/*  CompositionLocals: app-wide snackbar + haptics                     */
/* ------------------------------------------------------------------ */

/** Provided in MainShell. */
val LocalSnackbar = staticCompositionLocalOf<SnackbarHostState> {
    error("No SnackbarHostState provided. Wrap content in MainShell.")
}

/** Provided in MainShell. Use to launch coroutines for snackbar. */
val LocalAppScope = compositionLocalOf<CoroutineScope> {
    error("No CoroutineScope provided. Wrap content in MainShell.")
}

/* ------------------------------------------------------------------ */
/*  Convenience helpers                                                */
/* ------------------------------------------------------------------ */

fun CoroutineScope.toast(host: SnackbarHostState, message: String) {
    launch {
        host.currentSnackbarData?.dismiss()
        host.showSnackbar(message = message, duration = SnackbarDuration.Short)
    }
}

/**
 * Shows a snackbar with an Undo action. Returns true if the user pressed Undo,
 * false if the snackbar was dismissed (timeout or new snackbar).
 */
suspend fun SnackbarHostState.showUndo(message: String, actionLabel: String = "Undo"): Boolean {
    currentSnackbarData?.dismiss()
    val result = showSnackbar(
        message = message,
        actionLabel = actionLabel,
        withDismissAction = false,
        duration = SnackbarDuration.Short,
    )
    return result == SnackbarResult.ActionPerformed
}

fun HapticFeedback.tap() = performHapticFeedback(HapticFeedbackType.TextHandleMove)
fun HapticFeedback.confirm() = performHapticFeedback(HapticFeedbackType.LongPress)

/**
 * Surfaces a transient error message via the app snackbar then clears it via [onClear].
 * Drop into any screen that exposes a nullable error in its VM state.
 */
@Composable
fun ErrorSnackbar(error: String?, onClear: () -> Unit) {
    val snackbar = LocalSnackbar.current
    LaunchedEffect(error) {
        if (!error.isNullOrBlank()) {
            snackbar.currentSnackbarData?.dismiss()
            snackbar.showSnackbar(message = error, duration = SnackbarDuration.Short)
            onClear()
        }
    }
}
