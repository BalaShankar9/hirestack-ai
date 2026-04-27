package com.hirestack.ai.ui.salary

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
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.SalaryAnalysis
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
import com.hirestack.ai.ui.theme.Brand

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SalaryScreen(onBack: () -> Unit, vm: SalaryViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    com.hirestack.ai.ui.components.ErrorSnackbar(state.error) { vm.clearError() }
    val haptic = LocalHapticFeedback.current
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Salary Coach",
                subtitle = "${state.items.size} analyses",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.items.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("My salary analyses (${state.items.size})")
                                appendLine()
                                state.items.take(15).forEach { s ->
                                    val title = s.job_title ?: "Role"
                                    val sub = listOfNotNull(s.company, s.location).joinToString(" • ")
                                    appendLine("- $title${if (sub.isNotBlank()) " — $sub" else ""}")
                                    val mkt = listOfNotNull(
                                        s.market_low?.let { "low ${it.toInt()}" },
                                        s.market_median?.let { "median ${it.toInt()}" },
                                        s.market_high?.let { "high ${it.toInt()}" },
                                    ).joinToString(" / ")
                                    if (mkt.isNotBlank()) appendLine("    Market: $mkt")
                                    s.recommended_target?.let { appendLine("    Target: ${it.toInt()}") }
                                    s.current_salary?.let { appendLine("    Current: ${it.toInt()}") }
                                }
                                if (state.items.size > 15) {
                                    appendLine()
                                    appendLine("…and ${state.items.size - 15} more")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack salary analyses")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share salary analyses"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share salary analyses")
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
                            title = "No salary analyses yet",
                            description = "Saved market & negotiation analyses will appear here.",
                            actionLabel = "Refresh",
                            onAction = { haptic.tap(); vm.refresh() },
                        )
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(state.items, key = { it.id }) { SalaryCard(it) }
                        }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun SalaryCard(a: SalaryAnalysis) {
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
            val titleText = a.job_title ?: "Salary analysis"
            Text(
                titleText,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = { copy(titleText, "title") },
                ),
            )
            val sub = listOfNotNull(a.company, a.location).joinToString(" • ")
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
            Spacer(Modifier.height(12.dp))
            a.market_median?.let { StatLine("Market median", formatMoney(it)) }
            a.market_low?.let { StatLine("Market low", formatMoney(it)) }
            a.market_high?.let { StatLine("Market high", formatMoney(it)) }
            a.recommended_target?.let { StatLine("Recommended target", formatMoney(it), highlight = true) }
            a.current_salary?.let { if (it > 0) StatLine("Current", formatMoney(it)) }
            a.experience_years?.let { if (it > 0) StatLine("Experience", "${it.toInt()} yrs") }
            a.negotiation_script?.let {
                Spacer(Modifier.height(12.dp))
                Text("Negotiation script", style = MaterialTheme.typography.labelLarge)
                Spacer(Modifier.height(4.dp))
                Text(
                    it,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(it, "script") },
                    ),
                )
            }
        }
    }
}

@Composable
private fun StatLine(label: String, value: String, highlight: Boolean = false) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 3.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            color = if (highlight) Brand.Indigo else MaterialTheme.colorScheme.onSurface,
        )
    }
}

private fun formatMoney(v: Double): String {
    val rounded = v.toLong()
    val s = rounded.toString()
    val withCommas = s.reversed().chunked(3).joinToString(",").reversed()
    return "$$withCommas"
}
