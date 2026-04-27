package com.hirestack.ai.ui.more

import androidx.compose.foundation.layout.Arrangement
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
import androidx.compose.foundation.background
import androidx.compose.foundation.combinedClickable
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.outlined.Chat
import androidx.compose.material.icons.automirrored.outlined.LibraryBooks
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.Bolt
import androidx.compose.material.icons.outlined.Bookmarks
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.Language
import androidx.compose.material.icons.outlined.MicNone
import androidx.compose.material.icons.outlined.Money
import androidx.compose.material.icons.outlined.PeopleAlt
import androidx.compose.material.icons.outlined.School
import androidx.compose.material.icons.outlined.Style
import androidx.compose.material.icons.outlined.Work
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.input.nestedscroll.nestedScroll
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import com.hirestack.ai.ui.auth.AuthViewModel
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.GradientHeroCard
import com.hirestack.ai.ui.components.HireStackSecondaryButton
import com.hirestack.ai.ui.components.NavListItem
import com.hirestack.ai.ui.components.SectionHeader
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.theme.BrandGradient
import kotlinx.coroutines.launch

@OptIn(androidx.compose.material3.ExperimentalMaterial3Api::class)
@Composable
fun MoreScreen(
    authVm: AuthViewModel,
    onLoggedOut: () -> Unit,
    onOpenAccount: () -> Unit,
    onOpenEvidence: () -> Unit,
    onOpenBenchmark: () -> Unit,
    onOpenBuilder: () -> Unit,
    onOpenConsultant: () -> Unit,
    onOpenExports: () -> Unit,
    onOpenJobs: () -> Unit,
    onOpenProfiles: () -> Unit,
    onOpenAts: () -> Unit,
    onOpenDocs: () -> Unit,
    onOpenCandidates: () -> Unit,
    onOpenInterviews: () -> Unit,
    onOpenCareer: () -> Unit,
    onOpenLearning: () -> Unit,
    onOpenSalary: () -> Unit,
    onOpenVariants: () -> Unit,
    onOpenKnowledge: () -> Unit,
) {
    val auth by authVm.state.collectAsState()
    val scrollBehavior = androidx.compose.material3.TopAppBarDefaults.enterAlwaysScrollBehavior()

    Scaffold(
        modifier = Modifier.nestedScroll(scrollBehavior.nestedScrollConnection),
        topBar = { BrandTopBar(title = "More", subtitle = "Everything HireStack", scrollBehavior = scrollBehavior) },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    GradientHeroCard(brush = BrandGradient.HeroDark, onClick = onOpenAccount) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            androidx.compose.foundation.layout.Box(
                                Modifier
                                    .size(48.dp)
                                    .background(Color.White.copy(alpha = 0.18f), CircleShape),
                                contentAlignment = Alignment.Center,
                            ) { Icon(Icons.Outlined.Badge, null, tint = Color.White) }
                            Spacer(Modifier.width(14.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    auth.email ?: "Account",
                                    color = Color.White,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Text(
                                    "Tap to manage profile, billing, members",
                                    color = Color.White.copy(alpha = 0.78f),
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                            }
                        }
                    }
                }

                item { SectionHeader(title = "Studio") }
                item {
                    SoftCard {
                        Column {
                            NavListItem(title = "Benchmark", subtitle = "Score a JD", icon = Icons.Outlined.Insights, onClick = onOpenBenchmark)
                            NavListItem(title = "Builder", subtitle = "Generate tailored docs", icon = Icons.Outlined.AutoAwesome, onClick = onOpenBuilder)
                            NavListItem(title = "Consultant", subtitle = "Coach + roadmaps", icon = Icons.AutoMirrored.Outlined.Chat, onClick = onOpenConsultant)
                            NavListItem(title = "Evidence", subtitle = "Your wins library", icon = Icons.Outlined.Bookmarks, onClick = onOpenEvidence)
                            NavListItem(title = "Exports", subtitle = "PDFs & DOCX", icon = Icons.Outlined.Download, onClick = onOpenExports)
                        }
                    }
                }

                item { SectionHeader(title = "Workspace") }
                item {
                    SoftCard {
                        Column {
                            NavListItem(title = "Jobs", icon = Icons.Outlined.Work, onClick = onOpenJobs)
                            NavListItem(title = "Profiles", icon = Icons.Outlined.PeopleAlt, onClick = onOpenProfiles)
                            NavListItem(title = "ATS", icon = Icons.Outlined.Bolt, onClick = onOpenAts)
                            NavListItem(title = "Docs", icon = Icons.AutoMirrored.Outlined.LibraryBooks, onClick = onOpenDocs)
                            NavListItem(title = "Variants", icon = Icons.Outlined.Style, onClick = onOpenVariants)
                            NavListItem(title = "Knowledge", icon = Icons.AutoMirrored.Outlined.LibraryBooks, onClick = onOpenKnowledge)
                        }
                    }
                }

                item { SectionHeader(title = "Career") }
                item {
                    SoftCard {
                        Column {
                            NavListItem(title = "Candidates", icon = Icons.Outlined.PeopleAlt, onClick = onOpenCandidates)
                            NavListItem(title = "Interviews", icon = Icons.Outlined.MicNone, onClick = onOpenInterviews)
                            NavListItem(title = "Career", icon = Icons.Outlined.Language, onClick = onOpenCareer)
                            NavListItem(title = "Learning", icon = Icons.Outlined.School, onClick = onOpenLearning)
                            NavListItem(title = "Salary", icon = Icons.Outlined.Money, onClick = onOpenSalary)
                        }
                    }
                }

                item {
                    var confirmSignOut by remember { mutableStateOf(false) }
                    val signOutHaptic = androidx.compose.ui.platform.LocalHapticFeedback.current
                    HireStackSecondaryButton(
                        label = "Sign out",
                        onClick = { confirmSignOut = true },
                        modifier = Modifier.fillMaxWidth(),
                    )
                    if (confirmSignOut) {
                        androidx.compose.material3.AlertDialog(
                            onDismissRequest = { confirmSignOut = false },
                            title = { Text("Sign out?") },
                            text = { Text("You'll need to sign in again to access your account.") },
                            confirmButton = {
                                androidx.compose.material3.TextButton(onClick = {
                                    confirmSignOut = false
                                    signOutHaptic.confirm()
                                    authVm.logout(onLoggedOut)
                                }) { Text("Sign out") }
                            },
                            dismissButton = {
                                androidx.compose.material3.TextButton(onClick = { confirmSignOut = false }) { Text("Cancel") }
                            },
                        )
                    }
                }

                item { SectionHeader(title = "Appearance") }
                item {
                    SoftCard {
                        Column {
                            val themeMode = com.hirestack.ai.ui.theme.LocalThemeMode.current
                            Text(
                                "Theme",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold,
                                modifier = Modifier.padding(bottom = 8.dp),
                            )
                            Row(
                                modifier = Modifier.fillMaxWidth(),
                                horizontalArrangement = Arrangement.spacedBy(8.dp),
                            ) {
                                com.hirestack.ai.ui.theme.ThemeMode.values().forEach { mode ->
                                    androidx.compose.material3.FilterChip(
                                        selected = themeMode.value == mode,
                                        onClick = { themeMode.value = mode },
                                        label = { Text(mode.name) },
                                        modifier = Modifier.weight(1f),
                                        colors = androidx.compose.material3.FilterChipDefaults.filterChipColors(
                                            selectedContainerColor = Brand.Indigo.copy(alpha = 0.20f),
                                        ),
                                    )
                                }
                            }
                        }
                    }
                }

                item {
                    Spacer(Modifier.height(8.dp))
                    val versionLine = "HireStack AI v${com.hirestack.ai.BuildConfig.VERSION_NAME} (${com.hirestack.ai.BuildConfig.BUILD_TYPE})"
                    val versionClipboard = androidx.compose.ui.platform.LocalClipboardManager.current
                    val versionSnackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
                    val versionScope = com.hirestack.ai.ui.components.LocalAppScope.current
                    val versionHaptic = androidx.compose.ui.platform.LocalHapticFeedback.current
                    @OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
                    Text(
                        versionLine,
                        style = MaterialTheme.typography.bodySmall,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier
                            .fillMaxWidth()
                            .combinedClickable(
                                onClick = {},
                                onLongClick = {
                                    versionClipboard.setText(androidx.compose.ui.text.AnnotatedString(versionLine))
                                    versionHaptic.confirm()
                                    versionScope.launch { versionSnackbar.showSnackbar("Copied version info") }
                                },
                            ),
                    )
                }

                item { Spacer(Modifier.height(16.dp)) }
            }
        }
    }
}
