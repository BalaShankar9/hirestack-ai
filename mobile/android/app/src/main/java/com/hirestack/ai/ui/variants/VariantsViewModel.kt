package com.hirestack.ai.ui.variants

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.DocVariant
import com.hirestack.ai.data.network.HireStackApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class VariantsState(
    val isLoading: Boolean = true,
    val items: List<DocVariant> = emptyList(),
    val error: String? = null,
    val selecting: String? = null,
)

@HiltViewModel
class VariantsViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(VariantsState())
    val state: StateFlow<VariantsState> = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listVariants()
                _state.value = VariantsState(isLoading = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load variants",
                )
            }
        }
    }

    fun select(id: String) {
        _state.value = _state.value.copy(selecting = id)
        viewModelScope.launch {
            try {
                api.selectVariant(id)
                refresh()
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    selecting = null,
                    error = e.message ?: "Failed to select variant",
                )
            }
        }
    }
}
