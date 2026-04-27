package com.hirestack.ai.ui

import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.size
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.outlined.Apps
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.MoreHoriz
import androidx.compose.material.icons.outlined.Widgets
import androidx.compose.material3.FloatingActionButton
import androidx.compose.material3.FloatingActionButtonDefaults
import androidx.compose.material3.Icon
import androidx.compose.material3.NavigationBar
import androidx.compose.material3.NavigationBarItem
import androidx.compose.material3.NavigationBarItemDefaults
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SnackbarHost
import androidx.compose.material3.SnackbarHostState
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.runtime.getValue
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavGraph.Companion.findStartDestination
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.currentBackStackEntryAsState
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.hirestack.ai.ui.account.AccountScreen
import com.hirestack.ai.ui.account.ApiKeysScreen
import com.hirestack.ai.ui.account.AuditScreen
import com.hirestack.ai.ui.account.BillingScreen
import com.hirestack.ai.ui.account.ExportScreen
import com.hirestack.ai.ui.account.MembersScreen
import com.hirestack.ai.ui.applications.ApplicationWorkspaceScreen
import com.hirestack.ai.ui.applications.ApplicationsScreen
import com.hirestack.ai.ui.applications.DocumentViewerScreen
import com.hirestack.ai.ui.applications.NewApplicationScreen
import com.hirestack.ai.ui.ats.AtsScreen
import com.hirestack.ai.ui.auth.AuthViewModel
import com.hirestack.ai.ui.candidates.CandidatesScreen
import com.hirestack.ai.ui.career.CareerScreen
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.dashboard.DashboardScreen
import com.hirestack.ai.ui.docs.DocsScreen
import com.hirestack.ai.ui.evidence.EvidenceScreen
import com.hirestack.ai.ui.insights.InsightsScreen
import com.hirestack.ai.ui.interview.InterviewDetailScreen
import com.hirestack.ai.ui.interview.InterviewListScreen
import com.hirestack.ai.ui.jobs.AddJobScreen
import com.hirestack.ai.ui.jobs.JobBoardScreen
import com.hirestack.ai.ui.jobs.JobDetailScreen
import com.hirestack.ai.ui.knowledge.KnowledgeScreen
import com.hirestack.ai.ui.learning.LearningScreen
import com.hirestack.ai.ui.more.MoreScreen
import com.hirestack.ai.ui.profiles.ProfilesScreen
import com.hirestack.ai.ui.salary.SalaryScreen
import com.hirestack.ai.ui.studio.BenchmarkScreen
import com.hirestack.ai.ui.studio.BuilderScreen
import com.hirestack.ai.ui.studio.ConsultantScreen
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.variants.VariantsScreen
import java.net.URLDecoder
import java.net.URLEncoder

object MainRoutes {
    const val HOME = "main/home"
    const val APPS = "main/apps"
    const val INSIGHTS = "main/insights"
    const val MORE = "main/more"

    const val NEW_APP = "main/apps/new"
    const val APP_WORKSPACE = "main/apps/{appId}"
    const val DOC_VIEWER = "main/doc/{title}/{html}"

    const val BENCHMARK = "main/studio/benchmark"
    const val BUILDER = "main/studio/builder"
    const val CONSULTANT = "main/studio/consultant"
    const val EVIDENCE = "main/studio/evidence"
    const val EXPORTS = "main/studio/exports"

    const val ACCOUNT = "main/account"
    const val BILLING = "main/account/billing"
    const val MEMBERS = "main/account/members"
    const val API_KEYS = "main/account/apikeys"
    const val AUDIT = "main/account/audit"

    const val JOBS = "main/jobs"
    const val ADD_JOB = "main/jobs/new"
    const val JOB_DETAIL = "main/jobs/{jobId}"
    const val PROFILES = "main/profiles"
    const val ATS = "main/ats"
    const val DOCS = "main/docs"
    const val CANDIDATES = "main/candidates"
    const val INTERVIEWS = "main/interviews"
    const val INTERVIEW_DETAIL = "main/interviews/{sessionId}"
    const val CAREER = "main/career"
    const val LEARNING = "main/learning"
    const val SALARY = "main/salary"
    const val VARIANTS = "main/variants"
    const val KNOWLEDGE = "main/knowledge"

