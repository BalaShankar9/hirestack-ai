package com.hirestack.ai.ui.profiles

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Star
import androidx.compose.material.icons.filled.StarBorder
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.PersonOutline
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.Profile
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
import com.hirestack.ai.ui.components.ErrorSnackbar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.tap
import com.hirestack.ai.ui.components.toast
import com.hirestack.ai.ui.theme.Brand
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ProfilesScreen(onBack: () -> Unit, vm: ProfilesViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    var pendingDelete by remember { mutableStateOf<Profile?>(null) }
    ErrorSnackbar(state.error) { vm.clearError() }
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Resume profiles",
                subtitle = "${state.items.size} saved",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("My HireStack profiles (${state.items.size})")
                                appendLine()
                                state.items.take(20).forEach { p ->
                                    val name = p.full_name ?: "(unnamed)"
                                    val primary = if (p.is_primary == true) " ★" else ""
                                    appendLine("- $name$primary")
                                    p.headline?.let { appendLine("    $it") }
                                    val contact = listOfNotNull(p.email, p.phone, p.location).joinToString(" • ")
                                    if (contact.isNotBlank()) appendLine("    $contact")
                                }
                                if (state.items.size > 20) {
                                    appendLine()
                                    appendLine("…and ${state.items.size - 20} more")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack resume profiles")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share resume profiles"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share resume profiles")
                        }
                    }
                },
            )
        },
    ) { padding ->
        BrandBackground {
            Box(modifier = Modifier.fillMaxSize().padding(padding)) {
                PullToRefreshBox(
                    isRefreshing = state.isLoading && state.items.isNotEmpty(),
                    onRefresh = { haptic.tap(); vm.refresh() },
                    modifier = Modifier.fillMaxSize(),
                ) {
                    when {
                        state.isLoading && state.items.isEmpty() -> SkeletonList(rows = 5)
                        state.error != null && state.items.isEmpty() -> Column(Modifier.padding(20.dp)) {
                            InlineBanner(state.error!!, tone = PillTone.Danger)
                            Spacer(Modifier.height(12.dp))
                            HireStackPrimaryButton("Retry", onClick = { vm.refresh() })
                        }
                        state.items.isEmpty() -> EmptyState(
                            title = "No resume profiles yet",
                            description = "Profiles appear here once you've uploaded a resume to your account.",
                            actionLabel = "Refresh",
                            onAction = { haptic.tap(); vm.refresh() },
                        )
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            item {
                                Text(
                                    "Tap the star to set a profile as primary.",
                                    style = MaterialTheme.typography.bodySmall,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                            items(state.items, key = { it.id }) { p ->
                                val dismissState = rememberSwipeToDismissBoxState(
                                    confirmValueChange = { value ->
                                        if (value == SwipeToDismissBoxValue.EndToStart) {
                                            haptic.tap()
                                            pendingDelete = p
                                            false
                                        } else false
                                    },
                                )
                                SwipeToDismissBox(
                                    state = dismissState,
                                    enableDismissFromStartToEnd = false,
                                    backgroundContent = {
                                        Box(
                                            modifier = Modifier
                                                .fillMaxSize()
                                                .background(Brand.Danger.copy(alpha = 0.18f), RoundedCornerShape(20.dp))
                                                .padding(horizontal = 24.dp),
                                            contentAlignment = Alignment.CenterEnd,
                                        ) {
                                            Icon(Icons.Outlined.Delete, contentDescription = "Delete", tint = Brand.Danger)
                                        }
                                    },
                                ) {
                                    ProfileRow(
                                        profile = p,
                                        onTogglePrimary = {
                                            haptic.tap()
                                            vm.setPrimary(p.id)
                                            scope.toast(snackbar, "Primary updated")
                                        },
                                        onDelete = { pendingDelete = p },
                                    )
                                }
                            }
                            state.error?.let {
                                item { InlineBanner(it, tone = PillTone.Danger) }
                            }
                        }
                    }
                }
            }
        }
    }

    pendingDelete?.let { p ->
        AlertDialog(
            onDismissRequest = { pendingDelete = null },
            title = { Text("Delete profile?") },
            text = { Text(p.full_name ?: p.email ?: p.id) },
            confirmButton = {
                TextButton(
                    onClick = {
                        val id = p.id
                        pendingDelete = null
                        haptic.confirm()
                        vm.delete(id)
                        scope.toast(snackbar, "Profile deleted")
                    },
                    colors = ButtonDefaults.textButtonColors(contentColor = Brand.Danger),
                ) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { pendingDelete = null }) { Text("Cancel") }
            },
        )
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ProfileRow(profile: Profile, onTogglePrimary: () -> Unit, onDelete: () -> Unit) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Surface(
                color = Brand.Cyan.copy(alpha = 0.16f),
                shape = CircleShape,
                modifier = Modifier.size(44.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Outlined.PersonOutline, null, tint = Brand.Cyan)
                }
            }
            Spacer(Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                val titleText = profile.full_name ?: profile.headline ?: profile.email ?: "Unnamed profile"
                Text(
                    titleText,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(titleText, "name") },
                    ),
                )
                val sub = listOfNotNull(profile.email, profile.location).joinToString(" • ")
                if (sub.isNotBlank()) {
                    Spacer(Modifier.height(2.dp))
                    Text(
                        sub,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.combinedClickable(
                            onClick = {},
                            onLongClick = { copy(sub, "details") },
                        ),
                    )
                }
                if (profile.is_primary == true) {
                    Spacer(Modifier.height(6.dp))
                    StatusPill(text = "Primary", tone = PillTone.Brand)
                }
            }
            IconButton(onClick = onTogglePrimary) {
                if (profile.is_primary == true) {
                    Icon(Icons.Default.Star, contentDescription = "Primary", tint = Brand.Amber)
                } else {
                    Icon(Icons.Default.StarBorder, contentDescription = "Set primary")
                }
            }
            TextButton(
                onClick = onDelete,
                colors = ButtonDefaults.textButtonColors(contentColor = Brand.Danger),
            ) { Text("Delete") }
        }
    }
}
