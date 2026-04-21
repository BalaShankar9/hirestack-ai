package com.hirestack.ai.ui.interview

import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.InterviewSession
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class InterviewListState(
    val isLoading: Boolean = false,
    val items: List<InterviewSession> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class InterviewListViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(InterviewListState(isLoading = true))
    val state: StateFlow<InterviewListState> = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listInterviewSessions()
                _state.value = _state.value.copy(isLoading = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load sessions",
                )
            }
        }
    }
}

data class InterviewDetailState(
    val isLoading: Boolean = true,
    val session: InterviewSession? = null,
    val error: String? = null,
)

@HiltViewModel
class InterviewDetailViewModel @Inject constructor(
    private val api: HireStackApi,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {
    private val sessionId: String = checkNotNull(savedStateHandle["sessionId"])
    private val _state = MutableStateFlow(InterviewDetailState())
    val state: StateFlow<InterviewDetailState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = InterviewDetailState(isLoading = true)
        viewModelScope.launch {
            try {
                val s = api.getInterviewSession(sessionId)
                _state.value = InterviewDetailState(isLoading = false, session = s)
            } catch (e: Exception) {
                _state.value = InterviewDetailState(
                    isLoading = false,
                    error = e.message ?: "Failed to load session",
                )
            }
        }
    }
}
