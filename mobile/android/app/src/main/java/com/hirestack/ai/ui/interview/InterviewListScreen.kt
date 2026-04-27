package com.hirestack.ai.ui.interview

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
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.RecordVoiceOver
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Text
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
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.InterviewSession
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
import com.hirestack.ai.ui.components.ErrorSnackbar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.showUndo
import com.hirestack.ai.ui.components.tap
import com.hirestack.ai.ui.theme.Brand
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InterviewListScreen(
    onBack: () -> Unit,
    onSessionClick: (String) -> Unit,
    vm: InterviewListViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val appScope = LocalAppScope.current
    var query by rememberSaveable { mutableStateOf("") }
    val keyboardController = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    androidx.activity.compose.BackHandler(enabled = query.isNotEmpty()) { query = "" }
    ErrorSnackbar(state.error) { vm.clearError() }
    val q = query.trim().lowercase()
    val visible = if (q.isBlank()) state.items else state.items.filter { s ->
        (s.job_title?.lowercase()?.contains(q) == true) ||
            (s.company?.lowercase()?.contains(q) == true) ||
            (s.interview_type?.lowercase()?.contains(q) == true) ||
            (s.status?.lowercase()?.contains(q) == true)
    }

    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Interview Coach",
                subtitle = "${state.items.size} sessions",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        androidx.compose.material3.IconButton(onClick = {
                            val report = buildString {
                                appendLine("My interview sessions (${state.items.size})")
                                appendLine()
                                state.items.take(20).forEach { s ->
                                    val title = s.job_title ?: "Session"
                                    val sub = listOfNotNull(s.company, s.interview_type, s.difficulty).joinToString(" • ")
                                    appendLine("- $title${if (sub.isNotBlank()) " — $sub" else ""}")
                                    val score = s.overall_score ?: s.average_score
                                    val statusBits = listOfNotNull(
                                        s.status?.takeIf { it.isNotBlank() },
                                        s.question_count?.let { "$it questions" },
                                        score?.let { "score ${"%.1f".format(it)}" },
                                    ).joinToString(" • ")
                                    if (statusBits.isNotBlank()) appendLine("    $statusBits")
                                }
                                if (state.items.size > 20) {
                                    appendLine()
                                    appendLine("…and ${state.items.size - 20} more")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack interview sessions")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share interview sessions"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share interview sessions")
                        }
                    }
                },
            )
        },
    ) { padding ->
        BrandBackground {
            Column(modifier = Modifier.fillMaxSize().padding(padding)) {
                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    placeholder = { Text("Search sessions") },
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
                        .padding(horizontal = 20.dp, vertical = 8.dp),
                )
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
                            title = "No interview sessions yet",
                            description = "Practice sessions with AI-generated questions will appear here once started.",
                            actionLabel = "Refresh",
                            onAction = { haptic.tap(); vm.refresh() },
                        )
                        visible.isEmpty() -> EmptyState(
                            title = "No matches",
                            description = "No sessions match \"$query\".",
                        )
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(visible, key = { it.id }) { s ->
                                val dismissState = rememberSwipeToDismissBoxState(
                                    confirmValueChange = { value ->
                                        if (value == SwipeToDismissBoxValue.EndToStart) {
                                            val removed = vm.removeLocally(s.id) ?: return@rememberSwipeToDismissBoxState false
                                            haptic.tap()
                                            appScope.launch {
                                                val undone = snackbar.showUndo("Session deleted")
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
                                            CustomAccessibilityAction(label = "Delete session") {
                                                val r = vm.removeLocally(s.id)
                                                if (r != null) { appScope.launch { val u = snackbar.showUndo("Session deleted"); if (u) vm.restore(r) else vm.commitDelete(r.id) }; true } else false
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
                                    SessionRow(s) { haptic.tap(); onSessionClick(s.id) }
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
private fun SessionRow(session: InterviewSession, onClick: () -> Unit) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard(onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Surface(
                color = Brand.Pink.copy(alpha = 0.16f),
                shape = CircleShape,
                modifier = Modifier.size(44.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Outlined.RecordVoiceOver, null, tint = Brand.Pink)
                }
            }
            Spacer(Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                val titleText = session.job_title ?: "Interview session"
                Text(
                    titleText,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                    modifier = Modifier.combinedClickable(
                        onClick = onClick,
                        onLongClick = { copy(titleText, "title") },
                    ),
                )
                val sub = listOfNotNull(session.company, session.interview_type, session.difficulty).joinToString(" • ")
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
                session.status?.let {
                    Spacer(Modifier.height(6.dp))
                    StatusPill(text = it, tone = PillTone.Brand)
                }
            }
            val score = session.overall_score ?: session.average_score
            if (score != null) {
                Spacer(Modifier.size(8.dp))
                Text(
                    "${score.toInt()}",
                    style = MaterialTheme.typography.headlineSmall,
                    color = Brand.Indigo,
                    fontWeight = FontWeight.Bold,
                )
            }
        }
    }
}
