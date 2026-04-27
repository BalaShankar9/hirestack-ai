package com.hirestack.ai.ui.applications

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.Application
import com.hirestack.ai.data.network.SupabaseRest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ApplicationsState(
    val isLoading: Boolean = false,
    val refreshing: Boolean = false,
    val items: List<Application> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class ApplicationsViewModel @Inject constructor(
    private val rest: SupabaseRest,
) : ViewModel() {

    private val _state = MutableStateFlow(ApplicationsState())
    val state: StateFlow<ApplicationsState> = _state.asStateFlow()

    init { load() }

    fun load() {
        if (_state.value.isLoading) return
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = rest.listApplications(limit = 100)
                _state.value = ApplicationsState(items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Couldn't load applications",
                )
            }
        }
    }

    fun refresh() {
        _state.value = _state.value.copy(refreshing = true, error = null)
        viewModelScope.launch {
            try {
                val items = rest.listApplications(limit = 100)
                _state.value = _state.value.copy(refreshing = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    refreshing = false,
                    error = e.message ?: "Refresh failed",
                )
            }
        }
    }

    fun delete(id: String) {
        viewModelScope.launch {
            runCatching { rest.deleteApplication(id) }
            _state.value = _state.value.copy(items = _state.value.items.filterNot { it.id == id })
        }
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}
