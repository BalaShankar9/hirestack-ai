package com.hirestack.ai.ui.profile

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hirestack.ai.ui.auth.AuthViewModel

@Composable
fun ProfileScreen(
    vm: AuthViewModel,
    onLoggedOut: () -> Unit,
) {
    val state by vm.state.collectAsState()

    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        Text(
            "Profile",
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
            "Coming next",
            style = MaterialTheme.typography.titleMedium,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(8.dp))
        listOf(
            "Tier 3 — Resume profiles, ATS scanner, document library",
            "Tier 4 — Pipeline, candidates, interview coach",
            "Tier 5 — Career analytics, learning, salary",
            "Tier 6 — Nexus, variants, knowledge",
            "Tier 7 — Polish + signed APK",
        ).forEach {
            Text(
                "• $it",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
                modifier = Modifier.padding(vertical = 2.dp),
            )
        }

        Spacer(Modifier.height(28.dp))
        OutlinedButton(
            onClick = { vm.logout(onLoggedOut) },
            modifier = Modifier.fillMaxWidth(),
        ) {
            Text("Sign out")
        }
    }
}
