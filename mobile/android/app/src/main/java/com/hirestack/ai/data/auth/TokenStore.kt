package com.hirestack.ai.data.auth

import android.content.Context
import androidx.datastore.preferences.core.edit
import androidx.datastore.preferences.core.stringPreferencesKey
import androidx.datastore.preferences.preferencesDataStore
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.first
import kotlinx.coroutines.flow.map
import javax.inject.Inject
import javax.inject.Singleton

private val Context.authDataStore by preferencesDataStore(name = "hirestack_auth")

@Singleton
class TokenStore @Inject constructor(
    @ApplicationContext private val ctx: Context,
) {
    private val accessKey = stringPreferencesKey("access_token")
    private val refreshKey = stringPreferencesKey("refresh_token")
    private val emailKey = stringPreferencesKey("email")

    val accessToken: Flow<String?> = ctx.authDataStore.data.map { it[accessKey] }
    val email: Flow<String?> = ctx.authDataStore.data.map { it[emailKey] }

    suspend fun save(access: String, refresh: String?, email: String?) {
        ctx.authDataStore.edit {
            it[accessKey] = access
            if (refresh != null) it[refreshKey] = refresh
            if (email != null) it[emailKey] = email
        }
    }

    suspend fun clear() {
        ctx.authDataStore.edit { it.clear() }
    }

    suspend fun snapshotAccess(): String? =
        ctx.authDataStore.data.map { it[accessKey] }.first()
}
