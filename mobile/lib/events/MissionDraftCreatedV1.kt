// To parse the JSON, install Klaxon and do:
//
//   val missionDraftCreatedV1 = MissionDraftCreatedV1.fromJson(jsonString)

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
    .convert(Author::class,    { Author.fromValue(it.string!!) },    { "\"${it.value}\"" })

/**
 * Emitted when a new mission draft is created (by user or by an agent).
 */
data class MissionDraftCreatedV1 (
    @Json(name = "event_type")
    val eventType: EventType,

    @Json(name = "event_version")
    val eventVersion: Long,

    val payload: Payload
) {
    public fun toJson() = klaxon.toJsonString(this)

    companion object {
        public fun fromJson(json: String) = klaxon.parse<MissionDraftCreatedV1>(json)
    }
}

enum class EventType(val value: String) {
    MissionDraftCreated("mission.draft.created");

    companion object {
        public fun fromValue(value: String): EventType = when (value) {
            "mission.draft.created" -> MissionDraftCreated
            else                    -> throw IllegalArgumentException()
        }
    }
}

data class Payload (
    val author: Author,

    @Json(name = "draft_id")
    val draftID: String,

    @Json(name = "mission_id")
    val missionID: String,

    val title: String? = null
)

enum class Author(val value: String) {
    Agent("agent"),
    User("user");

    companion object {
        public fun fromValue(value: String): Author = when (value) {
            "agent" -> Agent
            "user"  -> User
            else    -> throw IllegalArgumentException()
        }
    }
}
