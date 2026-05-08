// To parse the JSON, install Klaxon and do:
//
//   val eventEnvelope = EventEnvelope.fromJson(jsonString)

package com.hirestack.events.generated

import com.beust.klaxon.*

private val klaxon = Klaxon()

/**
 * Canonical wrapper around every domain event. Mirrors backend/app/core/events/envelope.py.
 */
data class EventEnvelope (
    /**
     * UUIDv4 generated at emit time.
     */
    @Json(name = "event_id")
    val eventID: String,

    /**
     * Dotted lower-snake-case identifier, e.g. ``generation.completed``.
     */
    @Json(name = "event_type")
    val eventType: String,

    @Json(name = "event_version")
    val eventVersion: Long,

    @Json(name = "idempotency_key")
    val idempotencyKey: String? = null,

    /**
     * RFC3339 with timezone (UTC). Naive timestamps are rejected.
     */
    @Json(name = "occurred_at")
    val occurredAt: String,

    @Json(name = "org_id")
    val orgID: String,

    val payload: Map<String, Any?>
) {
    public fun toJson() = klaxon.toJsonString(this)

    companion object {
        public fun fromJson(json: String) = klaxon.parse<EventEnvelope>(json)
    }
}
