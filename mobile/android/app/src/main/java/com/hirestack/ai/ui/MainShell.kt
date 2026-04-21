package com.hirestack.ai.ui

import androidx.compose.foundation.layout.padding
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Dashboard
import androidx.compose.material.icons.filled.Person
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
import com.hirestack.ai.ui.auth.AuthViewModel
import com.hirestack.ai.ui.dashboard.DashboardScreen
import com.hirestack.ai.ui.jobs.AddJobScreen
import com.hirestack.ai.ui.jobs.JobBoardScreen
import com.hirestack.ai.ui.jobs.JobDetailScreen
import com.hirestack.ai.ui.profile.ProfileScreen

object MainRoutes {
    const val DASHBOARD = "main/dashboard"
    const val JOBS = "main/jobs"
    const val PROFILE = "main/profile"
    const val JOB_DETAIL = "main/jobs/{jobId}"
    const val ADD_JOB = "main/jobs/new"

    fun jobDetail(id: String) = "main/jobs/$id"
}

private data class TabSpec(val route: String, val label: String, val icon: ImageVector)

private val tabs = listOf(
    TabSpec(MainRoutes.DASHBOARD, "Dashboard", Icons.Default.Dashboard),
    TabSpec(MainRoutes.JOBS, "Jobs", Icons.Default.Work),
    TabSpec(MainRoutes.PROFILE, "Profile", Icons.Default.Person),
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
            composable(MainRoutes.PROFILE) {
                ProfileScreen(vm = authVm, onLoggedOut = onLoggedOut)
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
        }
    }
}
