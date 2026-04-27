package com.hirestack.ai.ui.docs

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.DocumentLibraryItem
import com.hirestack.ai.data.network.HireStackApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class DocsState(
    val isLoading: Boolean = false,
    val items: List<DocumentLibraryItem> = emptyList(),
    val category: String? = null,
    val error: String? = null,
)

@HiltViewModel
class DocsViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(DocsState(isLoading = true))
    val state: StateFlow<DocsState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val resp = api.listDocuments(limit = 100, category = _state.value.category)
                _state.value = _state.value.copy(isLoading = false, items = resp.documents)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load documents",
                )
            }
        }
    }

    fun setCategory(category: String?) {
        _state.value = _state.value.copy(category = category)
        refresh()
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}
