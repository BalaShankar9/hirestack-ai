package com.hirestack.ai.data.network

import okhttp3.Interceptor
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.Protocol
import okhttp3.Request
import okhttp3.Response
import okhttp3.ResponseBody.Companion.toResponseBody
import org.junit.Assert.assertEquals
import org.junit.Assert.assertSame
import org.junit.Assert.assertThrows
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.IOException

/**
 * Pinned contract for [RetryInterceptor] (S9-F1, risk R1).
 *
 * The interceptor must:
 *  - Retry GET / HEAD up to 3 attempts on IOException and on
 *    HTTP 502 / 503 / 504.
 *  - NEVER retry POST / PUT / PATCH / DELETE (would replay writes).
 *  - Stop on the first 2xx / 4xx and return that response unchanged.
 *  - Return the LAST 5xx response if all attempts exhausted (do not
 *    swallow the error into a fake 200).
 *  - Re-throw the LAST IOException if all attempts exhausted.
 *  - Backoff 0 / 400 / 1200 ms between attempts.
 */
class RetryInterceptorTest {

    private val sut = RetryInterceptor()

    private fun req(method: String): Request {
        val builder = Request.Builder().url("https://example.test/r")
        return when (method.uppercase()) {
            "GET" -> builder.get().build()
            "HEAD" -> builder.head().build()
            "POST" -> builder.post("".toRequestBody()).build()
            "PUT" -> builder.put("".toRequestBody()).build()
            "DELETE" -> builder.delete().build()
            "PATCH" -> builder.patch("".toRequestBody()).build()
            else -> error("unsupported method $method")
        }
    }

    private fun String.toRequestBody(): okhttp3.RequestBody =
        okhttp3.RequestBody.create("text/plain".toMediaType(), this)

    private fun resp(code: Int, request: Request): Response =
        Response.Builder()
            .request(request)
            .protocol(Protocol.HTTP_1_1)
            .code(code)
            .message("status $code")
            .body("".toResponseBody("text/plain".toMediaType()))
            .build()

    private class StubChain(
        private val request: Request,
        private val plan: List<() -> Response>,
    ) : Interceptor.Chain {
        var calls = 0
            private set

        override fun request(): Request = request
        override fun proceed(request: Request): Response {
            val idx = calls
            calls += 1
            check(idx < plan.size) { "chain.proceed called ${calls} times but only ${plan.size} planned" }
            return plan[idx]()
        }
        override fun connection(): okhttp3.Connection? = null
        override fun call(): okhttp3.Call = throw UnsupportedOperationException()
        override fun connectTimeoutMillis(): Int = 0
        override fun withConnectTimeout(timeout: Int, unit: java.util.concurrent.TimeUnit): Interceptor.Chain = this
        override fun readTimeoutMillis(): Int = 0
        override fun withReadTimeout(timeout: Int, unit: java.util.concurrent.TimeUnit): Interceptor.Chain = this
        override fun writeTimeoutMillis(): Int = 0
        override fun withWriteTimeout(timeout: Int, unit: java.util.concurrent.TimeUnit): Interceptor.Chain = this
    }

    @Test
    fun `passes through 200 on first attempt without retry`() {
        val r = req("GET")
        val ok = resp(200, r)
        val chain = StubChain(r, listOf({ ok }))
        val out = sut.intercept(chain)
        assertSame(ok, out)
        assertEquals(1, chain.calls)
    }

    @Test
    fun `does not retry POST on 503`() {
        val r = req("POST")
        val fail = resp(503, r)
        val chain = StubChain(r, listOf({ fail }))
        val out = sut.intercept(chain)
        assertEquals(503, out.code)
        assertEquals(1, chain.calls)
    }

    @Test
    fun `does not retry PUT on IOException`() {
        val r = req("PUT")
        val chain = StubChain(r, listOf({ throw IOException("boom") }))
        assertThrows(IOException::class.java) { sut.intercept(chain) }
        assertEquals(1, chain.calls)
    }

    @Test
    fun `does not retry PATCH or DELETE`() {
        for (m in listOf("PATCH", "DELETE")) {
            val r = req(m)
            val fail = resp(502, r)
            val chain = StubChain(r, listOf({ fail }))
            val out = sut.intercept(chain)
            assertEquals(502, out.code)
            assertEquals(1, chain.calls)
        }
    }

    @Test
    fun `retries GET on 502 then succeeds`() {
        val r = req("GET")
        val ok = resp(200, r)
        val plan: List<() -> Response> = listOf({ resp(502, r) }, { ok })
        val chain = StubChain(r, plan)
        val started = System.currentTimeMillis()
        val out = sut.intercept(chain)
        val elapsed = System.currentTimeMillis() - started
        assertEquals(200, out.code)
        assertEquals(2, chain.calls)
        // Backoff for attempt 1 is 400 ms.
        assertTrue("expected >=350 ms backoff, got $elapsed", elapsed >= 350)
    }

    @Test
    fun `retries HEAD on 503 then succeeds`() {
        val r = req("HEAD")
        val plan: List<() -> Response> = listOf({ resp(503, r) }, { resp(200, r) })
        val chain = StubChain(r, plan)
        val out = sut.intercept(chain)
        assertEquals(200, out.code)
        assertEquals(2, chain.calls)
    }

    @Test
    fun `returns last 5xx response when retries exhausted`() {
        val r = req("GET")
        val plan: List<() -> Response> = listOf(
            { resp(503, r) },
            { resp(503, r) },
            { resp(504, r) },
        )
        val chain = StubChain(r, plan)
        val out = sut.intercept(chain)
        // Returns a response (not a thrown error) so callers see real status.
        assertEquals(504, out.code)
        assertEquals(3, chain.calls)
    }

    @Test
    fun `rethrows last IOException when retries exhausted`() {
        val r = req("GET")
        val errors = listOf(IOException("a"), IOException("b"), IOException("c"))
        val plan: List<() -> Response> = errors.map { e -> { throw e } }
        val chain = StubChain(r, plan)
        val ex = assertThrows(IOException::class.java) { sut.intercept(chain) }
        assertEquals("c", ex.message)
        assertEquals(3, chain.calls)
    }

    @Test
    fun `recovers from initial IOException then succeeds on 200`() {
        val r = req("GET")
        val plan: List<() -> Response> = listOf(
            { throw IOException("transient") },
            { resp(200, r) },
        )
        val chain = StubChain(r, plan)
        val out = sut.intercept(chain)
        assertEquals(200, out.code)
        assertEquals(2, chain.calls)
    }

    @Test
    fun `does not retry on 4xx (client errors are terminal)`() {
        val r = req("GET")
        for (code in listOf(400, 401, 403, 404, 422)) {
            val plan: List<() -> Response> = listOf({ resp(code, r) })
            val chain = StubChain(r, plan)
            val out = sut.intercept(chain)
            assertEquals(code, out.code)
            assertEquals(1, chain.calls)
        }
    }

    @Test
    fun `does not retry on 500 (only 502 503 504 are retryable)`() {
        val r = req("GET")
        val plan: List<() -> Response> = listOf({ resp(500, r) })
        val chain = StubChain(r, plan)
        val out = sut.intercept(chain)
        assertEquals(500, out.code)
        assertEquals(1, chain.calls)
    }

    @Test
    fun `caps at 3 attempts even if all fail with retryable 5xx`() {
        val r = req("GET")
        var calls = 0
        val plan: List<() -> Response> = List(3) { { calls++; resp(503, r) } }
        val chain = StubChain(r, plan)
        sut.intercept(chain)
        assertEquals(3, chain.calls)
        assertEquals(3, calls)
    }
}
