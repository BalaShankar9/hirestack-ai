package com.hirestack.ai.ui.career

import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Share
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.CareerPortfolio
import com.hirestack.ai.data.network.CareerSnapshot
import com.hirestack.ai.data.network.ConversionFunnel
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.tap
import com.hirestack.ai.ui.theme.Brand
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CareerScreen(onBack: () -> Unit, vm: CareerViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    val haptic = LocalHapticFeedback.current
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Career analytics",
                subtitle = "Portfolio + funnel + 90d",
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    val portfolio = state.portfolio
                    val funnel = state.funnel
                    if (portfolio != null || funnel != null) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        androidx.compose.material3.IconButton(onClick = {
                            val report = buildString {
                                appendLine("Career analytics")
                                appendLine()
                                portfolio?.let { p ->
                                    appendLine("Portfolio")
                                    appendLine("- Applications: ${p.total_applications ?: "—"}")
                                    appendLine("- Active applications: ${p.active_applications ?: "—"}")
                                    appendLine("- Evidence items: ${p.total_evidence ?: "—"}")
                                    appendLine("- Skills tracked: ${p.skills_count ?: "—"}")
                                    appendLine("- Latest score: ${p.current_score?.let { "${it.toInt()}%" } ?: "—"}")
                                    appendLine("- Streak: ${p.streak_days?.let { "$it days" } ?: "—"}")
                                    p.last_activity?.let { appendLine("- Last activity: $it") }
                                    appendLine()
                                }
                                funnel?.let { f ->
                                    appendLine("Conversion funnel")
                                    appendLine("- Exported: ${f.exported}")
                                    appendLine("- Applied: ${f.applied}")
                                    appendLine("- Screened: ${f.screened}")
                                    appendLine("- Interview: ${f.interview}")
                                    appendLine("- Interview done: ${f.interview_done}")
                                    appendLine("- Offer: ${f.offer}")
                                    appendLine("- Accepted: ${f.accepted}")
                                    appendLine("- Rejected: ${f.rejected}")
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "Career analytics")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share career analytics"),
                                )
                            }
                        }) {
                            androidx.compose.material3.Icon(
                                Icons.Outlined.Share,
                                contentDescription = "Share career analytics",
                            )
                        }
                    }
                },
            )
        },
    ) { padding ->
        BrandBackground {
            Box(modifier = Modifier.fillMaxSize().padding(padding)) {
                PullToRefreshBox(
                    isRefreshing = state.isLoading && state.portfolio != null,
                    onRefresh = { haptic.tap(); vm.refresh() },
                    modifier = Modifier.fillMaxSize(),
                ) {
                    when {
                        state.isLoading && state.portfolio == null -> SkeletonList(rows = 6)
                        state.error != null && state.portfolio == null -> Column(Modifier.padding(20.dp)) {
                            InlineBanner(state.error!!, tone = PillTone.Danger)
                            Spacer(Modifier.height(12.dp))
                            HireStackPrimaryButton("Retry", onClick = { vm.refresh() })
                        }
                        else -> Column(
                            modifier = Modifier
                                .fillMaxSize()
                                .verticalScroll(rememberScrollState())
                                .padding(20.dp),
                            verticalArrangement = Arrangement.spacedBy(14.dp),
                        ) {
                            state.portfolio?.let { PortfolioCard(it) }
                            state.funnel?.let { FunnelCard(it) }
                            TimelineCard(state.timeline)
                        }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun PortfolioCard(p: CareerPortfolio) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val summary = buildString {
        appendLine("Career portfolio")
        appendLine("- Applications: ${p.total_applications ?: "—"}")
        appendLine("- Active applications: ${p.active_applications ?: "—"}")
        appendLine("- Evidence items: ${p.total_evidence ?: "—"}")
        appendLine("- Skills tracked: ${p.skills_count ?: "—"}")
        appendLine("- Latest score: ${p.current_score?.let { "${it.toInt()}%" } ?: "—"}")
        appendLine("- Streak: ${p.streak_days?.let { "$it days" } ?: "—"}")
        p.last_activity?.let { appendLine("- Last activity: $it") }
    }.trimEnd()
    SoftCard {
        Column(
            modifier = Modifier.combinedClickable(
                onClick = {},
                onLongClick = {
                    clipboard.setText(androidx.compose.ui.text.AnnotatedString(summary))
                    haptic.confirm()
                    scope.launch { snackbar.showSnackbar("Copied portfolio summary") }
                },
            ),
        ) {
            Text("Portfolio", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            StatLine("Applications", p.total_applications?.toString() ?: "—")
            StatLine("Active applications", p.active_applications?.toString() ?: "—")
            StatLine("Evidence items", p.total_evidence?.toString() ?: "—")
            StatLine("Skills tracked", p.skills_count?.toString() ?: "—")
            StatLine("Latest score", p.current_score?.let { "${it.toInt()}%" } ?: "—", highlight = true)
            StatLine("Streak", p.streak_days?.let { "$it days" } ?: "—")
            p.last_activity?.let { StatLine("Last activity", it) }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun FunnelCard(f: ConversionFunnel) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val summary = buildString {
        appendLine("Conversion funnel")
        appendLine("- Exported: ${f.exported}")
        appendLine("- Applied: ${f.applied}")
        appendLine("- Screened: ${f.screened}")
        appendLine("- Interview: ${f.interview}")
        appendLine("- Interview done: ${f.interview_done}")
        appendLine("- Offer: ${f.offer}")
        appendLine("- Accepted: ${f.accepted}")
        appendLine("- Rejected: ${f.rejected}")
    }.trimEnd()
    SoftCard {
        Column(
            modifier = Modifier.combinedClickable(
                onClick = {},
                onLongClick = {
                    clipboard.setText(androidx.compose.ui.text.AnnotatedString(summary))
                    haptic.confirm()
                    scope.launch { snackbar.showSnackbar("Copied funnel summary") }
                },
            ),
        ) {
            Text("Conversion funnel", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            StatLine("Exported", f.exported.toString())
            StatLine("Applied", f.applied.toString())
            StatLine("Screened", f.screened.toString())
            StatLine("Interview", f.interview.toString())
            StatLine("Interview done", f.interview_done.toString())
            StatLine("Offer", f.offer.toString(), highlight = true)
            StatLine("Accepted", f.accepted.toString(), highlight = true)
            StatLine("Rejected", f.rejected.toString())
        }
    }
}

@Composable
private fun TimelineCard(timeline: List<CareerSnapshot>) {
    SoftCard {
        Column {
            Text("Timeline (90 days)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            if (timeline.isEmpty()) {
                Text(
                    "No snapshots yet. New ones appear after your daily refresh.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                timeline.take(20).forEach { s ->
                    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp), verticalAlignment = Alignment.CenterVertically) {
                        Text(
                            s.date ?: s.captured_at?.take(10) ?: "—",
                            modifier = Modifier.weight(1f),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        s.score?.let {
                            Text(
                                "${it.toInt()}%",
                                style = MaterialTheme.typography.bodyMedium,
                                color = Brand.Indigo,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                        s.applications?.let {
                            Spacer(Modifier.width(12.dp))
                            Text("$it apps", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun StatLine(label: String, value: String, highlight: Boolean = false) {
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp), verticalAlignment = Alignment.CenterVertically) {
        Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
        Text(
            value,
            style = MaterialTheme.typography.bodyMedium,
            fontWeight = FontWeight.SemiBold,
            color = if (highlight) Brand.Indigo else MaterialTheme.colorScheme.onSurface,
        )
    }
}
