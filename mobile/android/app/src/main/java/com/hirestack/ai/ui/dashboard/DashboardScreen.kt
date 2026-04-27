package com.hirestack.ai.ui.dashboard

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.combinedClickable
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
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Bolt
import androidx.compose.material.icons.outlined.Bookmarks
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.LocalFireDepartment
import androidx.compose.material.icons.outlined.MicNone
import androidx.compose.material.icons.outlined.Money
import androidx.compose.material.icons.outlined.PeopleAlt
import androidx.compose.material.icons.outlined.Close
import androidx.compose.material.icons.outlined.Search
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.outlined.Work
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.DashboardResponse
import com.hirestack.ai.ui.auth.AuthViewModel
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.GradientHeroCard
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.ScoreRing
import com.hirestack.ai.ui.components.SectionHeader
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.theme.BrandGradient
import kotlinx.coroutines.launch

private data class QuickAction(
    val label: String,
    val icon: ImageVector,
    val tint: Color,
    val onClick: () -> Unit,
)

private data class StatTile(
    val label: String,
    val value: String,
    val icon: ImageVector,
    val tint: Color,
)

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun DashboardScreen(
    onNewApplication: () -> Unit = {},
    onOpenJobs: () -> Unit = {},
    onOpenProfiles: () -> Unit = {},
    onOpenInterviews: () -> Unit = {},
    onOpenBenchmark: () -> Unit = {},
    onOpenEvidence: () -> Unit = {},
    onOpenSalary: () -> Unit = {},
    authVm: AuthViewModel = hiltViewModel(),
    vm: DashboardViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val auth by authVm.state.collectAsState()
    val data = state.data
    com.hirestack.ai.ui.components.ErrorSnackbar(if (data != null) state.error else null) { vm.clearError() }

    var jumpOpen by remember { mutableStateOf(false) }
    var jumpQuery by remember { mutableStateOf("") }
    val jumpSheet = rememberModalBottomSheetState(skipPartiallyExpanded = true)
    val destinations = remember(
        onNewApplication, onOpenJobs, onOpenProfiles, onOpenInterviews,
        onOpenBenchmark, onOpenEvidence, onOpenSalary,
    ) {
        listOf(
            "New application" to onNewApplication,
            "Job board" to onOpenJobs,
            "Resume profiles" to onOpenProfiles,
            "Interview Coach" to onOpenInterviews,
            "Benchmark studio" to onOpenBenchmark,
            "Evidence locker" to onOpenEvidence,
            "Salary Coach" to onOpenSalary,
        )
    }
    val visibleDestinations = remember(jumpQuery, destinations) {
        if (jumpQuery.isBlank()) destinations
        else destinations.filter { it.first.contains(jumpQuery, ignoreCase = true) }
    }

    Scaffold(
        topBar = {
            BrandTopBar(
                title = "Welcome back",
                subtitle = auth.displayName ?: auth.email ?: "Your career, accelerated",
                actions = {
                    val d = data
                    if (d != null) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("HireStack AI snapshot")
                                d.latest_score?.let { appendLine("- Latest match score: ${it.toInt()}%") }
                                appendLine("- Applications: ${d.applications} (${d.active_applications} active)")
                                appendLine("- Jobs analyzed: ${d.jobs_analyzed}")
                                appendLine("- Profiles: ${d.profiles}")
                                appendLine("- Evidence items: ${d.evidence_items}")
                                appendLine("- ATS scans: ${d.ats_scans}")
                                appendLine("- Salary analyses: ${d.salary_analyses}")
                                appendLine("- Interview sessions: ${d.interview_sessions}")
                                appendLine("- Learning streak: ${d.learning_streak} days")
                                appendLine("- Tasks: ${d.completed_tasks}/${d.total_tasks}")
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "HireStack AI snapshot")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share HireStack snapshot"),
                                )
                            }
                        }) {
                            Icon(
                                Icons.Outlined.Share,
                                contentDescription = "Share snapshot",
                            )
                        }
                    }
                    IconButton(onClick = { jumpOpen = true }) {
                        Icon(Icons.Outlined.Search, contentDescription = "Jump to")
                    }
                },
            )
        },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            PullToRefreshBox(
                isRefreshing = state.isLoading && data != null,
                onRefresh = { vm.refresh() },
                modifier = Modifier.fillMaxSize().padding(padding),
            ) {
                when {
                    state.isLoading && data == null -> SkeletonList(rows = 6)
                    data == null -> {
                        Column(
                            Modifier.fillMaxSize().padding(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            state.error?.let { InlineBanner(it, tone = PillTone.Danger) }
                        }
                    }
                    else -> DashboardContent(
                        data = data,
                        error = state.error,
                        onNewApplication = onNewApplication,
                        onOpenJobs = onOpenJobs,
                        onOpenProfiles = onOpenProfiles,
                        onOpenInterviews = onOpenInterviews,
                        onOpenBenchmark = onOpenBenchmark,
                        onOpenEvidence = onOpenEvidence,
                        onOpenSalary = onOpenSalary,
                    )
                }
            }
        }
    }

    if (jumpOpen) {
        ModalBottomSheet(
            onDismissRequest = { jumpOpen = false; jumpQuery = "" },
            sheetState = jumpSheet,
        ) {
            val jumpFocus = remember { androidx.compose.ui.focus.FocusRequester() }
            LaunchedEffect(Unit) { jumpFocus.requestFocus() }
            Column(modifier = Modifier.padding(horizontal = 20.dp, vertical = 8.dp)) {
                Text("Jump to", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(12.dp))
                OutlinedTextField(
                    value = jumpQuery,
                    onValueChange = { jumpQuery = it },
                    placeholder = { Text("Search destinations") },
                    leadingIcon = { Icon(Icons.Outlined.Search, null) },
                    trailingIcon = {
                        if (jumpQuery.isNotEmpty()) {
                            androidx.compose.material3.IconButton(onClick = { jumpQuery = "" }) {
                                Icon(Icons.Outlined.Close, contentDescription = "Clear search")
                            }
                        }
                    },
                    singleLine = true,
                    shape = RoundedCornerShape(14.dp),
                    keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Search),
                    keyboardActions = androidx.compose.foundation.text.KeyboardActions(onSearch = {
                        val first = visibleDestinations.firstOrNull()
                        if (first != null) {
                            jumpOpen = false
                            jumpQuery = ""
                            first.second()
                        }
                    }),
                    modifier = Modifier.fillMaxWidth().focusRequester(jumpFocus),
                )
                Spacer(Modifier.height(12.dp))
                if (visibleDestinations.isEmpty()) {
                    Text(
                        "No matches for \"$jumpQuery\"",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.padding(vertical = 12.dp),
                    )
                }
                visibleDestinations.forEach { (label, action) ->
                    Surface(
                        modifier = Modifier
                            .fillMaxWidth()
                            .padding(vertical = 4.dp),
                        shape = RoundedCornerShape(14.dp),
                        color = Color.Transparent,
                        onClick = {
                            jumpOpen = false
                            jumpQuery = ""
                            action()
                        },
                    ) {
                        Row(
                            modifier = Modifier.padding(horizontal = 16.dp, vertical = 14.dp),
                            verticalAlignment = Alignment.CenterVertically,
                        ) {
                            Text(label, style = MaterialTheme.typography.bodyLarge)
                        }
                    }
                }
                Spacer(Modifier.height(20.dp))
            }
        }
    }
}

