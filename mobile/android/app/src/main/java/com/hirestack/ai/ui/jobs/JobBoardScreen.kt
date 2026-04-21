package com.hirestack.ai.ui.jobs

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.Job

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JobBoardScreen(
    onJobClick: (String) -> Unit,
    onAddJob: () -> Unit,
    vm: JobBoardViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    Scaffold(
        floatingActionButton = {
            ExtendedFloatingActionButton(
                onClick = onAddJob,
                icon = { Icon(Icons.Default.Add, contentDescription = null) },
                text = { Text("New job") },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.padding(padding).fillMaxSize()) {
            Row(
                verticalAlignment = Alignment.CenterVertically,
                modifier = Modifier.fillMaxWidth().padding(16.dp),
            ) {
                Text(
                    "Job board",
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.weight(1f))
                TextButton(onClick = { vm.refresh() }, enabled = !state.isLoading) {
                    Text(if (state.isLoading) "Loading…" else "Refresh")
                }
            }
            if (state.error != null) {
                ErrorCard(state.error!!) { vm.clearError() }
            }
            if (state.items.isEmpty() && !state.isLoading) {
                EmptyState(onAdd = onAddJob)
            } else {
                LazyColumn(
                    contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                    modifier = Modifier.fillMaxSize(),
                ) {
                    items(state.items, key = { it.id }) { job ->
                        JobRow(job = job, onClick = { onJobClick(job.id) })
                    }
                }
            }
        }
    }
}

@Composable
private fun JobRow(job: Job, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                job.title,
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
            val subtitle = listOfNotNull(job.company, job.location).joinToString(" • ")
            if (subtitle.isNotBlank()) {
                Spacer(Modifier.height(4.dp))
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            val tags = listOfNotNull(job.job_type, job.experience_level, job.salary_range)
            if (tags.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Row(
                    horizontalArrangement = Arrangement.spacedBy(6.dp),
                ) {
                    tags.take(3).forEach { tag ->
                        AssistChip(onClick = onClick, label = { Text(tag) })
                    }
                }
            }
        }
    }
}

@Composable
private fun EmptyState(onAdd: () -> Unit) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            "No jobs yet",
            style = MaterialTheme.typography.titleLarge,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "Save a job description here to benchmark, scan with ATS, and craft tailored documents from the web app.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
        Spacer(Modifier.height(24.dp))
        Button(onClick = onAdd) { Text("Add your first job") }
    }
}

@Composable
private fun ErrorCard(message: String, onDismiss: () -> Unit) {
    Card(
        colors = CardDefaults.cardColors(
            containerColor = MaterialTheme.colorScheme.errorContainer,
        ),
        modifier = Modifier.fillMaxWidth().padding(horizontal = 16.dp),
    ) {
        Column(modifier = Modifier.padding(16.dp)) {
            Text(
                message,
                color = MaterialTheme.colorScheme.onErrorContainer,
                style = MaterialTheme.typography.bodyMedium,
            )
            Spacer(Modifier.height(4.dp))
            TextButton(onClick = onDismiss) { Text("Dismiss") }
        }
    }
}
