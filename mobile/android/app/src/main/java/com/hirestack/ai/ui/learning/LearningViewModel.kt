package com.hirestack.ai.ui.learning

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.LearningChallenge
import com.hirestack.ai.data.network.LearningStreak
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class LearningState(
    val isLoading: Boolean = true,
    val streak: LearningStreak? = null,
    val today: List<LearningChallenge> = emptyList(),
    val history: List<LearningChallenge> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class LearningViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(LearningState())
    val state: StateFlow<LearningState> = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                coroutineScope {
                    val s = async { runCatching { api.learningStreak() }.getOrNull() }
                    val t = async { runCatching { api.learningToday() }.getOrDefault(emptyList()) }
                    val h = async { runCatching { api.learningHistory(limit = 50) }.getOrDefault(emptyList()) }
                    _state.value = LearningState(
                        isLoading = false,
                        streak = s.await(),
                        today = t.await(),
                        history = h.await(),
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load learning data",
                )
            }
        }
    }
}
