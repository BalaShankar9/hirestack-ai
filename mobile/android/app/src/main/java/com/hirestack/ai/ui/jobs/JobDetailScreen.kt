package com.hirestack.ai.ui.jobs

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.lifecycle.SavedStateHandle
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.Job
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

    init {
        load()
    }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val job = api.getJob(jobId)
                _state.value = JobDetailState(isLoading = false, job = job)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load job",
                )
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
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun JobDetailScreen(
    onBack: () -> Unit,
    vm: JobDetailViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    var showConfirm by remember { mutableStateOf(false) }

    LaunchedEffect(state.deleted) {
        if (state.deleted) onBack()
    }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Job") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
                actions = {
                    if (state.job != null) {
                        TextButton(
                            onClick = { showConfirm = true },
                            colors = ButtonDefaults.textButtonColors(
                                contentColor = MaterialTheme.colorScheme.error,
                            ),
                        ) { Text("Delete") }
                    }
                },
            )
        },
    ) { padding ->
        Box(modifier = Modifier.padding(padding).fillMaxSize()) {
            when {
                state.isLoading -> {
                    CircularProgressIndicator(modifier = Modifier.padding(32.dp))
                }
                state.error != null -> {
                    Column(modifier = Modifier.padding(24.dp)) {
                        Text("Error", style = MaterialTheme.typography.titleMedium)
                        Spacer(Modifier.height(8.dp))
                        Text(state.error!!, color = MaterialTheme.colorScheme.error)
                        Spacer(Modifier.height(16.dp))
                        Button(onClick = { vm.load() }) { Text("Retry") }
                    }
                }
                state.job != null -> JobContent(state.job!!)
            }
        }
    }

    if (showConfirm) {
        AlertDialog(
            onDismissRequest = { showConfirm = false },
            title = { Text("Delete this job?") },
            text = { Text("This removes the saved job description from your account.") },
            confirmButton = {
                TextButton(onClick = {
                    showConfirm = false
                    vm.delete()
                }) { Text("Delete") }
            },
            dismissButton = {
                TextButton(onClick = { showConfirm = false }) { Text("Cancel") }
            },
        )
    }
}

@Composable
private fun JobContent(job: Job) {
    Column(
        modifier = Modifier
            .fillMaxSize()
            .verticalScroll(rememberScrollState())
            .padding(20.dp),
    ) {
        Text(
            job.title,
            style = MaterialTheme.typography.headlineSmall,
            fontWeight = FontWeight.Bold,
        )
        val subtitle = listOfNotNull(job.company, job.location).joinToString(" • ")
        if (subtitle.isNotBlank()) {
            Spacer(Modifier.height(6.dp))
            Text(
                subtitle,
                style = MaterialTheme.typography.bodyLarge,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
        Spacer(Modifier.height(16.dp))
        MetaRow("Job type", job.job_type)
        MetaRow("Experience", job.experience_level)
        MetaRow("Salary", job.salary_range)
        MetaRow("Source", job.source_url)

        if (!job.description.isNullOrBlank()) {
            Spacer(Modifier.height(20.dp))
            Text("Description", style = MaterialTheme.typography.titleMedium)
            Spacer(Modifier.height(8.dp))
            Text(job.description, style = MaterialTheme.typography.bodyMedium)
        }
    }
}

@Composable
private fun MetaRow(label: String, value: String?) {
    if (value.isNullOrBlank()) return
    Row(modifier = Modifier.fillMaxWidth().padding(vertical = 4.dp)) {
        Text(
            label,
            style = MaterialTheme.typography.bodyMedium,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            modifier = Modifier.width(100.dp),
        )
        Text(
            value,
            style = MaterialTheme.typography.bodyMedium,
            modifier = Modifier.weight(1f),
        )
    }
}
