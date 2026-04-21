package com.hirestack.ai.ui.ats

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
import com.hirestack.ai.data.network.AtsScan

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AtsScreen(
    onBack: () -> Unit,
    vm: AtsViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    var resumeText by remember { mutableStateOf("") }
    var jdText by remember { mutableStateOf("") }
    var showForm by remember { mutableStateOf(false) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("ATS Scanner") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    TextButton(onClick = { showForm = !showForm }) {
                        Text(if (showForm) "Hide" else "New scan")
                    }
                },
            )
        },
    ) { padding ->
        LazyColumn(
            modifier = Modifier.fillMaxSize().padding(padding),
            contentPadding = PaddingValues(20.dp),
            verticalArrangement = Arrangement.spacedBy(16.dp),
        ) {
            if (showForm) {
                item {
                    Card(modifier = Modifier.fillMaxWidth()) {
                        Column(modifier = Modifier.padding(16.dp)) {
                            Text("Run a new scan", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            Spacer(Modifier.height(12.dp))
                            OutlinedTextField(
                                value = resumeText,
                                onValueChange = { resumeText = it },
                                label = { Text("Resume / document text") },
                                modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp),
                                minLines = 5,
                            )
                            Spacer(Modifier.height(12.dp))
                            OutlinedTextField(
                                value = jdText,
                                onValueChange = { jdText = it },
                                label = { Text("Job description text") },
                                modifier = Modifier.fillMaxWidth().heightIn(min = 140.dp),
                                minLines = 5,
                            )
                            Spacer(Modifier.height(12.dp))
                            state.error?.let {
                                Text(it, color = MaterialTheme.colorScheme.error)
                                Spacer(Modifier.height(8.dp))
                            }
                            Button(
                                onClick = { vm.runScan(resumeText, jdText) },
                                enabled = !state.running,
                                modifier = Modifier.fillMaxWidth(),
                            ) {
                                if (state.running) {
                                    CircularProgressIndicator(
                                        modifier = Modifier.size(20.dp),
                                        strokeWidth = 2.dp,
                                        color = MaterialTheme.colorScheme.onPrimary,
                                    )
                                } else {
                                    Text("Run scan")
                                }
                            }
                        }
                    }
                }
                state.lastResult?.let { result ->
                    item {
                        ResultCard(result = result, headline = "Latest scan")
                    }
                }
            }

            item {
                Text(
                    "History",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
            }

            when {
                state.isLoading && state.items.isEmpty() -> item {
                    Box(modifier = Modifier.fillMaxWidth().padding(32.dp), contentAlignment = Alignment.Center) {
                        CircularProgressIndicator()
                    }
                }
                state.items.isEmpty() -> item {
                    Text(
                        "No previous scans yet.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                else -> items(state.items, key = { it.id ?: it.hashCode().toString() }) { scan ->
                    ResultCard(result = scan, headline = scan.created_at ?: "Scan")
                }
            }
        }
    }
}

@Composable
private fun ResultCard(result: AtsScan, headline: String) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(headline, style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Text(
                        "${result.ats_score}%",
                        style = MaterialTheme.typography.headlineMedium,
                        fontWeight = FontWeight.Bold,
                        color = MaterialTheme.colorScheme.primary,
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
                Text("Matched", style = MaterialTheme.typography.labelLarge)
                Spacer(Modifier.height(4.dp))
                Text(
                    result.matched_keywords.take(20).joinToString(", "),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
            if (result.missing_keywords.isNotEmpty()) {
                Spacer(Modifier.height(12.dp))
                Text("Missing", style = MaterialTheme.typography.labelLarge, color = MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(4.dp))
                Text(
                    result.missing_keywords.take(20).joinToString(", "),
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.error,
                )
            }
        }
    }
}
