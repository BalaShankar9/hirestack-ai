package com.hirestack.ai.ui.applications

import android.app.Activity
import android.net.Uri
import android.provider.OpenableColumns
import androidx.activity.compose.BackHandler
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.Check
import androidx.compose.material.icons.outlined.CloudUpload
import androidx.compose.material.icons.outlined.Description
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
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
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.HireStackSecondaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SectionHeader
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.theme.BrandGradient

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun NewApplicationScreen(
    onClose: () -> Unit,
    onLaunched: (String) -> Unit,
) {
    val vm: NewApplicationViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    LaunchedEffect(state.createdApplicationId) {
        state.createdApplicationId?.let(onLaunched)
    }

    val isDirty = state.title.isNotBlank() || state.company.isNotBlank() ||
        state.location.isNotBlank() || state.jdText.isNotBlank() ||
        state.resumeFileName != null || state.resumeText != null
    var confirmDiscard by remember { mutableStateOf(false) }
    val safeClose: () -> Unit = { if (isDirty) confirmDiscard = true else onClose() }

    BackHandler(enabled = state.step > 0) { vm.back() }
    BackHandler(enabled = state.step == 0 && isDirty && !confirmDiscard) { confirmDiscard = true }

    Scaffold(
        topBar = {
            BrandTopBar(
                title = "New application",
                subtitle = "Step ${state.step + 1} of 4",
                onBack = safeClose,
            )
        },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            Column(
                Modifier
                    .fillMaxSize()
                    .padding(padding)
                    .imePadding()
                    .padding(horizontal = 20.dp)
                    .verticalScroll(rememberScrollState()),
            ) {
                StepDots(step = state.step, total = 4)
                Spacer(Modifier.height(16.dp))

                when (state.step) {
                    0 -> JobDetailsStep(state, vm)
                    1 -> ResumeStep(state, vm)
                    2 -> ModulesStep(state, vm)
                    3 -> ReviewStep(state)
                }

                Spacer(Modifier.height(24.dp))

                if (state.launchError != null) {
                    InlineBanner(message = state.launchError!!, tone = PillTone.Danger)
                    Spacer(Modifier.height(12.dp))
                }

                Row(
                    Modifier.fillMaxWidth().padding(bottom = 32.dp),
                    horizontalArrangement = Arrangement.SpaceBetween,
                    verticalAlignment = Alignment.CenterVertically,
                ) {
                    if (state.step > 0) {
                        HireStackSecondaryButton(label = "Back", onClick = vm::back)
                    } else {
                        Spacer(Modifier.width(1.dp))
                    }

                    val canAdvance = when (state.step) {
                        0 -> state.title.isNotBlank() && state.jdText.isNotBlank()
                        1 -> state.resumeFileName != null || (state.resumeText?.isNotBlank() == true)
                        2 -> state.modules.isNotEmpty()
                        3 -> !state.launching
                        else -> false
                    }

                    HireStackPrimaryButton(
                        label = if (state.step == 3) "Generate" else "Next",
                        onClick = {
                            if (state.step < 3) vm.next() else vm.launch()
                        },
                        enabled = canAdvance,
                        loading = state.launching,
                    )
                }
                val advanceHint: String? = when {
                    state.step == 0 && state.title.isNotBlank() && state.jdText.isNotBlank() -> null
                    state.step == 1 && (state.resumeFileName != null || (state.resumeText?.isNotBlank() == true)) -> null
                    state.step == 2 && state.modules.isNotEmpty() -> null
                    state.step == 3 -> null
                    state.step == 0 && state.title.isBlank() && state.jdText.isBlank() -> "Add a job title and paste the JD to continue"
                    state.step == 0 && state.title.isBlank() -> "Add a job title to continue"
                    state.step == 0 && state.jdText.isBlank() -> "Paste the job description to continue"
                    state.step == 1 -> "Upload a resume or paste resume text to continue"
                    state.step == 2 -> "Pick at least one module to continue"
                    else -> null
                }
                advanceHint?.let { hint ->
                    Spacer(Modifier.height(8.dp))
                    androidx.compose.material3.Text(
                        hint,
                        style = androidx.compose.material3.MaterialTheme.typography.bodySmall,
                        color = androidx.compose.material3.MaterialTheme.colorScheme.onSurfaceVariant,
                    )
                }
            }
        }
    }

    if (confirmDiscard) {
        val discardHaptic = androidx.compose.ui.platform.LocalHapticFeedback.current
        androidx.compose.material3.AlertDialog(
            onDismissRequest = { confirmDiscard = false },
            title = { androidx.compose.material3.Text("Discard application?") },
            text = { androidx.compose.material3.Text("You'll lose the details you've entered for this new application.") },
            confirmButton = {
                androidx.compose.material3.TextButton(
                    onClick = { confirmDiscard = false; discardHaptic.confirm(); onClose() },
                    colors = androidx.compose.material3.ButtonDefaults.textButtonColors(contentColor = com.hirestack.ai.ui.theme.Brand.Danger),
                ) { androidx.compose.material3.Text("Discard") }
            },
            dismissButton = {
                androidx.compose.material3.TextButton(onClick = { confirmDiscard = false }) { androidx.compose.material3.Text("Keep editing") }
            },
        )
    }
}

