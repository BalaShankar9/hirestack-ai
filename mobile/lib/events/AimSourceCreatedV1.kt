// To parse the JSON, install Klaxon and do:
//
//   val aimSourceCreatedV1 = AimSourceCreatedV1.fromJson(jsonString)

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
    .convert(Kind::class,      { Kind.fromValue(it.string!!) },      { "\"${it.value}\"" })

/**
 * Emitted when a new source (article, transcript, doc) is added to the AIM library.
 */
data class AimSourceCreatedV1 (
    @Json(name = "event_type")
    val eventType: EventType,

    @Json(name = "event_version")
    val eventVersion: Long,

    val payload: Payload
) {
    public fun toJson() = klaxon.toJsonString(this)

    companion object {
        public fun fromJson(json: String) = klaxon.parse<AimSourceCreatedV1>(json)
    }
}

enum class EventType(val value: String) {
    AimSourceCreated("aim.source.created");

    companion object {
        public fun fromValue(value: String): EventType = when (value) {
            "aim.source.created" -> AimSourceCreated
            else                 -> throw IllegalArgumentException()
        }
    }
}

data class Payload (
    val kind: Kind,

    @Json(name = "source_id")
    val sourceID: String,

    val title: String? = null,
    val url: String? = null
)

enum class Kind(val value: String) {
    Article("article"),
    Doc("doc"),
    Other("other"),
    Podcast("podcast"),
    Video("video");

    companion object {
        public fun fromValue(value: String): Kind = when (value) {
            "article" -> Article
            "doc"     -> Doc
            "other"   -> Other
            "podcast" -> Podcast
            "video"   -> Video
            else      -> throw IllegalArgumentException()
        }
    }
}
