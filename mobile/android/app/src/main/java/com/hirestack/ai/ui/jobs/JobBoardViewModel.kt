package com.hirestack.ai.ui.jobs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.CreateJobRequest
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.Job
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class JobBoardState(
    val isLoading: Boolean = false,
    val items: List<Job> = emptyList(),
    val error: String? = null,
    val creating: Boolean = false,
)

@HiltViewModel
class JobBoardViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(JobBoardState())
    val state: StateFlow<JobBoardState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listJobs(limit = 100, offset = 0)
                _state.value = _state.value.copy(isLoading = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load jobs",
                )
            }
        }
    }

    fun createJob(req: CreateJobRequest, onCreated: (String) -> Unit) {
        if (req.title.isBlank()) {
            _state.value = _state.value.copy(error = "Title is required")
            return
        }
        _state.value = _state.value.copy(creating = true, error = null)
        viewModelScope.launch {
            try {
                val created = api.createJob(req)
                _state.value = _state.value.copy(
                    creating = false,
                    items = listOf(created) + _state.value.items,
                )
                onCreated(created.id)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    creating = false,
                    error = e.message ?: "Failed to create job",
                )
            }
        }
    }

    fun delete(id: String) {
        viewModelScope.launch {
            try {
                api.deleteJob(id)
                _state.value = _state.value.copy(
                    items = _state.value.items.filterNot { it.id == id },
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Failed to delete")
            }
        }
    }

    fun clearError() {
        _state.value = _state.value.copy(error = null)
    }
}
