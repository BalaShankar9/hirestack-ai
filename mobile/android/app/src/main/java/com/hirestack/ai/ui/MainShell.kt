package com.hirestack.ai.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material.icons.filled.Work
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.hirestack.ai.ui.ats.AtsScreen
import com.hirestack.ai.ui.auth.AuthViewModel
import com.hirestack.ai.ui.candidates.CandidatesScreen
import com.hirestack.ai.ui.dashboard.DashboardScreen
import com.hirestack.ai.ui.docs.DocsScreen
import com.hirestack.ai.ui.interview.InterviewDetailScreen
import com.hirestack.ai.ui.interview.InterviewListScreen
import com.hirestack.ai.ui.jobs.AddJobScreen
import com.hirestack.ai.ui.jobs.JobBoardScreen
import com.hirestack.ai.ui.jobs.JobDetailScreen
import com.hirestack.ai.ui.profile.ProfileScreen
import com.hirestack.ai.ui.profiles.ProfilesScreen

object MainRoutes {
    const val DASHBOARD = "main/dashboard"
    const val JOBS = "main/jobs"
    const val MORE = "main/more"
    const val JOB_DETAIL = "main/jobs/{jobId}"
    const val ADD_JOB = "main/jobs/new"
    const val PROFILES = "main/more/profiles"
    const val ATS = "main/more/ats"
    const val DOCS = "main/more/docs"
    const val CANDIDATES = "main/more/candidates"
    const val INTERVIEWS = "main/more/interviews"
    const val INTERVIEW_DETAIL = "main/more/interviews/{sessionId}"

    fun jobDetail(id: String) = "main/jobs/$id"
    fun interviewDetail(id: String) = "main/more/interviews/$id"
}

private data class TabSpec(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    TabSpec(MainRoutes.DASHBOARD, "Dashboard", Icons.Default.Dashboard),
    TabSpec(MainRoutes.JOBS, "Jobs", Icons.Default.Work),
    TabSpec(MainRoutes.MORE, "More", Icons.Default.MoreHoriz),
)

@Composable
fun MainShell(
    authVm: AuthViewModel,
    onLoggedOut: () -> Unit,
) {
    val nav: NavHostController = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route

    val showBottomBar = currentRoute in tabs.map { it.route }

    Scaffold(
        bottomBar = {
            if (showBottomBar) {
                NavigationBar {
                    tabs.forEach { tab ->
                        NavigationBarItem(
                            selected = currentRoute == tab.route,
                            onClick = {
                                if (currentRoute != tab.route) {
                                    nav.navigate(tab.route) {
                                        popUpTo(nav.graph.findStartDestination().id) {
                                            saveState = true
                                        }
                                        launchSingleTop = true
                                        restoreState = true
                                    }
                                }
                            },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                        )
                    }
                }
            }
        },
    ) { padding ->
        NavHost(
            navController = nav,
            startDestination = MainRoutes.DASHBOARD,
            modifier = Modifier.padding(padding),
        ) {
            composable(MainRoutes.DASHBOARD) {
                DashboardScreen()
            }
            composable(MainRoutes.JOBS) {
                val vm: com.hirestack.ai.ui.jobs.JobBoardViewModel =
                    androidx.hilt.navigation.compose.hiltViewModel(it)
                JobBoardScreen(
                    onJobClick = { id -> nav.navigate(MainRoutes.jobDetail(id)) },
                    onAddJob = { nav.navigate(MainRoutes.ADD_JOB) },
                    vm = vm,
                )
            }
            composable(MainRoutes.MORE) {
                ProfileScreen(
                    vm = authVm,
                    onLoggedOut = onLoggedOut,
                    onOpenProfiles = { nav.navigate(MainRoutes.PROFILES) },
                    onOpenAts = { nav.navigate(MainRoutes.ATS) },
                    onOpenDocs = { nav.navigate(MainRoutes.DOCS) },
                    onOpenCandidates = { nav.navigate(MainRoutes.CANDIDATES) },
                    onOpenInterviews = { nav.navigate(MainRoutes.INTERVIEWS) },
                )
            }
            composable(
                route = MainRoutes.JOB_DETAIL,
                arguments = listOf(navArgument("jobId") { type = NavType.StringType }),
            ) {
                JobDetailScreen(onBack = { nav.popBackStack() })
            }
            composable(MainRoutes.ADD_JOB) {
                // Reuse the JobBoard VM so newly-created jobs appear in the list.
                val parentEntry = remember(it) { nav.getBackStackEntry(MainRoutes.JOBS) }
                val vm: com.hirestack.ai.ui.jobs.JobBoardViewModel =
                    androidx.hilt.navigation.compose.hiltViewModel(parentEntry)
                AddJobScreen(
                    onBack = { nav.popBackStack() },
                    onCreated = { id ->
                        nav.popBackStack()
                        nav.navigate(MainRoutes.jobDetail(id))
                    },
                    vm = vm,
                )
            }
            composable(MainRoutes.PROFILES) {
                ProfilesScreen(onBack = { nav.popBackStack() })
            }
            composable(MainRoutes.ATS) {
                AtsScreen(onBack = { nav.popBackStack() })
            }
            composable(MainRoutes.DOCS) {
                DocsScreen(onBack = { nav.popBackStack() })
            }
            composable(MainRoutes.CANDIDATES) {
                CandidatesScreen(onBack = { nav.popBackStack() })
            }
            composable(MainRoutes.INTERVIEWS) {
                InterviewListScreen(
                    onBack = { nav.popBackStack() },
                    onSessionClick = { id -> nav.navigate(MainRoutes.interviewDetail(id)) },
                )
            }
            composable(
                route = MainRoutes.INTERVIEW_DETAIL,
                arguments = listOf(navArgument("sessionId") { type = NavType.StringType }),
            ) {
                InterviewDetailScreen(onBack = { nav.popBackStack() })
            }
        }
    }
}
