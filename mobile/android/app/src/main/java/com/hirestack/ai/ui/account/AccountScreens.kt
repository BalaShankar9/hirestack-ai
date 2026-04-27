package com.hirestack.ai.ui.account

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
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.width
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.background
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.Badge
import androidx.compose.material.icons.outlined.Bolt
import androidx.compose.material.icons.outlined.CreditCard
import androidx.compose.material.icons.outlined.Download
import androidx.compose.material.icons.outlined.History
import androidx.compose.material.icons.outlined.Group
import androidx.compose.material.icons.outlined.VpnKey
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.AssistChip
import androidx.compose.material3.AssistChipDefaults
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.FilterChip
import androidx.compose.material3.Icon
import androidx.compose.material3.LinearProgressIndicator
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
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
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.unit.dp
import androidx.hilt.navigation.compose.hiltViewModel
import com.hirestack.ai.data.network.ApiKey
import com.hirestack.ai.data.network.AuditEvent
import com.hirestack.ai.data.network.BillingStatus
import com.hirestack.ai.data.network.ExportRecord
import com.hirestack.ai.data.network.OrgMember
import com.hirestack.ai.ui.components.BrandBackground
import com.hirestack.ai.ui.components.BrandTopBar
import com.hirestack.ai.ui.components.EmptyState
import com.hirestack.ai.ui.components.GradientHeroCard
import com.hirestack.ai.ui.components.HireStackPrimaryButton
import com.hirestack.ai.ui.components.HireStackSecondaryButton
import com.hirestack.ai.ui.components.InlineBanner
import com.hirestack.ai.ui.components.NavListItem
import com.hirestack.ai.ui.components.PillTone
import com.hirestack.ai.ui.components.SectionHeader
import com.hirestack.ai.ui.components.SkeletonList
import com.hirestack.ai.ui.components.SoftCard
import com.hirestack.ai.ui.components.StatusPill
import com.hirestack.ai.ui.components.confirm
import androidx.compose.foundation.combinedClickable
import kotlinx.coroutines.launch
import com.hirestack.ai.ui.theme.Brand
import com.hirestack.ai.ui.theme.BrandGradient

