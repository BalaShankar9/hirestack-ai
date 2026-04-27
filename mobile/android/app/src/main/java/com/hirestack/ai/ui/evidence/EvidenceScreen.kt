package com.hirestack.ai.ui.evidence

import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Bookmarks
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.EvidenceItem
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.theme.Brand
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun EvidenceScreen() {
    val vm: EvidenceViewModel = hiltViewModel()
    val state by vm.state.collectAsState()
    com.hirestack.ai.ui.components.ErrorSnackbar(state.error) { vm.clearError() }
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            BrandTopBar(
                title = "Evidence",
                subtitle = "Receipts, snippets, and proof points",
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("My evidence (${state.items.size})")
                                appendLine()
                                state.items.take(30).forEach { ev ->
                                    val title = ev.title ?: "(untitled)"
                                    val type = ev.type?.takeIf { it.isNotBlank() }?.let { " [$it]" } ?: ""
                                    appendLine("- $title$type")
                                    ev.description?.takeIf { it.isNotBlank() }?.let { appendLine("    $it") }
                                    val link = ev.url ?: ev.file_url ?: ev.storage_url
                                    if (!link.isNullOrBlank()) appendLine("    $link")
                                    if (!ev.skills.isNullOrEmpty()) appendLine("    skills: ${ev.skills.joinToString(", ")}")
                                }
                                if (state.items.size > 30) {
                                    appendLine()
                                    appendLine("…and ${state.items.size - 30} more")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack evidence locker")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share evidence"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share evidence")
                        }
                    }
                },
            )
        },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            PullToRefreshBox(
                isRefreshing = state.refreshing,
                onRefresh = vm::refresh,
                modifier = Modifier.fillMaxSize().padding(padding),
            ) {
                when {
                    state.isLoading && state.items.isEmpty() -> SkeletonList()
                    state.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        EmptyState(
                            title = "No evidence yet",
                            description = "Add wins, snippets, and links to strengthen every application.",
                            icon = Icons.Outlined.Bookmarks,
                            actionLabel = "Refresh",
                            onAction = vm::refresh,
                        )
                    }
                    else -> LazyColumn(
                        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        items(state.items, key = { it.id }) { ev -> EvidenceCard(ev) }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun EvidenceCard(ev: EvidenceItem) {
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
                Icon(
                    Icons.Outlined.Bookmarks,
                    contentDescription = null,
                    tint = Brand.Indigo,
                )
                Spacer(Modifier.width(10.dp))
                val titleText = ev.title ?: ev.type ?: "Evidence"
                Text(
                    titleText,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier
                        .weight(1f)
                        .combinedClickable(
                            onClick = {},
                            onLongClick = { copy(titleText, "title") },
                        ),
                )
                if (ev.type != null) StatusPill(text = ev.type!!.uppercase(), tone = PillTone.Brand)
            }
            if (!ev.description.isNullOrBlank()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    ev.description!!,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(ev.description!!, "description") },
                    ),
                )
            }
            val tags = (ev.skills.orEmpty() + ev.tools.orEmpty() + ev.tags.orEmpty()).distinct()
            if (tags.isNotEmpty()) {
                Spacer(Modifier.height(10.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    tags.take(5).forEach { t -> StatusPill(text = t) }
                }
            }
        }
    }
}