@Composable
private fun DashboardContent(
    data: DashboardResponse,
    error: String?,
    onNewApplication: () -> Unit,
    onOpenJobs: () -> Unit,
    onOpenProfiles: () -> Unit,
    onOpenInterviews: () -> Unit,
    onOpenBenchmark: () -> Unit,
    onOpenEvidence: () -> Unit,
    onOpenSalary: () -> Unit,
) {
    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        if (error != null) {
            item { InlineBanner(error, tone = PillTone.Warning) }
        }

        item { HeroScoreCard(data, onOpenBenchmark) }

        item { SectionHeader(title = "Quick actions") }
        item {
            QuickActionsRow(
                actions = listOf(
                    QuickAction("New app", Icons.Outlined.AutoAwesome, Brand.Indigo, onNewApplication),
                    QuickAction("Browse jobs", Icons.Outlined.Work, Brand.Cyan, onOpenJobs),
                    QuickAction("Resume", Icons.Outlined.Description, Brand.Violet, onOpenProfiles),
                    QuickAction("Practice", Icons.Outlined.MicNone, Brand.Emerald, onOpenInterviews),
                ),
            )
        }

        item { SectionHeader(title = "At a glance") }
        item {
            val streak = data.learning_streak
            val tasks = data.summary?.task_completion_rate?.toInt() ?: 0
            StreakCard(streak = streak, taskRate = tasks)
        }

        item { SectionHeader(title = "Workspace") }
        item {
            StatGrid(
                tiles = listOf(
                    StatTile("Applications", data.applications.toString(), Icons.Outlined.AutoAwesome, Brand.Indigo),
                    StatTile("Active", data.active_applications.toString(), Icons.Outlined.Bolt, Brand.Cyan),
                    StatTile("Profiles", data.profiles.toString(), Icons.Outlined.PeopleAlt, Brand.Violet),
                    StatTile("Jobs", data.jobs_analyzed.toString(), Icons.Outlined.Work, Brand.Emerald),
                ),
                onClicks = listOf(onNewApplication, onNewApplication, onOpenProfiles, onOpenJobs),
            )
        }
        item {
            StatGrid(
                tiles = listOf(
                    StatTile("Evidence", data.evidence_items.toString(), Icons.Outlined.Bookmarks, Brand.Pink),
                    StatTile("ATS scans", data.ats_scans.toString(), Icons.Outlined.Search, Brand.Amber),
                    StatTile("Salary", data.salary_analyses.toString(), Icons.Outlined.Money, Brand.Emerald),
                    StatTile("Interviews", data.interview_sessions.toString(), Icons.Outlined.MicNone, Brand.Cyan),
                ),
                onClicks = listOf(onOpenEvidence, onOpenBenchmark, onOpenSalary, onOpenInterviews),
            )
        }
    }
}

