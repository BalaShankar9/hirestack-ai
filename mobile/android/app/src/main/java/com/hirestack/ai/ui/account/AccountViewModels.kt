package com.hirestack.ai.ui.account

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.ApiKey
import com.hirestack.ai.data.network.AuditEvent
import com.hirestack.ai.data.network.BillingStatus
import com.hirestack.ai.data.network.CreateApiKeyRequest
import com.hirestack.ai.data.network.CreateApiKeyResponse
import com.hirestack.ai.data.network.ExportRecord
import com.hirestack.ai.data.network.ExportRequest
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.MeResponse
import com.hirestack.ai.data.network.OrgMember
import com.hirestack.ai.data.network.Organization
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.async
import kotlinx.coroutines.coroutineScope
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

/* ---------------------- Export ---------------------- */

data class ExportState(
    val isLoading: Boolean = true,
    val refreshing: Boolean = false,
    val items: List<ExportRecord> = emptyList(),
    val error: String? = null,
    val creating: Boolean = false,
    val createError: String? = null,
)

@HiltViewModel
class ExportViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(ExportState())
    val state: StateFlow<ExportState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listExports()
                _state.value = _state.value.copy(isLoading = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    fun refresh() {
        _state.value = _state.value.copy(refreshing = true)
        viewModelScope.launch {
            try {
                val items = api.listExports()
                _state.value = _state.value.copy(refreshing = false, items = items, error = null)
            } catch (e: Exception) {
                _state.value = _state.value.copy(refreshing = false, error = e.message)
            }
        }
    }

    fun createExport(applicationId: String, docType: String, format: String) {
        _state.value = _state.value.copy(creating = true, createError = null)
        viewModelScope.launch {
            try {
                api.createExport(ExportRequest(applicationId, docType, format))
                _state.value = _state.value.copy(creating = false)
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(creating = false, createError = e.message)
            }
        }
    }
}

/* ---------------------- Account hub ---------------------- */

data class AccountState(
    val isLoading: Boolean = true,
    val me: MeResponse? = null,
    val billing: BillingStatus? = null,
    val orgs: List<Organization> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class AccountViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(AccountState())
    val state: StateFlow<AccountState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val next = coroutineScope {
                    val me = async { runCatching { api.me() }.getOrNull() }
                    val billing = async { runCatching { api.billingStatus() }.getOrNull() }
                    val orgs = async { runCatching { api.listOrgs() }.getOrDefault(emptyList()) }
                    AccountState(
                        isLoading = false,
                        me = me.await(),
                        billing = billing.await(),
                        orgs = orgs.await(),
                    )
                }
                _state.value = next
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }
}

/* ---------------------- Billing ---------------------- */

data class BillingState(
    val isLoading: Boolean = true,
    val status: BillingStatus? = null,
    val portalUrl: String? = null,
    val error: String? = null,
)

@HiltViewModel
class BillingViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(BillingState())
    val state: StateFlow<BillingState> = _state.asStateFlow()

    init { load() }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val s = api.billingStatus()
                _state.value = _state.value.copy(isLoading = false, status = s)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    fun openPortal() {
        viewModelScope.launch {
            runCatching { api.billingPortal() }
                .onSuccess { _state.value = _state.value.copy(portalUrl = it.url) }
                .onFailure { _state.value = _state.value.copy(error = it.message) }
        }
    }

    fun consumePortal() { _state.value = _state.value.copy(portalUrl = null) }
}

/* ---------------------- Members ---------------------- */

data class MembersState(
    val isLoading: Boolean = true,
    val orgs: List<Organization> = emptyList(),
    val selectedOrgId: String? = null,
    val members: List<OrgMember> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class MembersViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(MembersState())
    val state: StateFlow<MembersState> = _state.asStateFlow()

    init { loadOrgs() }

    private fun loadOrgs() {
        viewModelScope.launch {
            try {
                val orgs = api.listOrgs()
                val first = orgs.firstOrNull()?.id
                _state.value = _state.value.copy(orgs = orgs)
                first?.let { selectOrg(it) } ?: run {
                    _state.value = _state.value.copy(isLoading = false)
                }
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    fun selectOrg(id: String) {
        _state.value = _state.value.copy(selectedOrgId = id, isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val members = api.listOrgMembers(id)
                _state.value = _state.value.copy(isLoading = false, members = members)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }
}

/* ---------------------- API Keys ---------------------- */

data class ApiKeysState(
    val isLoading: Boolean = true,
    val keys: List<ApiKey> = emptyList(),
    val newKeyName: String = "",
    val creating: Boolean = false,
    val justCreated: CreateApiKeyResponse? = null,
    val error: String? = null,
)

@HiltViewModel
class ApiKeysViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(ApiKeysState())
    val state: StateFlow<ApiKeysState> = _state.asStateFlow()

    init { load() }

    fun setName(v: String) { _state.value = _state.value.copy(newKeyName = v) }
    fun dismissCreated() { _state.value = _state.value.copy(justCreated = null, newKeyName = "") }

    fun load() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val keys = api.listApiKeys()
                _state.value = _state.value.copy(isLoading = false, keys = keys)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    fun create() {
        val name = _state.value.newKeyName.trim()
        if (name.isBlank()) {
            _state.value = _state.value.copy(error = "Name is required")
            return
        }
        _state.value = _state.value.copy(creating = true, error = null)
        viewModelScope.launch {
            try {
                val res = api.createApiKey(CreateApiKeyRequest(name))
                _state.value = _state.value.copy(creating = false, justCreated = res)
                load()
            } catch (e: Exception) {
                _state.value = _state.value.copy(creating = false, error = e.message)
            }
        }
    }

    fun revoke(id: String) {
        viewModelScope.launch {
            runCatching { api.revokeApiKey(id) }
                .onSuccess { load() }
                .onFailure { _state.value = _state.value.copy(error = it.message ?: "Failed to revoke key") }
        }
    }
}

/* ---------------------- Audit ---------------------- */

data class AuditState(
    val isLoading: Boolean = true,
    val orgs: List<Organization> = emptyList(),
    val selectedOrgId: String? = null,
    val events: List<AuditEvent> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class AuditViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {
    private val _state = MutableStateFlow(AuditState())
    val state: StateFlow<AuditState> = _state.asStateFlow()

    init { loadOrgs() }

    private fun loadOrgs() {
        viewModelScope.launch {
            try {
                val orgs = api.listOrgs()
                val first = orgs.firstOrNull()?.id
                _state.value = _state.value.copy(orgs = orgs)
                first?.let { selectOrg(it) } ?: run { _state.value = _state.value.copy(isLoading = false) }
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }

    fun selectOrg(id: String) {
        _state.value = _state.value.copy(selectedOrgId = id, isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val events = api.listOrgAudit(id)
                _state.value = _state.value.copy(isLoading = false, events = events)
            } catch (e: Exception) {
                _state.value = _state.value.copy(isLoading = false, error = e.message)
            }
        }
    }
}
