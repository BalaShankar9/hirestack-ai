package com.hirestack.ai.data.network

import com.squareup.moshi.Moshi
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Pinned wire contract for the Moshi-serialised mobile data classes
 * in [ParityModels.kt] (S9-F4, risk R5).
 *
 * Intent: catch silent field renames or shape changes that would
 * desync mobile from the FastAPI / PostgREST backend.
 */
class ParityModelsAdapterTest {

    private val moshi: Moshi = Moshi.Builder().build()

    @Test
    fun `Application parses required id and snake_case fields`() {
        val json = """
            {
              "id": "app-1",
              "user_id": "u-1",
              "title": "Senior SRE",
              "status": "drafting",
              "job_title": "Site Reliability Engineer",
              "company": "Acme",
              "location": "Remote",
              "jd_text": "Run reliable systems",
              "facts_locked": true,
              "cv_html": "<p>cv</p>",
              "cover_letter_html": "<p>cl</p>",
              "personal_statement_html": "<p>ps</p>",
              "portfolio_html": "<p>port</p>",
              "resume_html": "<p>res</p>",
              "created_at": "2026-04-01T00:00:00Z",
              "updated_at": "2026-04-02T00:00:00Z"
            }
        """.trimIndent()
        val adapter = moshi.adapter(Application::class.java)
        val app = adapter.fromJson(json)!!
        assertEquals("app-1", app.id)
        assertEquals("u-1", app.user_id)
        assertEquals("Senior SRE", app.title)
        assertEquals("Site Reliability Engineer", app.job_title)
        assertEquals(true, app.facts_locked)
        assertEquals("<p>cv</p>", app.cv_html)
        assertEquals("2026-04-01T00:00:00Z", app.created_at)
    }

    @Test
    fun `Application defaults all optional fields to null`() {
        val adapter = moshi.adapter(Application::class.java)
        val app = adapter.fromJson("""{"id":"a-2"}""")!!
        assertEquals("a-2", app.id)
        assertNull(app.user_id)
        assertNull(app.title)
        assertNull(app.status)
        assertNull(app.cv_html)
        assertNull(app.modules)
        assertNull(app.scores)
        assertNull(app.created_at)
    }

    @Test
    fun `Application ignores unknown fields by default`() {
        val adapter = moshi.adapter(Application::class.java)
        val app = adapter.fromJson(
            """{"id":"a-3","completely_new_backend_field":"shrug","another":42}""",
        )!!
        assertEquals("a-3", app.id)
    }

    @Test
    fun `Application parses nested ScoresShape and ConfirmedFacts`() {
        val json = """
            {
              "id": "a-4",
              "scores": {
                "overall": 87.5,
                "keyword": 90.0,
                "readability": 82.0,
                "structure": 88.0,
                "ats": 91.0,
                "topFix": "Add metrics"
              },
              "confirmed_facts": {
                "full_name": "Jane Q",
                "email": "jane@example.com",
                "current_title": "SRE",
                "years_experience": 9,
                "location": "EU"
              }
            }
        """.trimIndent()
        val adapter = moshi.adapter(Application::class.java)
        val app = adapter.fromJson(json)!!
        assertNotNull(app.scores)
        assertEquals(87.5, app.scores!!.overall!!, 0.001)
        assertEquals("Add metrics", app.scores!!.topFix)
        assertNotNull(app.confirmed_facts)
        assertEquals("Jane Q", app.confirmed_facts!!.full_name)
        assertEquals(9, app.confirmed_facts!!.years_experience)
    }

    @Test
    fun `Application ModuleStatusEntry uses camelCase updatedAt`() {
        // Pin: this field is camelCase even though the rest of the
        // payload is snake_case. Backend writes it that way; renaming
        // here would silently lose timestamps in the UI.
        val json = """
            {
              "id": "a-5",
              "modules": {
                "cv": {"state": "complete", "message": "ok", "updatedAt": 1714000000}
              }
            }
        """.trimIndent()
        val adapter = moshi.adapter(Application::class.java)
        val app = adapter.fromJson(json)!!
        val cv = app.modules!!.getValue("cv")
        assertEquals("complete", cv.state)
        assertEquals(1714000000L, cv.updatedAt)
    }

