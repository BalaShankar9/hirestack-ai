package com.hirestack.ai.ui.studio

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.BenchmarkDoc
import com.hirestack.ai.data.network.BuilderDocument
import com.hirestack.ai.data.network.BuilderGenerateRequest
import com.hirestack.ai.data.network.CareerRoadmap
import com.hirestack.ai.data.network.CoachRequest
import com.hirestack.ai.data.network.CoachTurn
import com.hirestack.ai.data.network.GenerateBenchmarkRequest
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.RoadmapRequest
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/* -------------------------- Benchmark -------------------------- */

data class BenchmarkState(
    val jdText: String = "",
    val jobTitle: String = "",
    val company: String = "",
    val isLoading: Boolean = false,
    val result: BenchmarkDoc? = null,
    val error: String? = null,
)

@HiltViewModel
class BenchmarkViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(BenchmarkState())
    val state: StateFlow<BenchmarkState> = _state.asStateFlow()

    fun onJd(v: String) { _state.value = _state.value.copy(jdText = v) }
    fun onTitle(v: String) { _state.value = _state.value.copy(jobTitle = v) }
    fun onCompany(v: String) { _state.value = _state.value.copy(company = v) }

    fun generate() {
        val s = _state.value
        if (s.jdText.isBlank()) {
            _state.value = s.copy(error = "Paste a job description first")
            return
        }
        _state.value = s.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val res = api.generateBenchmark(
                    GenerateBenchmarkRequest(
                        jd_text = s.jdText.trim(),
                        job_title = s.jobTitle.ifBlank { null },
                        company = s.company.ifBlank { null },
                    ),
                )
                _state.value = _state.value.copy(isLoading = false, result = res)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }
}

/* -------------------------- Builder ---------------------------- */

data class BuilderState(
    val docType: String = "cv",
    val jdText: String = "",
    val tone: String = "professional",
    val isLoading: Boolean = false,
    val result: BuilderDocument? = null,
    val history: List<BuilderDocument> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class BuilderViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(BuilderState())
    val state: StateFlow<BuilderState> = _state.asStateFlow()

    init { refresh() }

    fun setDocType(v: String) { _state.value = _state.value.copy(docType = v) }
    fun setJd(v: String) { _state.value = _state.value.copy(jdText = v) }
    fun setTone(v: String) { _state.value = _state.value.copy(tone = v) }

    fun refresh() {
        viewModelScope.launch {
            runCatching { api.listBuilderDocuments() }
                .onSuccess { _state.value = _state.value.copy(history = it) }
        }
    }

    fun generate() {
        val s = _state.value
        _state.value = s.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val res = api.builderGenerate(
                    BuilderGenerateRequest(
                        doc_type = s.docType,
                        jd_text = s.jdText.ifBlank { null },
                        tone = s.tone,
                    ),
                )
                _state.value = _state.value.copy(isLoading = false, result = res)
                refresh()
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }
}

/* -------------------------- Consultant ------------------------- */

data class ConsultantState(
    val tab: Int = 0,                            // 0 = Coach, 1 = Roadmaps
    // Coach
    val draft: String = "",
    val sending: Boolean = false,
    val turns: List<CoachTurn> = emptyList(),
    val coachError: String? = null,
    // Roadmaps
    val roadmaps: List<CareerRoadmap> = emptyList(),
    val targetRole: String = "",
    val targetCompany: String = "",
    val timeframeMonths: String = "12",
    val creatingRoadmap: Boolean = false,
    val roadmapError: String? = null,
)

@HiltViewModel
class ConsultantViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(ConsultantState())
    val state: StateFlow<ConsultantState> = _state.asStateFlow()

    init { refreshRoadmaps() }

    fun setTab(i: Int) { _state.value = _state.value.copy(tab = i) }
    fun setDraft(v: String) { _state.value = _state.value.copy(draft = v) }
    fun setRole(v: String) { _state.value = _state.value.copy(targetRole = v) }
    fun setCompany(v: String) { _state.value = _state.value.copy(targetCompany = v) }
    fun setTimeframe(v: String) { _state.value = _state.value.copy(timeframeMonths = v) }

    fun send() {
        val s = _state.value
        if (s.draft.isBlank() || s.sending) return
        val turn = CoachTurn(role = "user", content = s.draft.trim())
        _state.value = s.copy(
            sending = true,
            draft = "",
            turns = s.turns + turn,
            coachError = null,
        )
        viewModelScope.launch {
            try {
                val res = api.coach(CoachRequest(message = turn.content, history = _state.value.turns))
                val reply = CoachTurn(role = "assistant", content = res.reply ?: "(no response)")
                _state.value = _state.value.copy(sending = false, turns = _state.value.turns + reply)
            } catch (e: Exception) {
                _state.value = _state.value.copy(sending = false, coachError = e.message)
            }
        }
    }

    fun refreshRoadmaps() {
        viewModelScope.launch {
            runCatching { api.listRoadmaps() }
                .onSuccess { _state.value = _state.value.copy(roadmaps = it) }
        }
    }

    fun createRoadmap() {
        val s = _state.value
        if (s.targetRole.isBlank()) {
            _state.value = s.copy(roadmapError = "Target role is required")
            return
        }
        _state.value = s.copy(creatingRoadmap = true, roadmapError = null)
        viewModelScope.launch {
            try {
                api.createRoadmap(
                    RoadmapRequest(
                        target_role = s.targetRole.trim(),
                        target_company = s.targetCompany.ifBlank { null },
                        timeframe_months = s.timeframeMonths.toIntOrNull(),
                    ),
                )
                _state.value = _state.value.copy(creatingRoadmap = false)
                refreshRoadmaps()
            } catch (e: Exception) {
                _state.value = _state.value.copy(creatingRoadmap = false, roadmapError = e.message)
            }
        }
    }
}
