package com.hirestack.ai.ui.jobs

import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import kotlinx.coroutines.launch
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
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Work
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.ExtendedFloatingActionButton
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberSwipeToDismissBoxState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.Job
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
import com.hirestack.ai.ui.components.ErrorSnackbar
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.showUndo
import com.hirestack.ai.ui.components.tap
import com.hirestack.ai.ui.theme.Brand
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JobBoardScreen(
    onJobClick: (String) -> Unit,
    onAddJob: () -> Unit,
    vm: JobBoardViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val appScope = LocalAppScope.current
    var query by rememberSaveable { mutableStateOf("") }
    val keyboardController = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    androidx.activity.compose.BackHandler(enabled = query.isNotEmpty()) { query = "" }
    ErrorSnackbar(state.error) { vm.clearError() }

    val visible = remember(state.items, query) {
        if (query.isBlank()) state.items else state.items.filter {
            it.title.contains(query, ignoreCase = true) ||
                (it.company ?: "").contains(query, ignoreCase = true) ||
                (it.location ?: "").contains(query, ignoreCase = true)
        }
    }

    val scrollBehavior = TopAppBarDefaults.enterAlwaysScrollBehavior()
    val listState = androidx.compose.foundation.lazy.rememberLazyListState()
    val fabExpanded by remember { androidx.compose.runtime.derivedStateOf { listState.firstVisibleItemIndex == 0 } }

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Job board",
                subtitle = "${state.items.size} saved",
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        androidx.compose.material3.IconButton(onClick = {
                            val report = buildString {
                                appendLine("My saved jobs (${state.items.size})")
                                appendLine()
                                state.items.take(50).forEach { j ->
                                    val sub = listOfNotNull(j.company, j.location).joinToString(" • ")
                                    appendLine("- ${j.title}${if (sub.isNotBlank()) " — $sub" else ""}")
                                    if (!j.source_url.isNullOrBlank()) appendLine("    ${j.source_url}")
                                }
                                if (state.items.size > 50) {
                                    appendLine()
                                    appendLine("…and ${state.items.size - 50} more")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My saved jobs")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share job board"),
                                )
                            }
                        }) {
                            androidx.compose.material3.Icon(
                                Icons.Outlined.Share,
                                contentDescription = "Share saved jobs",
                            )
                        }
                    }
                },
            )
        },
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = { haptic.tap(); onAddJob() },
                icon = { Icon(Icons.Filled.Add, contentDescription = null) },
                text = { Text("New job") },
                expanded = fabExpanded,
                containerColor = Brand.Indigo,
                contentColor = Color.White,
            )
        },
    ) { padding ->
        BrandBackground {
            Column(modifier = Modifier.padding(padding).fillMaxSize()) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    placeholder = { Text("Search title, company, location") },
                    leadingIcon = { Icon(Icons.Outlined.Search, null) },
                    trailingIcon = {
                        if (query.isNotEmpty()) {
                            androidx.compose.material3.IconButton(onClick = { query = "" }) {
                                Icon(Icons.Outlined.Close, contentDescription = "Clear search")
                            }
                        }
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Search),
                    keyboardActions = androidx.compose.foundation.text.KeyboardActions(onSearch = { keyboardController?.hide() }),
                    modifier = Modifier
                        .fillMaxWidth()
                        .padding(horizontal = 16.dp, vertical = 8.dp),
                )

                if (state.error != null) {
                    Box(Modifier.padding(horizontal = 16.dp)) {
                        InlineBanner(state.error!!, tone = PillTone.Danger)
                    }
                }

                PullToRefreshBox(
                    isRefreshing = state.isLoading && state.items.isNotEmpty(),
                    onRefresh = { haptic.tap(); vm.refresh() },
                    modifier = Modifier.fillMaxSize(),
                ) {
                    when {
                        state.isLoading && state.items.isEmpty() -> SkeletonList(rows = 6)
                        visible.isEmpty() && query.isNotBlank() -> EmptyState(
                            title = "No matches",
                            description = "Try a different search term.",
                        )
                        visible.isEmpty() -> EmptyState(
                            title = "No jobs yet",
                            description = "Save a job description to benchmark, scan with ATS, and craft tailored documents.",
                            actionLabel = "Add your first job",
                            onAction = { haptic.tap(); onAddJob() },
                        )
                        else -> LazyColumn(
                            state = listState,
                            contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                            modifier = Modifier.fillMaxSize(),
                        ) {
                            items(visible, key = { it.id }) { job ->
                                val dismissState = rememberSwipeToDismissBoxState(
                                    confirmValueChange = { value ->
                                        if (value == SwipeToDismissBoxValue.EndToStart) {
                                            val removed = vm.removeLocally(job.id) ?: return@rememberSwipeToDismissBoxState false
                                            haptic.tap()
                                            appScope.launch {
                                                val undone = snackbar.showUndo("Job deleted")
                                                if (undone) vm.restore(removed) else vm.commitDelete(removed.id)
                                            }
                                            true
                                        } else false
                                    },
                                )
                                SwipeToDismissBox(
                                    state = dismissState,
                                    enableDismissFromStartToEnd = false,
                                    modifier = Modifier.semantics {
                                        customActions = listOf(
                                            CustomAccessibilityAction(label = "Delete job") {
                                                val r = vm.removeLocally(job.id)
                                                if (r != null) { appScope.launch { val u = snackbar.showUndo("Job deleted"); if (u) vm.restore(r) else vm.commitDelete(r.id) }; true } else false
                                            },
                                        )
                                    },
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
                                    JobRow(job) { haptic.tap(); onJobClick(job.id) }
                                }
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
private fun JobRow(job: Job, onClick: () -> Unit) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(androidx.compose.ui.text.AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard(onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(44.dp)
                    .background(Brand.Indigo.copy(alpha = 0.14f), CircleShape),
                contentAlignment = Alignment.Center,
            ) { Icon(Icons.Outlined.Work, null, tint = Brand.Indigo) }
            Spacer(Modifier.size(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    job.title,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                    modifier = Modifier.combinedClickable(
                        onClick = onClick,
                        onLongClick = { copy(job.title, "title") },
                    ),
                )
                val sub = listOfNotNull(job.company, job.location).joinToString(" • ")
                if (sub.isNotBlank()) {
                    Spacer(Modifier.height(2.dp))
                    Text(
                        sub,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                        modifier = Modifier.combinedClickable(
                            onClick = onClick,
                            onLongClick = { copy(sub, "details") },
                        ),
                    )
                }
                val tags = listOfNotNull(job.job_type, job.experience_level, job.salary_range)
                if (tags.isNotEmpty()) {
                    Spacer(Modifier.height(8.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        tags.take(3).forEach { tag ->
                            StatusPill(text = tag, tone = PillTone.Brand)
                        }
                    }
                }
            }
        }
    }
}
