// To parse the JSON, install Klaxon and do:
//
//   val generationRequestedV1 = GenerationRequestedV1.fromJson(jsonString)

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

/**
 * Emitted when an application's generation pipeline is enqueued.
 */
data class GenerationRequestedV1 (
    @Json(name = "event_type")
    val eventType: EventType,

    @Json(name = "event_version")
    val eventVersion: Long,

    val payload: Payload
) {
    public fun toJson() = klaxon.toJsonString(this)

    companion object {
        public fun fromJson(json: String) = klaxon.parse<GenerationRequestedV1>(json)
    }
}

enum class EventType(val value: String) {
    GenerationRequested("generation.requested");

    companion object {
        public fun fromValue(value: String): EventType = when (value) {
            "generation.requested" -> GenerationRequested
            else                   -> throw IllegalArgumentException()
        }
    }
}

data class Payload (
    @Json(name = "application_id")
    val applicationID: String,

    @Json(name = "job_id")
    val jobID: String,

    @Json(name = "requested_modules")
    val requestedModules: List<String>,

    @Json(name = "user_id")
    val userID: String
)