    fun appWorkspace(id: String) = "main/apps/$id"
    fun docViewer(title: String, html: String): String {
        val t = URLEncoder.encode(title, "UTF-8")
        val h = URLEncoder.encode(html.ifEmpty { "<p>Empty</p>" }, "UTF-8")
        return "main/doc/$t/$h"
    }
    fun jobDetail(id: String) = "main/jobs/$id"
    fun interviewDetail(id: String) = "main/interviews/$id"
}

private data class TabSpec(val route: String, val label: String, val icon: ImageVector)

private val bottomTabs = listOf(
    TabSpec(MainRoutes.HOME, "Home", Icons.Outlined.Widgets),
    TabSpec(MainRoutes.APPS, "Apps", Icons.Outlined.Apps),
    TabSpec(MainRoutes.INSIGHTS, "Insights", Icons.Outlined.Insights),
    TabSpec(MainRoutes.MORE, "More", Icons.Outlined.MoreHoriz),
)

@Composable
fun MainShell(
    authVm: AuthViewModel,
    onLoggedOut: () -> Unit,
    initialDeepLink: String? = null,
) {
    val nav: NavHostController = rememberNavController()
    val backStack by nav.currentBackStackEntryAsState()
    val currentRoute = backStack?.destination?.route
    val snackbarHost = remember { SnackbarHostState() }
    val appScope = rememberCoroutineScope()

    val showBottomBar = currentRoute in bottomTabs.map { it.route }

    val signOutCtx = androidx.compose.ui.platform.LocalContext.current
    val onLoggedOutWithToast: () -> Unit = {
        android.widget.Toast.makeText(signOutCtx, "Signed out", android.widget.Toast.LENGTH_SHORT).show()
        onLoggedOut()
    }

    androidx.compose.runtime.LaunchedEffect(initialDeepLink) {
        when (initialDeepLink) {
            "add-job" -> nav.navigate(MainRoutes.ADD_JOB)
            "ats" -> nav.navigate(MainRoutes.ATS)
            "interview" -> nav.navigate(MainRoutes.INTERVIEWS)
        }
    }

    fun goTab(route: String) {
        if (currentRoute == route) return
        nav.navigate(route) {
            popUpTo(nav.graph.findStartDestination().id) { saveState = true }
            launchSingleTop = true
            restoreState = true
        }
    }

    CompositionLocalProvider(
        LocalSnackbar provides snackbarHost,
        LocalAppScope provides appScope,
    ) {
    Scaffold(
        snackbarHost = { SnackbarHost(snackbarHost, modifier = Modifier.imePadding()) },
        bottomBar = {
            if (showBottomBar) {
                NavigationBar(containerColor = Color.Transparent) {
                    bottomTabs.take(2).forEach { tab ->
                        NavigationBarItem(
                            selected = currentRoute == tab.route,
                            onClick = { goTab(tab.route) },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = Brand.Indigo,
                                selectedTextColor = Brand.Indigo,
                                indicatorColor = Brand.Indigo.copy(alpha = 0.16f),
                            ),
                        )
                    }
                    NavigationBarItem(
                        selected = false,
                        onClick = { nav.navigate(MainRoutes.NEW_APP) },
                        icon = {
                            FloatingActionButton(
                                onClick = { nav.navigate(MainRoutes.NEW_APP) },
                                containerColor = Brand.Indigo,
                                contentColor = Color.White,
                                elevation = FloatingActionButtonDefaults.elevation(0.dp, 0.dp),
                                modifier = Modifier.size(48.dp),
                            ) { Icon(Icons.Filled.Add, contentDescription = "New application") }
                        },
                        label = { Spacer(Modifier.size(0.dp)) },
                    )
                    bottomTabs.drop(2).forEach { tab ->
                        NavigationBarItem(
                            selected = currentRoute == tab.route,
                            onClick = { goTab(tab.route) },
                            icon = { Icon(tab.icon, contentDescription = tab.label) },
                            label = { Text(tab.label) },
                            colors = NavigationBarItemDefaults.colors(
                                selectedIconColor = Brand.Indigo,
                                selectedTextColor = Brand.Indigo,
                                indicatorColor = Brand.Indigo.copy(alpha = 0.16f),
                            ),
                        )
                    }
                }
            }
        },
    ) { padding ->
        androidx.compose.foundation.layout.Column(modifier = Modifier.padding(padding).imePadding()) {
            com.hirestack.ai.ui.components.OfflineBanner()
        NavHost(
            navController = nav,
            startDestination = MainRoutes.HOME,
            enterTransition = {
                androidx.compose.animation.slideInHorizontally(
                    initialOffsetX = { it / 6 },
                    animationSpec = androidx.compose.animation.core.tween(220),
                ) + androidx.compose.animation.fadeIn(animationSpec = androidx.compose.animation.core.tween(220))
            },
            exitTransition = {
                androidx.compose.animation.fadeOut(animationSpec = androidx.compose.animation.core.tween(180))
            },
            popEnterTransition = {
                androidx.compose.animation.slideInHorizontally(
                    initialOffsetX = { -it / 6 },
                    animationSpec = androidx.compose.animation.core.tween(220),
                ) + androidx.compose.animation.fadeIn(animationSpec = androidx.compose.animation.core.tween(220))
            },
            popExitTransition = {
                androidx.compose.animation.slideOutHorizontally(
                    targetOffsetX = { it / 6 },
                    animationSpec = androidx.compose.animation.core.tween(220),
                ) + androidx.compose.animation.fadeOut(animationSpec = androidx.compose.animation.core.tween(220))
            },
        ) {
            composable(MainRoutes.HOME) {
                DashboardScreen(
                    onNewApplication = { nav.navigate(MainRoutes.NEW_APP) },
                    onOpenJobs = { nav.navigate(MainRoutes.JOBS) },
                    onOpenProfiles = { nav.navigate(MainRoutes.PROFILES) },
                    onOpenInterviews = { nav.navigate(MainRoutes.INTERVIEWS) },
                    onOpenBenchmark = { nav.navigate(MainRoutes.BENCHMARK) },
                    onOpenEvidence = { nav.navigate(MainRoutes.EVIDENCE) },
                    onOpenSalary = { nav.navigate(MainRoutes.SALARY) },
                    authVm = authVm,
                )
            }
            composable(MainRoutes.APPS) {
                ApplicationsScreen(
                    onCreate = { nav.navigate(MainRoutes.NEW_APP) },
                    onOpen = { id -> nav.navigate(MainRoutes.appWorkspace(id)) },
                )
            }
            composable(MainRoutes.INSIGHTS) { InsightsScreen() }
            composable(MainRoutes.MORE) {
                MoreScreen(
                    authVm = authVm,
                    onLoggedOut = onLoggedOutWithToast,
                    onOpenAccount = { nav.navigate(MainRoutes.ACCOUNT) },
                    onOpenEvidence = { nav.navigate(MainRoutes.EVIDENCE) },
                    onOpenBenchmark = { nav.navigate(MainRoutes.BENCHMARK) },
                    onOpenBuilder = { nav.navigate(MainRoutes.BUILDER) },
                    onOpenConsultant = { nav.navigate(MainRoutes.CONSULTANT) },
                    onOpenExports = { nav.navigate(MainRoutes.EXPORTS) },
                    onOpenJobs = { nav.navigate(MainRoutes.JOBS) },
                    onOpenProfiles = { nav.navigate(MainRoutes.PROFILES) },
                    onOpenAts = { nav.navigate(MainRoutes.ATS) },
                    onOpenDocs = { nav.navigate(MainRoutes.DOCS) },
                    onOpenCandidates = { nav.navigate(MainRoutes.CANDIDATES) },
                    onOpenInterviews = { nav.navigate(MainRoutes.INTERVIEWS) },
                    onOpenCareer = { nav.navigate(MainRoutes.CAREER) },
                    onOpenLearning = { nav.navigate(MainRoutes.LEARNING) },
                    onOpenSalary = { nav.navigate(MainRoutes.SALARY) },
                    onOpenVariants = { nav.navigate(MainRoutes.VARIANTS) },
                    onOpenKnowledge = { nav.navigate(MainRoutes.KNOWLEDGE) },
                )
            }

            composable(MainRoutes.NEW_APP) {
                NewApplicationScreen(
                    onClose = { nav.popBackStack() },
                    onLaunched = { id ->
                        nav.popBackStack()
                        nav.navigate(MainRoutes.appWorkspace(id))
                    },
                )
            }
            composable(
                route = MainRoutes.APP_WORKSPACE,
                arguments = listOf(navArgument("appId") { type = NavType.StringType }),
            ) { entry ->
                val appId = entry.arguments?.getString("appId") ?: ""
                ApplicationWorkspaceScreen(
                    applicationId = appId,
                    onClose = { nav.popBackStack() },
                    onOpenDocument = { title, html ->
                        nav.navigate(MainRoutes.docViewer(title, html))
                    },
                )
            }
            composable(
                route = MainRoutes.DOC_VIEWER,
                arguments = listOf(
                    navArgument("title") { type = NavType.StringType },
                    navArgument("html") { type = NavType.StringType },
                ),
            ) { entry ->
                val title = URLDecoder.decode(entry.arguments?.getString("title") ?: "", "UTF-8")
                val html = URLDecoder.decode(entry.arguments?.getString("html") ?: "", "UTF-8")
                DocumentViewerScreen(
                    title = title,
                    html = html,
                    onClose = { nav.popBackStack() },
                )
            }

            composable(MainRoutes.BENCHMARK) { BenchmarkScreen() }
            composable(MainRoutes.BUILDER) {
                BuilderScreen(onOpenDocument = { title, html ->
                    nav.navigate(MainRoutes.docViewer(title, html))
                })
            }
            composable(MainRoutes.CONSULTANT) { ConsultantScreen() }
            composable(MainRoutes.EVIDENCE) { EvidenceScreen() }
            composable(MainRoutes.EXPORTS) { ExportScreen() }

            composable(MainRoutes.ACCOUNT) {
                AccountScreen(
                    onOpenBilling = { nav.navigate(MainRoutes.BILLING) },
                    onOpenMembers = { nav.navigate(MainRoutes.MEMBERS) },
                    onOpenApiKeys = { nav.navigate(MainRoutes.API_KEYS) },
                    onOpenAudit = { nav.navigate(MainRoutes.AUDIT) },
                    onOpenExports = { nav.navigate(MainRoutes.EXPORTS) },
                    onSignOut = { authVm.logout(onLoggedOutWithToast) },
                )
            }
            composable(MainRoutes.BILLING) { BillingScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.MEMBERS) { MembersScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.API_KEYS) { ApiKeysScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.AUDIT) { AuditScreen(onBack = { nav.popBackStack() }) }

            composable(MainRoutes.JOBS) {
                val vm: com.hirestack.ai.ui.jobs.JobBoardViewModel = hiltViewModel(it)
                JobBoardScreen(
                    onJobClick = { id -> nav.navigate(MainRoutes.jobDetail(id)) },
                    onAddJob = { nav.navigate(MainRoutes.ADD_JOB) },
                    vm = vm,
                )
            }
            composable(
                route = MainRoutes.JOB_DETAIL,
                arguments = listOf(navArgument("jobId") { type = NavType.StringType }),
            ) { JobDetailScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.ADD_JOB) {
                val parentEntry = remember(it) { nav.getBackStackEntry(MainRoutes.JOBS) }
                val vm: com.hirestack.ai.ui.jobs.JobBoardViewModel = hiltViewModel(parentEntry)
                AddJobScreen(
                    onBack = { nav.popBackStack() },
                    onCreated = { id ->
                        nav.popBackStack()
                        nav.navigate(MainRoutes.jobDetail(id))
                    },
                    vm = vm,
                )
            }
            composable(MainRoutes.PROFILES) { ProfilesScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.ATS) { AtsScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.DOCS) { DocsScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.CANDIDATES) { CandidatesScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.INTERVIEWS) {
                InterviewListScreen(
                    onBack = { nav.popBackStack() },
                    onSessionClick = { id -> nav.navigate(MainRoutes.interviewDetail(id)) },
                )
            }
            composable(
                route = MainRoutes.INTERVIEW_DETAIL,
                arguments = listOf(navArgument("sessionId") { type = NavType.StringType }),
            ) { InterviewDetailScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.CAREER) { CareerScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.LEARNING) { LearningScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.SALARY) { SalaryScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.VARIANTS) { VariantsScreen(onBack = { nav.popBackStack() }) }
            composable(MainRoutes.KNOWLEDGE) { KnowledgeScreen(onBack = { nav.popBackStack() }) }
        }
        }
    }
    }
}
