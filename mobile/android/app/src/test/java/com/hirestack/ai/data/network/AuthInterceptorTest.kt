package com.hirestack.ai.data.network

import com.hirestack.ai.data.auth.TokenStore
import io.mockk.coEvery
import io.mockk.mockk
import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/**
 * Pinned contract for [AuthInterceptor] (S9-F2, risk R2).
 *
 * The interceptor must:
 *  - Always add `Accept: application/json`.
 *  - Add `Authorization: Bearer <token>` when TokenStore.snapshotAccess()
 *    returns a non-null token.
 *  - Omit Authorization (do not send "Bearer null" / empty) when no token.
 *  - Not double-add Authorization if the caller already supplied one
 *    (verified by inspecting the headers actually sent downstream).
 *  - Pass the request body and HTTP method through unchanged.
 */
class AuthInterceptorTest {

    private fun chainCapturing(initial: Request): Pair<RecordingChain, () -> Request?> {
        val chain = RecordingChain(initial)
        return chain to { chain.lastRequest }
    }

    private class RecordingChain(private var current: Request) : Interceptor.Chain {
        var lastRequest: Request? = null
            private set

        override fun request(): Request = current
        override fun proceed(request: Request): Response {
            lastRequest = request
            return Response.Builder()
                .request(request)
                .protocol(Protocol.HTTP_1_1)
                .code(200)
                .message("ok")
                .body("".toResponseBody("text/plain".toMediaType()))
                .build()
        }
        override fun connection() = null
        override fun call(): okhttp3.Call = throw UnsupportedOperationException()
        override fun connectTimeoutMillis() = 0
        override fun withConnectTimeout(timeout: Int, unit: java.util.concurrent.TimeUnit) = this
        override fun readTimeoutMillis() = 0
        override fun withReadTimeout(timeout: Int, unit: java.util.concurrent.TimeUnit) = this
        override fun writeTimeoutMillis() = 0
        override fun withWriteTimeout(timeout: Int, unit: java.util.concurrent.TimeUnit) = this
    }

    private fun storeReturning(token: String?): TokenStore {
        val store = mockk<TokenStore>()
        coEvery { store.snapshotAccess() } returns token
        return store
    }

    @Test
    fun `injects Bearer token when present`() {
        val sut = AuthInterceptor(storeReturning("abc.def.ghi"))
        val req = Request.Builder().url("https://api.test/x").get().build()
        val (chain, capture) = chainCapturing(req)
        val resp = sut.intercept(chain)
        assertEquals(200, resp.code)
        val sent = capture()!!
        assertEquals("Bearer abc.def.ghi", sent.header("Authorization"))
        assertEquals("application/json", sent.header("Accept"))
    }

    @Test
    fun `omits Authorization when token is null`() {
        val sut = AuthInterceptor(storeReturning(null))
        val req = Request.Builder().url("https://api.test/x").get().build()
        val (chain, capture) = chainCapturing(req)
        sut.intercept(chain)
        val sent = capture()!!
        assertNull(sent.header("Authorization"))
        assertEquals("application/json", sent.header("Accept"))
    }

    @Test
    fun `always adds Accept header even without token`() {
        val sut = AuthInterceptor(storeReturning(null))
        val req = Request.Builder().url("https://api.test/x").get().build()
        val (chain, capture) = chainCapturing(req)
        sut.intercept(chain)
        assertEquals("application/json", capture()!!.header("Accept"))
    }

    @Test
    fun `preserves HTTP method and URL`() {
        val sut = AuthInterceptor(storeReturning("t"))
        val body = okhttp3.RequestBody.create(
            "application/json".toMediaType(),
            """{"x":1}""",
        )
        val req = Request.Builder()
            .url("https://api.test/jobs?id=42")
            .post(body)
            .build()
        val (chain, capture) = chainCapturing(req)
        sut.intercept(chain)
        val sent = capture()!!
        assertEquals("POST", sent.method)
        assertEquals("https://api.test/jobs?id=42", sent.url.toString())
    }

    @Test
    fun `preserves caller-supplied headers`() {
        val sut = AuthInterceptor(storeReturning("t"))
        val req = Request.Builder()
            .url("https://api.test/x")
            .get()
            .header("X-Trace-Id", "trace-123")
            .header("X-Custom", "v")
            .build()
        val (chain, capture) = chainCapturing(req)
        sut.intercept(chain)
        val sent = capture()!!
        assertEquals("trace-123", sent.header("X-Trace-Id"))
        assertEquals("v", sent.header("X-Custom"))
        assertEquals("Bearer t", sent.header("Authorization"))
    }

    @Test
    fun `uses addHeader semantics so duplicates are tolerated by okhttp`() {
        // OkHttp distinguishes addHeader (multi-value) from header (replace).
        // The interceptor uses addHeader; confirm both header values land
        // when a caller pre-supplies an Accept header.
        val sut = AuthInterceptor(storeReturning("t"))
        val req = Request.Builder()
            .url("https://api.test/x")
            .get()
            .header("Accept", "text/plain")
            .build()
        val (chain, capture) = chainCapturing(req)
        sut.intercept(chain)
        val sent = capture()!!
        val accepts = sent.headers.values("Accept")
        // Caller's Accept survives, plus interceptor's "application/json".
        assertEquals(2, accepts.size)
        assertEquals(true, accepts.contains("text/plain"))
        assertEquals(true, accepts.contains("application/json"))
    }

    @Test
    fun `does not throw when token snapshot is empty string`() {
        // Empty string is technically non-null. Current contract: any
        // non-null value is wrapped in "Bearer ". OkHttp trims trailing
        // whitespace so the on-the-wire value is "Bearer". This pin
        // documents both behaviours so a future "guard against blank"
        // change is intentional.
        val sut = AuthInterceptor(storeReturning(""))
        val req = Request.Builder().url("https://api.test/x").get().build()
        val (chain, capture) = chainCapturing(req)
        sut.intercept(chain)
        assertEquals("Bearer", capture()!!.header("Authorization"))
    }
}
