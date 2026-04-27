package com.hirestack.ai.ui.insights

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.DevGoal
import com.hirestack.ai.data.network.DevSummary
import com.hirestack.ai.data.network.GapReport
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.UserSkill
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class InsightsState(
    val isLoading: Boolean = true,
    val refreshing: Boolean = false,
    val summary: DevSummary? = null,
    val skills: List<UserSkill> = emptyList(),
    val goals: List<DevGoal> = emptyList(),
    val gapReports: List<GapReport> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class InsightsViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(InsightsState())
    val state: StateFlow<InsightsState> = _state.asStateFlow()

    init { load() }

    private suspend fun fetchAll(): InsightsState = coroutineScope {
        val summaryDef = async { runCatching { api.developmentSummary() }.getOrNull() }
        val skillsDef = async { runCatching { api.listUserSkills() }.getOrDefault(emptyList()) }
        val goalsDef = async { runCatching { api.listGoals() }.getOrDefault(emptyList()) }
        val gapsDef = async { runCatching { api.listGapReports() }.getOrDefault(emptyList()) }
        InsightsState(
            isLoading = false,
            summary = summaryDef.await(),
            skills = skillsDef.await(),
            goals = goalsDef.await(),
            gapReports = gapsDef.await(),
        )
    }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                _state.value = fetchAll()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Couldn't load insights",
                )
            }
        }
    }

    fun refresh() {
        _state.value = _state.value.copy(refreshing = true)
        viewModelScope.launch {
            try {
                val next = fetchAll()
                _state.value = next.copy(refreshing = false)
            } catch (e: Exception) {
                _state.value = _state.value.copy(refreshing = false, error = e.message)
            }
        }
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}
