package com.hirestack.ai.ui.jobs

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.CreateJobRequest

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddJobScreen(
    onBack: () -> Unit,
    onCreated: (String) -> Unit,
    vm: JobBoardViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    var title by remember { mutableStateOf("") }
    var company by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }
    var jobType by remember { mutableStateOf("") }
    var experience by remember { mutableStateOf("") }
    var salary by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var sourceUrl by remember { mutableStateOf("") }

    Scaffold(
        topBar = {
            TopAppBar(
                title = { Text("Add job") },
                navigationIcon = {
                    IconButton(onClick = onBack) {
                        Icon(Icons.AutoMirrored.Filled.ArrowBack, contentDescription = "Back")
                    }
                },
            )
        },
    ) { padding ->
        Column(
            modifier = Modifier
                .padding(padding)
                .fillMaxSize()
                .verticalScroll(rememberScrollState())
                .padding(20.dp),
        ) {
            OutlinedTextField(
                value = title,
                onValueChange = { title = it },
                label = { Text("Title *") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = company,
                onValueChange = { company = it },
                label = { Text("Company") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = location,
                onValueChange = { location = it },
                label = { Text("Location") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(12.dp))
            Row(modifier = Modifier.fillMaxWidth()) {
                OutlinedTextField(
                    value = jobType,
                    onValueChange = { jobType = it },
                    label = { Text("Job type") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                )
                Spacer(Modifier.width(12.dp))
                OutlinedTextField(
                    value = experience,
                    onValueChange = { experience = it },
                    label = { Text("Experience") },
                    modifier = Modifier.weight(1f),
                    singleLine = true,
                )
            }
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = salary,
                onValueChange = { salary = it },
                label = { Text("Salary range") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = sourceUrl,
                onValueChange = { sourceUrl = it },
                label = { Text("Source URL") },
                modifier = Modifier.fillMaxWidth(),
                singleLine = true,
            )
            Spacer(Modifier.height(12.dp))
            OutlinedTextField(
                value = description,
                onValueChange = { description = it },
                label = { Text("Description (paste JD here)") },
                modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp),
                minLines = 6,
            )
            Spacer(Modifier.height(20.dp))

            state.error?.let {
                Text(it, color = MaterialTheme.colorScheme.error)
                Spacer(Modifier.height(8.dp))
            }

            Button(
                onClick = {
                    vm.createJob(
                        CreateJobRequest(
                            title = title.trim(),
                            company = company.ifBlank { null },
                            location = location.ifBlank { null },
                            job_type = jobType.ifBlank { null },
                            experience_level = experience.ifBlank { null },
                            salary_range = salary.ifBlank { null },
                            description = description.ifBlank { null },
                            source_url = sourceUrl.ifBlank { null },
                        ),
                        onCreated = onCreated,
                    )
                },
                enabled = !state.creating && title.isNotBlank(),
                modifier = Modifier.fillMaxWidth(),
            ) {
                if (state.creating) {
                    CircularProgressIndicator(
                        modifier = Modifier.size(20.dp),
                        strokeWidth = 2.dp,
                        color = MaterialTheme.colorScheme.onPrimary,
                    )
                } else {
                    Text("Save job")
                }
            }
        }
    }
}