/* ============================================================
 *                      EXPORT
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ExportScreen() {
    val vm: ExportViewModel = hiltViewModel()
    val state by vm.state.collectAsState()
    val uriHandler = LocalUriHandler.current

    Scaffold(
        topBar = { BrandTopBar(title = "Exports", subtitle = "PDF & DOCX downloads") },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            PullToRefreshBox(
                isRefreshing = state.refreshing,
                onRefresh = vm::refresh,
                modifier = Modifier.fillMaxSize().padding(padding),
            ) {
                when {
                    state.isLoading && state.items.isEmpty() -> SkeletonList()
                    state.items.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        EmptyState(
                            title = "No exports yet",
                            description = "Generate a PDF or DOCX from any application to see it here.",
                            icon = Icons.Outlined.Download,
                            actionLabel = "Refresh",
                            onAction = vm::refresh,
                        )
                    }
                    else -> LazyColumn(
                        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        state.error?.let { item { InlineBanner(message = it, tone = PillTone.Warning) } }
                        items(state.items, key = { it.id }) { rec -> ExportCard(rec) { url -> uriHandler.openUri(url) } }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ExportCard(rec: ExportRecord, onOpen: (String) -> Unit) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val link = rec.download_url ?: rec.file_url
    SoftCard {
        Row(
            verticalAlignment = Alignment.CenterVertically,
            modifier = Modifier.combinedClickable(
                onClick = { if (!link.isNullOrBlank()) onOpen(link) },
                onLongClick = {
                    if (!link.isNullOrBlank()) {
                        clipboard.setText(androidx.compose.ui.text.AnnotatedString(link))
                        haptic.confirm()
                        scope.launch { snackbar.showSnackbar("Copied download link") }
                    }
                },
            ),
        ) {
            Box(
                Modifier
                    .size(40.dp)
                    .background(Brand.Indigo.copy(alpha = 0.18f), RoundedCornerShape(12.dp)),
                contentAlignment = Alignment.Center,
            ) { Icon(Icons.Outlined.Download, contentDescription = null, tint = Brand.Indigo) }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    rec.doc_type ?: "Document",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    "${(rec.format ?: "pdf").uppercase()} · ${rec.created_at?.take(10) ?: ""}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            StatusPill(text = "Open", tone = PillTone.Brand)
        }
    }
}

/* ============================================================
 *                      ACCOUNT (hub)
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AccountScreen(
    onOpenBilling: () -> Unit,
    onOpenMembers: () -> Unit,
    onOpenApiKeys: () -> Unit,
    onOpenAudit: () -> Unit,
    onOpenExports: () -> Unit,
    onSignOut: () -> Unit,
) {
    val vm: AccountViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = { BrandTopBar(title = "Account", subtitle = "You, your plan, your team") },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            if (state.isLoading) {
                Box(Modifier.fillMaxSize().padding(padding)) { SkeletonList() }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    item { ProfileHero(state) }
                    state.billing?.let { item { BillingSummaryCard(it, onClick = onOpenBilling) } }
                    item {
                        SoftCard {
                            Column(verticalArrangement = Arrangement.spacedBy(2.dp)) {
                                NavListItem(title = "Billing & plan", icon = Icons.Outlined.CreditCard, onClick = onOpenBilling)
                                NavListItem(title = "Team members", icon = Icons.Outlined.Group, onClick = onOpenMembers)
                                NavListItem(title = "API keys", icon = Icons.Outlined.VpnKey, onClick = onOpenApiKeys)
                                NavListItem(title = "Audit log", icon = Icons.Outlined.History, onClick = onOpenAudit)
                                NavListItem(title = "Exports", icon = Icons.Outlined.Download, onClick = onOpenExports)
                            }
                        }
                    }
                    item {
                        var confirmSignOut by remember { mutableStateOf(false) }
                        val signOutHaptic = androidx.compose.ui.platform.LocalHapticFeedback.current
                        HireStackSecondaryButton(
                            label = "Sign out",
                            onClick = { confirmSignOut = true },
                            modifier = Modifier.fillMaxWidth(),
                        )
                        if (confirmSignOut) {
                            androidx.compose.material3.AlertDialog(
                                onDismissRequest = { confirmSignOut = false },
                                title = { Text("Sign out?") },
                                text = { Text("You'll need to sign in again to access your account.") },
                                confirmButton = {
                                    androidx.compose.material3.TextButton(onClick = {
                                        confirmSignOut = false
                                        signOutHaptic.confirm()
                                        onSignOut()
                                    }) { Text("Sign out") }
                                },
                                dismissButton = {
                                    androidx.compose.material3.TextButton(onClick = { confirmSignOut = false }) { Text("Cancel") }
                                },
                            )
                        }
                    }
                    state.error?.let { item { InlineBanner(message = it, tone = PillTone.Warning) } }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ProfileHero(state: AccountState) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(androidx.compose.ui.text.AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    GradientHeroCard(brush = BrandGradient.HeroDark) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(56.dp)
                    .background(Color.White.copy(alpha = 0.18f), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Icon(
                    Icons.Outlined.Badge,
                    contentDescription = null,
                    tint = Color.White,
                )
            }
            Spacer(Modifier.width(14.dp))
            Column(Modifier.weight(1f)) {
                val displayName = state.me?.full_name ?: state.me?.email ?: "Signed in"
                Text(
                    displayName,
                    color = Color.White,
                    style = MaterialTheme.typography.titleMedium,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(displayName, "name") },
                    ),
                )
                val emailVal = state.me?.email ?: ""
                Text(
                    emailVal,
                    color = Color.White.copy(alpha = 0.78f),
                    style = MaterialTheme.typography.bodyMedium,
                    modifier = if (emailVal.isNotBlank()) Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(emailVal, "email") },
                    ) else Modifier,
                )
            }
            state.me?.role?.let { StatusPill(text = it.uppercase(), tone = PillTone.Brand) }
        }
    }
}

@Composable
private fun BillingSummaryCard(b: BillingStatus, onClick: () -> Unit) {
    SoftCard(onClick = onClick) {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.Bolt, contentDescription = null, tint = Brand.Indigo)
            Spacer(Modifier.width(10.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    "Plan: ${(b.plan ?: "free").replaceFirstChar { it.titlecase() }}",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                )
                Text(
                    "Status: ${b.status ?: "—"}${if (b.testing_mode == true) " · TESTING" else ""}",
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                )
            }
            StatusPill(
                text = (b.status ?: "active").uppercase(),
                tone = when (b.status) {
                    "past_due" -> PillTone.Danger
                    "trialing" -> PillTone.Info
                    else -> PillTone.Success
                },
            )
        }
    }
}

/* ============================================================
 *                      BILLING
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun BillingScreen(onBack: () -> Unit) {
    val vm: BillingViewModel = hiltViewModel()
    val state by vm.state.collectAsState()
    val uriHandler = LocalUriHandler.current

    LaunchedEffect(state.portalUrl) {
        state.portalUrl?.let {
            uriHandler.openUri(it)
            vm.consumePortal()
        }
    }

    Scaffold(
        topBar = { BrandTopBar(title = "Billing", subtitle = "Plan, seats, usage", onBack = onBack) },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            if (state.isLoading) {
                Box(Modifier.fillMaxSize().padding(padding)) { SkeletonList() }
            } else {
                LazyColumn(
                    modifier = Modifier.fillMaxSize().padding(padding),
                    contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                    verticalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    state.status?.let { s ->
                        item { BillingHero(s) }
                        item { UsageCard(s) }
                    }
                    item {
                        HireStackPrimaryButton(
                            label = "Open billing portal",
                            onClick = vm::openPortal,
                            modifier = Modifier.fillMaxWidth(),
                        )
                    }
                    state.error?.let { item { InlineBanner(message = it, tone = PillTone.Danger) } }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun BillingHero(s: BillingStatus) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val planText = "${(s.plan ?: "free").replaceFirstChar { it.titlecase() }} plan"
    val statusText = "Status: ${s.status ?: "—"}" + (s.period_end?.let { " · renews $it" }.orEmpty())
    val full = "$planText\n$statusText"
    GradientHeroCard(brush = BrandGradient.Aurora) {
        Column(
            modifier = androidx.compose.ui.Modifier.combinedClickable(
                onClick = {},
                onLongClick = {
                    clipboard.setText(androidx.compose.ui.text.AnnotatedString(full))
                    haptic.confirm()
                    scope.launch { snackbar.showSnackbar("Copied billing summary") }
                },
            ),
        ) {
            Text(
                planText,
                color = Color.White,
                style = MaterialTheme.typography.titleLarge,
                fontWeight = FontWeight.Bold,
            )
            Spacer(Modifier.height(6.dp))
            Text(
                statusText,
                color = Color.White.copy(alpha = 0.86f),
                style = MaterialTheme.typography.bodyMedium,
            )
            if (s.testing_mode == true) {
                Spacer(Modifier.height(8.dp))
                StatusPill(text = "TESTING MODE", tone = PillTone.Warning)
            }
        }
    }
}

@Composable
private fun UsageCard(s: BillingStatus) {
    SoftCard {
        Column(verticalArrangement = Arrangement.spacedBy(12.dp)) {
            Text("Usage", style = MaterialTheme.typography.titleSmall, fontWeight = FontWeight.SemiBold)
            UsageRow("Seats", s.seats_used, s.seats)
            UsageRow("Applications", s.applications_used, s.applications_limit)
            UsageRow("Exports", s.exports_used, s.exports_limit)
        }
    }
}

@Composable
private fun UsageRow(label: String, used: Int?, limit: Int?) {
    val u = used ?: 0
    val l = limit ?: 0
    Column {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Text(label, modifier = Modifier.weight(1f), style = MaterialTheme.typography.bodyMedium)
            Text("$u / ${if (l > 0) l.toString() else "∞"}", style = MaterialTheme.typography.labelLarge)
        }
        if (l > 0) {
            Spacer(Modifier.height(6.dp))
            LinearProgressIndicator(
                progress = { (u.toFloat() / l.toFloat()).coerceIn(0f, 1f) },
                modifier = Modifier.fillMaxWidth(),
            )
        }
    }
}

/* ============================================================
 *                      MEMBERS
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun MembersScreen(onBack: () -> Unit) {
    val vm: MembersViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = { BrandTopBar(title = "Members", subtitle = "Workspace teammates", onBack = onBack) },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            Column(Modifier.fillMaxSize().padding(padding)) {
                if (state.orgs.size > 1) {
                    Row(
                        Modifier.fillMaxWidth().padding(20.dp, 4.dp, 20.dp, 0.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        state.orgs.take(3).forEach { org ->
                            FilterChip(
                                selected = state.selectedOrgId == org.id,
                                onClick = { vm.selectOrg(org.id) },
                                label = { Text(org.name ?: "Org") },
                            )
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                }
                when {
                    state.isLoading -> SkeletonList()
                    state.orgs.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        EmptyState(
                            title = "No organizations",
                            description = "Create a workspace to invite teammates.",
                            icon = Icons.Outlined.Group,
                        )
                    }
                    state.members.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        EmptyState(
                            title = "No members yet",
                            description = "Invite teammates from your team dashboard.",
                            icon = Icons.Outlined.Group,
                            actionLabel = "Refresh",
                            onAction = { state.selectedOrgId?.let { vm.selectOrg(it) } },
                        )
                    }
                    else -> LazyColumn(
                        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                        verticalArrangement = Arrangement.spacedBy(12.dp),
                    ) {
                        state.error?.let { item { InlineBanner(message = it, tone = PillTone.Warning) } }
                        items(state.members, key = { it.id ?: it.user_id ?: it.email ?: "" }) { m -> MemberCard(m) }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun MemberCard(m: OrgMember) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val copyEmail: () -> Unit = {
        val e = m.email
        if (!e.isNullOrBlank()) {
            clipboard.setText(androidx.compose.ui.text.AnnotatedString(e))
            haptic.confirm()
            scope.launch { snackbar.showSnackbar("Copied email") }
        }
    }
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Box(
                Modifier
                    .size(40.dp)
                    .background(Brand.Indigo.copy(alpha = 0.18f), CircleShape),
                contentAlignment = Alignment.Center,
            ) {
                Text(
                    (m.full_name ?: m.email ?: "?").take(1).uppercase(),
                    color = Brand.Indigo,
                    fontWeight = FontWeight.Bold,
                )
            }
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                Text(
                    m.full_name ?: m.email ?: "Member",
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.combinedClickable(onClick = {}, onLongClick = copyEmail),
                )
                if (!m.email.isNullOrBlank() && m.full_name != null) {
                    Text(
                        m.email!!,
                        style = MaterialTheme.typography.bodyMedium,
                        color = MaterialTheme.colorScheme.onSurfaceVariant,
                        modifier = Modifier.combinedClickable(onClick = {}, onLongClick = copyEmail),
                    )
                }
            }
            m.role?.let { StatusPill(text = it.uppercase(), tone = PillTone.Brand) }
        }
    }
}

/* ============================================================
 *                      API KEYS
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun ApiKeysScreen(onBack: () -> Unit) {
    val vm: ApiKeysViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = { BrandTopBar(title = "API keys", subtitle = "Programmatic access", onBack = onBack) },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            LazyColumn(
                modifier = Modifier.fillMaxSize().padding(padding),
                contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                verticalArrangement = Arrangement.spacedBy(14.dp),
            ) {
                item {
                    SoftCard {
                        Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                            Text(
                                "New key",
                                style = MaterialTheme.typography.titleSmall,
                                fontWeight = FontWeight.SemiBold,
                            )
                            OutlinedTextField(
                                value = state.newKeyName,
                                onValueChange = vm::setName,
                                modifier = Modifier.fillMaxWidth(),
                                placeholder = { Text("Key name (e.g. CI Bot)") },
                                shape = RoundedCornerShape(16.dp),
                                singleLine = true,
                                keyboardOptions = androidx.compose.foundation.text.KeyboardOptions(imeAction = androidx.compose.ui.text.input.ImeAction.Done),
                                keyboardActions = androidx.compose.foundation.text.KeyboardActions(onDone = {
                                    if (state.newKeyName.isNotBlank() && !state.creating) vm.create()
                                }),
                                colors = TextFieldDefaults.colors(
                                    focusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
                                    unfocusedContainerColor = MaterialTheme.colorScheme.surfaceContainerLow,
                                ),
                            )
                            HireStackPrimaryButton(
                                label = if (state.creating) "Creating…" else "Create key",
                                onClick = vm::create,
                                modifier = Modifier.fillMaxWidth(),
                                enabled = !state.creating,
                                loading = state.creating,
                            )
                            state.error?.let { InlineBanner(message = it, tone = PillTone.Danger) }
                        }
                    }
                }
                item { SectionHeader(title = "Keys") }
                if (state.isLoading && state.keys.isEmpty()) {
                    item { SkeletonList(rows = 3) }
                } else if (state.keys.isEmpty()) {
                    item {
                        EmptyState(
                            title = "No API keys yet",
                            description = "Create a key above to start automating.",
                            icon = Icons.Outlined.VpnKey,
                            actionLabel = "Refresh",
                            onAction = vm::load,
                        )
                    }
                } else {
                    items(state.keys, key = { it.id }) { k -> ApiKeyCard(k, onRevoke = { vm.revoke(k.id) }) }
                }
            }
        }
    }

    state.justCreated?.let { created ->
        val revealClipboard = androidx.compose.ui.platform.LocalClipboardManager.current
        val revealSnackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
        val revealScope = com.hirestack.ai.ui.components.LocalAppScope.current
        val revealHaptic = androidx.compose.ui.platform.LocalHapticFeedback.current
        androidx.compose.runtime.LaunchedEffect(created.id) {
            revealSnackbar.showSnackbar("Key created — copy it now, it won't be shown again")
        }
        AlertDialog(
            onDismissRequest = vm::dismissCreated,
            confirmButton = { TextButton(onClick = vm::dismissCreated) { Text("Got it") } },
            dismissButton = {
                TextButton(onClick = {
                    revealClipboard.setText(androidx.compose.ui.text.AnnotatedString(created.key))
                    revealHaptic.confirm()
                    revealScope.launch { revealSnackbar.showSnackbar("Key copied to clipboard") }
                }) { Text("Copy") }
            },
            title = { Text("Save this key now") },
            text = {
                Column {
                    Text("This is the only time the full key will be shown.")
                    Spacer(Modifier.height(8.dp))
                    Text(
                        created.key,
                        style = MaterialTheme.typography.bodySmall,
                        fontWeight = FontWeight.SemiBold,
                    )
                }
            },
        )
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun ApiKeyCard(k: ApiKey, onRevoke: () -> Unit) {
    var confirmRevoke by remember { mutableStateOf(false) }
    val revokeHaptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val appScope = com.hirestack.ai.ui.components.LocalAppScope.current
    val copyHaptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.VpnKey, contentDescription = null, tint = Brand.Indigo)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                val keyName = k.name ?: "Key"
                Text(
                    keyName,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = {
                            clipboard.setText(androidx.compose.ui.text.AnnotatedString(keyName))
                            copyHaptic.confirm()
                            appScope.launch { snackbar.showSnackbar("Copied key name") }
                        },
                    ),
                )
                val prefixText = "${k.prefix ?: "sk_***"} · ${k.created_at?.take(10) ?: ""}"
                Text(
                    prefixText,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = {
                            val pfx = k.prefix
                            if (!pfx.isNullOrBlank()) {
                                clipboard.setText(androidx.compose.ui.text.AnnotatedString(pfx))
                                copyHaptic.confirm()
                                appScope.launch { snackbar.showSnackbar("Copied key prefix") }
                            }
                        },
                    ),
                )
            }
            if (k.revoked_at == null) {
                AssistChip(
                    onClick = { confirmRevoke = true },
                    label = { Text("Revoke") },
                    colors = AssistChipDefaults.assistChipColors(labelColor = Brand.Indigo),
                )
            } else {
                StatusPill(text = "REVOKED", tone = PillTone.Danger)
            }
        }
    }
    if (confirmRevoke) {
        AlertDialog(
            onDismissRequest = { confirmRevoke = false },
            title = { Text("Revoke this key?") },
            text = { Text("Any service using \"${k.name ?: "this key"}\" will lose access immediately. This can't be undone.") },
            confirmButton = {
                TextButton(
                    onClick = { confirmRevoke = false; revokeHaptic.confirm(); onRevoke() },
                    colors = ButtonDefaults.textButtonColors(contentColor = Brand.Danger),
                ) { Text("Revoke") }
            },
            dismissButton = {
                TextButton(onClick = { confirmRevoke = false }) { Text("Cancel") }
            },
        )
    }
}

/* ============================================================
 *                      AUDIT
 * ============================================================ */

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun AuditScreen(onBack: () -> Unit) {
    val vm: AuditViewModel = hiltViewModel()
    val state by vm.state.collectAsState()

    Scaffold(
        topBar = { BrandTopBar(title = "Audit log", subtitle = "Workspace activity", onBack = onBack) },
        containerColor = Color.Transparent,
    ) { padding ->
        BrandBackground {
            Column(Modifier.fillMaxSize().padding(padding)) {
                if (state.orgs.size > 1) {
                    Row(
                        Modifier.fillMaxWidth().padding(20.dp, 4.dp, 20.dp, 0.dp),
                        horizontalArrangement = Arrangement.spacedBy(8.dp),
                    ) {
                        state.orgs.take(3).forEach { org ->
                            FilterChip(
                                selected = state.selectedOrgId == org.id,
                                onClick = { vm.selectOrg(org.id) },
                                label = { Text(org.name ?: "Org") },
                            )
                        }
                    }
                    Spacer(Modifier.height(8.dp))
                }
                when {
                    state.isLoading -> SkeletonList()
                    state.events.isEmpty() -> Box(Modifier.fillMaxSize(), contentAlignment = Alignment.Center) {
                        EmptyState(
                            title = "No activity",
                            description = "Workspace events will appear here.",
                            icon = Icons.Outlined.History,
                            actionLabel = "Refresh",
                            onAction = { state.selectedOrgId?.let { vm.selectOrg(it) } },
                        )
                    }
                    else -> LazyColumn(
                        contentPadding = PaddingValues(20.dp, 8.dp, 20.dp, 32.dp),
                        verticalArrangement = Arrangement.spacedBy(10.dp),
                    ) {
                        state.error?.let { item { InlineBanner(message = it, tone = PillTone.Warning) } }
                        items(state.events, key = { it.id ?: (it.event ?: "") + (it.created_at ?: "") }) { e -> AuditCard(e) }
                    }
                }
            }
        }
    }
}

