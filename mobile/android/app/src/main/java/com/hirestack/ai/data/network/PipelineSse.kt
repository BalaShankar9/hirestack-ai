package com.hirestack.ai.data.network

import com.hirestack.ai.BuildConfig
import com.hirestack.ai.data.auth.TokenStore
import com.squareup.moshi.Moshi
import kotlinx.coroutines.channels.awaitClose
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.callbackFlow
import kotlinx.coroutines.flow.firstOrNull
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.Response
import okhttp3.sse.EventSource
import okhttp3.sse.EventSourceListener
import okhttp3.sse.EventSources
import javax.inject.Inject
import javax.inject.Singleton

/**
 * SSE client for the live generation pipeline. Streams progress, agent
 * activity, and stage transitions from `/api/generate/jobs/{id}/stream`.
 *
 * Emits PipelineEvent on the IO dispatcher; the consumer ViewModel collects
 * on viewModelScope and pushes into a Compose state.
 */
@Singleton
class PipelineSse @Inject constructor(
    private val client: OkHttpClient,
    private val moshi: Moshi,
    private val tokens: TokenStore,
) {
    private val baseUrl = "${BuildConfig.BACKEND_BASE_URL.trimEnd('/')}"
    private val factory = EventSources.createFactory(
        // SSE wants no read timeout — clone the shared OkHttpClient with that tuning.
        client.newBuilder().readTimeout(0, java.util.concurrent.TimeUnit.MILLISECONDS).build(),
    )
    private val mapAdapter = moshi.adapter(Map::class.java)

    fun streamJob(jobId: String): Flow<PipelineEvent> = callbackFlow {
        val token = tokens.accessToken.firstOrNull()
        val url = "$baseUrl/generate/jobs/$jobId/stream"
        val req = Request.Builder()
            .url(url)
            .header("Accept", "text/event-stream")
            .let { if (token != null) it.header("Authorization", "Bearer $token") else it }
            .build()

        val source: EventSource = factory.newEventSource(req, object : EventSourceListener() {
            override fun onEvent(eventSource: EventSource, id: String?, type: String?, data: String) {
                val parsed = runCatching { mapAdapter.fromJson(data) as? Map<*, *> }.getOrNull()
                val ev = PipelineEvent(
                    name = type ?: "message",
                    progress = (parsed?.get("progress") as? Number)?.toInt(),
                    phase = parsed?.get("phase") as? String,
                    agent = (parsed?.get("agent") ?: parsed?.get("agent_name")) as? String,
                    stage = parsed?.get("stage") as? String,
                    status = parsed?.get("status") as? String,
                    message = parsed?.get("message") as? String,
                    raw = parsed,
                )
                trySend(ev)
                if (type == "complete" || type == "error") {
                    eventSource.cancel()
                    close()
                }
            }

            override fun onFailure(eventSource: EventSource, t: Throwable?, response: Response?) {
                trySend(
                    PipelineEvent(
                        name = "error",
                        message = t?.message ?: "Stream failed (${response?.code})",
                    ),
                )
                close()
            }

            override fun onClosed(eventSource: EventSource) {
                close()
            }
        })

        awaitClose { source.cancel() }
    }
}

data class PipelineEvent(
    val name: String,
    val progress: Int? = null,
    val phase: String? = null,
    val agent: String? = null,
    val stage: String? = null,
    val status: String? = null,
    val message: String? = null,
    val raw: Map<*, *>? = null,
)
