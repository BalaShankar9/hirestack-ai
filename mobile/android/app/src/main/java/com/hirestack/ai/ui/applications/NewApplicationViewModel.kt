package com.hirestack.ai.ui.applications

import android.content.Context
import android.net.Uri
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.Application
import com.hirestack.ai.data.network.CreateApplicationRequest
import com.hirestack.ai.data.network.CreateGenerationJobRequest
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.SupabaseRest
import dagger.hilt.android.lifecycle.HiltViewModel
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import okhttp3.MediaType.Companion.toMediaTypeOrNull
import okhttp3.MultipartBody
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject

/**
 * 4-step wizard:
 *   1. Job details (title, company, location, JD text)
 *   2. Resume (upload PDF/DOCX → parsed to plain text)
 *   3. Modules to generate (CV, Cover letter, Personal statement, etc.)
 *   4. Review + launch
 *
 * On launch:
 *   - createApplication() via SupabaseRest
 *   - createGenerationJob() via FastAPI → returns job id
 *   - emit success with applicationId so screen can navigate to workspace
 */
data class WizardState(
    val step: Int = 0,                      // 0..3
    // Step 1
    val title: String = "",
    val company: String = "",
    val location: String = "",
    val jdText: String = "",
    // Step 2
    val resumeFileName: String? = null,
    val resumeText: String? = null,
    val parsing: Boolean = false,
    val parseError: String? = null,
    // Step 3
    val modules: Set<String> = setOf(
        "cv",
        "cover_letter",
        "personal_statement",
    ),
    // Submit
    val launching: Boolean = false,
    val launchError: String? = null,
    val createdApplicationId: String? = null,
)

@HiltViewModel
class NewApplicationViewModel @Inject constructor(
    @ApplicationContext private val ctx: Context,
    private val api: HireStackApi,
    private val rest: SupabaseRest,
) : ViewModel() {

    private val _state = MutableStateFlow(WizardState())
    val state: StateFlow<WizardState> = _state.asStateFlow()

    fun onTitle(v: String) { _state.value = _state.value.copy(title = v) }
    fun onCompany(v: String) { _state.value = _state.value.copy(company = v) }
    fun onLocation(v: String) { _state.value = _state.value.copy(location = v) }
    fun onJdText(v: String) { _state.value = _state.value.copy(jdText = v) }

    fun toggleModule(key: String) {
        val s = _state.value
        val m = s.modules.toMutableSet()
        if (!m.add(key)) m.remove(key)
        _state.value = s.copy(modules = m)
    }

    fun next() {
        val s = _state.value
        if (s.step >= 3) return
        _state.value = s.copy(step = s.step + 1)
    }

    fun back() {
        val s = _state.value
        if (s.step <= 0) return
        _state.value = s.copy(step = s.step - 1)
    }

    fun parseResume(uri: Uri, displayName: String) {
        _state.value = _state.value.copy(parsing = true, parseError = null, resumeFileName = displayName)
        viewModelScope.launch {
            try {
                val bytes = ctx.contentResolver.openInputStream(uri)?.use { it.readBytes() }
                    ?: throw IllegalStateException("Couldn't open the file")
                val mediaType = (ctx.contentResolver.getType(uri) ?: "application/octet-stream")
                    .toMediaTypeOrNull()
                val body = bytes.toRequestBody(mediaType)
                val part = MultipartBody.Part.createFormData("file", displayName, body)
                val parsed = api.parseResume(part)
                _state.value = _state.value.copy(
                    parsing = false,
                    resumeText = parsed.text,
                    parseError = if (parsed.text.isNullOrBlank()) "We couldn't extract text from this file." else null,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    parsing = false,
                    parseError = e.message ?: "Couldn't parse resume",
                )
            }
        }
    }

    fun pasteResumeText(t: String) {
        _state.value = _state.value.copy(resumeText = t, parseError = null, resumeFileName = "Pasted text")
    }

    fun launch() {
        val s = _state.value
        if (s.title.isBlank() || s.jdText.isBlank()) {
            _state.value = s.copy(launchError = "Title and job description are required")
            return
        }
        _state.value = s.copy(launching = true, launchError = null)
        viewModelScope.launch {
            try {
                val app: Application = rest.createApplication(
                    CreateApplicationRequest(
                        title = s.title.trim(),
                        job_title = s.title.trim(),
                        company = s.company.trim().ifBlank { null },
                        location = s.location.trim().ifBlank { null },
                        jd_text = s.jdText.trim(),
                    ),
                )
                runCatching {
                    api.createGenerationJob(
                        CreateGenerationJobRequest(
                            application_id = app.id,
                            requested_modules = s.modules.toList(),
                        ),
                    )
                }
                _state.value = _state.value.copy(
                    launching = false,
                    createdApplicationId = app.id,
                )
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    launching = false,
                    launchError = e.message ?: "Couldn't start generation",
                )
            }
        }
    }
}
