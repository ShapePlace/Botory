package dev.botory.android.data

import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject

@Serializable
data class EndpointRef(
    val kind: String,
    val id: String,
    val name: String? = null
)

@Serializable
data class Envelope(
    val id: String = "",
    val v: Int = 1,
    val type: String,
    val ts: String = "",
    val source: EndpointRef,
    val target: EndpointRef,
    val payload: JsonObject = JsonObject(emptyMap())
)

@Serializable
data class InlineButton(
    val id: String = "",
    val label: String,
    val callback: String,
    val icon: String? = null,
    val tone: String = "default"
)

@Serializable
data class ToolParam(
    val name: String,
    val type: String = "string",
    val label: String,
    val required: Boolean = true,
    val default: JsonElement? = null,
    val options: JsonArray? = null
)

@Serializable
data class ToolDefinition(
    @SerialName("tool_id") val toolId: String,
    val title: String,
    val description: String = "",
    val icon: String = "bolt",
    val params: List<ToolParam> = emptyList()
)

@Serializable
data class WidgetDefinition(
    @SerialName("widget_id") val widgetId: String,
    val title: String,
    val interval: Double = 5.0
)

@Serializable
data class EntityDescriptor(
    val id: String,
    val name: String,
    val kind: String = "bot",
    val description: String = "",
    val commands: List<String> = emptyList(),
    val tools: List<ToolDefinition> = emptyList(),
    val widgets: List<WidgetDefinition> = emptyList(),
    val online: Boolean = true
)

@Serializable
data class ManagedProjectUi(
    @SerialName("project_id") val projectId: String,
    val name: String,
    val entrypoint: String,
    val running: Boolean = false,
    val pid: Int? = null,
    val logs: List<String> = emptyList()
)

data class WidgetBlockUi(
    val kind: String,
    val id: String = "",
    val label: String,
    val value: Float = 0f,
    val display: String = "",
    val checked: Boolean = false
)

data class SplitButtonUi(
    val primary: InlineButton,
    val menu: List<InlineButton>
)

data class ChatMessageUi(
    val id: String,
    val fromBot: Boolean,
    val text: String,
    val time: String,
    val buttonRows: List<List<InlineButton>> = emptyList(),
    val splitButton: SplitButtonUi? = null,
    val cardTitle: String? = null,
    val cardBlocks: List<WidgetBlockUi> = emptyList(),
    val isStreaming: Boolean = false,
    val queuedOffline: Boolean = false
)

data class WidgetCardUi(
    val widgetId: String,
    val entityId: String,
    val title: String,
    val subtitle: String,
    val blocks: List<WidgetBlockUi>
)

enum class TransportMode {
    DEMO,
    LAN,
    RELAY,
    OFFLINE
}
