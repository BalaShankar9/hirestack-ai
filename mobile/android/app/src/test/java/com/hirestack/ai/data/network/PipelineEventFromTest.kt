package com.hirestack.ai.data.network

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Test

/**
 * Pinned contract for [PipelineEvent.from] (S9-F3, risk R4).
 *
 * Extracted from PipelineSse.onEvent so it can be unit-tested without
 * an OkHttp EventSource. The SSE callback now delegates to this factory.
 */
class PipelineEventFromTest {

    @Test
    fun `name defaults to message when type is null`() {
        val ev = PipelineEvent.from(null, mapOf("progress" to 42))
        assertEquals("message", ev.name)
    }

    @Test
    fun `name uses event type verbatim when provided`() {
        val ev = PipelineEvent.from("progress", mapOf("progress" to 10))
        assertEquals("progress", ev.name)
    }

    @Test
    fun `progress accepts Int Long and Double`() {
        assertEquals(7, PipelineEvent.from("p", mapOf("progress" to 7)).progress)
        assertEquals(7, PipelineEvent.from("p", mapOf("progress" to 7L)).progress)
        assertEquals(7, PipelineEvent.from("p", mapOf("progress" to 7.0)).progress)
        // Truncation, not rounding (Number.toInt()).
        assertEquals(7, PipelineEvent.from("p", mapOf("progress" to 7.9)).progress)
    }

    @Test
    fun `progress is null when missing`() {
        assertNull(PipelineEvent.from("p", mapOf("phase" to "x")).progress)
    }

    @Test
    fun `progress is null when value is non-numeric`() {
        assertNull(PipelineEvent.from("p", mapOf("progress" to "fast")).progress)
    }

    @Test
    fun `agent falls back to agent_name when agent is missing`() {
        val ev = PipelineEvent.from("p", mapOf("agent_name" to "RoleProfiler"))
        assertEquals("RoleProfiler", ev.agent)
    }

    @Test
    fun `agent prefers agent over agent_name when both present`() {
        val ev = PipelineEvent.from(
            "p",
            mapOf("agent" to "FactsExtractor", "agent_name" to "ignored"),
        )
        assertEquals("FactsExtractor", ev.agent)
    }

    @Test
    fun `agent is null when neither key is present`() {
        assertNull(PipelineEvent.from("p", mapOf("phase" to "x")).agent)
    }

    @Test
    fun `agent is null when value is non-string`() {
        assertNull(PipelineEvent.from("p", mapOf("agent" to 42)).agent)
    }

    @Test
    fun `phase stage status message read as strings only`() {
        val ev = PipelineEvent.from(
            "p",
            mapOf(
                "phase" to "draft",
                "stage" to "tailoring",
                "status" to "running",
                "message" to "Drafting CV",
            ),
        )
        assertEquals("draft", ev.phase)
        assertEquals("tailoring", ev.stage)
        assertEquals("running", ev.status)
        assertEquals("Drafting CV", ev.message)
    }

    @Test
    fun `non-string phase is dropped silently`() {
        val ev = PipelineEvent.from("p", mapOf("phase" to 1))
        assertNull(ev.phase)
    }

    @Test
    fun `raw echoes the parsed map verbatim`() {
        val parsed = mapOf("progress" to 50, "extra_field" to "kept")
        val ev = PipelineEvent.from("p", parsed)
        assertSame(parsed, ev.raw)
    }

    @Test
    fun `null parsed map yields null fields and null raw`() {
        val ev = PipelineEvent.from("error", null)
        assertEquals("error", ev.name)
        assertNull(ev.progress)
        assertNull(ev.phase)
        assertNull(ev.agent)
        assertNull(ev.stage)
        assertNull(ev.status)
        assertNull(ev.message)
        assertNull(ev.raw)
    }

    @Test
    fun `null parsed map with null type defaults to message name`() {
        val ev = PipelineEvent.from(null, null)
        assertEquals("message", ev.name)
        assertNull(ev.raw)
    }

    @Test
    fun `empty map yields all-null typed fields but keeps raw`() {
        val parsed = emptyMap<String, Any?>()
        val ev = PipelineEvent.from("complete", parsed)
        assertEquals("complete", ev.name)
        assertNull(ev.progress)
        assertNull(ev.phase)
        assertSame(parsed, ev.raw)
    }
}
