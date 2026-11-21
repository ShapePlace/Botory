package dev.botory.android.data

import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.SupervisorJob
import kotlinx.coroutines.delay
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.launch
import kotlinx.serialization.decodeFromString
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.contentOrNull
import kotlinx.serialization.json.decodeFromJsonElement
import kotlinx.serialization.json.floatOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.MultipartBody
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.Response
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import java.util.concurrent.TimeUnit

data class BotoryUiState(
    val setupCompleted: Boolean = false,
    val hubName: String = "Local Demo Hub",
    val hubId: String = "hub_demo",
    val lanUrl: String = "ws://127.0.0.1:8765",
    val relayUrl: String = "",
    val transport: TransportMode = TransportMode.DEMO,
    val entities: List<EntityDescriptor> = emptyList(),
    val messagesByEntity: Map<String, List<ChatMessageUi>> = emptyMap(),
    val widgets: List<WidgetCardUi> = emptyList(),
    val projects: List<ManagedProjectUi> = emptyList(),
    val unreadByEntity: Map<String, Int> = emptyMap(),
    val lastToolResult: String? = null,
    val snackbarMessage: String? = null,
    val connectionError: String? = null
)

class BotoryClient {
    private val scope = CoroutineScope(SupervisorJob() + Dispatchers.IO)
    private val json = Json {
        ignoreUnknownKeys = true
        encodeDefaults = true
    }
    private val httpClient = OkHttpClient.Builder()
        .pingInterval(20, TimeUnit.SECONDS)
        .connectTimeout(5, TimeUnit.SECONDS)
        .build()

    private var webSocket: WebSocket? = null
    private val offlineQueue = mutableListOf<Envelope>()

    private val _state = MutableStateFlow(createInitialDemoState())
    val state: StateFlow<BotoryUiState> = _state.asStateFlow()

    private fun nowTime(): String =
        SimpleDateFormat("HH:mm", Locale.getDefault()).format(Date())

    fun completeSetupWithDemo() {
        loadDemoMode()
        _state.update { it.copy(setupCompleted = true) }
    }

    fun openSetupWizard() {
        _state.update { it.copy(setupCompleted = false) }
    }

    fun clearSnackbar() {
        _state.update { it.copy(snackbarMessage = null) }
    }

    fun clearToolResult() {
        _state.update { it.copy(lastToolResult = null) }
    }

    fun markRead(entityId: String) {
        _state.update { s ->
            s.copy(unreadByEntity = s.unreadByEntity + (entityId to 0))
        }
    }

    fun loadDemoMode() {
        webSocket?.close(1000, "Switched to Demo")
        webSocket = null
        _state.value = createInitialDemoState().copy(setupCompleted = true)
    }

    fun connectWithPairingInput(rawInput: String, preferRelay: Boolean = false) {
        try {
            val cfg = PairingUriParser.parse(rawInput)
            _state.update {
                it.copy(
                    setupCompleted = true,
                    hubId = cfg.hubId,
                    hubName = cfg.hubName,
                    lanUrl = cfg.lanAddress,
                    relayUrl = cfg.relayUrl ?: "",
                    connectionError = null
                )
            }
            if (preferRelay && !cfg.relayUrl.isNullOrBlank()) {
                connectWebSocket(buildRelayClientUrl(cfg.relayUrl, cfg.hubId), TransportMode.RELAY)
            } else if (cfg.lanAddress.isNotBlank()) {
                connectWebSocket(buildLanClientUrl(cfg.lanAddress), TransportMode.LAN)
            }
        } catch (e: Exception) {
            _state.update { it.copy(snackbarMessage = "Invalid address: ${e.message}") }
        }
    }

