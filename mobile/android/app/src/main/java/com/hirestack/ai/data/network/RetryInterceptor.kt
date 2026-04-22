package com.hirestack.ai.data.network

import okhttp3.Interceptor
import okhttp3.Response
import java.io.IOException
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Retries idempotent requests on transient failures.
 *
 * Retries on:
 *  - IOException (connect timeout, read timeout, dropped socket)
 *  - HTTP 502 / 503 / 504 (Railway cold starts, brief gateway hiccups)
 *
 * Skipped for non-idempotent verbs (POST/PUT/PATCH/DELETE) so we never replay
 * a write that may have partially succeeded server-side.
 */
@Singleton
class RetryInterceptor @Inject constructor() : Interceptor {

    private val maxAttempts = 3
    private val backoffMs = longArrayOf(0, 400, 1200)

    override fun intercept(chain: Interceptor.Chain): Response {
        val request = chain.request()
        val isIdempotent = request.method.equals("GET", ignoreCase = true) ||
            request.method.equals("HEAD", ignoreCase = true)

        if (!isIdempotent) {
            return chain.proceed(request)
        }

        var lastIo: IOException? = null
        var lastResponse: Response? = null

        for (attempt in 0 until maxAttempts) {
            if (attempt > 0) {
                Thread.sleep(backoffMs[attempt.coerceAtMost(backoffMs.lastIndex)])
                lastResponse?.close()
                lastResponse = null
            }
            try {
                val response = chain.proceed(request)
                if (response.code in setOf(502, 503, 504) && attempt < maxAttempts - 1) {
                    lastResponse = response
                    continue
                }
                return response
            } catch (e: IOException) {
                lastIo = e
                if (attempt == maxAttempts - 1) throw e
            }
        }
        return lastResponse ?: throw (lastIo ?: IOException("Request failed"))
    }
}