@Composable
@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
private fun HeroScoreCard(data: DashboardResponse, onClick: () -> Unit) {
    val score = data.latest_score?.toInt()
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    GradientHeroCard(brush = BrandGradient.HeroDark, onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ScoreRing(
                score = score ?: 0,
                label = if (score != null) "match" else "—",
                sizeDp = 92,
                strokeDp = 9,
                brush = BrandGradient.Aurora,
            )
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "Latest match score",
                    color = Color.White.copy(alpha = 0.78f),
                    style = MaterialTheme.typography.labelMedium,
                )
                Spacer(Modifier.height(4.dp))
                val scoreText = if (score != null) "$score%" else "Run a benchmark"
                Text(
                    scoreText,
                    color = Color.White,
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    modifier = if (score != null) Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = {
                            clipboard.setText(androidx.compose.ui.text.AnnotatedString("$score%"))
                            haptic.confirm()
                            scope.launch { snackbar.showSnackbar("Copied match score") }
                        },
                    ) else Modifier,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    if (score != null) "Tap to open Studio · long-press score to copy" else "Score a job description to begin",
                    color = Color.White.copy(alpha = 0.78f),
                    style = MaterialTheme.typography.bodySmall,
                )
            }
        }
    }
}

@Composable
private fun QuickActionsRow(actions: List<QuickAction>) {
    Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
        actions.forEach { a ->
            Column(
                modifier = Modifier
                    .weight(1f)
                    .clip(RoundedCornerShape(20.dp))
                    .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f))
                    .clickable(onClick = a.onClick)
                    .padding(vertical = 14.dp, horizontal = 8.dp),
                horizontalAlignment = Alignment.CenterHorizontally,
            ) {
                Box(
                    Modifier.size(44.dp).background(a.tint.copy(alpha = 0.18f), CircleShape),
                    contentAlignment = Alignment.Center,
                ) { Icon(a.icon, null, tint = a.tint) }
                Spacer(Modifier.height(6.dp))
                Text(
                    a.label,
                    style = MaterialTheme.typography.labelMedium,
                    fontWeight = FontWeight.Medium,
                    maxLines = 1,
                )
            }
        }
    }
}

@Composable
private fun StreakCard(streak: Int, taskRate: Int) {
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically, modifier = Modifier.padding(4.dp)) {
            Box(
                Modifier.size(48.dp).background(Brand.Amber.copy(alpha = 0.18f), CircleShape),
                contentAlignment = Alignment.Center,
            ) { Icon(Icons.Outlined.LocalFireDepartment, null, tint = Brand.Amber) }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "$streak day streak",
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    "$taskRate% of tasks complete",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@Composable
private fun StatGrid(tiles: List<StatTile>, onClicks: List<() -> Unit> = emptyList()) {
    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
        tiles.chunked(2).forEachIndexed { rowIndex, row ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                row.forEachIndexed { idx, tile ->
                    val flatIdx = rowIndex * 2 + idx
                    StatTileCard(
                        tile = tile,
                        onClick = onClicks.getOrNull(flatIdx) ?: {},
                        modifier = Modifier.weight(1f),
                    )
                }
                if (row.size == 1) Spacer(Modifier.weight(1f))
            }
        }
    }
}

@Composable
private fun StatTileCard(tile: StatTile, onClick: () -> Unit, modifier: Modifier = Modifier) {
    Box(
        modifier = modifier
            .clip(RoundedCornerShape(20.dp))
            .background(MaterialTheme.colorScheme.surfaceVariant.copy(alpha = 0.45f))
            .clickable(onClick = onClick)
            .padding(16.dp),
    ) {
        Column {
            Box(
                Modifier.size(34.dp).background(tile.tint.copy(alpha = 0.18f), CircleShape),
                contentAlignment = Alignment.Center,
            ) { Icon(tile.icon, null, tint = tile.tint, modifier = Modifier.size(20.dp)) }
            Spacer(Modifier.height(10.dp))
            Text(
                tile.value,
                style = MaterialTheme.typography.headlineSmall,
                fontWeight = FontWeight.Bold,
            )
            Text(
                tile.label,
                style = MaterialTheme.typography.bodySmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
