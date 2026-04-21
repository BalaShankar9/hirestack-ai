package com.hirestack.ai.ui.profiles

import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.hirestack.ai.data.network.HireStackApi
import com.hirestack.ai.data.network.Profile
import dagger.hilt.android.lifecycle.HiltViewModel
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.launch
import javax.inject.Inject

data class ProfilesState(
    val isLoading: Boolean = false,
    val items: List<Profile> = emptyList(),
    val error: String? = null,
)

@HiltViewModel
class ProfilesViewModel @Inject constructor(
    private val api: HireStackApi,
) : ViewModel() {

    private val _state = MutableStateFlow(ProfilesState(isLoading = true))
    val state: StateFlow<ProfilesState> = _state.asStateFlow()

    init {
        refresh()
    }

    fun refresh() {
        _state.value = _state.value.copy(isLoading = true, error = null)
        viewModelScope.launch {
            try {
                val items = api.listProfiles()
                _state.value = ProfilesState(isLoading = false, items = items)
            } catch (e: Exception) {
                _state.value = _state.value.copy(
                    isLoading = false,
                    error = e.message ?: "Failed to load profiles",
                )
            }
        }
    }

    fun setPrimary(id: String) {
        viewModelScope.launch {
            try {
                api.setPrimaryProfile(id)
                refresh()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Failed to set primary")
            }
        }
    }

    fun delete(id: String) {
        viewModelScope.launch {
            try {
                api.deleteProfile(id)
                refresh()
            } catch (e: Exception) {
                _state.value = _state.value.copy(error = e.message ?: "Failed to delete")
            }
        }
    }
}
