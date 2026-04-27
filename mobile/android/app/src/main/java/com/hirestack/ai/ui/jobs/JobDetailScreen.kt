package com.hirestack.ai.ui.jobs

import androidx.compose.foundation.combinedClickable
import com.hirestack.ai.ui.components.confirm
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Delete
import androidx.compose.material.icons.outlined.Share
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.Job
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.tap
import com.hirestack.ai.ui.components.toast
import com.hirestack.ai.ui.theme.Brand
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class JobDetailState(
    val isLoading: Boolean = false,
    val job: Job? = null,
    val error: String? = null,
    val deleted: Boolean = false,
)

@HiltViewModel
class JobDetailViewModel @Inject constructor(
    private val api: HireStackApi,
    savedStateHandle: SavedStateHandle,
) : ViewModel() {
    private val jobId: String = checkNotNull(savedStateHandle["jobId"])
    private val _state = MutableStateFlow(JobDetailState(isLoading = true))
    val state: StateFlow<JobDetailState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val job = api.getJob(jobId)
                _state.value = JobDetailState(isLoading = false, job = job)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message ?: "Failed to load job")
            }
        }
    }

    fun delete() {
        viewModelScope.launch {
            try {
                api.deleteJob(jobId)
                _state.value = _state.value.copy(deleted = true)
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Failed to delete")
            }
        }
    }

    fun clearError() { _state.value = _state.value.copy(error = null) }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JobDetailScreen(onBack: () -> Unit, vm: JobDetailViewModel = hiltViewModel()) {
    val state by vm.state.collectAsState()
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    var showConfirm by remember { mutableStateOf(false) }

    LaunchedEffect(state.deleted) {
        if (state.deleted) {
            scope.toast(snackbar, "Job deleted")
            onBack()
        }
    }

    com.hirestack.ai.ui.components.ErrorSnackbar(if (state.job != null) state.error else null) { vm.clearError() }

    Scaffold(
        containerColor = Color.Transparent,
        topBar = {
            BrandTopBar(
                title = "Job",
                subtitle = state.job?.company,
                onBack = onBack,
                actions = {
                    if (state.job != null) {
                        val shareCtx = androidx.compose.ui.platform.LocalContext.current
                        val j = state.job!!
                        IconButton(onClick = {
                            val body = buildString {
                                append(j.title)
                                if (!j.company.isNullOrBlank()) append(" @ ").append(j.company)
                                if (!j.location.isNullOrBlank()) append(" — ").append(j.location)
                                if (!j.source_url.isNullOrBlank()) append("\n").append(j.source_url)
                            }
                            val send = android.content.Intent(android.content.Intent.ACTION_SEND).apply {
                                type = "text/plain"
                                putExtra(android.content.Intent.EXTRA_SUBJECT, j.title)
                                putExtra(android.content.Intent.EXTRA_TEXT, body)
                            }
                            runCatching { shareCtx.startActivity(android.content.Intent.createChooser(send, j.title)) }
                        }) {
                            Icon(androidx.compose.material.icons.Icons.Outlined.Share, contentDescription = "Share job")
                        }
                        IconButton(onClick = { haptic.tap(); showConfirm = true }) {
                            Icon(Icons.Outlined.Delete, contentDescription = "Delete", tint = Brand.Danger)
                        }
                    }
                },
            )
        },
    ) { padding ->
        BrandBackground {
            Box(modifier = Modifier.padding(padding).fillMaxSize()) {
                when {
                    state.isLoading -> SkeletonList(rows = 5)
                    state.error != null -> Column(Modifier.padding(20.dp)) {
                        InlineBanner(state.error!!, tone = PillTone.Danger)
                        Spacer(Modifier.height(12.dp))
                        HireStackPrimaryButton("Retry", onClick = { vm.load() })
                    }
                    state.job != null -> JobContent(state.job!!)
                }
            }
        }
    }

    if (showConfirm) {
        AlertDialog(
            onDismissRequest = { showConfirm = false },
            title = { Text("Delete this job?") },
            text = { Text("This removes the saved job description from your account.") },
            confirmButton = {
                TextButton(
                    onClick = { showConfirm = false; haptic.confirm(); vm.delete() },
                    colors = ButtonDefaults.textButtonColors(contentColor = Brand.Danger),
                ) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { showConfirm = false }) { Text("Cancel") }
            },
        )
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun JobContent(job: Job) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(androidx.compose.ui.text.AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(horizontal = 20.dp, vertical = 12.dp),
    ) {
        SoftCard {
            Column {
                Text(
                    job.title,
                    style = MaterialTheme.typography.headlineSmall,
                    fontWeight = FontWeight.Bold,
                    modifier = Modifier.combinedClickable(onClick = {}, onLongClick = { copy(job.title, "title") }),
                )
                val subtitle = listOfNotNull(job.company, job.location).joinToString(" • ")
                if (subtitle.isNotBlank()) {
                    Spacer(Modifier.height(6.dp))
                    Text(
                        subtitle,
                        style = MaterialTheme.typography.bodyLarge,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.combinedClickable(onClick = {}, onLongClick = { copy(subtitle, "details") }),
                    )
                }
                val tags = listOfNotNull(job.job_type, job.experience_level, job.salary_range)
                if (tags.isNotEmpty()) {
                    Spacer(Modifier.height(12.dp))
                    Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                        tags.forEach { StatusPill(text = it, tone = PillTone.Brand) }
                    }
                }
            }
        }

        if (!job.source_url.isNullOrBlank()) {
            Spacer(Modifier.height(12.dp))
            val openCtx = androidx.compose.ui.platform.LocalContext.current
            SoftCard(
                onClick = {
                    runCatching {
                        openCtx.startActivity(
                            android.content.Intent(android.content.Intent.ACTION_VIEW, android.net.Uri.parse(job.source_url))
                        )
                    }
                },
            ) {
                Column {
                    Text("Source — tap to open", style = MaterialTheme.typography.labelMedium, color = MaterialTheme.colorScheme.onSurfaceVariant)
                    Spacer(Modifier.height(4.dp))
                    Text(job.source_url, style = MaterialTheme.typography.bodyMedium, color = Brand.Indigo)
                }
            }
        }

        if (!job.description.isNullOrBlank()) {
            Spacer(Modifier.height(12.dp))
            SoftCard {
                Column {
                    Text("Description — long-press to copy", style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold)
                    Spacer(Modifier.height(8.dp))
                    Text(
                        job.description,
                        style = MaterialTheme.typography.bodyMedium,
                        modifier = Modifier.combinedClickable(
                            onClick = {},
                            onLongClick = { copy(job.description, "description") },
                        ),
                    )
                }
            }
        }
        Spacer(Modifier.height(24.dp))
    }
}
