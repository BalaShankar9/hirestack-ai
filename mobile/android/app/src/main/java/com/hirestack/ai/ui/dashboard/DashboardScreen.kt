package com.hirestack.ai.ui.dashboard

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.DashboardResponse

private data class Stat(val label: String, val value: String, val hint: String? = null)

@Composable
fun DashboardScreen(
    vm: DashboardViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val data = state.data

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(16.dp),
    ) {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text(
                "Dashboard",
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.weight(1f))
            TextButton(onClick = { vm.refresh() }, enabled = !state.isLoading) {
                Text(if (state.isLoading) "Loading…" else "Refresh")
            }
        }
        Spacer(Modifier.height(8.dp))

        if (state.error != null) {
            ErrorBanner(message = state.error!!, onRetry = { vm.refresh() })
            Spacer(Modifier.height(16.dp))
        }

        if (data != null) {
            HeadlineCard(data)
            Spacer(Modifier.height(16.dp))
            StatGrid(stats = buildStats(data))
        } else if (state.isLoading) {
            Box(
                modifier = Modifier
                    .fillMaxWidth()
                    .padding(top = 64.dp),
                contentAlignment = Alignment.Center,
            ) {
                CircularProgressIndicator()
            }
        }
    }
}

@Composable
private fun HeadlineCard(data: DashboardResponse) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(20.dp)) {
            Text(
                "Latest match score",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(4.dp))
            Text(
                text = data.latest_score?.let { "${it.toInt()}%" } ?: "—",
                style = MaterialTheme.typography.displaySmall,
                fontWeight = FontWeight.Bold,
            )
            data.summary?.let { s ->
                Spacer(Modifier.height(8.dp))
                Text(
                    "Tasks complete: ${s.task_completion_rate}%",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun StatGrid(stats: List<Stat>) {
    // We can't use LazyVerticalGrid inside a verticalScroll Column;
    // emulate a 2-col grid manually.
    Column(modifier = Modifier.fillMaxWidth()) {
        stats.chunked(2).forEach { row ->
            Row(modifier = Modifier.fillMaxWidth()) {
                row.forEachIndexed { idx, stat ->
                    StatCard(
                        stat = stat,
                        modifier = Modifier
                            .weight(1f)
                            .padding(end = if (idx == 0 && row.size == 2) 8.dp else 0.dp),
                    )
                    if (idx == 0 && row.size == 1) {
                        // single item — leave the right slot empty
                        Spacer(modifier = Modifier.weight(1f))
                    }
                }
            }
            Spacer(Modifier.height(12.dp))
        }
    }
}

@Composable
private fun StatCard(stat: Stat, modifier: Modifier = Modifier) {
    Card(modifier = modifier) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                stat.value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(2.dp))
            Text(
                stat.label,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}

@Composable
private fun ErrorBanner(message: String, onRetry: () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        ),
        modifier = Modifier.fillMaxWidth(),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                message,
                color = MaterialTheme.colorScheme.onErrorContainer,
                style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(Modifier.height(8.dp))
            TextButton(onClick = onRetry) { Text("Retry") }
        }
    }
}

private fun buildStats(d: DashboardResponse): List<Stat> = listOf(
    Stat("Applications", d.applications.toString()),
    Stat("Active", d.active_applications.toString()),
    Stat("Resume profiles", d.profiles.toString()),
    Stat("Jobs analyzed", d.jobs_analyzed.toString()),
    Stat("Evidence items", d.evidence_items.toString()),
    Stat("ATS scans", d.ats_scans.toString()),
    Stat("Salary analyses", d.salary_analyses.toString()),
    Stat("Interview sessions", d.interview_sessions.toString()),
    Stat("Learning streak", "${d.learning_streak} 🔥"),
)
