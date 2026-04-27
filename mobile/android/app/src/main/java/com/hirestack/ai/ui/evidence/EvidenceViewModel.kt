package com.hirestack.ai.ui.evidence

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.EvidenceItem
import com.hirestack.ai.data.network.SupabaseRest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class EvidenceState(
    val isLoading: Boolean = true,
    val refreshing: Boolean = false,
    val items: List<EvidenceItem> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class EvidenceViewModel @Inject constructor(
    private val rest: SupabaseRest,
) : ViewModel() {
    private val _state = MutableStateFlow(EvidenceState())
    val state: StateFlow<EvidenceState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = rest.listEvidence(limit = 200)
                _state.value = EvidenceState(items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Couldn't load evidence",
                )
            }
        }
    }

    fun refresh() {
        _state.value = _state.value.copy(refreshing = true)
        viewModelScope.launch {
            try {
                val items = rest.listEvidence(limit = 200)
                _state.value = _state.value.copy(refreshing = false, items = items, error = null)
            } catch (e: Exception) {
                _state.value = _state.value.copy(refreshing = false, error = e.message)
            }
        }
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}