    @Test
    fun `GenerationJob parses progress phase agent and step lists`() {
        val json = """
            {
              "id": "job-1",
              "user_id": "u-1",
              "application_id": "a-1",
              "status": "running",
              "progress": 42,
              "phase": "tailoring",
              "current_agent": "RoleProfiler",
              "completed_steps": ["intake", "facts"],
              "total_steps": 7,
              "requested_modules": ["cv", "cover_letter"],
              "started_at": "2026-04-01T00:00:00Z",
              "created_at": "2026-04-01T00:00:00Z"
            }
        """.trimIndent()
        val adapter = moshi.adapter(GenerationJob::class.java)
        val job = adapter.fromJson(json)!!
        assertEquals("job-1", job.id)
        assertEquals(42, job.progress)
        assertEquals("tailoring", job.phase)
        assertEquals("RoleProfiler", job.current_agent)
        assertEquals(listOf("intake", "facts"), job.completed_steps)
        assertEquals(7, job.total_steps)
        assertEquals(listOf("cv", "cover_letter"), job.requested_modules)
    }

    @Test
    fun `GenerationJobEvent uses agent_name and sequence_no`() {
        // Pin: the event payload uses agent_name (snake) while the
        // job payload uses current_agent. Both must remain stable.
        val json = """
            {
              "id": "ev-1",
              "job_id": "job-1",
              "sequence_no": 12,
              "event_name": "agent.start",
              "agent_name": "FactsExtractor",
              "stage": "facts",
              "status": "running",
              "message": "Extracting facts",
              "created_at": "2026-04-01T00:00:00Z"
            }
        """.trimIndent()
        val adapter = moshi.adapter(GenerationJobEvent::class.java)
        val ev = adapter.fromJson(json)!!
        assertEquals(12, ev.sequence_no)
        assertEquals("agent.start", ev.event_name)
        assertEquals("FactsExtractor", ev.agent_name)
        assertEquals("facts", ev.stage)
    }

    @Test
    fun `CreateGenerationJobRequest serialises requested_modules array`() {
        val adapter = moshi.adapter(CreateGenerationJobRequest::class.java)
        val req = CreateGenerationJobRequest(
            application_id = "a-1",
            requested_modules = listOf("cv", "cover_letter", "personal_statement"),
        )
        val json = adapter.toJson(req)
        assertTrue(
            "expected snake_case application_id, got: $json",
            json.contains("\"application_id\":\"a-1\""),
        )
        assertTrue(
            "expected snake_case requested_modules array, got: $json",
            json.contains("\"requested_modules\":[\"cv\",\"cover_letter\",\"personal_statement\"]"),
        )
    }

    @Test
    fun `CreateGenerationJobRequest defaults requested_modules to empty list`() {
        val adapter = moshi.adapter(CreateGenerationJobRequest::class.java)
        val req = adapter.fromJson("""{"application_id":"a-9"}""")!!
        assertEquals("a-9", req.application_id)
        assertEquals(emptyList<String>(), req.requested_modules)
    }

    @Test
    fun `GenerationJob round-trips`() {
        val adapter = moshi.adapter(GenerationJob::class.java)
        val original = GenerationJob(
            id = "job-rt",
            status = "complete",
            progress = 100,
            phase = "done",
            completed_steps = listOf("a", "b", "c"),
            total_steps = 3,
        )
        val json = adapter.toJson(original)
        val parsed = adapter.fromJson(json)!!
        assertEquals(original.id, parsed.id)
        assertEquals(original.status, parsed.status)
        assertEquals(original.progress, parsed.progress)
        assertEquals(original.completed_steps, parsed.completed_steps)
    }

    @Test
    fun `ResumeParseResponse keeps camelCase fileName and contentType`() {
        // Pin: parse-resume endpoint returns camelCase. Renaming would
        // break upload UI on resumes and cover letters.
        val json = """
            {"text":"Hello","fileName":"r.pdf","contentType":"application/pdf"}
        """.trimIndent()
        val adapter = moshi.adapter(ResumeParseResponse::class.java)
        val r = adapter.fromJson(json)!!
        assertEquals("Hello", r.text)
        assertEquals("r.pdf", r.fileName)
        assertEquals("application/pdf", r.contentType)
    }
}
