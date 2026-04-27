package com.hirestack.ai.ui.candidates

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
import androidx.compose.material.icons.outlined.Archive
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.FilterList
import androidx.compose.material.icons.outlined.PersonOutline
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.ScrollableTabRow
import androidx.compose.material3.Surface
import androidx.compose.material3.SwipeToDismissBox
import androidx.compose.material3.SwipeToDismissBoxValue
import androidx.compose.material3.Tab
import androidx.compose.material3.Text
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
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
import com.hirestack.ai.data.network.Candidate
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

private val STAGE_FILTERS = listOf(
    null to "All",
    "sourced" to "Sourced",
    "screened" to "Screened",
    "interviewed" to "Interviewed",
    "offered" to "Offered",
    "hired" to "Hired",
    "rejected" to "Rejected",
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CandidatesScreen(onBack: () -> Unit, vm: CandidatesViewModel = hiltViewModel()) {
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
            val q = query.trim().lowercase()
            it.name.lowercase().contains(q) ||
                (it.email?.lowercase()?.contains(q) == true) ||
                (it.location?.lowercase()?.contains(q) == true)
        }
    }

    var sheetOpen by remember { mutableStateOf(false) }
    val sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val currentLabel = STAGE_FILTERS.firstOrNull { it.first == state.stage }?.second ?: "All"

    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Candidates",
                subtitle = "${state.items.size} in pipeline",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        androidx.compose.material3.IconButton(onClick = {
                            val grouped = state.items.groupBy { it.pipeline_stage ?: "unstaged" }
                            val report = buildString {
                                appendLine("Candidate pipeline (${state.items.size})")
                                appendLine()
                                grouped.forEach { (stage, list) ->
                                    appendLine("$stage (${list.size})")
                                    list.take(15).forEach { c ->
                                        val sub = listOfNotNull(c.client_company, c.location).joinToString(" • ")
                                        appendLine("- ${c.name}${if (sub.isNotBlank()) " — $sub" else ""}")
                                        c.email?.takeIf { it.isNotBlank() }?.let { appendLine("    $it") }
                                    }
                                    if (list.size > 15) appendLine("    …and ${list.size - 15} more")
                                    appendLine()
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "Candidate pipeline snapshot")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share candidate pipeline"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share candidate pipeline")
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
                        .padding(horizontal = 20.dp, vertical = 8.dp),
                    verticalAlignment = Alignment.CenterVertically,
                    horizontalArrangement = Arrangement.spacedBy(8.dp),
                ) {
                    AssistChip(
                        onClick = { haptic.tap(); sheetOpen = true },
                        label = { Text("Stage: $currentLabel") },
                        leadingIcon = { Icon(Icons.Outlined.FilterList, contentDescription = null) },
                        colors = AssistChipDefaults.assistChipColors(
                            containerColor = MaterialTheme.colorScheme.surfaceContainerHigh,
                        ),
                    )
                }

                OutlinedTextField(
                    value = query,
                    onValueChange = { query = it },
                    placeholder = { Text("Search candidates") },
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
                        state.noOrg -> EmptyState(
                            title = "Recruiter feature",
                            description = "Create an organization first to start tracking candidates.",
                        )
                        state.isLoading && state.items.isEmpty() -> SkeletonList(rows = 6)
                        state.error != null && state.items.isEmpty() -> Column(Modifier.padding(20.dp)) {
                            InlineBanner(state.error!!, tone = PillTone.Danger)
                            Spacer(Modifier.height(12.dp))
                            HireStackPrimaryButton("Retry", onClick = { vm.refresh() })
                        }
                        visible.isEmpty() && query.isNotBlank() -> EmptyState(
                            title = "No matches",
                            description = "Try a different search term.",
                        )
                        visible.isEmpty() -> EmptyState(
                            title = if (state.stage == null) "No candidates yet" else "No candidates in '${state.stage}'",
                            description = "Candidates added to this organization will appear here.",
                        )
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(visible, key = { it.id }) { c ->
                                val dismissState = rememberSwipeToDismissBoxState(
                                    confirmValueChange = { value ->
                                        when (value) {
                                            SwipeToDismissBoxValue.EndToStart -> {
                                                val removed = vm.removeLocally(c.id) ?: return@rememberSwipeToDismissBoxState false
                                                haptic.tap()
                                                appScope.launch {
                                                    val undone = snackbar.showUndo("Candidate deleted")
                                                    if (undone) vm.restore(removed) else vm.commitDelete(removed.id)
                                                }
                                                true
                                            }
                                            SwipeToDismissBoxValue.StartToEnd -> {
                                                val removed = vm.removeLocally(c.id) ?: return@rememberSwipeToDismissBoxState false
                                                haptic.tap()
                                                appScope.launch {
                                                    val undone = snackbar.showUndo("Candidate archived")
                                                    if (undone) vm.restore(removed) else vm.commitArchive(removed.id)
                                                }
                                                true
                                            }
                                            else -> false
                                        }
                                    },
                                )
                                SwipeToDismissBox(
                                    state = dismissState,
                                    modifier = Modifier.semantics {
                                        customActions = listOf(
                                            CustomAccessibilityAction(label = "Delete candidate") {
                                                val r = vm.removeLocally(c.id)
                                                if (r != null) { appScope.launch { val u = snackbar.showUndo("Candidate deleted"); if (u) vm.restore(r) else vm.commitDelete(r.id) }; true } else false
                                            },
                                            CustomAccessibilityAction(label = "Archive candidate") {
                                                val r = vm.removeLocally(c.id)
                                                if (r != null) { appScope.launch { val u = snackbar.showUndo("Candidate archived"); if (u) vm.restore(r) else vm.commitArchive(r.id) }; true } else false
                                            },
                                        )
                                    },
                                    backgroundContent = {
                                        val isDelete = dismissState.dismissDirection == SwipeToDismissBoxValue.EndToStart
                                        val tint = if (isDelete) Brand.Danger else Brand.Amber
                                        val icon = if (isDelete) Icons.Outlined.Delete else Icons.Outlined.Archive
                                        val align = if (isDelete) Alignment.CenterEnd else Alignment.CenterStart
                                        Box(
                                            modifier = Modifier
                                                .fillMaxSize()
                                                .background(tint.copy(alpha = 0.18f), RoundedCornerShape(20.dp))
                                                .padding(horizontal = 24.dp),
                                            contentAlignment = align,
                                        ) {
                                            Icon(icon, contentDescription = if (isDelete) "Delete" else "Archive", tint = tint)
                                        }
                                    },
                                ) {
                                    CandidateRow(c)
                                }
                            }
                        }
                    }
                }
            }
        }
    }

    if (sheetOpen) {
        ModalBottomSheet(
            onDismissRequest = { sheetOpen = false },
            sheetState = sheetState,
        ) {
            Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
                Text("Filter by stage", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(12.dp))
                STAGE_FILTERS.forEach { (key, label) ->
                    val selected = state.stage == key
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        shape = RoundedCornerShape(14.dp),
                        color = if (selected) Brand.Indigo.copy(alpha = 0.18f) else Color.Transparent,
                        onClick = {
                            haptic.tap()
                            vm.setStage(key)
                            sheetOpen = false
                        },
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(
                                label,
                                style = MaterialTheme.typography.bodyLarge,
                                color = if (selected) Brand.Indigo else MaterialTheme.colorScheme.onSurface,
                                fontWeight = if (selected) FontWeight.SemiBold else FontWeight.Normal,
                            )
                        }
                    }
                }
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun CandidateRow(c: Candidate) {
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
                color = Brand.Violet.copy(alpha = 0.16f),
                shape = CircleShape,
                modifier = Modifier.size(44.dp),
            ) {
                Box(contentAlignment = Alignment.Center) {
                    Icon(Icons.Outlined.PersonOutline, null, tint = Brand.Violet)
                }
            }
            Spacer(Modifier.size(12.dp))
            Column(modifier = Modifier.weight(1f)) {
                Text(
                    c.name,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    maxLines = 1,
                    overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(c.name, "name") },
                    ),
                )
                val sub = listOfNotNull(c.email, c.location).joinToString(" • ")
                if (sub.isNotBlank()) {
                    Spacer(Modifier.height(2.dp))
                    Text(
                        sub,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        maxLines = 1,
                        overflow = androidx.compose.ui.text.style.TextOverflow.Ellipsis,
                        modifier = Modifier.combinedClickable(
                            onClick = {},
                            onLongClick = { copy(sub, "details") },
                        ),
                    )
                }
                if (c.tags.isNotEmpty()) {
                    Spacer(Modifier.height(6.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        c.tags.take(3).forEach { StatusPill(text = it, tone = PillTone.Brand) }
                    }
                }
            }
            c.pipeline_stage?.let {
                Spacer(Modifier.size(8.dp))
                StatusPill(text = it, tone = PillTone.Brand)
            }
        }
    }
}
