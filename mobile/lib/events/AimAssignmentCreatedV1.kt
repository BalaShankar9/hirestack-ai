// To parse the JSON, install Klaxon and do:
//
//   val aimAssignmentCreatedV1 = AimAssignmentCreatedV1.fromJson(jsonString)

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
 * Emitted when a learner picks up an AIM assignment.
 */
data class AimAssignmentCreatedV1 (
    @Json(name = "event_type")
    val eventType: EventType,

    @Json(name = "event_version")
    val eventVersion: Long,

    val payload: Payload
) {
    public fun toJson() = klaxon.toJsonString(this)

    companion object {
        public fun fromJson(json: String) = klaxon.parse<AimAssignmentCreatedV1>(json)
    }
}

enum class EventType(val value: String) {
    AimAssignmentCreated("aim.assignment.created");

    companion object {
        public fun fromValue(value: String): EventType = when (value) {
            "aim.assignment.created" -> AimAssignmentCreated
            else                     -> throw IllegalArgumentException()
        }
    }
}

data class Payload (
    @Json(name = "assignment_id")
    val assignmentID: String,

    @Json(name = "due_at")
    val dueAt: String? = null,

    @Json(name = "module_id")
    val moduleID: String,

    @Json(name = "user_id")
    val userID: String
)
