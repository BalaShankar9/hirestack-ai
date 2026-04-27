package com.hirestack.ai.ui.applications

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.Application
import com.hirestack.ai.data.network.GenerationJob
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.PipelineEvent
import com.hirestack.ai.data.network.PipelineSse
import com.hirestack.ai.data.network.SupabaseRest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.Job
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.catch
import kotlinx.coroutines.launch
import javax.inject.Inject

data class WorkspaceState(
    val isLoading: Boolean = true,
    val app: Application? = null,
    val job: GenerationJob? = null,
    val timeline: List<PipelineEvent> = emptyList(),
    val streaming: Boolean = false,
    val error: String? = null,
)

@HiltViewModel
class ApplicationWorkspaceViewModel @Inject constructor(
    private val rest: SupabaseRest,
    private val api: HireStackApi,
    private val sse: PipelineSse,
) : ViewModel() {

    private val _state = MutableStateFlow(WorkspaceState())
    val state: StateFlow<WorkspaceState> = _state.asStateFlow()

    private var streamJob: Job? = null

    fun load(applicationId: String) {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val app = rest.getApplication(applicationId)
                _state.value = _state.value.copy(isLoading = false, app = app)
                // If the app references a job in modules/state, pick it up.
                // We probe last 3 known modules for any with a job_id.
                // (Current schema embeds job state inside `modules`; a dedicated
                //  endpoint will replace this when added.)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Couldn't load application",
                )
            }
        }
    }

    fun reload() {
        val id = _state.value.app?.id ?: return
        load(id)
    }

    fun retryLastJob() {
        val jobId = _state.value.job?.id ?: return
        viewModelScope.launch {
            runCatching { api.retryGenerationJob(jobId) }
            reload()
        }
    }

    fun cancelLastJob() {
        val jobId = _state.value.job?.id ?: return
        viewModelScope.launch {
            runCatching { api.cancelGenerationJob(jobId) }
            stopStream()
            reload()
        }
    }

    fun streamJob(jobId: String) {
        stopStream()
        _state.value = _state.value.copy(streaming = true, timeline = emptyList())
        streamJob = viewModelScope.launch {
            sse.streamJob(jobId)
                .catch { e ->
                    _state.value = _state.value.copy(
                        streaming = false,
                        error = e.message,
                    )
                }
                .collect { ev ->
                    val newTimeline = (_state.value.timeline + ev).takeLast(80)
                    _state.value = _state.value.copy(timeline = newTimeline)
                    if (ev.name == "complete" || ev.name == "error") {
                        _state.value = _state.value.copy(streaming = false)
                        reload()
                    }
                }
        }
    }

    fun stopStream() {
        streamJob?.cancel()
        streamJob = null
        _state.value = _state.value.copy(streaming = false)
    }

    override fun onCleared() {
        super.onCleared()
        stopStream()
    }
}
