package com.hirestack.ai.ui.knowledge

import android.content.Context
import android.content.Intent
import android.net.Uri
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
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.semantics.CustomAccessibilityAction
import androidx.compose.ui.semantics.customActions
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.KnowledgeResource
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
fun KnowledgeScreen(onBack: () -> Unit, vm: KnowledgeViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    val ctx = LocalContext.current
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val appScope = LocalAppScope.current
    var query by rememberSaveable { mutableStateOf("") }
    val keyboardController = androidx.compose.ui.platform.LocalSoftwareKeyboardController.current
    androidx.activity.compose.BackHandler(enabled = query.isNotEmpty()) { query = "" }
    ErrorSnackbar(state.error) { vm.clearError() }

    val q = query.trim().lowercase()
    fun matches(r: KnowledgeResource): Boolean {
        if (q.isBlank()) return true
        return (r.title?.lowercase()?.contains(q) == true) ||
            (r.description?.lowercase()?.contains(q) == true) ||
            (r.category?.lowercase()?.contains(q) == true) ||
            (r.skills?.any { it.lowercase().contains(q) } == true)
    }
    val recPairs = state.recommendations
        .mapNotNull { rec -> rec.knowledge_resources?.let { rec to it } }
        .filter { matches(it.second) }
    val recResources = recPairs.map { it.second }
    val inProgressResources = state.progress
        .filter { it.status != null && it.status != "completed" }
        .mapNotNull { it.knowledge_resources }
        .filter(::matches)
    val catalog = state.resources.filter(::matches)

    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Knowledge",
                subtitle = "${state.resources.size} resources",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    val featured = state.resources.filter { it.is_featured == true }
                    val pickList = if (featured.isNotEmpty()) featured else state.resources
                    if (pickList.isNotEmpty()) {
                        val shareCtx = LocalContext.current
                        androidx.compose.material3.IconButton(onClick = {
                            val report = buildString {
                                val label = if (featured.isNotEmpty()) "Featured knowledge picks" else "HireStack knowledge resources"
                                appendLine("$label (${pickList.size})")
                                appendLine()
                                pickList.take(20).forEach { r ->
                                    val title = r.title ?: "(untitled)"
                                    val meta = listOfNotNull(r.category, r.difficulty, r.resource_type).joinToString(" • ")
                                    appendLine("- $title${if (meta.isNotBlank()) " [$meta]" else ""}")
                                    r.author?.let { appendLine("    by $it") }
                                    if (!r.url.isNullOrBlank()) appendLine("    ${r.url}")
                                }
                                if (pickList.size > 20) {
                                    appendLine()
                                    appendLine("…and ${pickList.size - 20} more")
                                }
                            }.trimEnd()
                            val send = Intent(Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(Intent.EXTRA_SUBJECT, "HireStack knowledge picks")
                                putExtra(Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    Intent.createChooser(send, "Share knowledge picks"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share knowledge picks")
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
                    placeholder = { Text("Search resources, skills, topics") },
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
                    isRefreshing = state.isLoading && state.resources.isNotEmpty(),
                    onRefresh = { haptic.tap(); vm.refresh() },
                    modifier = Modifier.fillMaxSize(),
                ) {
                    when {
                        state.isLoading && state.resources.isEmpty() -> SkeletonList(rows = 6)
                        state.error != null && state.resources.isEmpty() -> Column(Modifier.padding(20.dp)) {
                            InlineBanner(state.error!!, tone = PillTone.Danger)
                            Spacer(Modifier.height(12.dp))
                            HireStackPrimaryButton("Retry", onClick = { vm.refresh() })
                        }
                        state.resources.isEmpty() -> EmptyState(
                            title = "No resources yet",
                            description = "The knowledge catalog will populate once your tenant publishes resources.",
                        )
                        catalog.isEmpty() && recResources.isEmpty() && inProgressResources.isEmpty() -> EmptyState(
                            title = "No matches",
                            description = "Nothing matches \"$query\". Try a different keyword.",
                        )
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(10.dp),
                        ) {
                            if (recResources.isNotEmpty()) {
                                item { SectionHeader("Recommended for you") }
                                items(recPairs, key = { "rec-${it.first.id}" }) { (rec, resource) ->
                                    val dismissState = rememberSwipeToDismissBoxState(
                                        confirmValueChange = { value ->
                                            if (value == SwipeToDismissBoxValue.EndToStart) {
                                                val removed = vm.removeRecLocally(rec.id) ?: return@rememberSwipeToDismissBoxState false
                                                haptic.tap()
                                                appScope.launch {
                                                    val undone = snackbar.showUndo("Recommendation dismissed")
                                                    if (undone) vm.restoreRec(removed) else vm.commitDismissRec(removed.id)
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
                                                CustomAccessibilityAction(label = "Dismiss recommendation") {
                                                    val r = vm.removeRecLocally(rec.id)
                                                    if (r != null) { appScope.launch { val u = snackbar.showUndo("Recommendation dismissed"); if (u) vm.restoreRec(r) else vm.commitDismissRec(r.id) }; true } else false
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
                                                Icon(Icons.Outlined.Close, contentDescription = "Dismiss", tint = Brand.Danger)
                                            }
                                        },
                                    ) {
                                        ResourceCard(resource, ctx, haptic)
                                    }
                                }
                            }
                            if (inProgressResources.isNotEmpty()) {
                                item { SectionHeader("In progress") }
                                items(inProgressResources, key = { "ip-${it.id}" }) { ResourceCard(it, ctx, haptic) }
                            }
                            if (catalog.isNotEmpty()) {
                                item { SectionHeader("Browse catalog") }
                                items(catalog, key = { "cat-${it.id}" }) { ResourceCard(it, ctx, haptic) }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(
        text,
        style = MaterialTheme.typography.titleMedium,
        fontWeight = FontWeight.SemiBold,
        modifier = Modifier.padding(top = 8.dp, bottom = 2.dp),
    )
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ResourceCard(r: KnowledgeResource, ctx: Context, haptic: androidx.compose.ui.hapticfeedback.HapticFeedback) {
    val canOpen = !r.url.isNullOrBlank()
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard(onClick = if (canOpen) ({ haptic.tap(); openUrl(ctx, r.url!!) }) else null) {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    val titleText = r.title ?: "(untitled)"
                    Text(
                        titleText,
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                        modifier = Modifier.combinedClickable(
                            onClick = { if (canOpen) { haptic.tap(); openUrl(ctx, r.url!!) } },
                            onLongClick = { copy(r.url ?: titleText, if (r.url != null) "link" else "title") },
                        ),
                    )
                    r.description?.let {
                        Spacer(Modifier.height(4.dp))
                        Text(it, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant, maxLines = 3)
                    }
                }
                if (canOpen) {
                    Icon(Icons.AutoMirrored.Filled.OpenInNew, contentDescription = "Open", tint = Brand.Indigo)
                }
            }
            Spacer(Modifier.height(8.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                r.category?.let { StatusPill(text = it, tone = PillTone.Brand) }
                r.resource_type?.let { StatusPill(text = it, tone = PillTone.Neutral) }
                r.difficulty?.let { StatusPill(text = it, tone = PillTone.Neutral) }
            }
        }
    }
}

private fun openUrl(ctx: Context, url: String) {
    runCatching {
        val intent = Intent(Intent.ACTION_VIEW, Uri.parse(url)).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
    }
}
