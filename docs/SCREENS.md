# Botory Screen Reference

This document maps each implemented screen in `android-app/app/src/main/java/dev/botory/android/` to its components and responsibilities.

1. **`SetupScreen.kt` — Onboarding & Connection Setup**
   - Same-device Termux quick setup card (`ws://127.0.0.1:8765`) with CLI snippet (`pip install botory`, `botory setup`, `botory hub`).
   - Custom LAN IP or `botory://pair?...` URI input.
   - Demo mode entry button.
2. **`ChatsScreen.kt` — Entities Feed**
   - Header with active Hub summary and `TransportStatusChip`.
   - Search bar and category `FilterChip` row (`All`, `Bots`, `IoT`, `Local AI`, `Tools`).
   - Entity cards with distinct `BotoryShapes` avatars and unread badges.
3. **`ChatRoomScreen.kt` — Interactive Chat**
   - `TopAppBar` with shaped entity badge.
   - Scrollable slash-command `SuggestionChip` row.
   - Grouped bubbles supporting streaming `LoadingIndicator`, embedded `LinearWavyProgressIndicator` cards, `FilledTonalButton` rows, and `SplitButtonLayout`.
4. **`WidgetsScreen.kt` — Bento Dashboard & Tool Forms**
   - Live `LinearWavyProgressIndicator` telemetry cards.
   - Interactive `Switch` and `Slider` controls.
   - `@app.tool` list launching a schema-driven `ModalBottomSheet` parameter form.
5. **`HubScreen.kt` — Hub, Network & ZIP Project Importer**
   - Active Hub status and `TransportMode` switcher.
   - Connection input with one-tap `Termux` localhost button.
   - Android document picker (`ActivityResultContracts.OpenDocument`) uploading `.zip` Python projects to the Hub with `Run / Stop` lifecycle toggles.
