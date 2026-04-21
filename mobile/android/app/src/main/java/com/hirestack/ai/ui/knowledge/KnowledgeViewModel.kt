package com.hirestack.ai.ui.knowledge

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.KnowledgeProgress
import com.hirestack.ai.data.network.KnowledgeRecommendation
import com.hirestack.ai.data.network.KnowledgeResource
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class KnowledgeState(
    val isLoading: Boolean = true,
    val resources: List<KnowledgeResource> = emptyList(),
    val progress: List<KnowledgeProgress> = emptyList(),
    val recommendations: List<KnowledgeRecommendation> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class KnowledgeViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(KnowledgeState())
    val state: StateFlow<KnowledgeState> = _state.asStateFlow()

    init { refresh() }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                coroutineScope {
                    val r = async {
                        runCatching { api.listKnowledgeResources(limit = 50) }
                            .getOrDefault(emptyList())
                    }
                    val p = async {
                        runCatching { api.knowledgeProgress() }
                            .getOrDefault(emptyList())
                    }
                    val rec = async {
                        runCatching { api.knowledgeRecommendations() }
                            .getOrDefault(emptyList())
                    }
                    _state.value = KnowledgeState(
                        isLoading = false,
                        resources = r.await(),
                        progress = p.await(),
                        recommendations = rec.await(),
                    )
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load knowledge library",
                )
            }
        }
    }
}
