# Botory Design & Screen Overview (Material 3 Expressive)

## Design Principles

- **Material 3 Expressive:** Uses `MaterialExpressiveTheme`, `MotionScheme.expressive()`, dynamic Material You colors (with expressive fallback palettes), and organic entity shapes (`BotCookie`, `IotSquircle`, `AiBurst`, `ToolClover`).
- **Network Semantics:** Clear status indicators for `Demo`, `LAN` (Wi-Fi / localhost), `Relay` (remote tunnel), and `Offline` (local queue).
- **Navigation Chrome:** A bottom `HorizontalFloatingToolbar` switches between **Chats**, **Widgets**, and **Hub**, paired with a `VibrantFloatingActionButton` quick-action menu.

## Core Screens

1. **Setup Wizard (`SetupScreen`):** First-run onboarding for same-device **Termux** (`127.0.0.1:8765`), custom **LAN / Pairing URI**, or **Interactive Demo**.
2. **Chats Feed (`ChatsScreen`):** Searchable, filterable list of bots, IoT bridges, local AI agents, and tools with shaped avatars and unread badges.
3. **Chat Room (`ChatRoomScreen`):** Slash-command chips, Markdown-ready bubbles, streaming indicator, inline button rows, `SplitButtonLayout`, and embedded `LinearWavyProgressIndicator` cards.
4. **Widgets & Tools (`WidgetsScreen`):** Bento dashboard for live system telemetry, IoT switches/sliders, and dynamically generated `@app.tool` forms (`ModalBottomSheet`).
5. **Hub & ZIP Runner (`HubScreen`):** Transport switcher (`Demo / LAN / Relay / Offline`), Hub connection box with one-tap `Termux` preset, `.zip` Python project importer, managed project `Run / Stop` controls, and live connected entities list.
