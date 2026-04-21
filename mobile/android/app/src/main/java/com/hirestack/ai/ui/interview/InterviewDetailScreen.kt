package com.hirestack.ai.ui.interview

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
import com.hirestack.ai.data.network.InterviewAnswer
import com.hirestack.ai.data.network.InterviewQuestion
import com.hirestack.ai.data.network.InterviewSession

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun InterviewDetailScreen(
    onBack: () -> Unit,
    vm: InterviewDetailViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text(state.session?.job_title ?: "Session") },
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
                state.isLoading -> Box(
                    modifier = Modifier.fillMaxSize(),
                    contentAlignment = Alignment.Center,
                ) { CircularProgressIndicator() }
                state.error != null -> Column(modifier = Modifier.padding(24.dp)) {
                    Text("Error", style = MaterialTheme.typography.titleMedium)
                    Spacer(Modifier.height(8.dp))
                    Text(state.error!!, color = MaterialTheme.colorScheme.error)
                    Spacer(Modifier.height(16.dp))
                    Button(onClick = { vm.load() }) { Text("Retry") }
                }
                state.session != null -> SessionContent(state.session!!)
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
            Card(modifier = Modifier.fillMaxWidth()) {
                Column(modifier = Modifier.padding(16.dp)) {
                    Text(
                        s.job_title ?: "Interview session",
                        style = MaterialTheme.typography.titleLarge,
                        fontWeight = FontWeight.Bold,
                    )
                    val sub = listOfNotNull(s.company, s.interview_type, s.difficulty).joinToString(" • ")
                    if (sub.isNotBlank()) {
                        Spacer(Modifier.height(4.dp))
                        Text(
                            sub,
                            style = MaterialTheme.typography.bodyMedium,
                            color = MaterialTheme.colorScheme.onSurfaceVariant,
                        )
                    }
                    Spacer(Modifier.height(12.dp))
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        val score = s.overall_score ?: s.average_score
                        if (score != null) {
                            Text(
                                "${score.toInt()}%",
                                style = MaterialTheme.typography.headlineMedium,
                                color = MaterialTheme.colorScheme.primary,
                                fontWeight = FontWeight.Bold,
                            )
                            Spacer(Modifier.width(12.dp))
                        }
                        s.status?.let {
                            AssistChip(onClick = {}, label = { Text(it) })
                        }
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

@Composable
private fun QuestionCard(q: InterviewQuestion, a: InterviewAnswer?) {
    Card(modifier = Modifier.fillMaxWidth()) {
        Column(modifier = Modifier.padding(16.dp)) {
            q.category?.let {
                Text(it.uppercase(), style = MaterialTheme.typography.labelSmall, color = MaterialTheme.colorScheme.primary)
                Spacer(Modifier.height(4.dp))
            }
            Text(
                q.question ?: "(no question text)",
                style = MaterialTheme.typography.bodyLarge,
                fontWeight = FontWeight.SemiBold,
            )
            if (a != null) {
                Spacer(Modifier.height(12.dp))
                Text("Your answer", style = MaterialTheme.typography.labelLarge)
                Spacer(Modifier.height(4.dp))
                Text(
                    a.answer_text ?: "(no answer)",
                    style = MaterialTheme.typography.bodyMedium,
                )
                a.score?.let {
                    Spacer(Modifier.height(8.dp))
                    Text(
                        "Score: ${it.toInt()}",
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.primary,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
                a.feedback?.let {
                    Spacer(Modifier.height(8.dp))
                    Text("Feedback", style = MaterialTheme.typography.labelLarge)
                    Spacer(Modifier.height(4.dp))
                    Text(it, style = MaterialTheme.typography.bodyMedium)
                }
            }
        }
    }
}
