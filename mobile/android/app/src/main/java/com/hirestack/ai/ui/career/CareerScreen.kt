package com.hirestack.ai.ui.career

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.CareerPortfolio
import com.hirestack.ai.data.network.CareerSnapshot
import com.hirestack.ai.data.network.ConversionFunnel

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun CareerScreen(
    onBack: () -> Unit,
    vm: CareerViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Career analytics") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Box(modifier = Modifier.fillMaxSize().padding(padding)) {
            when {
                state.isLoading && state.portfolio == null -> {
                    Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
                state.error != null && state.portfolio == null -> {
                    Column(modifier = Modifier.padding(24.dp)) {
                        Text("Error", style = MaterialTheme.typography.titleMedium)
                        Spacer(Modifier.height(8.dp))
                        Text(state.error!!, color = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.height(16.dp))
                        Button(onClick = { vm.refresh() }) { Text("Retry") }
                    }
                }
                else -> {
                    Column(
                        modifier = Modifier
                            .fillMaxSize()
                            .verticalScroll(rememberScrollState())
                            .padding(20.dp),
                    ) {
                        state.portfolio?.let { PortfolioCard(it) }
                        Spacer(Modifier.height(16.dp))
                        state.funnel?.let { FunnelCard(it) }
                        Spacer(Modifier.height(16.dp))
                        TimelineCard(state.timeline)
                    }
                }
            }
        }
    }
}

@Composable
private fun PortfolioCard(p: CareerPortfolio) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text("Portfolio", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            StatLine("Applications", p.total_applications?.toString() ?: "—")
            StatLine("Active applications", p.active_applications?.toString() ?: "—")
            StatLine("Evidence items", p.total_evidence?.toString() ?: "—")
            StatLine("Skills tracked", p.skills_count?.toString() ?: "—")
            StatLine("Latest score", p.current_score?.let { "${it.toInt()}%" } ?: "—")
            StatLine("Streak", p.streak_days?.let { "$it days" } ?: "—")
            p.last_activity?.let { StatLine("Last activity", it) }
        }
    }
}

@Composable
private fun FunnelCard(f: ConversionFunnel) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text("Conversion funnel", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(12.dp))
            StatLine("Exported", f.exported.toString())
            StatLine("Applied", f.applied.toString())
            StatLine("Screened", f.screened.toString())
            StatLine("Interview", f.interview.toString())
            StatLine("Interview done", f.interview_done.toString())
            StatLine("Offer", f.offer.toString())
            StatLine("Accepted", f.accepted.toString())
            StatLine("Rejected", f.rejected.toString())
        }
    }
}

@Composable
private fun TimelineCard(timeline: List<CareerSnapshot>) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text("Timeline (90 days)", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
            Spacer(Modifier.height(8.dp))
            if (timeline.isEmpty()) {
                Text(
                    "No snapshots yet. Capture one from the web app or trigger a daily refresh.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            } else {
                timeline.take(20).forEach { s ->
                    Row(
                        modifier = Modifier.fillMaxWidth().padding(vertical = 6.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(
                            s.date ?: s.captured_at?.take(10) ?: "—",
                            modifier = Modifier.weight(1f),
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        s.score?.let {
                            Text(
                                "${it.toInt()}%",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.SemiBold,
                            )
                        }
                        s.applications?.let {
                            Spacer(Modifier.width(12.dp))
                            Text(
                                "$it apps",
                                style = MaterialTheme.typography.bodySmall,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    }
                    HorizontalDivider()
                }
            }
        }
    }
}

@Composable
private fun StatLine(label: String, value: String) {
    Row(
        modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Text(
            label,
            modifier = Modifier.weight(1f),
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Text(value, style = MaterialTheme.typography.bodyMedium, fontWeight = FontWeight.SemiBold)
    }
}
