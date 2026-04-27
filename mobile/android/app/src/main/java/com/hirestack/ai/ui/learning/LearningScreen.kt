package com.hirestack.ai.ui.learning

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
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
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
import com.hirestack.ai.data.network.LearningChallenge
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.tap
import com.hirestack.ai.ui.theme.Brand
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun LearningScreen(onBack: () -> Unit, vm: LearningViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    com.hirestack.ai.ui.components.ErrorSnackbar(state.error) { vm.clearError() }
    val haptic = LocalHapticFeedback.current
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Learning",
                subtitle = state.streak?.let { "${it.current_streak} day streak" },
                onBack = onBack,
                scrollBehavior = scrollBehavior,
                actions = {
                    val streak = state.streak
                    if (streak != null || state.history.isNotEmpty() || state.today.isNotEmpty()) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        IconButton(onClick = {
                            val report = buildString {
                                appendLine("HireStack learning progress")
                                appendLine()
                                if (streak != null) {
                                    appendLine("Streak")
                                    appendLine("- Current: ${streak.current_streak} days")
                                    appendLine("- Longest: ${streak.longest_streak} days")
                                    appendLine("- Total challenges: ${streak.total_challenges}")
                                    appendLine("- Total correct: ${streak.total_correct}")
                                    appendLine()
                                }
                                if (state.today.isNotEmpty()) {
                                    appendLine("Today's challenges (${state.today.size})")
                                    state.today.take(10).forEach { c ->
                                        val skill = c.skill ?: "Skill"
                                        val diff = c.difficulty?.let { " [$it]" } ?: ""
                                        val mark = when (c.is_correct) { true -> " ✓"; false -> " ✗"; else -> "" }
                                        appendLine("- $skill$diff$mark")
                                    }
                                    appendLine()
                                }
                                if (state.history.isNotEmpty()) {
                                    appendLine("Recent history (${state.history.size})")
                                    state.history.take(10).forEach { c ->
                                        val skill = c.skill ?: "Skill"
                                        val mark = when (c.is_correct) { true -> " ✓"; false -> " ✗"; else -> "" }
                                        appendLine("- $skill$mark")
                                    }
                                }
                            }.trimEnd()
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, "My HireStack learning progress")
                                putExtra(android.content.Intent.EXTRA_TEXT, report)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share learning progress"),
                                )
                            }
                        }) {
                            Icon(Icons.Outlined.Share, contentDescription = "Share learning progress")
                        }
                    }
                },
            )
        },
    ) { padding ->
        BrandBackground {
            Box(modifier = Modifier.fillMaxSize().padding(padding)) {
                PullToRefreshBox(
                    isRefreshing = state.isLoading && state.streak != null,
                    onRefresh = { haptic.tap(); vm.refresh() },
                    modifier = Modifier.fillMaxSize(),
                ) {
                    when {
                        state.isLoading && state.streak == null -> SkeletonList(rows = 5)
                        state.error != null && state.streak == null -> Column(Modifier.padding(20.dp)) {
                            InlineBanner(state.error!!, tone = PillTone.Danger)
                            Spacer(Modifier.height(12.dp))
                            HireStackPrimaryButton("Retry", onClick = { vm.refresh() })
                        }
                        else -> LazyColumn(
                            modifier = Modifier.fillMaxSize(),
                            contentPadding = PaddingValues(20.dp),
                            verticalArrangement = Arrangement.spacedBy(12.dp),
                        ) {
                            item { StreakCard(state) }
                            item {
                                Text("Today", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                            }
                            if (state.today.isEmpty()) {
                                item {
                                    Text(
                                        "No challenges queued. Today's set will appear here once generated.",
                                        style = MaterialTheme.typography.bodyMedium,
                                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                                    )
                                }
                            } else {
                                items(state.today, key = { "today-${it.id}" }) { ChallengeCard(it) }
                            }
                            if (state.history.isNotEmpty()) {
                                item {
                                    Spacer(Modifier.height(8.dp))
                                    Text("History", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                                }
                                items(state.history, key = { "hist-${it.id}" }) { ChallengeCard(it) }
                            }
                        }
                    }
                }
            }
        }
    }
}

@Composable
private fun StreakCard(s: LearningState) {
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Column(modifier = Modifier.weight(1f)) {
                Text("Current streak", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    "${s.streak?.current_streak ?: 0} days",
                    style = MaterialTheme.typography.headlineMedium,
                    fontWeight = FontWeight.Bold,
                    color = Brand.Amber,
                )
            }
            Column(horizontalAlignment = Alignment.End) {
                Text("Longest", style = MaterialTheme.typography.bodySmall, color = MaterialTheme.colorScheme.onSurfaceVariant)
                Text(
                    "${s.streak?.longest_streak ?: 0}",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    "${s.streak?.total_correct ?: 0}/${s.streak?.total_challenges ?: 0} correct",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ChallengeCard(c: LearningChallenge) {
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
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                c.skill?.let { StatusPill(text = it, tone = PillTone.Brand) }
                c.difficulty?.let { StatusPill(text = it, tone = PillTone.Neutral) }
            }
            Spacer(Modifier.height(8.dp))
            val questionText = c.question ?: "(no question)"
            Text(
                questionText,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = { if (c.question != null) copy(questionText, "question") },
                ),
            )
            c.user_answer?.let {
                Spacer(Modifier.height(8.dp))
                Text("Your answer", style = MaterialTheme.typography.labelLarge)
                Text(
                    it,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(it, "answer") },
                    ),
                )
            }
            c.score?.let {
                Spacer(Modifier.height(6.dp))
                Text(
                    "Score: ${it.toInt()}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (c.is_correct == true) Brand.Emerald else Brand.Danger,
                    fontWeight = FontWeight.SemiBold,
                )
            }
        }
    }
}
