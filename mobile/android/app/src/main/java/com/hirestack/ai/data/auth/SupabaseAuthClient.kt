package com.hirestack.ai.data.auth

import com.hirestack.ai.BuildConfig
import io.github.jan.supabase.SupabaseClient
import io.github.jan.supabase.createSupabaseClient
import io.github.jan.supabase.gotrue.Auth
import io.github.jan.supabase.gotrue.auth
import io.github.jan.supabase.gotrue.providers.builtin.Email
import javax.inject.Inject
import javax.inject.Singleton

@Singleton
class SupabaseAuthClient @Inject constructor(
    private val tokenStore: TokenStore,
) {
    val client: SupabaseClient = createSupabaseClient(
        supabaseUrl = BuildConfig.SUPABASE_URL,
        supabaseKey = BuildConfig.SUPABASE_ANON_KEY,
    ) { install(Auth) }

    suspend fun signIn(email: String, password: String) {
        client.auth.signInWith(Email) {
            this.email = email
            this.password = password
        }
        persistSession()
    }

    suspend fun signUp(email: String, password: String, fullName: String?) {
        client.auth.signUpWith(Email) {
            this.email = email
            this.password = password
        }
        // Some Supabase setups auto-login after signup; if so, persist.
        runCatching { persistSession() }
    }

    suspend fun signOut() {
        runCatching { client.auth.signOut() }
        tokenStore.clear()
    }

    private suspend fun persistSession() {
        val session = client.auth.currentSessionOrNull()
        if (session != null) {
            tokenStore.save(
                access = session.accessToken,
                refresh = session.refreshToken,
                email = session.user?.email,
            )
        }
    }
}