@Composable
private fun StepDots(step: Int, total: Int) {
    Row(
        Modifier.padding(top = 8.dp),
        horizontalArrangement = Arrangement.spacedBy(8.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        repeat(total) { i ->
            val active = i <= step
            Box(
                Modifier
                    .height(6.dp)
                    .let { if (i == step) it.width(36.dp) else it.width(20.dp) }
                    .background(
                        if (active) Brand.Indigo else MaterialTheme.colorScheme.surfaceContainerHigh,
                        RoundedCornerShape(3.dp),
                    ),
            )
        }
    }
}

/* ---- Step 1 ---- */

@Composable
private fun JobDetailsStep(state: WizardState, vm: NewApplicationViewModel) {
    SectionHeader(title = "Tell us about the role")
    SoftCard {
        Column {
            Text(
                "Paste the job description and a few key facts. We use these to tailor every document.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(14.dp))
            BrandField(value = state.title, onChange = vm::onTitle, label = "Job title *")
            Spacer(Modifier.height(10.dp))
            BrandField(value = state.company, onChange = vm::onCompany, label = "Company")
            Spacer(Modifier.height(10.dp))
            BrandField(value = state.location, onChange = vm::onLocation, label = "Location")
            Spacer(Modifier.height(10.dp))
            BrandField(
                value = state.jdText,
                onChange = vm::onJdText,
                label = "Job description *",
                minLines = 6,
            )
        }
    }
}

/* ---- Step 2 ---- */

@Composable
private fun ResumeStep(state: WizardState, vm: NewApplicationViewModel) {
    val ctx = LocalContext.current
    val launcher = rememberLauncherForActivityResult(
        ActivityResultContracts.GetContent(),
    ) { uri: Uri? ->
        if (uri != null) {
            val name = queryDisplayName(ctx, uri) ?: "resume"
            vm.parseResume(uri, name)
        }
    }

    SectionHeader(title = "Add your latest resume")
    SoftCard {
        Column {
            Text(
                "We'll use this as the source of truth for your facts. Your data stays private to your account.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(14.dp))

            UploadDropzone(
                fileName = state.resumeFileName,
                parsing = state.parsing,
                onPick = { launcher.launch("*/*") },
            )

            if (state.parseError != null) {
                Spacer(Modifier.height(10.dp))
                InlineBanner(message = state.parseError!!, tone = PillTone.Warning)
            }

            if (!state.resumeText.isNullOrBlank()) {
                Spacer(Modifier.height(14.dp))
                Text(
                    "Preview",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    state.resumeText!!.take(600) +
                        if ((state.resumeText?.length ?: 0) > 600) "…" else "",
                    style = MaterialTheme.typography.bodySmall,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }

            Spacer(Modifier.height(18.dp))
            Text(
                "Or paste plain text",
                style = MaterialTheme.typography.labelLarge,
                fontWeight = FontWeight.SemiBold,
            )
            Spacer(Modifier.height(6.dp))
            BrandField(
                value = state.resumeText.orEmpty(),
                onChange = vm::pasteResumeText,
                label = "Paste resume text",
                minLines = 4,
            )
        }
    }
}

@Composable
private fun UploadDropzone(fileName: String?, parsing: Boolean, onPick: () -> Unit) {
    Box(
        Modifier
            .fillMaxWidth()
            .background(BrandGradient.Cool, RoundedCornerShape(20.dp))
            .border(
                1.dp,
                MaterialTheme.colorScheme.outlineVariant,
                RoundedCornerShape(20.dp),
            )
            .clickable(onClick = onPick)
            .padding(20.dp),
    ) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(48.dp)
                    .background(Color.White.copy(alpha = 0.18f), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    if (fileName != null) Icons.Outlined.Description else Icons.Outlined.CloudUpload,
                    contentDescription = null,
                    tint = Color.White,
                )
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    fileName ?: "Upload PDF or DOCX",
                    style = MaterialTheme.typography.titleSmall,
                    color = Color.White,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    if (parsing) "Parsing…" else "Tap to choose a file",
                    style = MaterialTheme.typography.bodySmall,
                    color = Color.White.copy(alpha = 0.85f),
                )
                if (parsing) {
                    Spacer(Modifier.height(8.dp))
                    LinearProgressIndicator(
                        modifier = Modifier.fillMaxWidth(),
                        color = Color.White,
                        trackColor = Color.White.copy(alpha = 0.25f),
                    )
                }
            }
        }
    }
}

