package com.hirestack.ai.ui.salary

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.SalaryAnalysis
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class SalaryState(
    val isLoading: Boolean = true,
    val items: List<SalaryAnalysis> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class SalaryViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(SalaryState())
    val state: StateFlow<SalaryState> = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listSalaryAnalyses()
                _state.value = SalaryState(isLoading = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load analyses",
                )
            }
        }
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}
