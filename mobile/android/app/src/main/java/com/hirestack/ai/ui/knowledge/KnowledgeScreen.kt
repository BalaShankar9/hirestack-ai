package com.hirestack.ai.ui.knowledge

import android.content.Intent
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.automirrored.filled.OpenInNew
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.KnowledgeResource

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun KnowledgeScreen(
    onBack: () -> Unit,
    vm: KnowledgeViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val ctx = LocalContext.current

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Knowledge library") },
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
                state.isLoading && state.resources.isEmpty() -> Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }
                state.error != null && state.resources.isEmpty() -> Column(modifier = Modifier.padding(24.dp)) {
                    Text("Error", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    Text(state.error!!, color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { vm.refresh() }) { Text("Retry") }
                }
                else -> LazyColumn(
                    modifier = Modifier.fillMaxSize(),
                    contentPadding = PaddingValues(20.dp),
                    verticalArrangement = Arrangement.spacedBy(12.dp),
                ) {
                    if (state.recommendations.isNotEmpty()) {
                        item { SectionHeader("Recommended for you") }
                        items(state.recommendations, key = { "rec-${it.id}" }) { rec ->
                            val res = rec.knowledge_resources
                            if (res != null) {
                                ResourceCard(
                                    res = res,
                                    badge = rec.reason,
                                    onOpen = { res.url?.let { openUrl(ctx, it) } },
                                )
                            }
                        }
                    }
                    if (state.progress.isNotEmpty()) {
                        item { SectionHeader("In progress") }
                        items(state.progress, key = { "prog-${it.id ?: it.resource_id}" }) { p ->
                            val res = p.knowledge_resources
                            if (res != null) {
                                ResourceCard(
                                    res = res,
                                    badge = p.status?.let { "${it.replaceFirstChar { c -> c.titlecase() }} • ${p.progress_pct ?: 0}%" },
                                    onOpen = { res.url?.let { openUrl(ctx, it) } },
                                )
                            }
                        }
                    }
                    item { SectionHeader("Browse catalog") }
                    if (state.resources.isEmpty()) {
                        item {
                            Text(
                                "No published resources yet.",
                                style = MaterialTheme.typography.bodyMedium,
                                color = MaterialTheme.colorScheme.onSurfaceVariant,
                            )
                        }
                    } else {
                        items(state.resources, key = { "res-${it.id}" }) { r ->
                            ResourceCard(
                                res = r,
                                badge = r.category,
                                onOpen = { r.url?.let { openUrl(ctx, it) } },
                            )
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun SectionHeader(text: String) {
    Text(text, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
}

@Composable
private fun ResourceCard(
    res: KnowledgeResource,
    badge: String?,
    onOpen: () -> Unit,
) {
    val canOpen = !res.url.isNullOrBlank()
    Card(modifier = Modifier.fillMaxWidth().clickable(enabled = canOpen, onClick = onOpen)) {
        Column(modifier = Modifier.padding(16.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Column(modifier = Modifier.weight(1f)) {
                    Text(
                        res.title ?: "Untitled",
                        style = MaterialTheme.typography.titleMedium,
                        fontWeight = FontWeight.SemiBold,
                    )
                    val sub = listOfNotNull(
                        res.resource_type,
                        res.difficulty,
                        res.duration_minutes?.let { "${it} min" },
                    ).joinToString(" • ")
                    if (sub.isNotBlank()) {
                        Spacer(Modifier.height(2.dp))
                        Text(
                            sub,
                            style = MaterialTheme.typography.bodySmall,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                }
                if (canOpen) {
                    Icon(
                        Icons.AutoMirrored.Filled.OpenInNew,
                        contentDescription = "Open",
                        tint = MaterialTheme.colorScheme.primary,
                    )
                }
            }
            res.description?.takeIf { it.isNotBlank() }?.let {
                Spacer(Modifier.height(6.dp))
                Text(it, style = MaterialTheme.typography.bodyMedium, maxLines = 3)
            }
            badge?.takeIf { it.isNotBlank() }?.let {
                Spacer(Modifier.height(8.dp))
                AssistChip(onClick = {}, label = { Text(it) })
            }
        }
    }
}

private fun openUrl(ctx: android.content.Context, url: String) {
    runCatching {
        val intent = Intent(Intent.ACTION_VIEW, android.net.Uri.parse(url))
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        ctx.startActivity(intent)
    }
}
