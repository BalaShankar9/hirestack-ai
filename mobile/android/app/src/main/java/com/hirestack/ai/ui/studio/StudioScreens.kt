package com.hirestack.ai.ui.studio

import androidx.compose.foundation.combinedClickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.AutoAwesome
import androidx.compose.material.icons.outlined.Insights
import androidx.compose.material.icons.outlined.Map
import androidx.compose.material.icons.automirrored.outlined.Send
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.SegmentedButton
import androidx.compose.material3.SegmentedButtonDefaults
import androidx.compose.material3.SingleChoiceSegmentedButtonRow
import androidx.compose.material3.Tab
import androidx.compose.material3.TabRow
import androidx.compose.material3.Text
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.BenchmarkDoc
import com.hirestack.ai.data.network.CareerRoadmap
import com.hirestack.ai.data.network.CoachTurn
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.GradientHeroCard
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SectionHeader
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.LocalAppScope
import com.hirestack.ai.ui.components.LocalSnackbar
import com.hirestack.ai.ui.components.confirm
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.theme.BrandGradient
import kotlinx.coroutines.launch

/* -------------------- Shared field -------------------- */

@Composable
private fun StudioField(
    value: String,
    onChange: (String) -> Unit,
    placeholder: String,
    modifier: Modifier = Modifier,
    minLines: Int = 1,
    maxLines: Int = 1,
    keyboardOptions: KeyboardOptions = KeyboardOptions.Default,
) {
    OutlinedTextField(
        value = value,
        onValueChange = onChange,
        placeholder = { Text(placeholder) },
        modifier = modifier.fillMaxWidth(),
        shape = RoundedCornerShape(16.dp),
        minLines = minLines,
        maxLines = maxLines,
        keyboardOptions = keyboardOptions,
        colors = TextFieldDefaults.colors(
            focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
            unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
        ),
    )
}