@OptIn(androidx.compose.foundation.ExperimentalFoundationApi::class)
@Composable
private fun AuditCard(e: AuditEvent) {
    val clipboard = androidx.compose.ui.platform.LocalClipboardManager.current
    val snackbar = com.hirestack.ai.ui.components.LocalSnackbar.current
    val scope = com.hirestack.ai.ui.components.LocalAppScope.current
    val haptic = androidx.compose.ui.platform.LocalHapticFeedback.current
    val copy: (String, String) -> Unit = { value, label ->
        clipboard.setText(androidx.compose.ui.text.AnnotatedString(value))
        haptic.confirm()
        scope.launch { snackbar.showSnackbar("Copied $label") }
    }
    SoftCard {
        Row(verticalAlignment = Alignment.CenterVertically) {
            Icon(Icons.Outlined.History, contentDescription = null, tint = Brand.Indigo)
            Spacer(Modifier.width(12.dp))
            Column(Modifier.weight(1f)) {
                val eventText = e.event ?: "Event"
                Text(
                    eventText,
                    style = MaterialTheme.typography.titleSmall,
                    fontWeight = FontWeight.SemiBold,
                    modifier = Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(eventText, "event") },
                    ),
                )
                val sub = listOfNotNull(e.actor, e.target).joinToString(" → ")
                Text(
                    sub,
                    style = MaterialTheme.typography.bodyMedium,
                    color = MaterialTheme.colorScheme.onSurfaceVariant,
                    modifier = if (sub.isNotBlank()) Modifier.combinedClickable(
                        onClick = {},
                        onLongClick = { copy(sub, "actor → target") },
                    ) else Modifier,
                )
            }
            Text(
                e.created_at?.take(10) ?: "",
                style = MaterialTheme.typography.labelSmall,
                color = MaterialTheme.colorScheme.onSurfaceVariant,
            )
        }
    }
}
