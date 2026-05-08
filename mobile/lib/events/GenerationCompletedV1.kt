// To parse the JSON, install Klaxon and do:
//
//   val generationCompletedV1 = GenerationCompletedV1.fromJson(jsonString)

package com.hirestack.events.generated

import com.beust.klaxon.*

private fun <T> Klaxon.convert(k: kotlin.reflect.KClass<*>, fromJson: (JsonValue) -> T, toJson: (T) -> String, isUnion: Boolean = false) =
    this.converter(object: Converter {
        @Suppress("UNCHECKED_CAST")
        override fun toJson(value: Any)        = toJson(value as T)
        override fun fromJson(jv: JsonValue)   = fromJson(jv) as Any
        override fun canConvert(cls: Class<*>) = cls == k.java || (isUnion && cls.superclass == k.java)
    })

private val klaxon = Klaxon()
    .convert(EventType::class, { EventType.fromValue(it.string!!) }, { "\"${it.value}\"" })
    .convert(Status::class,    { Status.fromValue(it.string!!) },    { "\"${it.value}\"" })

/**
 * Emitted when the generation pipeline reaches a terminal state (success or failure).
 */
data class GenerationCompletedV1 (
    @Json(name = "event_type")
    val eventType: EventType,

    @Json(name = "event_version")
    val eventVersion: Long,

    val payload: Payload
) {
    public fun toJson() = klaxon.toJsonString(this)

    companion object {
        public fun fromJson(json: String) = klaxon.parse<GenerationCompletedV1>(json)
    }
}

enum class EventType(val value: String) {
    GenerationCompleted("generation.completed");

    companion object {
        public fun fromValue(value: String): EventType = when (value) {
            "generation.completed" -> GenerationCompleted
            else                   -> throw IllegalArgumentException()
        }
    }
}

data class Payload (
    @Json(name = "application_id")
    val applicationID: String,

    @Json(name = "duration_ms")
    val durationMS: Long? = null,

    @Json(name = "error_class")
    val errorClass: String? = null,

    @Json(name = "job_id")
    val jobID: String,

    val status: Status,

    @Json(name = "user_id")
    val userID: String
)

enum class Status(val value: String) {
    Cancelled("cancelled"),
    Failed("failed"),
    Succeeded("succeeded");

    companion object {
        public fun fromValue(value: String): Status = when (value) {
            "cancelled" -> Cancelled
            "failed"    -> Failed
            "succeeded" -> Succeeded
            else        -> throw IllegalArgumentException()
        }
    }
}
