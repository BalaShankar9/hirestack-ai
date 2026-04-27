package com.hirestack.ai.ui.interview

import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Share
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
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.InterviewAnswer
import com.hirestack.ai.data.network.InterviewQuestion
import com.hirestack.ai.data.network.InterviewSession
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.theme.Brand
import kotlinx.coroutines.launch

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InterviewDetailScreen(onBack: () -> Unit, vm: InterviewDetailViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = state.session?.job_title ?: "Session",
                subtitle = state.session?.company,
                onBack = onBack,
                actions = {
                    val s = state.session
                    if (s != null) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        androidx.compose.material3.IconButton(onClick = {
                            val transcript = buildInterviewTranscript(s)
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(
                                    android.content.Intent.EXTRA_SUBJECT,
                                    "Interview transcript: ${s.job_title ?: "session"}",
                                )
                                putExtra(android.content.Intent.EXTRA_TEXT, transcript)
                            }
                            runCatching {
                                shareCtx.startActivity(
                                    android.content.Intent.createChooser(send, "Share interview transcript"),
                                )
                            }
                        }) {
                            androidx.compose.material3.Icon(
                                Icons.Outlined.Share,
                                contentDescription = "Share transcript",
                            )
                        }
                    }
                },
            )
        },
    ) { padding ->
        BrandBackground {
            Box(modifier = Modifier.fillMaxSize().padding(padding)) {
                when {
                    state.isLoading -> Box(
                        modifier = Modifier.fillMaxSize(),
                        contentAlignment = Alignment.Center,
                    ) { CircularProgressIndicator(color = Brand.Indigo) }
                    state.error != null -> Column(Modifier.padding(20.dp)) {
                        InlineBanner(state.error!!, tone = PillTone.Danger)
                        Spacer(Modifier.height(12.dp))
                        HireStackPrimaryButton("Retry", onClick = { vm.load() })
                    }
                    state.session != null -> SessionContent(state.session!!)
                }
            }
        }
    }
}

@Composable
private fun SessionContent(s: InterviewSession) {
    val answersByQid = remember(s) { s.answers.associateBy { it.question_id } }

    LazyColumn(
        modifier = Modifier.fillMaxSize(),
        contentPadding = PaddingValues(20.dp),
        verticalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        item {
            SoftCard {
                Column {
                    Text(s.job_title ?: "Interview session", style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold)
                    val sub = listOfNotNull(s.company, s.interview_type, s.difficulty).joinToString(" • ")
                    if (sub.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(sub, style = MaterialTheme.typography.bodyMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    Spacer(Modifier.height(12.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val score = s.overall_score ?: s.average_score
                        if (score != null) {
                            Text(
                                "${score.toInt()}%",
                                style = MaterialTheme.typography.headlineMedium,
                                color = Brand.Indigo,
                                fontWeight = FontWeight.Bold,
                            )
                            Spacer(Modifier.width(12.dp))
                        }
                        s.status?.let { StatusPill(text = it, tone = PillTone.Brand) }
                    }
                }
            }
        }

        if (s.questions.isEmpty()) {
            item {
                Text(
                    "No questions captured for this session.",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
        } else {
            items(s.questions, key = { it.id ?: it.hashCode().toString() }) { q ->
                QuestionCard(q, answersByQid[q.id])
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun QuestionCard(q: InterviewQuestion, a: InterviewAnswer?) {
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
            q.category?.let {
                Text(it.uppercase(), style = MaterialTheme.typography.labelSmall, color = Brand.Indigo)
                Spacer(Modifier.height(4.dp))
            }
            val questionText = q.question ?: "(no question text)"
            Text(
                questionText,
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = { if (q.question != null) copy(questionText, "question") },
                ),
            )
            if (a != null) {
                Spacer(Modifier.height(12.dp))
                Text("Your answer", style = MaterialTheme.typography.labelLarge)
                Spacer(Modifier.height(4.dp))
                val answerText = a.answer_text ?: "(no answer)"
                Text(
                    answerText,
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { if (a.answer_text != null) copy(answerText, "answer") },
                    ),
                )
                a.score?.let {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Score: ${it.toInt()}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = Brand.Emerald,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                a.feedback?.let { fb ->
                    Spacer(Modifier.height(8.dp))
                    Text("Feedback", style = MaterialTheme.typography.labelLarge)
                    Spacer(Modifier.height(4.dp))
                    Text(
                        fb,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.combinedClickable(
                            onClick = {},
                            onLongClick = { copy(fb, "feedback") },
                        ),
                    )
                }
            }
        }
    }
}

private fun buildInterviewTranscript(s: InterviewSession): String {
    val answersByQid = s.answers.associateBy { it.question_id }
    return buildString {
        appendLine(s.job_title ?: "Interview session")
        val sub = listOfNotNull(s.company, s.interview_type, s.difficulty).joinToString(" • ")
        if (sub.isNotBlank()) appendLine(sub)
        val score = s.overall_score ?: s.average_score
        if (score != null) appendLine("Score: ${score.toInt()}%")
        appendLine()
        s.questions.forEachIndexed { idx, q ->
            appendLine("Q${idx + 1}. ${q.question ?: "(no question text)"}")
            val a = answersByQid[q.id]
            if (a != null) {
                appendLine("Answer: ${a.answer_text ?: "(no answer)"}")
                a.score?.let { appendLine("Score: ${it.toInt()}") }
                a.feedback?.let { appendLine("Feedback: $it") }
            }
            appendLine()
        }
    }.trimEnd()
}
