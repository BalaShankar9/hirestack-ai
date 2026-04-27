package com.hirestack.ai.ui.applications

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.WorkOutline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
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
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.Application
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.ScoreRing
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.confirm
import kotlinx.coroutines.launch
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.theme.Brand

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ApplicationsScreen(
    onCreate: () -> Unit,
    onOpen: (String) -> Unit,
) {
    val vm: ApplicationsViewModel = hiltViewModel()
    val state by vm.state.collectAsState()
    com.hirestack.ai.ui.components.ErrorSnackbar(state.error) { vm.clearError() }
    val listState = androidx.compose.foundation.lazy.rememberLazyListState()
    val fabExpanded by remember { androidx.compose.runtime.derivedStateOf { listState.firstVisibleItemIndex == 0 } }
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            BrandTopBar(
                title = "Applications",
                subtitle = "Tailored CV, cover letter, and intel for every role",
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("My applications (${state.items.size})")
                                appendLine()
                                state.items.take(50).forEach { a ->
                                    val title = a.job_title ?: a.title ?: "Untitled role"
                                    val sub = listOfNotNull(a.company, a.location).joinToString(" • ")
                                    val statusSuffix = a.status?.takeIf { it.isNotBlank() }?.let { " [$it]" } ?: ""
                                    appendLine("- $title${if (sub.isNotBlank()) " — $sub" else ""}$statusSuffix")
                                }
                                if (state.items.size > 50) {
                                    appendLine()
                                    appendLine("…and ${state.items.size - 50} more")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack applications")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share applications"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share applications")
                        }
                    }
                },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = onCreate,
                icon = { Icon(Icons.Filled.Add, contentDescription = null) },
                text = { Text("New application") },
                expanded = fabExpanded,
                containerColor = Brand.Indigo,
                contentColor = androidx.compose.ui.graphics.Color.White,
            )
        },
        containerColor = androidx.compose.ui.graphics.Color.Transparent,
    ) { padding ->
        BrandBackground {
            PullToRefreshBox(
                isRefreshing = state.refreshing,
                onRefresh = vm::refresh,
                modifier = Modifier
                    .fillMaxSize()
                    .padding(padding),
            ) {
                when {
                    state.isLoading && state.items.isEmpty() -> {
                        SkeletonList()
                    }
                    state.items.isEmpty() -> {
                        Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            EmptyState(
                                title = "No applications yet",
                                description = "Tap “New application” to generate a tailored CV, cover letter, and personal statement in minutes.",
                                actionLabel = "Start your first one",
                                onAction = onCreate,
                            )
                        }
                    }
                    else -> {
                        LazyColumn(
                            state = listState,
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 96.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            if (state.error != null) {
                                item {
                                    InlineBanner(
                                        message = state.error!!,
                                        tone = PillTone.Warning,
                                    )
                                }
                            }
                            items(state.items, key = { it.id }) { app ->
                                ApplicationCard(app = app, onOpen = { onOpen(app.id) })
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
private fun ApplicationCard(app: Application, onOpen: () -> Unit) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(androidx.compose.ui.text.AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard(onClick = onOpen) {
        Column(Modifier.padding(18.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Icon(
                    Icons.Outlined.WorkOutline,
                    contentDescription = null,
                    tint = Brand.Indigo,
                    modifier = Modifier.padding(end = 10.dp),
                )
                Column(Modifier.weight(1f)) {
                    val titleText = app.title ?: app.job_title ?: "Untitled application"
                    Text(
                        titleText,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.combinedClickable(
                            onClick = onOpen,
                            onLongClick = { copy(titleText, "title") },
                        ),
                    )
                    val sub = listOfNotNull(app.company, app.location).joinToString(" • ")
                    if (sub.isNotEmpty()) {
                        Text(
                            sub,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            modifier = Modifier.combinedClickable(
                                onClick = onOpen,
                                onLongClick = { copy(sub, "details") },
                            ),
                        )
                    }
                }
                val score = (app.scores?.overall ?: 0.0).toInt()
                if (score > 0) {
                    ScoreRing(score = score, sizeDp = 56, strokeDp = 6)
                }
            }
            Spacer(Modifier.height(14.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusPill(
                    text = (app.status ?: "draft").uppercase(),
                    tone = when (app.status) {
                        "complete", "completed", "ready" -> PillTone.Success
                        "running", "generating", "in_progress" -> PillTone.Info
                        "error", "failed" -> PillTone.Danger
                        else -> PillTone.Neutral
                    },
                )
                Spacer(Modifier.width(8.dp))
                if (app.facts_locked == true) {
                    StatusPill(text = "Facts locked", tone = PillTone.Success)
                }
                Spacer(Modifier.weight(1f))
                Text(
                    app.updated_at?.take(10) ?: "",
                    style = MaterialTheme.typography.labelSmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}
