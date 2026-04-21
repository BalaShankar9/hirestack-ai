package com.hirestack.ai.ui.auth

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.auth.SupabaseAuthClient
import com.hirestack.ai.data.auth.TokenStore
import com.hirestack.ai.data.network.HireStackApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AuthState(
    val isLoading: Boolean = false,
    val isAuthenticated: Boolean = false,
    val email: String? = null,
    val displayName: String? = null,
    val error: String? = null,
)

@HiltViewModel
class AuthViewModel @Inject constructor(
    private val supabase: SupabaseAuthClient,
    private val tokenStore: TokenStore,
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(AuthState())
    val state: StateFlow<AuthState> = _state.asStateFlow()

    init { restoreSession() }

    private fun restoreSession() = viewModelScope.launch {
        val token = tokenStore.snapshotAccess()
        val email = tokenStore.email.first()
        if (!token.isNullOrEmpty()) {
            _state.value = AuthState(isAuthenticated = true, email = email)
            // Best-effort verify in background
            runCatching { api.verify() }.onFailure {
                // token may be stale — leave session optimistic for now
            }
        }
    }

    fun login(email: String, password: String, onDone: (Boolean) -> Unit) =
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            runCatching { supabase.signIn(email.trim(), password) }
                .onSuccess {
                    _state.value = AuthState(isAuthenticated = true, email = email.trim())
                    onDone(true)
                }
                .onFailure { e ->
                    _state.value = AuthState(error = e.message ?: "Login failed")
                    onDone(false)
                }
        }

    fun signUp(email: String, password: String, fullName: String?, onDone: (Boolean) -> Unit) =
        viewModelScope.launch {
            _state.value = _state.value.copy(isLoading = true, error = null)
            runCatching { supabase.signUp(email.trim(), password, fullName?.trim()) }
                .onSuccess {
                    val token = tokenStore.snapshotAccess()
                    if (!token.isNullOrEmpty()) {
                        _state.value = AuthState(isAuthenticated = true, email = email.trim())
                        onDone(true)
                    } else {
                        // Email-confirm flow — no session yet
                        _state.value = AuthState(
                            error = "Check your email to confirm before signing in."
                        )
                        onDone(false)
                    }
                }
                .onFailure { e ->
                    _state.value = AuthState(error = e.message ?: "Sign up failed")
                    onDone(false)
                }
        }

    fun logout(onDone: () -> Unit) = viewModelScope.launch {
        supabase.signOut()
        _state.value = AuthState()
        onDone()
    }

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }
}
