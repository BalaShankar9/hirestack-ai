package com.hirestack.ai.ui.docs

import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.foundation.rememberScrollState
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.FilterChipDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.DocumentLibraryItem
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.tap
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DocsScreen(onBack: () -> Unit, vm: DocsViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    com.hirestack.ai.ui.components.ErrorSnackbar(state.error) { vm.clearError() }
    val haptic = LocalHapticFeedback.current
    val tabs = listOf(null to "All", "fixed" to "Fixed", "tailored" to "Tailored", "benchmark" to "Benchmark")
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Document library",
                subtitle = "${state.items.size} docs",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val grouped = state.items.groupBy { (it.doc_category ?: it.doc_type ?: "other").lowercase() }
                            val report = buildString {
                                appendLine("My document library (${state.items.size})")
                                appendLine()
                                grouped.forEach { (cat, list) ->
                                    appendLine("$cat (${list.size})")
                                    list.take(15).forEach { d ->
                                        val title = d.label ?: d.doc_type ?: "(untitled)"
                                        val ver = d.version?.let { " v$it" } ?: ""
                                        val status = d.status?.takeIf { it.isNotBlank() }?.let { " [$it]" } ?: ""
                                        appendLine("- $title$ver$status")
                                    }
                                    if (list.size > 15) appendLine("    …and ${list.size - 15} more")
                                    appendLine()
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack document library")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share document library"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share document library")
                        }
                    }
                },
            )
        },
    ) { padding ->
        BrandBackground {
            Column(modifier = Modifier.fillMaxSize().padding(padding)) {
                Row(
                    modifier = Modifier
                        .fillMaxWidth()
                        .horizontalScroll(rememberScrollState())
                        .padding(horizontal = 20.dp, vertical = 8.dp),
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    tabs.forEach { (key, label) ->
                        FilterChip(
                            selected = state.category == key,
                            onClick = { haptic.tap(); vm.setCategory(key) },
                            label = { Text(label) },
                            colors = FilterChipDefaults.filterChipColors(
                                selectedContainerColor = com.hirestack.ai.ui.theme.Brand.Indigo.copy(alpha = 0.20f),
                                selectedLabelColor = com.hirestack.ai.ui.theme.Brand.Indigo,
                            ),
                        )
                    }
                }

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
                            title = "No documents in this category",
                            description = "Documents you generate will appear here.",
                            actionLabel = "Refresh",
                            onAction = { haptic.tap(); vm.refresh() },
                        )
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(state.items, key = { it.id }) { DocRow(it) }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun DocRow(doc: DocumentLibraryItem) {
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
            val titleText = doc.label ?: doc.doc_type ?: "Untitled"
            Text(
                titleText,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = { copy(titleText, "label") },
                ),
            )
            Spacer(Modifier.height(4.dp))
            val parts = listOfNotNull(doc.doc_category, doc.doc_type, doc.status)
            val sub = parts.joinToString(" • ")
            Text(
                sub,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = { if (sub.isNotBlank()) copy(sub, "details") },
                ),
            )
            doc.version?.let {
                Spacer(Modifier.height(2.dp))
                Text("v$it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
            doc.updated_at?.let {
                Spacer(Modifier.height(2.dp))
                Text("Updated $it", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
    }
}
