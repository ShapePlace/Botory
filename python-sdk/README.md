# botory

**Botory** is a local-first Python SDK, Hub, and optional Relay for building bots, IoT bridges, AI agents, live widgets, and RPC tools that talk directly to a native Android client — without Telegram or third-party cloud lock-in.

## Installation

```bash
pip install botory
```

*(Zero Rust dependencies — works cleanly on desktop Linux/macOS/Windows and Android Termux.)*

## Quick Start

1. Run the interactive setup wizard (optional) or launch the local Hub:

```bash
botory setup
botory hub --host 0.0.0.0 --port 8765
```

2. Create a bot (`bot.py`):

```python
from botory import SimpleBot

bot = SimpleBot(entity_id="hello_bot", name="Hello Bot")

@bot.command("start")
def start(ctx):
    ctx.reply("Hello from Botory!", buttons=[[("Check Status", "cb:status")]])

@bot.callback("cb:status")
def status(ctx):
    ctx.answer("Everything is running smoothly!")

bot.run()
```

3. Build live Bento widgets and RPC tools (`@app.tool`, `@app.widget`):

```python
from typing import Literal
from botory import BotoryApp, WavyProgress

app = BotoryApp(entity_id="homelab", name="HomeLab", kind="tool")

@app.tool(id="backup.run", title="Quick Project Backup")
async def run_backup(target: Literal["~/projects", "~/configs"] = "~/projects", compress: bool = True):
    return {"ok": True, "archive": f"{target}.tar.zst", "compressed": compress}

@app.widget(id="cpu_load", title="CPU", interval=2.0)
async def cpu_widget():
    return [WavyProgress(label="CPU", value=0.32, display="32%")]

app.run()
```
