package com.hirestack.ai.ui.jobs

import androidx.activity.compose.BackHandler
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Business
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material.icons.outlined.Link
import androidx.compose.material.icons.outlined.LocationOn
import androidx.compose.material.icons.outlined.Payments
import androidx.compose.material.icons.outlined.Star
import androidx.compose.material.icons.outlined.Work
import androidx.compose.material.icons.outlined.WorkOutline
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.CreateJobRequest
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.components.tap
import com.hirestack.ai.ui.components.toast

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AddJobScreen(
    onBack: () -> Unit,
    onCreated: (String) -> Unit,
    vm: JobBoardViewModel = hiltViewModel(),
) {
    val state by vm.state.collectAsState()
    val haptic = LocalHapticFeedback.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val clipboard = LocalClipboardManager.current

    var title by remember { mutableStateOf("") }
    var company by remember { mutableStateOf("") }
    var location by remember { mutableStateOf("") }
    var jobType by remember { mutableStateOf("") }
    var experience by remember { mutableStateOf("") }
    var salary by remember { mutableStateOf("") }
    var description by remember { mutableStateOf("") }
    var sourceUrl by remember { mutableStateOf("") }

    val isDirty = title.isNotBlank() || company.isNotBlank() || description.isNotBlank()
    var confirmExit by remember { mutableStateOf(false) }

    BackHandler(enabled = isDirty && !confirmExit) {
        confirmExit = true
        scope.toast(snackbar, "Press back again to discard")
    }

    Scaffold(
        containerColor = Color.Transparent,
        topBar = { BrandTopBar(title = "Add job", subtitle = "Save a JD to your board", onBack = onBack) },
    ) { padding ->
        BrandBackground {
            Column(
                modifier = Modifier
                    .padding(padding)
                    .fillMaxSize()
                    .imePadding()
                    .verticalScroll(rememberScrollState())
                    .padding(horizontal = 20.dp, vertical = 16.dp),
            ) {
                SoftCard {
                    Column {
                        Field("Title *", title, Icons.Outlined.Work) { title = it }
                        Spacer(Modifier.height(12.dp))
                        Field("Company", company, Icons.Outlined.Business) { company = it }
                        Spacer(Modifier.height(12.dp))
                        Field("Location", location, Icons.Outlined.LocationOn) { location = it }
                        Spacer(Modifier.height(12.dp))
                        Row(Modifier.fillMaxWidth()) {
                            Box(Modifier.weight(1f)) {
                                Field("Job type", jobType, Icons.Outlined.WorkOutline) { jobType = it }
                            }
                            Spacer(Modifier.width(12.dp))
                            Box(Modifier.weight(1f)) {
                                Field("Experience", experience, Icons.Outlined.Star) { experience = it }
                            }
                        }
                        Spacer(Modifier.height(12.dp))
                        Field("Salary range", salary, Icons.Outlined.Payments) { salary = it }
                        Spacer(Modifier.height(12.dp))
                        Field("Source URL", sourceUrl, Icons.Outlined.Link) { sourceUrl = it }
                    }
                }
                Spacer(Modifier.height(12.dp))
                SoftCard {
                    Column {
                        Row(
                            verticalAlignment = androidx.compose.ui.Alignment.CenterVertically,
                            modifier = Modifier.fillMaxWidth(),
                        ) {
                            Text(
                                "Job description",
                                style = androidx.compose.material3.MaterialTheme.typography.titleSmall,
                                modifier = Modifier.weight(1f),
                            )
                            androidx.compose.material3.TextButton(onClick = {
                                val pasted = clipboard.getText()?.text.orEmpty()
                                if (pasted.isBlank()) {
                                    scope.toast(snackbar, "Clipboard is empty")
                                } else {
                                    description = if (description.isBlank()) pasted else description + "\n\n" + pasted
                                    haptic.confirm()
                                    scope.toast(snackbar, "Pasted ${pasted.length} chars")
                                }
                            }) { Text("Paste from clipboard") }
                        }
                        Spacer(Modifier.height(8.dp))
                        OutlinedTextField(
                            value = description,
                            onValueChange = { description = it },
                            placeholder = { Text("Paste the JD here…") },
                            leadingIcon = { Icon(Icons.Outlined.Description, null) },
                            modifier = Modifier.fillMaxWidth().heightIn(min = 160.dp),
                            shape = RoundedCornerShape(14.dp),
                            minLines = 6,
                        )
                    }
                }

                state.error?.let {
                    Spacer(Modifier.height(12.dp))
                    InlineBanner(it, tone = PillTone.Danger)
                }

                Spacer(Modifier.height(20.dp))
                HireStackPrimaryButton(
                    label = if (state.creating) "Saving…" else "Save job",
                    onClick = {
                        haptic.confirm()
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
                            onCreated = { id ->
                                scope.toast(snackbar, "Job saved")
                                onCreated(id)
                            },
                        )
                    },
                    enabled = !state.creating && title.isNotBlank(),
                    loading = state.creating,
                    modifier = Modifier.fillMaxWidth(),
                )
                Spacer(Modifier.height(24.dp))
            }
        }
    }
}

@Composable
private fun Field(
    label: String,
    value: String,
    icon: androidx.compose.ui.graphics.vector.ImageVector,
    onChange: (String) -> Unit,
) {
    val focusManager = androidx.compose.ui.platform.LocalFocusManager.current
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        leadingIcon = { Icon(icon, null) },
        singleLine = true,
        shape = RoundedCornerShape(14.dp),
        keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Next),
        keyboardActions = androidx.compose.foundation.text.KeyboardActions(
            onNext = { focusManager.moveFocus(androidx.compose.ui.focus.FocusDirection.Down) },
        ),
        modifier = Modifier.fillMaxWidth(),
    )
}
