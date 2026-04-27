package com.hirestack.ai.ui.variants

import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import com.hirestack.ai.data.network.DocVariant
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
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
fun VariantsScreen(onBack: () -> Unit, vm: VariantsViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    com.hirestack.ai.ui.components.ErrorSnackbar(state.error) { vm.clearError() }
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    var expanded by remember { mutableStateOf<String?>(null) }
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Doc Variants",
                subtitle = "${state.items.size} generated",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("My document variants (${state.items.size})")
                                appendLine()
                                state.items.take(30).forEach { v ->
                                    val name = v.variant_name ?: v.document_type ?: "(untitled)"
                                    val star = if (v.is_selected == true) " ★" else ""
                                    val tone = v.tone?.takeIf { it.isNotBlank() }?.let { " — $it" } ?: ""
                                    appendLine("- $name$star$tone")
                                    val metrics = buildList {
                                        v.ats_score?.let { add("ATS ${"%.0f".format(it)}") }
                                        v.readability_score?.let { add("Readability ${"%.0f".format(it)}") }
                                        v.word_count?.let { add("$it words") }
                                    }.joinToString(" • ")
                                    if (metrics.isNotBlank()) appendLine("    $metrics")
                                }
                                if (state.items.size > 30) appendLine("\n…and ${state.items.size - 30} more")
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack document variants")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share variants"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share variants")
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
                            title = "No variants yet",
                            description = "Tone variants from your A/B doc experiments will appear here.",
                            actionLabel = "Refresh",
                            onAction = { haptic.tap(); vm.refresh() },
                        )
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(state.items, key = { it.id }) { v ->
                                VariantCard(
                                    v = v,
                                    isExpanded = expanded == v.id,
                                    isSelecting = state.selecting == v.id,
                                    onToggle = { haptic.tap(); expanded = if (expanded == v.id) null else v.id },
                                    onSelect = {
                                        haptic.confirm()
                                        vm.select(v.id)
                                        scope.toast(snackbar, "Variant selected")
                                    },
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun VariantCard(
    v: DocVariant,
    isExpanded: Boolean,
    isSelecting: Boolean,
    onToggle: () -> Unit,
    onSelect: () -> Unit,
) {
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
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    val titleText = v.variant_name?.replaceFirstChar { it.titlecase() } ?: v.tone ?: "Variant"
                    Text(
                        titleText,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.combinedClickable(
                            onClick = {},
                            onLongClick = { copy(titleText, "name") },
                        ),
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        listOfNotNull(v.document_type, v.word_count?.let { "$it words" }).joinToString(" • "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (v.is_selected == true) {
                    Icon(Icons.Filled.CheckCircle, contentDescription = "Selected", tint = Brand.Emerald)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                v.ats_score?.let { StatusPill(text = "ATS ${it.toInt()}", tone = PillTone.Brand) }
                v.readability_score?.let { StatusPill(text = "Read ${it.toInt()}", tone = PillTone.Neutral) }
            }
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                TextButton(onClick = onToggle) {
                    Text(if (isExpanded) "Hide content" else "View content", color = Brand.Indigo)
                }
                Spacer(Modifier.weight(1f))
                if (v.is_selected != true) {
                    HireStackPrimaryButton(
                        label = if (isSelecting) "Selecting…" else "Select",
                        onClick = onSelect,
                        enabled = !isSelecting,
                        loading = isSelecting,
                    )
                }
            }
            if (isExpanded) {
                Spacer(Modifier.height(8.dp))
                HorizontalDivider()
                Spacer(Modifier.height(8.dp))
                val body = v.content ?: "(no content)"
                Text(
                    body,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { if (v.content != null) copy(body, "variant content") },
                    ),
                )
            }
        }
    }
}