/* ---- Step 3 ---- */

private val MODULE_OPTIONS = listOf(
    "cv" to "Tailored CV",
    "cover_letter" to "Cover letter",
    "personal_statement" to "Personal statement",
    "portfolio" to "Portfolio brief",
    "company_intel" to "Company intel",
    "interview_prep" to "Interview prep",
)

@Composable
private fun ModulesStep(state: WizardState, vm: NewApplicationViewModel) {
    SectionHeader(title = "What should we generate?")
    SoftCard {
        Column {
            Text(
                "Pick everything you'd like in this batch. You can always add more later.",
                style = MaterialTheme.typography.bodyMedium,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
            Spacer(Modifier.height(12.dp))
            MODULE_OPTIONS.forEach { (key, label) ->
                ModuleRow(
                    label = label,
                    selected = state.modules.contains(key),
                    onToggle = { vm.toggleModule(key) },
                )
            }
        }
    }
}

@Composable
private fun ModuleRow(label: String, selected: Boolean, onToggle: () -> Unit) {
    Row(
        Modifier
            .fillMaxWidth()
            .clickable(onClick = onToggle)
            .padding(vertical = 10.dp),
        verticalAlignment = Alignment.CenterVertically,
    ) {
        Box(
            Modifier
                .size(22.dp)
                .background(
                    if (selected) Brand.Indigo else Color.Transparent,
                    RoundedCornerShape(6.dp),
                )
                .border(
                    1.5.dp,
                    if (selected) Brand.Indigo else MaterialTheme.colorScheme.outline,
                    RoundedCornerShape(6.dp),
                ),
            contentAlignment = Alignment.Center,
        ) {
            if (selected) {
                Icon(
                    Icons.Filled.Check,
                    contentDescription = null,
                    tint = Color.White,
                    modifier = Modifier.size(16.dp),
                )
            }
        }
        Spacer(Modifier.width(14.dp))
        Text(label, style = MaterialTheme.typography.bodyLarge)
    }
}

/* ---- Step 4 ---- */

@Composable
private fun ReviewStep(state: WizardState) {
    SectionHeader(title = "Ready to launch")
    SoftCard {
        Column {
            ReviewRow("Role", state.title.ifBlank { "—" })
            ReviewRow("Company", state.company.ifBlank { "—" })
            ReviewRow("Location", state.location.ifBlank { "—" })
            ReviewRow(
                "Resume",
                state.resumeFileName ?: if (!state.resumeText.isNullOrBlank()) "Pasted text" else "None",
            )
            ReviewRow(
                "Modules",
                state.modules.mapNotNull { k -> MODULE_OPTIONS.firstOrNull { it.first == k }?.second }
                    .joinToString(" · "),
            )
        }
    }
    Spacer(Modifier.height(12.dp))
    Text(
        "We'll create the application, then start the AI pipeline. You'll watch every agent's work live in Mission Control.",
        style = MaterialTheme.typography.bodyMedium,
        color = MaterialTheme.colorScheme.onSurfaceVariant,
        modifier = Modifier.padding(horizontal = 4.dp),
    )
}

@Composable
private fun ReviewRow(label: String, value: String) {
    Column(Modifier.padding(vertical = 8.dp)) {
        Text(
            label.uppercase(),
            style = MaterialTheme.typography.labelSmall,
            color = MaterialTheme.colorScheme.onSurfaceVariant,
            fontWeight = FontWeight.SemiBold,
        )
        Spacer(Modifier.height(2.dp))
        Text(value, style = MaterialTheme.typography.bodyLarge)
    }
}

/* ---- Shared field ---- */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
private fun BrandField(
    value: String,
    onChange: (String) -> Unit,
    label: String,
    minLines: Int = 1,
) {
    val focusManager = androidx.compose.ui.platform.LocalFocusManager.current
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        label = { Text(label) },
        modifier = Modifier.fillMaxWidth(),
        minLines = minLines,
        singleLine = minLines == 1,
        shape = RoundedCornerShape(14.dp),
        keyboardOptions = if (minLines == 1)
            androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Next)
        else androidx.compose.foundation.text.KeyboardOptions.Default,
        keyboardActions = if (minLines == 1) androidx.compose.foundation.text.KeyboardActions(
            onNext = { focusManager.moveFocus(androidx.compose.ui.focus.FocusDirection.Down) },
        ) else androidx.compose.foundation.text.KeyboardActions.Default,
        colors = TextFieldDefaults.colors(
            focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
            unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
    )
}

private fun queryDisplayName(ctx: android.content.Context, uri: Uri): String? {
    return runCatching {
        ctx.contentResolver.query(uri, null, null, null, null)?.use { c ->
            val idx = c.getColumnIndex(OpenableColumns.DISPLAY_NAME)
            if (idx >= 0 && c.moveToFirst()) c.getString(idx) else null
        }
    }.getOrNull()
}
