package com.hirestack.ai.ui.variants

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.CheckCircle
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.DocVariant

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun VariantsScreen(
    onBack: () -> Unit,
    vm: VariantsViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    var expanded by remember { mutableStateOf<String?>(null) }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Doc Variants") },
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
                state.isLoading && state.items.isEmpty() -> Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }
                state.error != null && state.items.isEmpty() -> Column(modifier = Modifier.padding(24.dp)) {
                    Text("Error", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    Text(state.error!!, color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { vm.refresh() }) { Text("Retry") }
                }
                state.items.isEmpty() -> Column(
                    modifier = Modifier.fillMaxSize().padding(32.dp),
                    horizontalAlignment = Alignment.CenterHorizontally,
                    verticalArrangement = Arrangement.Center,
                ) {
                    Text("No variants yet", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Generate tone variants from the web A/B Doc Lab to compare them here.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    items(state.items, key = { it.id }) { v ->
                        VariantCard(
                            v = v,
                            isExpanded = expanded == v.id,
                            isSelecting = state.selecting == v.id,
                            onToggle = { expanded = if (expanded == v.id) null else v.id },
                            onSelect = { vm.select(v.id) },
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun VariantCard(
    v: DocVariant,
    isExpanded: Boolean,
    isSelecting: Boolean,
    onToggle: () -> Unit,
    onSelect: () -> Unit,
) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        v.variant_name?.replaceFirstChar { it.titlecase() } ?: v.tone ?: "Variant",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(Modifier.height(2.dp))
                    Text(
                        listOfNotNull(v.document_type, v.word_count?.let { "$it words" })
                            .joinToString(" • "),
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
                if (v.is_selected == true) {
                    Icon(
                        Icons.Filled.CheckCircle,
                        contentDescription = "Selected",
                        tint = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            Spacer(Modifier.height(8.dp))
            Row {
                v.ats_score?.let {
                    AssistChip(onClick = {}, label = { Text("ATS ${it.toInt()}") })
                    Spacer(Modifier.width(8.dp))
                }
                v.readability_score?.let {
                    AssistChip(onClick = {}, label = { Text("Read ${it.toInt()}") })
                }
            }
            Spacer(Modifier.height(8.dp))
            Row {
                TextButton(onClick = onToggle) {
                    Text(if (isExpanded) "Hide content" else "View content")
                }
                Spacer(Modifier.weight(1f))
                if (v.is_selected != true) {
                    Button(onClick = onSelect, enabled = !isSelecting) {
                        if (isSelecting) {
                            CircularProgressIndicator(
                                modifier = Modifier.size(16.dp),
                                strokeWidth = 2.dp,
                                color = MaterialTheme.colorScheme.onPrimary,
                            )
                        } else {
                            Text("Select")
                        }
                    }
                }
            }
            if (isExpanded) {
                Spacer(Modifier.height(8.dp))
                HorizontalDivider()
                Spacer(Modifier.height(8.dp))
                Text(
                    v.content ?: "(no content)",
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}
