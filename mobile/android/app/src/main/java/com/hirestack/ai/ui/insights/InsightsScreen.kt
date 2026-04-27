package com.hirestack.ai.ui.insights

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
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.background
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Bolt
import androidx.compose.material.icons.outlined.EmojiEvents
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material.icons.automirrored.outlined.TrendingUp
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
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
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.DevGoal
import com.hirestack.ai.data.network.GapReport
import com.hirestack.ai.data.network.UserSkill
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.GradientHeroCard
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.ScoreRing
import com.hirestack.ai.ui.components.SectionHeader
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.theme.BrandGradient
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InsightsScreen() {
    val vm: InsightsViewModel = hiltViewModel()
    val state by vm.state.collectAsState()
    com.hirestack.ai.ui.components.ErrorSnackbar(state.error) { vm.clearError() }
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = {
            BrandTopBar(
                title = "Insights",
                subtitle = "Skills, goals, and gaps in one place",
                scrollBehavior = scrollBehavior,
                actions = {
                    if (state.skills.isNotEmpty() || state.goals.isNotEmpty() || state.gapReports.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        androidx.compose.material3.IconButton(onClick = {
                            val report = buildString {
                                appendLine("HireStack Insights")
                                appendLine()
                                if (state.skills.isNotEmpty()) {
                                    appendLine("Top skills")
                                    state.skills.take(10).forEach { sk ->
                                        val lvl = sk.proficiency?.let { " (lvl $it)" } ?: ""
                                        appendLine("- ${sk.name ?: "—"}$lvl")
                                    }
                                    appendLine()
                                }
                                if (state.goals.isNotEmpty()) {
                                    appendLine("Goals")
                                    state.goals.forEach { g ->
                                        appendLine("- ${g.title ?: "Goal"}")
                                        g.description?.let { appendLine("    $it") }
                                    }
                                    appendLine()
                                }
                                if (state.gapReports.isNotEmpty()) {
                                    appendLine("Gaps")
                                    state.gapReports.forEach { r ->
                                        r.summary?.let { appendLine("- $it") }
                                    }
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "HireStack Insights")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share insights"),
                                )
                            }
                        }) {
                            androidx.compose.material3.Icon(
                                Icons.Outlined.Share,
                                contentDescription = "Share insights",
                            )
                        }
                    }
                },
            )
        },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            PullToRefreshBox(
                isRefreshing = state.refreshing,
                onRefresh = vm::refresh,
                modifier = Modifier.fillMaxSize().padding(padding),
            ) {
                if (state.isLoading) {
                    SkeletonList()
                } else {
                    LazyColumn(
                        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                        verticalArrangement = Arrangement.spacedBy(14.dp),
                    ) {
                        item { MasteryHero(state) }
                        item { SectionHeader(title = "Skills") }
                        if (state.skills.isEmpty()) {
                            item { SoftCard { Text("Your top skills will appear here once you add some.") } }
                        } else {
                            items(state.skills, key = { "s-${it.id}" }) { SkillRow(it) }
                        }
                        item { SectionHeader(title = "Goals") }
                        if (state.goals.isEmpty()) {
                            item { SoftCard { Text("Set learning goals to track development over time.") } }
                        } else {
                            items(state.goals, key = { "g-${it.id}" }) { GoalRow(it) }
                        }
                        item { SectionHeader(title = "Gap reports") }
                        if (state.gapReports.isEmpty()) {
                            item { SoftCard { Text("Run a gap analysis from any application to see results here.") } }
                        } else {
                            items(state.gapReports, key = { "gr-${it.id}" }) { GapRow(it) }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun MasteryHero(state: InsightsState) {
    GradientHeroCard(brush = BrandGradient.Aurora) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ScoreRing(
                score = (state.summary?.mastery_score ?: 0.0).toInt(),
                sizeDp = 88,
                strokeDp = 8,
            )
            Spacer(Modifier.width(18.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "Mastery score",
                    color = Color.White,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(6.dp))
                Row(horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                    HeroStat(label = "Skills", value = state.summary?.skills_count ?: state.skills.size, icon = Icons.Outlined.Bolt)
                    HeroStat(label = "Goals", value = state.summary?.active_goals ?: state.goals.size, icon = Icons.Outlined.EmojiEvents)
                    HeroStat(label = "Gaps", value = state.summary?.gaps_open ?: state.gapReports.sumOf { it.gap_count ?: 0 }, icon = Icons.AutoMirrored.Outlined.TrendingUp)
                }
            }
        }
    }
}

@Composable
private fun HeroStat(label: String, value: Int, icon: androidx.compose.ui.graphics.vector.ImageVector) {
    Box(
        Modifier
            .background(Color.White.copy(alpha = 0.16f), RoundedCornerShape(12.dp))
            .padding(horizontal = 10.dp, vertical = 8.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(icon, contentDescription = null, tint = Color.White, modifier = Modifier.size(14.dp))
            Spacer(Modifier.width(6.dp))
            Text(
                "$value $label",
                color = Color.White,
                style = MaterialTheme.typography.labelMedium,
                fontWeight = FontWeight.SemiBold,
            )
        }
    }
}

@Composable
private fun SkillRow(s: UserSkill) {
    SoftCard {
        Column {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    s.name ?: "Skill",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.weight(1f),
                )
                if (!s.level.isNullOrBlank()) StatusPill(text = s.level!!.uppercase(), tone = PillTone.Brand)
            }
            if (s.proficiency != null) {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { (s.proficiency!! / 100f).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun GoalRow(g: DevGoal) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard {
        Column {
            val titleText = g.title ?: "Goal"
            Text(
                titleText,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = { copy(titleText, "goal") },
                ),
            )
            if (!g.description.isNullOrBlank()) {
                Text(
                    g.description!!,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(g.description!!, "goal description") },
                    ),
                )
            }
            Spacer(Modifier.height(8.dp))
            Row(verticalAlignment = Alignment.CenterVertically) {
                StatusPill(
                    text = (g.status ?: "active").uppercase(),
                    tone = when (g.status) {
                        "complete", "completed" -> PillTone.Success
                        "blocked" -> PillTone.Danger
                        else -> PillTone.Info
                    },
                )
                Spacer(Modifier.width(8.dp))
                if (g.target_date != null) {
                    Text(
                        "by ${g.target_date}",
                        style = MaterialTheme.typography.labelMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
            if (g.progress_pct != null) {
                Spacer(Modifier.height(8.dp))
                LinearProgressIndicator(
                    progress = { (g.progress_pct!! / 100f).coerceIn(0f, 1f) },
                    modifier = Modifier.fillMaxWidth(),
                )
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun GapRow(r: GapReport) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            ScoreRing(
                score = (r.overall_match ?: 0.0).toInt(),
                sizeDp = 56,
                strokeDp = 6,
            )
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "Gap report",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    "${r.gap_count ?: 0} gaps · ${r.critical_count ?: 0} critical",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Text(
                r.created_at?.take(10) ?: "",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        if (!r.summary.isNullOrBlank()) {
            Spacer(Modifier.height(8.dp))
            Text(
                r.summary!!,
                style = MaterialTheme.typography.bodyMedium,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = {
                        clipboard.setText(AnnotatedString(r.summary!!))
                        haptic.confirm()
                        scope.launch { snackbar.showSnackbar("Copied gap summary") }
                    },
                ),
            )
        }
    }
}
