package com.hirestack.ai.ui.applications

import androidx.compose.foundation.background
import androidx.compose.foundation.horizontalScroll
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material.icons.filled.Refresh
import androidx.compose.material.icons.filled.Stop
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.Inventory2
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Work
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.Application
import com.hirestack.ai.data.network.PipelineEvent
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.GradientHeroCard
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.HireStackSecondaryButton
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.ScoreRing
import com.hirestack.ai.ui.components.SectionHeader
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.theme.BrandGradient
import kotlinx.coroutines.launch

private data class WorkspaceTab(val key: String, val label: String, val icon: ImageVector)

private val WORKSPACE_TABS = listOf(
    WorkspaceTab("mission", "Mission Control", Icons.Outlined.AutoAwesome),
    WorkspaceTab("cv", "CV", Icons.Outlined.Description),
    WorkspaceTab("cover", "Cover Letter", Icons.AutoMirrored.Outlined.Chat),
    WorkspaceTab("statement", "Statement", Icons.Outlined.Description),
    WorkspaceTab("intel", "Intel", Icons.Outlined.Work),
    WorkspaceTab("scores", "Scores", Icons.Outlined.Insights),
    WorkspaceTab("library", "Evidence", Icons.Outlined.Inventory2),
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ApplicationWorkspaceScreen(
    applicationId: String,
    onClose: () -> Unit,
    onOpenDocument: (title: String, html: String) -> Unit,
) {
    val vm: ApplicationWorkspaceViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    LaunchedEffect(applicationId) { vm.load(applicationId) }

    var tab by remember { mutableIntStateOf(0) }

    Scaffold(
        topBar = {
            BrandTopBar(
                title = state.app?.title ?: "Application",
                subtitle = state.app?.let {
                    listOfNotNull(it.company, it.location).joinToString(" • ").ifBlank { null }
                },
                onBack = onClose,
                actions = {
                    val shareCtx = androidx.compose.ui.platform.LocalContext.current
                    state.app?.let { a ->
                        IconButton(onClick = {
                            val body = buildString {
                                append(a.title ?: a.job_title ?: "Application")
                                if (!a.company.isNullOrBlank()) append(" @ ").append(a.company)
                                if (!a.location.isNullOrBlank()) append(" — ").append(a.location)
                            }
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, a.title ?: "Application")
                                putExtra(android.content.Intent.EXTRA_TEXT, body)
                            }
                            runCatching { shareCtx.startActivity(android.content.Intent.createChooser(send, a.title ?: "Application")) }
                        }) {
                            Icon(androidx.compose.material.icons.Icons.Outlined.Share, contentDescription = "Share")
                        }
                    }
                    IconButton(onClick = vm::reload) {
                        Icon(Icons.Filled.Refresh, contentDescription = "Refresh")
                    }
                },
            )
        },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            Column(
                Modifier
                    .fillMaxSize()
                    .padding(padding),
            ) {
                TabsRow(selected = tab, onSelect = { tab = it })
                when (WORKSPACE_TABS[tab].key) {
                    "mission" -> MissionControlPane(state, vm)
                    "cv" -> DocumentPane("Tailored CV", state.app?.cv_html, onOpenDocument)
                    "cover" -> DocumentPane("Cover Letter", state.app?.cover_letter_html, onOpenDocument)
                    "statement" -> DocumentPane("Personal Statement", state.app?.personal_statement_html, onOpenDocument)
                    "intel" -> CompanyIntelPane(state.app)
                    "scores" -> ScoresPane(state.app)
                    "library" -> EvidencePane(state.app?.id)
                }
            }
        }
    }
}

