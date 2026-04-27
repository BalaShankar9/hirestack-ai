package com.hirestack.ai.ui.ats

import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.AtsScan
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
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
fun AtsScreen(onBack: () -> Unit, vm: AtsViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    var resumeText by remember { mutableStateOf("") }
    var jdText by remember { mutableStateOf("") }
    var showForm by remember { mutableStateOf(false) }
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "ATS Scanner",
                subtitle = "${state.items.size} runs",
                onBack = onBack,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("My ATS scans (${state.items.size})")
                                appendLine()
                                state.items.take(15).forEach { s ->
                                    appendLine("- Score: ${s.ats_score}")
                                    s.keyword_match_rate?.let { appendLine("    Keyword match: ${(it * 100).toInt()}%") }
                                    if (s.matched_keywords.isNotEmpty()) {
                                        appendLine("    Matched: ${s.matched_keywords.take(8).joinToString(", ")}")
                                    }
                                    if (s.missing_keywords.isNotEmpty()) {
                                        appendLine("    Missing: ${s.missing_keywords.take(8).joinToString(", ")}")
                                    }
                                }
                                if (state.items.size > 15) {
                                    appendLine()
                                    appendLine("…and ${state.items.size - 15} more")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack ATS scans")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share ATS scans"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share ATS scans")
                        }
                    }
                    TextButton(onClick = { haptic.tap(); showForm = !showForm }) {
                        Text(if (showForm) "Hide" else "New scan", color = Brand.Indigo)
                    }
                },
                scrollBehavior = scrollBehavior,
            )
        },
    ) { padding ->
        BrandBackground {
            PullToRefreshBox(
                isRefreshing = state.isLoading && state.items.isNotEmpty(),
                onRefresh = { haptic.tap(); vm.refresh() },
                modifier = Modifier.fillMaxSize().padding(padding),
            ) {
                LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(20.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    if (showForm) {
                        item {
                            SoftCard {
                                Column {
                                    Text("Run a new scan", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                    Spacer(Modifier.height(12.dp))
                                    OutlinedTextField(
                                        value = resumeText,
                                        onValueChange = { resumeText = it },
                                        label = { Text("Resume / document text") },
                                        modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp),
                                        shape = RoundedCornerShape(14.dp),
                                        minLines = 5,
                                    )
                                    Spacer(Modifier.height(12.dp))
                                    OutlinedTextField(
                                        value = jdText,
                                        onValueChange = { jdText = it },
                                        label = { Text("Job description text") },
                                        modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp),
                                        shape = RoundedCornerShape(14.dp),
                                        minLines = 5,
                                    )
                                    state.error?.let {
                                        Spacer(Modifier.height(12.dp))
                                        InlineBanner(it, tone = PillTone.Danger)
                                    }
                                    Spacer(Modifier.height(14.dp))
                                    HireStackPrimaryButton(
                                        label = if (state.running) "Scanning…" else "Run scan",
                                        onClick = {
                                            haptic.confirm()
                                            vm.runScan(resumeText, jdText)
                                            scope.toast(snackbar, "Scan queued")
                                        },
                                        enabled = !state.running && resumeText.isNotBlank() && jdText.isNotBlank(),
                                        loading = state.running,
                                        modifier = Modifier.fillMaxWidth(),
                                    )
                                }
                            }
                        }
                        state.lastResult?.let { result ->
                            item { ResultCard(result, headline = "Latest scan") }
                        }
                    }

                    item {
                        Text("History", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    }

                    when {
                        state.isLoading && state.items.isEmpty() -> item { SkeletonList(rows = 4) }
                        state.items.isEmpty() -> item {
                            Text(
                                "No previous scans yet.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                        else -> items(state.items, key = { it.id ?: it.hashCode().toString() }) { scan ->
                            ResultCard(scan, headline = scan.created_at ?: "Scan")
                        }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ResultCard(result: AtsScan, headline: String) {
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
                    Text(headline, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        "${result.ats_score}%",
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                        color = Brand.Indigo,
                        modifier = Modifier.combinedClickable(
                            onClick = {},
                            onLongClick = { copy("${result.ats_score}%", "ATS score") },
                        ),
                    )
                }
                Column(horizontalAlignment = Alignment.End) {
                    result.keyword_match_rate?.let {
                        Text("Keywords ${(it * 100).toInt()}%", style = MaterialTheme.typography.bodySmall)
                    }
                    result.readability_score?.let {
                        Text("Readability ${it.toInt()}", style = MaterialTheme.typography.bodySmall)
                    }
                    result.format_score?.let {
                        Text("Format ${it.toInt()}", style = MaterialTheme.typography.bodySmall)
                    }
                }
            }

            if (result.matched_keywords.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusPill(text = "Matched ${result.matched_keywords.size}", tone = PillTone.Brand)
                }
                Spacer(Modifier.height(6.dp))
                val matchedText = result.matched_keywords.take(20).joinToString(", ")
                Text(
                    matchedText,
                    style = MaterialTheme.typography.bodySmall,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(result.matched_keywords.joinToString(", "), "matched keywords") },
                    ),
                )
            }
            if (result.missing_keywords.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    StatusPill(text = "Missing ${result.missing_keywords.size}", tone = PillTone.Danger)
                }
                Spacer(Modifier.height(6.dp))
                val missingText = result.missing_keywords.take(20).joinToString(", ")
                Text(
                    missingText,
                    style = MaterialTheme.typography.bodySmall,
                    color = Brand.Danger,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(result.missing_keywords.joinToString(", "), "missing keywords") },
                    ),
                )
            }
        }
    }
}