    fun switchTransport(target: TransportMode) {
        val current = _state.value
        when (target) {
            TransportMode.DEMO -> loadDemoMode()
            TransportMode.LAN -> {
                if (current.lanUrl.isBlank()) {
                    _state.update { it.copy(snackbarMessage = "Hub LAN address is empty") }
                } else {
                    connectWebSocket(buildLanClientUrl(current.lanUrl), TransportMode.LAN)
                }
            }
            TransportMode.RELAY -> {
                if (current.relayUrl.isBlank()) {
                    _state.update { it.copy(snackbarMessage = "Relay URL is not configured") }
                } else {
                    connectWebSocket(buildRelayClientUrl(current.relayUrl, current.hubId), TransportMode.RELAY)
                }
            }
            TransportMode.OFFLINE -> {
                webSocket?.close(1000, "Manual offline")
                webSocket = null
                _state.update { it.copy(transport = TransportMode.OFFLINE, snackbarMessage = "Offline mode enabled") }
            }
        }
    }

    private fun buildHttpBaseUrl(): String {
        val raw = _state.value.lanUrl.trim().trimEnd('/')
        return raw
            .replace("ws://", "http://")
            .replace("wss://", "https://")
            .removeSuffix("/ws/client")
    }

    private fun buildLanClientUrl(baseLan: String): String {
        val clean = baseLan.trimEnd('/')
        return if (clean.endsWith("/ws/client")) "$clean?client_id=android_app"
        else "$clean/ws/client?client_id=android_app"
    }

    private fun buildRelayClientUrl(baseRelay: String, hubId: String): String {
        val clean = baseRelay.trimEnd('/')
        return "$clean/ws/client/$hubId"
    }