@Composable
private fun TabsRow(selected: Int, onSelect: (Int) -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .horizontalScroll(rememberScrollState())
            .padding(horizontal = 12.dp, vertical = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
    ) {
        WORKSPACE_TABS.forEachIndexed { i, t ->
            val active = i == selected
            Card(
                onClick = { onSelect(i) },
                shape = RoundedCornerShape(20.dp),
                colors = CardDefaults.cardColors(
                    containerColor = if (active) Brand.Indigo else MaterialTheme.colorScheme.surfaceContainerLow,
                ),
            ) {
                Row(
                    modifier = Modifier.padding(horizontal = 14.dp, vertical = 10.dp),
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    Icon(
                        t.icon,
                        contentDescription = null,
                        tint = if (active) Color.White else MaterialTheme.colorScheme.onSurface,
                        modifier = Modifier.size(16.dp),
                    )
                    Spacer(Modifier.width(8.dp))
                    Text(
                        t.label,
                        color = if (active) Color.White else MaterialTheme.colorScheme.onSurface,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            }
        }
    }
}

/* ---------------- Mission Control ---------------- */

@Composable
private fun MissionControlPane(state: WorkspaceState, vm: ApplicationWorkspaceViewModel) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 96.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            GradientHeroCard(brush = BrandGradient.HeroDark) {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Box(
                            Modifier
                                .size(36.dp)
                                .background(Color.White.copy(alpha = 0.15f), CircleShape),
                            contentAlignment = Alignment.Center,
                        ) {
                            Icon(
                                Icons.Outlined.AutoAwesome,
                                contentDescription = null,
                                tint = Color.White,
                                modifier = Modifier.size(20.dp),
                            )
                        }
                        Spacer(Modifier.width(10.dp))
                        Text(
                            "Mission Control",
                            color = Color.White,
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    Spacer(Modifier.height(10.dp))
                    Text(
                        "Watch every agent work in real time as your application is built.",
                        color = Color.White.copy(alpha = 0.92f),
                        style = MaterialTheme.typography.bodyMedium,
                    )

                    val app = state.app
                    val activeJobId = (app?.modules?.values?.firstOrNull()?.message)
                        ?: state.job?.id
                    Spacer(Modifier.height(16.dp))
                    Row(
                        horizontalArrangement = Arrangement.spacedBy(10.dp),
                        verticalAlignment = Alignment.CenterVertically,
                    ) {
                        if (state.streaming) {
                            HireStackSecondaryButton(label = "Stop", onClick = vm::stopStream)
                        } else if (activeJobId != null) {
                            HireStackPrimaryButton(
                                label = "Stream live",
                                leadingIcon = Icons.Filled.PlayArrow,
                                onClick = { vm.streamJob(activeJobId) },
                            )
                        } else {
                            Text(
                                "No active job — pull to refresh",
                                color = Color.White.copy(alpha = 0.85f),
                                style = MaterialTheme.typography.bodySmall,
                            )
                        }
                    }
                }
            }
        }

        if (state.streaming || state.timeline.isNotEmpty()) {
            item { SectionHeader(title = "Live timeline") }
            items(state.timeline.reversed(), key = { it.hashCode() }) { ev ->
                EventCard(ev)
            }
        } else {
            item {
                SoftCard {
                    Column {
                        Text(
                            "Recent agents will stream here.",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                        Spacer(Modifier.height(6.dp))
                        Text(
                            "Tap “Stream live” to connect to the current generation job.",
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                            style = MaterialTheme.typography.bodySmall,
                        )
                    }
                }
            }
        }

        if (state.error != null) {
            item {
                SoftCard {
                    Text(state.error!!, color = Brand.Danger)
                }
            }
        }
    }
}

