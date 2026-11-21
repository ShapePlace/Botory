# Botory Architecture

Botory is a local-first automation and messaging platform combining a Python SDK, a local Hub server, an optional internet Relay, and a native Kotlin + Jetpack Compose (Material 3 Expressive) Android client.

## 1. Topology (Local-First + Optional Relay)

```text
+------------------------------+         +------------------------------+
|  Python Bot / AI Agent       |         |  Python IoT / RPC Tools      |
|  SimpleBot / Router / FSM    |         |  @app.tool / @app.widget     |
+--------------+---------------+         +--------------+---------------+
               | WebSocket                              | WebSocket
               v                                        v
+-----------------------------------------------------------------------+
|                       Botory Hub (PC / Termux / SBC)                  |
|  * aiohttp WebSocket Router         * Managed .zip Project Runner     |
|  * HTTP File Upload / Download      * Pairing URI Generator           |
|  * Built-in Web Console             * Outbound Relay Bridge           |
+--------------+----------------------------------------+---------------+
               |                                        |
      [LAN / Localhost]                         [Internet / WSS]
               |                                        v
               |                         +------------------------------+
               |                         |   Botory Relay (Optional)    |
               |                         +--------------+---------------+
               |                                        |
               v                                        v
+-----------------------------------------------------------------------+
|       Android Client (Kotlin + Java + Jetpack Compose M3 Expressive)  |
|  * In-App Setup Wizard (Termux / LAN / Demo)                          |
|  * Chats + Bento Widgets + Dynamic Tool Forms + ZIP Project Import    |
+-----------------------------------------------------------------------+
```

## 2. Python SDK (`botory`)

- **Zero-Rust Dependencies:** Relies solely on `aiohttp` and Python standard library dataclasses so installation succeeds cleanly on both desktop and Android Termux.
- **Hybrid Modes:**
  - `SimpleBot`: concise `@bot.command`, `@bot.callback`, `@bot.on_message` handlers (sync or async).
  - `BotoryApp` + `Router` + `F` + `StatesGroup` / `FSMContext`: modular async routing and state machines.
  - `@app.tool()`: inspects Python function signatures and type annotations (`str`, `int`, `float`, `bool`, `Literal[...]`) to auto-generate native Android parameter forms.
  - `@app.widget()` & `@app.on_widget_action()`: pushes live telemetry, toggles, and sliders to the Android Bento dashboard.
  - `msg.stream_reply()`: token-by-token streaming for local LLM agents.

## 3. Managed ZIP Project Runner

The Hub can receive `.zip` archives over HTTP (`POST /api/v1/projects/import`) from the Android client or via `botory import <file.zip>`, validate archive entries against path traversal, extract to `~/.botory/projects/<name>`, detect the Python entrypoint (`botory.json`, `main.py`, `bot.py`, `app.py`, or `run.py`), and start/stop the child process with `BOTORY_HUB_URL` injected automatically.

## 4. Android Client (`android-app/`)

- **Kotlin + Java Interop:** Compose UI and reactive OkHttp WebSocket state (`BotoryClient.kt`) combined with Java URI parsing (`PairingUriParser.java`).
- **Material 3 Expressive:** `MaterialExpressiveTheme`, `MotionScheme.expressive()`, `HorizontalFloatingToolbar`, `LinearWavyProgressIndicator`, `LoadingIndicator`, `SplitButtonLayout`, and organic entity shapes (`BotCookie`, `AiBurst`, `IotSquircle`, `ToolClover`).
