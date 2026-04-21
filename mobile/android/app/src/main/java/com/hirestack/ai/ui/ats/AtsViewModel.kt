package com.hirestack.ai.ui.ats

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.AtsScan
import com.hirestack.ai.data.network.AtsScanRequest
import com.hirestack.ai.data.network.HireStackApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class AtsState(
    val isLoading: Boolean = false,
    val items: List<AtsScan> = emptyList(),
    val error: String? = null,
    val running: Boolean = false,
    val lastResult: AtsScan? = null,
)

@HiltViewModel
class AtsViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(AtsState(isLoading = true))
    val state: StateFlow<AtsState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listAtsScans()
                _state.value = _state.value.copy(isLoading = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load scans",
                )
            }
        }
    }

    fun runScan(documentContent: String, jdText: String) {
        if (documentContent.isBlank() || jdText.isBlank()) {
            _state.value = _state.value.copy(error = "Both resume text and JD text are required.")
            return
        }
        _state.value = _state.value.copy(running = true, error = null, lastResult = null)
        viewModelScope.launch {
            try {
                val resp = api.runAtsScan(AtsScanRequest(documentContent.trim(), jdText.trim()))
                _state.value = _state.value.copy(running = false, lastResult = resp.data)
                refresh()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    running = false,
                    error = e.message ?: "Scan failed",
                )
            }
        }
    }

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }
}
