package com.hirestack.ai.ui.career

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.CareerPortfolio
import com.hirestack.ai.data.network.CareerSnapshot
import com.hirestack.ai.data.network.ConversionFunnel
import com.hirestack.ai.data.network.HireStackApi
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class CareerState(
    val isLoading: Boolean = true,
    val portfolio: CareerPortfolio? = null,
    val funnel: ConversionFunnel? = null,
    val timeline: List<CareerSnapshot> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class CareerViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(CareerState())
    val state: StateFlow<CareerState> = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                coroutineScope {
                    val p = async { runCatching { api.careerPortfolio() }.getOrNull() }
                    val f = async { runCatching { api.careerFunnel() }.getOrNull() }
                    val t = async {
                        runCatching { api.careerTimeline(days = 90) }.getOrDefault(emptyList())
                    }
                    _state.value = CareerState(
                        isLoading = false,
                        portfolio = p.await(),
                        funnel = f.await(),
                        timeline = t.await(),
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load career analytics",
                )
            }
        }
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}
