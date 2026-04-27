package com.hirestack.ai.ui

import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import com.hirestack.ai.ui.auth.AuthViewModel
import com.hirestack.ai.ui.auth.LoginScreen
import com.hirestack.ai.ui.auth.SignUpScreen

object Routes {
    const val LOGIN = "login"
    const val SIGNUP = "signup"
    const val HOME = "home"
}

@Composable
fun HireStackApp(initialDeepLink: String? = null) {
    val nav = rememberNavController()
    val authVm: AuthViewModel = hiltViewModel()
    val state by authVm.state.collectAsState()

    val start = if (state.isAuthenticated) Routes.HOME else Routes.LOGIN

    NavHost(navController = nav, startDestination = start) {
        composable(Routes.LOGIN) {
            LoginScreen(
                vm = authVm,
                onAuthenticated = {
                    nav.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onSignUpClick = { nav.navigate(Routes.SIGNUP) },
            )
        }
        composable(Routes.SIGNUP) {
            SignUpScreen(
                vm = authVm,
                onAuthenticated = {
                    nav.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                },
                onLoginClick = { nav.popBackStack() },
            )
        }
        composable(Routes.HOME) {
            MainShell(
                authVm = authVm,
                onLoggedOut = {
                    nav.navigate(Routes.LOGIN) {
                        popUpTo(Routes.HOME) { inclusive = true }
                    }
                },
                initialDeepLink = initialDeepLink,
            )
        }
    }
}
