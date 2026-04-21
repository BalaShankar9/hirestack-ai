package com.hirestack.ai.ui.candidates

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.Candidate

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
fun CandidatesScreen(
    onBack: () -> Unit,
    vm: CandidatesViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Candidates") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(modifier = Modifier.fillMaxSize().padding(padding)) {
            ScrollableTabRow(
                selectedTabIndex = STAGE_FILTERS.indexOfFirst { it.first == state.stage }.coerceAtLeast(0),
                edgePadding = 16.dp,
            ) {
                STAGE_FILTERS.forEach { (key, label) ->
                    Tab(
                        selected = state.stage == key,
                        onClick = { vm.setStage(key) },
                        text = { Text(label) },
                    )
                }
            }

            Box(modifier = Modifier.fillMaxSize()) {
                when {
                    state.noOrg -> NoOrgEmptyState()
                    state.isLoading && state.items.isEmpty() -> {
                        Box(modifier = Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                            CircularProgressIndicator()
                        }
                    }
                    state.error != null && state.items.isEmpty() -> {
                        Column(modifier = Modifier.padding(24.dp)) {
                            Text("Error", style = MaterialTheme.typography.titleMedium)
                            Spacer(Modifier.height(8.dp))
                            Text(state.error!!, color = MaterialTheme.colorScheme.error)
                            Spacer(Modifier.height(16.dp))
                            Button(onClick = { vm.refresh() }) { Text("Retry") }
                        }
                    }
                    state.items.isEmpty() -> {
                        EmptyState(stage = state.stage)
                    }
                    else -> {
                        LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            items(state.items, key = { it.id }) { c ->
                                CandidateRow(c)
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun CandidateRow(c: Candidate) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(c.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    val sub = listOfNotNull(c.email, c.location).joinToString(" • ")
                    if (sub.isNotBlank()) {
                        Spacer(Modifier.height(2.dp))
                        Text(
                            sub,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                c.pipeline_stage?.let {
                    AssistChip(onClick = {}, label = { Text(it) })
                }
            }
            if (c.tags.isNotEmpty()) {
                Spacer(Modifier.height(8.dp))
                Text(
                    c.tags.take(5).joinToString(" • "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            c.client_company?.let {
                Spacer(Modifier.height(4.dp))
                Text("Client: $it", style = MaterialTheme.typography.bodySmall)
            }
        }
    }
}

@Composable
private fun NoOrgEmptyState() {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text("Recruiter feature", style = MaterialTheme.typography.titleMedium)
        Spacer(Modifier.height(8.dp))
        Text(
            "Create an organization on the web app to start tracking candidates here.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}

@Composable
private fun EmptyState(stage: String?) {
    Column(
        modifier = Modifier.fillMaxSize().padding(32.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            if (stage == null) "No candidates yet" else "No candidates in '$stage'",
            style = MaterialTheme.typography.titleMedium,
        )
        Spacer(Modifier.height(8.dp))
        Text(
            "Add candidates from the web app to see them here.",
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
        )
    }
}