/* ============================================================
 *                       BENCHMARK
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BenchmarkScreen() {
    val vm: BenchmarkViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = { BrandTopBar(title = "Benchmark", subtitle = "Score a JD instantly") },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    GradientHeroCard(brush = BrandGradient.Cool) {
                        Column {
                            Row(verticalAlignment = Alignment.CenterVertically) {
                                Icon(Icons.Outlined.Insights, contentDescription = null, tint = Color.White)
                                Spacer(Modifier.width(10.dp))
                                Text(
                                    "Benchmark a job description",
                                    color = Color.White,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold,
                                )
                            }
                            Spacer(Modifier.height(6.dp))
                            Text(
                                "Get an instant readout — keyword density, ATS readability, " +
                                    "and the strongest match angles to lead with.",
                                color = Color.White.copy(alpha = 0.86f),
                                style = MaterialTheme.typography.bodyMedium,
                            )
                        }
                    }
                }
                item {
                    SoftCard {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            StudioField(state.jobTitle, vm::onTitle, "Job title (optional)")
                            StudioField(state.company, vm::onCompany, "Company (optional)")
                            StudioField(
                                value = state.jdText,
                                onChange = vm::onJd,
                                placeholder = "Paste the job description here…",
                                minLines = 6,
                                maxLines = 14,
                            )
                            HireStackPrimaryButton(
                                label = if (state.isLoading) "Generating…" else "Generate benchmark",
                                onClick = vm::generate,
                                modifier = Modifier.fillMaxWidth(),
                                enabled = !state.isLoading,
                                loading = state.isLoading,
                            )
                            state.error?.let { InlineBanner(message = it, tone = PillTone.Danger) }
                        }
                    }
                }
                state.result?.let { item { BenchmarkResultCard(it) } }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun BenchmarkResultCard(doc: BenchmarkDoc) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard {
        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
            Row(verticalAlignment = Alignment.CenterVertically) {
                Text(
                    "Benchmark result",
                    modifier = Modifier.weight(1f),
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                )
                doc.score?.let { StatusPill(text = "${it.toInt()}", tone = PillTone.Brand) }
            }
            if (!doc.job_title.isNullOrBlank() || !doc.company.isNullOrBlank()) {
                val sub = listOfNotNull(doc.job_title, doc.company).joinToString(" · ")
                Text(
                    sub,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(sub, "title and company") },
                    ),
                )
            }
            if (!doc.years_experience.isNullOrBlank()) {
                Text("Experience: ${doc.years_experience}", style = MaterialTheme.typography.bodyMedium)
            }
            doc.required_skills?.takeIf { it.isNotEmpty() }?.let { skills ->
                Text(
                    "Required",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(skills.joinToString(", "), "required skills") },
                    ),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    skills.take(8).forEach { StatusPill(text = it, tone = PillTone.Info) }
                }
            }
            doc.nice_to_have?.takeIf { it.isNotEmpty() }?.let { skills ->
                Text(
                    "Nice to have",
                    style = MaterialTheme.typography.labelLarge,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(skills.joinToString(", "), "nice-to-have skills") },
                    ),
                )
                Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                    skills.take(8).forEach { StatusPill(text = it) }
                }
            }
        }
    }
}

/* ============================================================
 *                        BUILDER
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BuilderScreen(onOpenDocument: (title: String, html: String) -> Unit = { _, _ -> }) {
    val vm: BuilderViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    val docTypes = listOf("cv" to "CV", "cover_letter" to "Cover", "portfolio" to "Portfolio", "personal_statement" to "Statement")
    val tones = listOf("professional", "warm", "bold")

    Scaffold(
        topBar = { BrandTopBar(title = "Builder", subtitle = "Spin up tailored docs") },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    GradientHeroCard(brush = BrandGradient.Aurora) {
                        Row(verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Outlined.AutoAwesome, contentDescription = null, tint = Color.White)
                            Spacer(Modifier.width(10.dp))
                            Column(Modifier.weight(1f)) {
                                Text(
                                    "Builder",
                                    color = Color.White,
                                    style = MaterialTheme.typography.titleMedium,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Text(
                                    "Pick a doc type, drop a JD, and ship.",
                                    color = Color.White.copy(alpha = 0.86f),
                                    style = MaterialTheme.typography.bodyMedium,
                                )
                            }
                        }
                    }
                }
                item {
                    SoftCard {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                                docTypes.forEachIndexed { index, (key, label) ->
                                    SegmentedButton(
                                        selected = state.docType == key,
                                        onClick = { vm.setDocType(key) },
                                        shape = SegmentedButtonDefaults.itemShape(index, docTypes.size),
                                    ) { Text(label) }
                                }
                            }
                            SingleChoiceSegmentedButtonRow(modifier = Modifier.fillMaxWidth()) {
                                tones.forEachIndexed { index, t ->
                                    SegmentedButton(
                                        selected = state.tone == t,
                                        onClick = { vm.setTone(t) },
                                        shape = SegmentedButtonDefaults.itemShape(index, tones.size),
                                    ) { Text(t.replaceFirstChar { c -> c.titlecase() }) }
                                }
                            }
                            StudioField(
                                value = state.jdText,
                                onChange = vm::setJd,
                                placeholder = "Paste a JD or notes (optional)",
                                minLines = 4,
                                maxLines = 10,
                            )
                            HireStackPrimaryButton(
                                label = if (state.isLoading) "Generating…" else "Generate document",
                                onClick = vm::generate,
                                modifier = Modifier.fillMaxWidth(),
                                enabled = !state.isLoading,
                                loading = state.isLoading,
                            )
                            state.error?.let { InlineBanner(message = it, tone = PillTone.Danger) }
                        }
                    }
                }
                state.result?.let { res ->
                    item {
                        SoftCard(onClick = { onOpenDocument(res.title ?: res.doc_type ?: "Document", res.html_content ?: "") }) {
                            Column {
                                Text(
                                    res.title ?: "Generated document",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Text(
                                    "Tap to open",
                                    style = MaterialTheme.typography.bodyMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
                if (state.history.isNotEmpty()) {
                    item { SectionHeader(title = "Recent") }
                    items(state.history, key = { it.id }) { doc ->
                        SoftCard(onClick = { onOpenDocument(doc.title ?: doc.doc_type ?: "Document", doc.html_content ?: "") }) {
                            Column {
                                Text(
                                    doc.title ?: doc.doc_type ?: "Document",
                                    style = MaterialTheme.typography.titleSmall,
                                    fontWeight = FontWeight.SemiBold,
                                )
                                Text(
                                    doc.created_at?.take(10) ?: "",
                                    style = MaterialTheme.typography.labelMedium,
                                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                                )
                            }
                        }
                    }
                }
            }
        }
    }
}

/* ============================================================
 *                       CONSULTANT
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ConsultantScreen() {
    val vm: ConsultantViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = { BrandTopBar(title = "Consultant", subtitle = "Coach + roadmaps") },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            Column(Modifier.fillMaxSize().padding(padding)) {
                TabRow(selectedTabIndex = state.tab, containerColor = Color.Transparent) {
                    Tab(
                        selected = state.tab == 0,
                        onClick = { vm.setTab(0) },
                        text = { Text("Coach") },
                    )
                    Tab(
                        selected = state.tab == 1,
                        onClick = { vm.setTab(1) },
                        text = { Text("Roadmaps") },
                    )
                }
                Spacer(Modifier.height(6.dp))
                when (state.tab) {
                    0 -> CoachPane(state, vm)
                    else -> RoadmapsPane(state, vm)
                }
            }
        }
    }
}

@Composable
private fun CoachPane(state: ConsultantState, vm: ConsultantViewModel) {
    Column(Modifier.fillMaxSize()) {
        LazyColumn(
            modifier = Modifier.weight(1f),
            contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 8.dp),
            verticalArrangement = Arrangement.spacedBy(8.dp),
            reverseLayout = true,
        ) {
            items(state.turns.reversed()) { t -> ChatBubble(t) }
            if (state.turns.isEmpty()) {
                item {
                    SoftCard {
                        Text(
                            "Ask anything — interviews, salary, career moves. " +
                                "The coach has full context of your applications.",
                            style = MaterialTheme.typography.bodyMedium,
                        )
                    }
                }
            }
        }
        state.coachError?.let {
            Box(Modifier.padding(horizontal = 20.dp)) {
                InlineBanner(message = it, tone = PillTone.Danger)
            }
        }
        Row(
            Modifier.fillMaxWidth().padding(20.dp, 8.dp, 20.dp, 16.dp),
            verticalAlignment = Alignment.Bottom,
        ) {
            StudioField(
                value = state.draft,
                onChange = vm::setDraft,
                placeholder = "Message the coach…",
                modifier = Modifier.weight(1f).wrapContentHeight(),
                minLines = 1,
                maxLines = 4,
            )
            Spacer(Modifier.width(8.dp))
            IconButton(
                onClick = { vm.send() },
                enabled = state.draft.isNotBlank() && !state.sending,
            ) { Icon(Icons.AutoMirrored.Outlined.Send, contentDescription = "Send", tint = Brand.Indigo) }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ChatBubble(turn: CoachTurn) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    val mine = turn.role == "user"
    Row(
        Modifier.fillMaxWidth(),
        horizontalArrangement = if (mine) Arrangement.End else Arrangement.Start,
    ) {
        Box(
            Modifier
                .padding(start = if (mine) 40.dp else 0.dp, end = if (mine) 0.dp else 40.dp)
        ) {
            SoftCard {
                Text(
                    turn.content,
                    style = MaterialTheme.typography.bodyMedium,
                    color = if (mine) Brand.Indigo else MaterialTheme.colorScheme.onSurface,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = {
                            clipboard.setText(AnnotatedString(turn.content))
                            haptic.confirm()
                            scope.launch { snackbar.showSnackbar(if (mine) "Copied your message" else "Copied coach reply") }
                        },
                    ),
                )
            }
        }
    }
}

@Composable
private fun RoadmapsPane(state: ConsultantState, vm: ConsultantViewModel) {
    LazyColumn(
        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
        verticalArrangement = Arrangement.spacedBy(14.dp),
    ) {
        item {
            SoftCard {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Outlined.Map, contentDescription = null, tint = Brand.Indigo)
                        Spacer(Modifier.width(8.dp))
                        Text(
                            "New roadmap",
                            style = MaterialTheme.typography.titleMedium,
                            fontWeight = FontWeight.SemiBold,
                        )
                    }
                    StudioField(state.targetRole, vm::setRole, "Target role (e.g. Senior PM)")
                    StudioField(state.targetCompany, vm::setCompany, "Target company (optional)")
                    StudioField(
                        value = state.timeframeMonths,
                        onChange = vm::setTimeframe,
                        placeholder = "Timeframe (months)",
                        keyboardOptions = KeyboardOptions(keyboardType = KeyboardType.Number),
                    )
                    HireStackPrimaryButton(
                        label = if (state.creatingRoadmap) "Drafting…" else "Generate roadmap",
                        onClick = vm::createRoadmap,
                        modifier = Modifier.fillMaxWidth(),
                        enabled = !state.creatingRoadmap,
                        loading = state.creatingRoadmap,
                    )
                    state.roadmapError?.let { InlineBanner(message = it, tone = PillTone.Danger) }
                }
            }
        }
        if (state.roadmaps.isNotEmpty()) {
            item { SectionHeader(title = "Your roadmaps") }
            items(state.roadmaps, key = { it.id }) { rm -> RoadmapCard(rm) }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun RoadmapCard(rm: CareerRoadmap) {
    val clipboard = LocalClipboardManager.current
    val snackbar = LocalSnackbar.current
    val scope = LocalAppScope.current
    val haptic = LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard {
        Column {
            val titleText = rm.target_role ?: "Roadmap"
            Text(
                titleText,
                style = MaterialTheme.typography.titleSmall,
                fontWeight = FontWeight.SemiBold,
                modifier = Modifier.combinedClickable(
                    onClick = {},
                    onLongClick = { copy(titleText, "target role") },
                ),
            )
            if (!rm.target_company.isNullOrBlank()) {
                Text(
                    rm.target_company!!,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(rm.target_company!!, "target company") },
                    ),
                )
            }
            Spacer(Modifier.height(6.dp))
            Row(horizontalArrangement = Arrangement.spacedBy(6.dp)) {
                rm.timeframe_months?.let { StatusPill(text = "${it}mo", tone = PillTone.Info) }
                rm.phases?.let { StatusPill(text = "${it.size} phases", tone = PillTone.Brand) }
            }
        }
    }
}
