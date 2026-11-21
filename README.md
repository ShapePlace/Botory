# Botory

**Botory** is a local-first ecosystem for Python bots, IoT bridges, AI agents, live Bento widgets, and RPC tools — featuring a native **Kotlin + Jetpack Compose (Material 3 Expressive)** Android client without Telegram or third-party cloud lock-in.

## Highlights

- **Local-First & Hybrid Relay:** Connects directly over Wi-Fi / LAN or Termux localhost (`127.0.0.1:8765`), with optional Relay tunneling for remote access.
- **Hybrid Python SDK (`botory`):**
  - `SimpleBot` for fast sync/async scripts;
  - `BotoryApp` + `Router` + `FSM` + streaming (`stream_reply()`) for structured agents;
  - `@app.tool()` (automatic parameter schema extraction into native Android forms) and `@app.widget()` (live Bento telemetry, toggles, and sliders).
- **Zero-Rust Termux Compatibility:** Built on `aiohttp` and Python standard library dataclasses (`pip install botory` works on Android Termux without Rust or native compilation).
- **ZIP Project Import & Runner:** Import `.zip` Python projects directly from the Android app (or CLI) into the Hub and start/stop them remotely.
- **Material 3 Expressive Android Client:** Built with Jetpack Compose (`MaterialExpressiveTheme`, `MotionScheme.expressive()`, `HorizontalFloatingToolbar`, `LinearWavyProgressIndicator`, `SplitButtonLayout`).

---

## Repository Structure

```text
Botory/
├── .github/workflows/
│   ├── android-apk.yml     # CI: Python tests, package build & Android Debug APK
│   └── publish-pypi.yml    # Release workflow for PyPI publishing
├── python-sdk/             # Python package `botory` (SDK + Hub + Relay + CLI)
├── android-app/            # Android app (Kotlin + Java + Jetpack Compose M3 Expressive)
├── prototype/index.html    # Interactive Material 3 Expressive UI & protocol studio
└── docs/                   # Architecture, protocol, and UI specifications
```

---

## Quick Start (Python SDK & Hub)

```bash
pip install -e "./python-sdk[dev]"
botory setup
botory hub
```

Run an example bot or widget service in another terminal:

```bash
python python-sdk/examples/simple_bot.py
# or
python python-sdk/examples/tools_and_widgets.py
```

Import and manage `.zip` Python projects from CLI:

```bash
botory import my_project.zip
botory projects
```

---

## Building the Android APK

Every push and pull request runs `.github/workflows/android-apk.yml`, compiling unit tests and publishing `app-debug.apk` as a workflow artifact under **Actions**.

The APK includes an **in-app Setup Wizard** (supporting same-device **Termux**, **LAN Hub**, **Pairing URI**, and an interactive **Demo** mode) alongside **ZIP Python project import**.
