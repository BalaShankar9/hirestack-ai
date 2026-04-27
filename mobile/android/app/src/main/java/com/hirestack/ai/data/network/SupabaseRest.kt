package com.hirestack.ai.data.network

import com.hirestack.ai.BuildConfig
import com.hirestack.ai.data.auth.TokenStore
import com.squareup.moshi.Moshi
import com.squareup.moshi.Types
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.flow.firstOrNull
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Direct Supabase PostgREST client — used for tables the FastAPI backend
 * doesn't proxy (applications, evidence_items, generation_job_events).
 *
 * Mirrors how the web frontend reads these tables: anon key + user JWT in the
 * Authorization header → RLS policies enforce access.
 *
 * This is intentionally a thin shim, not a generic SDK. Each method returns
 * a typed list/object using Moshi — adding a new table is a one-method addition.
 */
@Singleton
class SupabaseRest @Inject constructor(
    private val client: OkHttpClient,
    private val moshi: Moshi,
    private val tokens: TokenStore,
) {
    private val baseUrl = "${BuildConfig.SUPABASE_URL.trimEnd('/')}/rest/v1"
    private val anonKey = BuildConfig.SUPABASE_ANON_KEY

    private suspend fun request(
        path: String,
        method: String = "GET",
        body: String? = null,
        prefer: String? = null,
    ): String = withContext(Dispatchers.IO) {
        val token = tokens.accessToken.firstOrNull()
        val builder = Request.Builder()
            .url("$baseUrl/$path")
            .header("apikey", anonKey)
            .header("Authorization", "Bearer ${token ?: anonKey}")
            .header("Accept", "application/json")
        if (prefer != null) builder.header("Prefer", prefer)
        when (method) {
            "GET" -> builder.get()
            "POST" -> builder.post((body ?: "{}").toRequestBody("application/json".toMediaType()))
            "PATCH" -> builder.patch((body ?: "{}").toRequestBody("application/json".toMediaType()))
            "DELETE" -> builder.delete()
        }
        client.newCall(builder.build()).execute().use { resp ->
            val txt = resp.body?.string().orEmpty()
            if (!resp.isSuccessful) {
                throw SupabaseRestException(resp.code, txt.take(500))
            }
            txt
        }
    }

    /* ---- Applications ---- */

    suspend fun listApplications(limit: Int = 50): List<Application> {
        val raw = request("applications?select=*&order=updated_at.desc&limit=$limit")
        val type = Types.newParameterizedType(List::class.java, Application::class.java)
        return moshi.adapter<List<Application>>(type).fromJson(raw) ?: emptyList()
    }

    suspend fun getApplication(id: String): Application? {
        val raw = request("applications?select=*&id=eq.$id&limit=1")
        val type = Types.newParameterizedType(List::class.java, Application::class.java)
        return moshi.adapter<List<Application>>(type).fromJson(raw)?.firstOrNull()
    }

    suspend fun createApplication(req: CreateApplicationRequest): Application {
        val adapter = moshi.adapter(CreateApplicationRequest::class.java)
        val body = adapter.toJson(req)
        val raw = request(
            "applications?select=*",
            method = "POST",
            body = body,
            prefer = "return=representation",
        )
        val type = Types.newParameterizedType(List::class.java, Application::class.java)
        return moshi.adapter<List<Application>>(type).fromJson(raw)?.firstOrNull()
            ?: throw SupabaseRestException(500, "Empty response")
    }

    suspend fun deleteApplication(id: String) {
        request("applications?id=eq.$id", method = "DELETE")
    }

    /* ---- Evidence items ---- */

    suspend fun listEvidence(limit: Int = 100, applicationId: String? = null): List<EvidenceItem> {
        val filter = applicationId?.let { "&application_id=eq.$it" } ?: ""
        val raw = request("evidence_items?select=*&order=created_at.desc&limit=$limit$filter")
        val type = Types.newParameterizedType(List::class.java, EvidenceItem::class.java)
        return moshi.adapter<List<EvidenceItem>>(type).fromJson(raw) ?: emptyList()
    }

    /* ---- Generation job events (used for SSE-fallback polling) ---- */

    suspend fun listGenerationEvents(jobId: String, sinceSeq: Int = 0): List<GenerationJobEvent> {
        val raw = request(
            "generation_job_events?select=*&job_id=eq.$jobId" +
                "&sequence_no=gt.$sinceSeq&order=sequence_no.asc",
        )
        val type = Types.newParameterizedType(List::class.java, GenerationJobEvent::class.java)
        return moshi.adapter<List<GenerationJobEvent>>(type).fromJson(raw) ?: emptyList()
    }
}

class SupabaseRestException(val code: Int, override val message: String) : RuntimeException(message)
