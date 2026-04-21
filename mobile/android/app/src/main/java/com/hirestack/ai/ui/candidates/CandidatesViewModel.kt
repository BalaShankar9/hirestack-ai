package com.hirestack.ai.ui.candidates

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.Candidate
import com.hirestack.ai.data.network.HireStackApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class CandidatesState(
    val isLoading: Boolean = false,
    val items: List<Candidate> = emptyList(),
    val stage: String? = null,
    val error: String? = null,
    val noOrg: Boolean = false,
)

@HiltViewModel
class CandidatesViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(CandidatesState(isLoading = true))
    val state: StateFlow<CandidatesState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listCandidates(stage = _state.value.stage)
                _state.value = _state.value.copy(
                    isLoading = false,
                    items = items,
                    noOrg = false,
                )
            } catch (e: Exception) {
                val msg = e.message.orEmpty()
                val noOrg = msg.contains("Create an organization", ignoreCase = true) ||
                    msg.contains("404")
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = if (noOrg) null else (e.message ?: "Failed to load candidates"),
                    noOrg = noOrg,
                )
            }
        }
    }

    fun setStage(stage: String?) {
        _state.value = _state.value.copy(stage = stage)
        refresh()
    }
}
