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

    fun delete(id: String) {
        val before = _state.value.items
        _state.value = _state.value.copy(items = before.filterNot { it.id == id })
        viewModelScope.launch {
            try {
                api.deleteCandidate(id)
            } catch (e: Exception) {
                _state.value = _state.value.copy(items = before, error = e.message ?: "Failed to delete")
            }
        }
    }

    fun archive(id: String) {
        val before = _state.value.items
        _state.value = _state.value.copy(items = before.filterNot { it.id == id })
        viewModelScope.launch {
            try {
                api.moveCandidateStage(id, mapOf("stage" to "rejected"))
            } catch (e: Exception) {
                _state.value = _state.value.copy(items = before, error = e.message ?: "Failed to archive")
            }
        }
    }

    /** Removes locally and returns the snapshot for undo. */
    fun removeLocally(id: String): Candidate? {
        val before = _state.value.items
        val item = before.firstOrNull { it.id == id } ?: return null
        _state.value = _state.value.copy(items = before.filterNot { it.id == id })
        return item
    }

    fun restore(item: Candidate) {
        if (_state.value.items.any { it.id == item.id }) return
        _state.value = _state.value.copy(items = _state.value.items + item)
    }

    fun commitDelete(id: String) {
        viewModelScope.launch {
            try { api.deleteCandidate(id) }
            catch (e: Exception) { _state.value = _state.value.copy(error = e.message ?: "Failed to delete"); refresh() }
        }
    }

    fun commitArchive(id: String) {
        viewModelScope.launch {
            try { api.moveCandidateStage(id, mapOf("stage" to "rejected")) }
            catch (e: Exception) { _state.value = _state.value.copy(error = e.message ?: "Failed to archive"); refresh() }
        }
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}