@Composable
private fun EventCard(ev: PipelineEvent) {
    SoftCard {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusPill(
                    text = ev.name.uppercase(),
                    tone = when (ev.name) {
                        "complete" -> PillTone.Success
                        "error" -> PillTone.Danger
                        "agent_start", "stage" -> PillTone.Info
                        else -> PillTone.Brand
                    },
                )
                Spacer(Modifier.width(8.dp))
                if (!ev.agent.isNullOrBlank()) {
                    Text(
                        ev.agent!!,
                        style = MaterialTheme.typography.labelLarge,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                Spacer(Modifier.weight(1f))
                if (ev.progress != null) {
                    Text(
                        "${ev.progress}%",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (!ev.message.isNullOrBlank()) {
                Spacer(Modifier.height(6.dp))
                Text(ev.message!!, style = MaterialTheme.typography.bodyMedium)
            }
            if (ev.progress != null) {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { (ev.progress!! / 100f).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

/* ---------------- Document panes ---------------- */

@Composable
private fun DocumentPane(
    title: String,
    html: String?,
    onOpen: (String, String) -> Unit,
) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    Column(
        Modifier
            .fillMaxSize()
            .padding(20.dp),
    ) {
        if (html.isNullOrBlank()) {
            SoftCard {
                Column {
                    Text(
                        "Not generated yet",
                        style = MaterialTheme.typography.titleSmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                    Spacer(Modifier.height(6.dp))
                    Text(
                        "Once the pipeline completes this section, the document will appear here.",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        } else {
            SoftCard {
                Column {
                    Text(
                        "Tap Open for the formatted preview, or copy plain text to paste elsewhere.",
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                    Spacer(Modifier.height(12.dp))
                    HireStackPrimaryButton(
                        label = "Open $title",
                        onClick = { onOpen(title, html) },
                    )
                    Spacer(Modifier.height(8.dp))
                    HireStackSecondaryButton(
                        label = "Copy as plain text",
                        onClick = {
                            val plain = html
                                .replace(Regex("(?s)<style.*?</style>"), " ")
                                .replace(Regex("(?s)<script.*?</script>"), " ")
                                .replace(Regex("<br\\s*/?>", RegexOption.IGNORE_CASE), "\n")
                                .replace(Regex("</p>", RegexOption.IGNORE_CASE), "\n\n")
                                .replace(Regex("<[^>]+>"), "")
                                .replace("&nbsp;", " ")
                                .replace("&amp;", "&")
                                .replace("&lt;", "<")
                                .replace("&gt;", ">")
                                .replace(Regex("[ \\t]+"), " ")
                                .replace(Regex("\\n{3,}"), "\n\n")
                                .trim()
                            clipboard.setText(AnnotatedString(plain))
                            haptic.confirm()
                            scope.launch { snackbar.showSnackbar("Copied $title as plain text") }
                        },
                    )
                }
            }
        }
    }
}

/* ---------------- Intel ---------------- */

@Composable
private fun CompanyIntelPane(app: Application?) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(20.dp),
    ) {
        SoftCard {
            Column {
                Text(
                    "Company intel",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(8.dp))
                val intel = app?.company_intel
                if (intel.isNullOrEmpty()) {
                    Text(
                        "No intel generated yet.",
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                } else {
                    intel.forEach { (k, v) ->
                        Text(
                            k.replace("_", " ").replaceFirstChar { it.uppercase() },
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Text(v?.toString() ?: "—", style = MaterialTheme.typography.bodyMedium)
                        Spacer(Modifier.height(8.dp))
                    }
                }
            }
        }
    }
}

/* ---------------- Scores ---------------- */

@Composable
private fun ScoresPane(app: Application?) {
    val scores = app?.scores
    Column(
        Modifier
            .fillMaxSize()
            .padding(20.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (scores == null) {
            SoftCard {
                Text("Scores will appear here once generated.")
            }
        } else {
            SoftCard {
                Column(horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                    ScoreRing(score = (scores.overall ?: 0.0).toInt(), sizeDp = 132, strokeDp = 12)
                    Spacer(Modifier.height(10.dp))
                    Text("Overall match", style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold)
                }
            }
            ScoreRow("Keyword fit", scores.keyword)
            ScoreRow("Readability", scores.readability)
            ScoreRow("Structure", scores.structure)
            ScoreRow("ATS friendliness", scores.ats)
            if (!scores.topFix.isNullOrBlank()) {
                SoftCard {
                    Column {
                        Text(
                            "Top fix",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.SemiBold,
                        )
                        Spacer(Modifier.height(4.dp))
                        Text(scores.topFix!!, style = MaterialTheme.typography.bodyMedium)
                    }
                }
            }
        }
    }
}

@Composable
private fun ScoreRow(label: String, value: Double?) {
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
            Text(
                if (value == null) "—" else "${value.toInt()}",
                style = MaterialTheme.typography.titleMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
        if (value != null) {
            Spacer(Modifier.height(8.dp))
            LinearProgressIndicator(
                progress = { (value / 100.0).toFloat().coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/* ---------------- Evidence stub (read evidence_items filtered) ---------------- */

@Composable
private fun EvidencePane(applicationId: String?) {
    Column(
        Modifier
            .fillMaxSize()
            .padding(20.dp),
    ) {
        SoftCard {
            Column {
                Text(
                    "Evidence library",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    "Snippets, links, and proof points the AI used. Manage all evidence from the Evidence tab in the bottom bar.",
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    style = MaterialTheme.typography.bodyMedium,
                )
            }
        }
    }
}