    private fun connectWebSocket(url: String, mode: TransportMode) {
        webSocket?.close(1000, "Reconnecting")
        val request = Request.Builder().url(url).build()
        webSocket = httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onOpen(webSocket: WebSocket, response: Response) {
                _state.update {
                    it.copy(
                        transport = mode,
                        connectionError = null,
                        snackbarMessage = "Connected (${mode.name})"
                    )
                }
                flushOfflineQueue()
                refreshProjects()
            }

            override fun onMessage(webSocket: WebSocket, text: String) {
                handleIncomingJson(text)
            }

            override fun onFailure(webSocket: WebSocket, t: Throwable, response: Response?) {
                val cur = _state.value
                if (mode == TransportMode.LAN && cur.relayUrl.isNotBlank()) {
                    _state.update { it.copy(snackbarMessage = "LAN unreachable, falling back to Relay...") }
                    connectWebSocket(buildRelayClientUrl(cur.relayUrl, cur.hubId), TransportMode.RELAY)
                } else {
                    _state.update {
                        it.copy(
                            transport = TransportMode.OFFLINE,
                            connectionError = t.message ?: "Connection failed"
                        )
                    }
                }
            }
        })
    }

    fun refreshProjects() {
        if (_state.value.transport == TransportMode.DEMO) return
        val base = buildHttpBaseUrl()
        scope.launch {
            runCatching {
                val req = Request.Builder().url("$base/api/v1/projects").build()
                httpClient.newCall(req).execute().use { resp ->
                    if (resp.isSuccessful) {
                        val body = resp.body?.string().orEmpty()
                        val list = json.decodeFromString<List<ManagedProjectUi>>(body)
                        _state.update { it.copy(projects = list) }
                    }
                }
            }
        }
    }

    fun importProjectZip(zipBytes: ByteArray, filename: String) {
        if (_state.value.transport == TransportMode.DEMO) {
            val cleanName = filename.removeSuffix(".zip")
            val demoProj = ManagedProjectUi(
                projectId = cleanName,
                name = cleanName,
                entrypoint = "main.py",
                running = false
            )
            _state.update {
                it.copy(
                    projects = it.projects + demoProj,
                    snackbarMessage = "Imported '$filename' in Demo preview (connect Hub/Termux to run Python)"
                )
            }
            return
        }

        val base = buildHttpBaseUrl()
        scope.launch {
            runCatching {
                val fileBody = zipBytes.toRequestBody("application/zip".toMediaType())
                val multipart = MultipartBody.Builder()
                    .setType(MultipartBody.FORM)
                    .addFormDataPart("file", filename, fileBody)
                    .build()
                val req = Request.Builder()
                    .url("$base/api/v1/projects/import")
                    .post(multipart)
                    .build()
                httpClient.newCall(req).execute().use { resp ->
                    if (resp.isSuccessful) {
                        _state.update { it.copy(snackbarMessage = "Imported project: $filename") }
                        refreshProjects()
                    } else {
                        val err = resp.body?.string() ?: "HTTP ${resp.code}"
                        _state.update { it.copy(snackbarMessage = "Import failed: $err") }
                    }
                }
            }.onFailure { e ->
                _state.update { it.copy(snackbarMessage = "Import error: ${e.message}") }
            }
        }
    }

    fun toggleProjectRunning(project: ManagedProjectUi) {
        if (_state.value.transport == TransportMode.DEMO) {
            _state.update { s ->
                s.copy(
                    projects = s.projects.map {
                        if (it.projectId == project.projectId) it.copy(running = !it.running) else it
                    },
                    snackbarMessage = if (project.running) "Stopped ${project.name}" else "Started ${project.name}"
                )
            }
            return
        }

        val base = buildHttpBaseUrl()
        val action = if (project.running) "stop" else "start"
        scope.launch {
            runCatching {
                val emptyBody = ByteArray(0).toRequestBody(null)
                val req = Request.Builder()
                    .url("$base/api/v1/projects/${project.projectId}/$action")
                    .post(emptyBody)
                    .build()
                httpClient.newCall(req).execute().use { resp ->
                    if (resp.isSuccessful) {
                        _state.update { it.copy(snackbarMessage = "${project.name}: $action OK") }
                        refreshProjects()
                    }
                }
            }.onFailure { e ->
                _state.update { it.copy(snackbarMessage = "Project error: ${e.message}") }
            }
        }
    }

    private fun flushOfflineQueue() {
        val ws = webSocket ?: return
        val copy = offlineQueue.toList()
        offlineQueue.clear()
        copy.forEach { ws.send(json.encodeToString(it)) }
    }

    private fun sendOrQueue(env: Envelope) {
        val ws = webSocket
        if (_state.value.transport == TransportMode.OFFLINE || ws == null) {
            offlineQueue.add(env)
            _state.update { it.copy(snackbarMessage = "Saved to offline queue") }
        } else {
            ws.send(json.encodeToString(env))
        }
    }

    fun sendMessage(entityId: String, text: String) {
        val trimmed = text.trim()
        if (trimmed.isEmpty()) return

        val isOffline = _state.value.transport == TransportMode.OFFLINE
        val userMsg = ChatMessageUi(
            id = "u_${System.currentTimeMillis()}",
            fromBot = false,
            text = trimmed,
            time = nowTime(),
            queuedOffline = isOffline
        )
        appendMessage(entityId, userMsg)

        if (_state.value.transport == TransportMode.DEMO) {
            simulateDemoBotReply(entityId, trimmed)
            return
        }

        sendOrQueue(
            Envelope(
                type = "message.new",
                source = EndpointRef(kind = "client", id = "android_app"),
                target = EndpointRef(kind = "entity", id = entityId),
                payload = buildJsonObject { put("text", trimmed) }
            )
        )
    }

    fun sendCallback(entityId: String, callbackData: String) {
        if (_state.value.transport == TransportMode.DEMO) {
            simulateDemoCallback(entityId, callbackData)
            return
        }
        sendOrQueue(
            Envelope(
                type = "callback.query",
                source = EndpointRef(kind = "client", id = "android_app"),
                target = EndpointRef(kind = "entity", id = entityId),
                payload = buildJsonObject { put("data", callbackData) }
            )
        )
    }

    fun toggleWidget(entityId: String, widgetId: String, checked: Boolean) {
        _state.update { s ->
            val updated = s.widgets.map { card ->
                card.copy(
                    blocks = card.blocks.map { b ->
                        if (b.id == widgetId) b.copy(checked = checked) else b
                    }
                )
            }
            s.copy(widgets = updated)
        }

        if (_state.value.transport == TransportMode.DEMO) {
            _state.update { it.copy(snackbarMessage = "$widgetId: ${if (checked) "ON" else "OFF"}") }
            return
        }

        sendOrQueue(
            Envelope(
                type = "widget.action",
                source = EndpointRef(kind = "client", id = "android_app"),
                target = EndpointRef(kind = "entity", id = entityId),
                payload = buildJsonObject {
                    put("widget_id", widgetId)
                    put("checked", checked)
                }
            )
        )
    }

    fun changeWidgetSlider(entityId: String, widgetId: String, value: Float) {
        _state.update { s ->
            val updated = s.widgets.map { card ->
                card.copy(
                    blocks = card.blocks.map { b ->
                        if (b.id == widgetId) b.copy(value = value, display = "${value.toInt()}%") else b
                    }
                )
            }
            s.copy(widgets = updated)
        }

        if (_state.value.transport != TransportMode.DEMO) {
            sendOrQueue(
                Envelope(
                    type = "widget.action",
                    source = EndpointRef(kind = "client", id = "android_app"),
                    target = EndpointRef(kind = "entity", id = entityId),
                    payload = buildJsonObject {
                        put("widget_id", widgetId)
                        put("value", value)
                    }
                )
            )
        }
    }

    fun callTool(entityId: String, toolId: String, args: Map<String, Any>) {
        if (_state.value.transport == TransportMode.DEMO) {
            scope.launch {
                delay(400)
                _state.update {
                    it.copy(
                        lastToolResult = "Tool `$toolId` executed!\nArgs: $args\nResult: {\"status\": \"ok\", \"size_mb\": 48.4}",
                        snackbarMessage = "$toolId completed"
                    )
                }
            }
            return
        }

        val argsJson = buildJsonObject {
            args.forEach { (k, v) ->
                when (v) {
                    is Boolean -> put(k, v)
                    is Int -> put(k, v)
                    is Double -> put(k, v)
                    is Float -> put(k, v)
                    else -> put(k, v.toString())
                }
            }
        }
        sendOrQueue(
            Envelope(
                type = "tool.call",
                source = EndpointRef(kind = "client", id = "android_app"),
                target = EndpointRef(kind = "entity", id = entityId),
                payload = buildJsonObject {
                    put("tool_id", toolId)
                    put("args", argsJson)
                }
            )
        )
    }

    fun refreshDemoTelemetry() {
        if (_state.value.transport != TransportMode.DEMO) return
        val cpu = (18..72).random() / 100f
        val ram = (42..80).random() / 100f
        _state.update { s ->
            val updated = s.widgets.map { card ->
                if (card.widgetId == "pc_telemetry") {
                    card.copy(
                        blocks = listOf(
                            WidgetBlockUi("wavy_progress", "cpu", "CPU Load", cpu, "${(cpu * 100).toInt()}% · 49°C"),
                            WidgetBlockUi("wavy_progress", "ram", "RAM Usage", ram, "${(ram * 100).toInt()}% (9.3 / 16 GB)")
                        )
                    )
                } else card
            }
            s.copy(widgets = updated, snackbarMessage = "Telemetry refreshed")
        }
    }

    private fun handleIncomingJson(raw: String) {
        val env = runCatching { json.decodeFromString<Envelope>(raw) }.getOrNull() ?: return
        when (env.type) {
            "entity.sync" -> {
                val hubName = env.payload["hub_name"]?.jsonPrimitive?.contentOrNull ?: _state.value.hubName
                val ents = env.payload["entities"]?.jsonArray?.mapNotNull {
                    runCatching { json.decodeFromJsonElement<EntityDescriptor>(it) }.getOrNull()
                } ?: emptyList()
                _state.update { it.copy(hubName = hubName, entities = ents) }
            }

            "message.new" -> {
                val text = env.payload["text"]?.jsonPrimitive?.contentOrNull ?: ""
                val buttonRows = mutableListOf<List<InlineButton>>()
                var split: SplitButtonUi? = null
                env.payload["components"]?.jsonArray?.forEach { comp ->
                    val obj = comp.jsonObject
                    when (obj["kind"]?.jsonPrimitive?.contentOrNull) {
                        "button_group" -> {
                            val row = obj["items"]?.jsonArray?.mapNotNull {
                                runCatching { json.decodeFromJsonElement<InlineButton>(it) }.getOrNull()
                            } ?: emptyList()
                            if (row.isNotEmpty()) buttonRows.add(row)
                        }
                        "split_button" -> {
                            val prim = obj["primary"]?.let {
                                runCatching { json.decodeFromJsonElement<InlineButton>(it) }.getOrNull()
                            }
                            val menu = obj["menu"]?.jsonArray?.mapNotNull {
                                runCatching { json.decodeFromJsonElement<InlineButton>(it) }.getOrNull()
                            } ?: emptyList()
                            if (prim != null) split = SplitButtonUi(prim, menu)
                        }
                    }
                }
                val cardObj = env.payload["card"]?.jsonObject
                val cardTitle = cardObj?.get("title")?.jsonPrimitive?.contentOrNull
                val cardBlocks = parseBlocks(cardObj?.get("blocks"))

                appendMessage(
                    env.source.id,
                    ChatMessageUi(
                        id = env.id.ifBlank { "b_${System.currentTimeMillis()}" },
                        fromBot = true,
                        text = text,
                        time = nowTime(),
                        buttonRows = buttonRows,
                        splitButton = split,
                        cardTitle = cardTitle,
                        cardBlocks = cardBlocks
                    )
                )
            }

            "stream.start" -> {
                val msgId = env.payload["message_id"]?.jsonPrimitive?.contentOrNull ?: return
                appendMessage(
                    env.source.id,
                    ChatMessageUi(id = msgId, fromBot = true, text = "", time = nowTime(), isStreaming = true)
                )
            }

            "stream.delta" -> {
                val msgId = env.payload["message_id"]?.jsonPrimitive?.contentOrNull ?: return
                val delta = env.payload["delta"]?.jsonPrimitive?.contentOrNull ?: ""
                _state.update { s ->
                    val list = s.messagesByEntity[env.source.id].orEmpty().map { m ->
                        if (m.id == msgId) m.copy(text = m.text + delta) else m
                    }
                    s.copy(messagesByEntity = s.messagesByEntity + (env.source.id to list))
                }
            }

            "stream.end" -> {
                val msgId = env.payload["message_id"]?.jsonPrimitive?.contentOrNull ?: return
                _state.update { s ->
                    val list = s.messagesByEntity[env.source.id].orEmpty().map { m ->
                        if (m.id == msgId) m.copy(isStreaming = false) else m
                    }
                    s.copy(messagesByEntity = s.messagesByEntity + (env.source.id to list))
                }
            }

            "callback.answer" -> {
                val msg = env.payload["text"]?.jsonPrimitive?.contentOrNull ?: "Done"
                _state.update { it.copy(snackbarMessage = msg) }
            }

            "widget.state" -> {
                val wid = env.payload["widget_id"]?.jsonPrimitive?.contentOrNull ?: return
                val title = env.payload["title"]?.jsonPrimitive?.contentOrNull ?: wid
                val blocks = parseBlocks(env.payload["blocks"])
                if (blocks.isNotEmpty()) {
                    _state.update { s ->
                        val existing = s.widgets.filterNot { it.widgetId == wid && it.entityId == env.source.id }
                        val newCard = WidgetCardUi(wid, env.source.id, title, env.source.name ?: env.source.id, blocks)
                        s.copy(widgets = listOf(newCard) + existing)
                    }
                }
            }

            "tool.result" -> {
                val toolId = env.payload["tool_id"]?.jsonPrimitive?.contentOrNull ?: "tool"
                val status = env.payload["status"]?.jsonPrimitive?.contentOrNull ?: "ok"
                val res = env.payload["result"]?.toString() ?: env.payload["error"]?.toString() ?: ""
                _state.update {
                    it.copy(
                        lastToolResult = "Tool `$toolId` ($status):\n$res",
                        snackbarMessage = "$toolId: $status"
                    )
                }
            }
        }
    }

    private fun parseBlocks(element: JsonElement?): List<WidgetBlockUi> {
        val arr = runCatching { element?.jsonArray }.getOrNull() ?: return emptyList()
        return arr.mapNotNull { item ->
            val obj = runCatching { item.jsonObject }.getOrNull() ?: return@mapNotNull null
            val kind = obj["kind"]?.jsonPrimitive?.contentOrNull ?: return@mapNotNull null
            WidgetBlockUi(
                kind = kind,
                id = obj["id"]?.jsonPrimitive?.contentOrNull ?: "",
                label = obj["label"]?.jsonPrimitive?.contentOrNull ?: "",
                value = obj["value"]?.jsonPrimitive?.floatOrNull ?: 0f,
                display = obj["display"]?.jsonPrimitive?.contentOrNull ?: "",
                checked = obj["checked"]?.jsonPrimitive?.booleanOrNull ?: false
            )
        }
    }

    private fun appendMessage(entityId: String, msg: ChatMessageUi) {
        _state.update { s ->
            val current = s.messagesByEntity[entityId].orEmpty()
            val unread = (s.unreadByEntity[entityId] ?: 0) + if (msg.fromBot) 1 else 0
            s.copy(
                messagesByEntity = s.messagesByEntity + (entityId to (current + msg)),
                unreadByEntity = s.unreadByEntity + (entityId to unread)
            )
        }
    }

    private fun simulateDemoBotReply(entityId: String, text: String) {
        scope.launch {
            if (entityId == "local_ai") {
                val msgId = "demo_stream_${System.currentTimeMillis()}"
                appendMessage(
                    entityId,
                    ChatMessageUi(id = msgId, fromBot = true, text = "", time = nowTime(), isStreaming = true)
                )
                val words = "Generated locally without Telegram: your prompt \"$text\" was processed through Botory Hub.".split(" ")
                for (w in words) {
                    delay(65)
                    _state.update { s ->
                        val updated = s.messagesByEntity[entityId].orEmpty().map { m ->
                            if (m.id == msgId) m.copy(text = if (m.text.isEmpty()) w else "${m.text} $w") else m
                        }
                        s.copy(messagesByEntity = s.messagesByEntity + (entityId to updated))
                    }
                }
                _state.update { s ->
                    val updated = s.messagesByEntity[entityId].orEmpty().map { m ->
                        if (m.id == msgId) m.copy(isStreaming = false) else m
                    }
                    s.copy(messagesByEntity = s.messagesByEntity + (entityId to updated))
                }
                return@launch
            }

            delay(250)
            val replyText = when {
                text.startsWith("/status") -> "Host node is healthy. Connected via Botory Demo."
                text.startsWith("/help") -> "Commands: /status, /deploy, /logs. Or switch to the Widgets tab below!"
                else -> "Received command: \"$text\""
            }
            appendMessage(
                entityId,
                ChatMessageUi(id = "b_${System.currentTimeMillis()}", fromBot = true, text = replyText, time = nowTime())
            )
        }
    }

    private fun simulateDemoCallback(entityId: String, cb: String) {
        scope.launch {
            delay(180)
            when {
                cb.startsWith("svc:") -> _state.update { it.copy(snackbarMessage = "Service nginx: ${cb.substringAfter(':')} executed!") }
                cb == "homelab:stats" -> refreshDemoTelemetry()
                cb == "homelab:logs" -> appendMessage(
                    entityId,
                    ChatMessageUi("b_${System.currentTimeMillis()}", true, "[14:27:09] nginx 200 OK · 1.1ms\n[14:27:12] hub heartbeat OK", nowTime())
                )
                else -> _state.update { it.copy(snackbarMessage = "Callback: $cb") }
            }
        }
    }

    private fun createInitialDemoState(): BotoryUiState {
        val entities = listOf(
            EntityDescriptor(
                id = "homelab_bot",
                name = "HomeLab Sentinel",
                kind = "bot",
                description = "Server monitoring & Docker controller",
                commands = listOf("/status", "/services", "/deploy", "/help")
            ),
            EntityDescriptor(
                id = "desklab_iot",
                name = "DeskLab IoT Bridge",
                kind = "iot",
                description = "MQTT bridge for lighting & sensors",
                commands = listOf("/lights", "/scene_work")
            ),
            EntityDescriptor(
                id = "local_ai",
                name = "Local AI Copilot",
                kind = "ai",
                description = "Local LLM agent with live streaming",
                commands = listOf("/summarize", "/ping")
            ),
            EntityDescriptor(
                id = "file_tools",
                name = "Scripts & Backup Tool",
                kind = "tool",
                description = "Python RPC tools & project runner",
                commands = listOf("/backup"),
                tools = listOf(
                    ToolDefinition(
                        toolId = "backup.run",
                        title = "Quick Project Backup",
                        description = "Archives a local folder into .tar.zst",
                        params = listOf(
                            ToolParam(
                                name = "target",
                                type = "select",
                                label = "Target Directory",
                                options = JsonArray(listOf(JsonPrimitive("~/projects"), JsonPrimitive("~/obsidian"), JsonPrimitive("~/configs")))
                            ),
                            ToolParam(name = "compress", type = "boolean", label = "Compress (.tar.zst)", required = false, default = JsonPrimitive(true))
                        )
                    )
                )
            )
        )

        val msgs = mapOf(
            "homelab_bot" to listOf(
                ChatMessageUi(
                    id = "m1",
                    fromBot = true,
                    text = "Hi! I am HomeLab Sentinel running inside Botory without Telegram.",
                    time = "14:22",
                    buttonRows = listOf(
                        listOf(
                            InlineButton(label = "Metrics", callback = "homelab:stats"),
                            InlineButton(label = "Logs", callback = "homelab:logs")
                        )
                    ),
                    cardTitle = "Node Telemetry",
                    cardBlocks = listOf(
                        WidgetBlockUi("wavy_progress", "cpu", "CPU Load", 0.34f, "34% · 49°C"),
                        WidgetBlockUi("wavy_progress", "ram", "RAM Usage", 0.58f, "9.3 / 16 GB")
                    ),
                    splitButton = SplitButtonUi(
                        primary = InlineButton(label = "Restart nginx", callback = "svc:restart:nginx"),
                        menu = listOf(
                            InlineButton(label = "Graceful Reload", callback = "svc:reload:nginx"),
                            InlineButton(label = "Stop Container", callback = "svc:stop:nginx", tone = "destructive")
                        )
                    )
                )
            ),
            "desklab_iot" to listOf(
                ChatMessageUi("m2", true, "MQTT bridge active. Toggle lights and sensors from the Widgets tab.", "14:10")
            ),
            "local_ai" to listOf(
                ChatMessageUi("m3", true, "Send any prompt — I will stream the reply token by token.", "13:55")
            ),
            "file_tools" to listOf(
                ChatMessageUi("m4", true, "Ready to run @app.tool functions and manage imported .zip projects.", "12:30")
            )
        )

        val widgets = listOf(
            WidgetCardUi(
                widgetId = "pc_telemetry",
                entityId = "homelab_bot",
                title = "System Telemetry",
                subtitle = "Host Node • @app.widget",
                blocks = listOf(
                    WidgetBlockUi("wavy_progress", "cpu", "CPU Load", 0.34f, "34% · 49°C"),
                    WidgetBlockUi("wavy_progress", "ram", "RAM Usage", 0.58f, "58% (9.3 / 16 GB)")
                )
            ),
            WidgetCardUi(
                widgetId = "desk_controls",
                entityId = "desklab_iot",
                title = "DeskLab Controls (IoT)",
                subtitle = "MQTT Bridge",
                blocks = listOf(
                    WidgetBlockUi("toggle_row", "lamp_main", "Desk Lamp", checked = true),
                    WidgetBlockUi("slider", "lamp_brightness", "Brightness", value = 75f, display = "75%")
                )
            )
        )

        return BotoryUiState(
            entities = entities,
            messagesByEntity = msgs,
            widgets = widgets,
            unreadByEntity = mapOf("homelab_bot" to 1)
        )
    }
}
