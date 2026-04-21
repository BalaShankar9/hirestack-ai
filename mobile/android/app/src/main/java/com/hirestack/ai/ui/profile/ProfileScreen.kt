package com.hirestack.ai.ui.profile

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.KeyboardArrowRight
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hirestack.ai.ui.auth.AuthViewModel

@Composable
fun ProfileScreen(
    vm: AuthViewModel,
    onLoggedOut: () -> Unit,
    onOpenProfiles: () -> Unit,
    onOpenAts: () -> Unit,
    onOpenDocs: () -> Unit,
    onOpenCandidates: () -> Unit,
    onOpenInterviews: () -> Unit,
) {
    val state by vm.state.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        Text(
            "More",
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(16.dp))

        Card(modifier = Modifier.fillMaxWidth()) {
            Column(modifier = Modifier.padding(20.dp)) {
                Text(
                    state.displayName ?: state.email ?: "Signed in",
                    style = MaterialTheme.typography.titleLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                state.email?.let {
                    Spacer(Modifier.height(4.dp))
                    Text(
                        it,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }

        Spacer(Modifier.height(20.dp))
        Text(
            "Workspace",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(8.dp))

        NavRow("Resume profiles", "Manage parsed resumes & primary profile", onOpenProfiles)
        Spacer(Modifier.height(8.dp))
        NavRow("ATS Scanner", "Score documents against any JD", onOpenAts)
        Spacer(Modifier.height(8.dp))
        NavRow("Document library", "Benchmark, fixed and tailored docs", onOpenDocs)
        Spacer(Modifier.height(8.dp))
        NavRow("Candidates", "Recruiter pipeline (requires org)", onOpenCandidates)
        Spacer(Modifier.height(8.dp))
        NavRow("Interview Coach", "Practice sessions with feedback", onOpenInterviews)

        Spacer(Modifier.height(28.dp))
        OutlinedButton(
            onClick = { vm.logout(onLoggedOut) },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Sign out")
        }
    }
}

@Composable
private fun NavRow(title: String, subtitle: String, onClick: () -> Unit) {
    Card(
        modifier = Modifier.fillMaxWidth().clickable(onClick = onClick),
    ) {
        Row(
            modifier = Modifier.padding(16.dp),
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Column(modifier = Modifier.weight(1f)) {
                Text(title, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                Spacer(Modifier.height(2.dp))
                Text(
                    subtitle,
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            Icon(
                Icons.AutoMirrored.Filled.KeyboardArrowRight,
                contentDescription = null,
                tint = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
