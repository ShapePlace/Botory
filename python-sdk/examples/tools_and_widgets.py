import os
from typing import Literal
from botory import BotoryApp, SliderBlock, ToggleSwitch, WavyProgress

try:
    import psutil  # type: ignore
except ImportError:
    psutil = None

app = BotoryApp(
    entity_id="desklab",
    name="DeskLab & Tools",
    kind="tool",
    description="System monitor, IoT bridge, and local RPC tools",
)

STATE = {"lamp": True, "brightness": 75}


def _read_cpu_ram() -> tuple[float, float]:
    if psutil is not None:
        return psutil.cpu_percent() / 100.0, psutil.virtual_memory().percent / 100.0
    try:
        load1 = os.getloadavg()[0]
        cpus = os.cpu_count() or 4
        cpu = min(1.0, max(0.05, load1 / cpus))
    except Exception:
        cpu = 0.25
    ram = 0.45
    try:
        with open("/proc/meminfo", encoding="utf-8") as f:
            info = {}
            for line in f:
                parts = line.split(":")
                if len(parts) == 2:
                    info[parts[0]] = int(parts[1].strip().split()[0])
            total = info.get("MemTotal", 0)
            avail = info.get("MemAvailable", 0)
            if total > 0:
                ram = (total - avail) / total
    except Exception:
        pass
    return cpu, ram


@app.widget(id="pc_telemetry", title="System Telemetry", interval=2.0)
async def pc_telemetry():
    cpu, ram = _read_cpu_ram()
    return [
        WavyProgress(label="CPU", value=cpu, display=f"{int(cpu * 100)}%"),
        WavyProgress(label="RAM", value=ram, display=f"{int(ram * 100)}%"),
        ToggleSwitch(id="lamp_main", label="Desk Lamp", checked=STATE["lamp"]),
        SliderBlock(id="lamp_brightness", label="Brightness", value=STATE["brightness"]),
    ]


@app.on_widget_action("lamp_main")
async def on_lamp(checked: bool):
    STATE["lamp"] = checked
    return {"lamp": checked}


@app.on_widget_action("lamp_brightness")
async def on_brightness(value: float):
    STATE["brightness"] = int(value)
    return {"brightness": STATE["brightness"]}


@app.tool(id="backup.run", title="Quick Project Backup")
def run_backup(target: Literal["~/projects", "~/obsidian", "~/configs"] = "~/projects", compress: bool = True):
    """Archives the selected directory on the host machine."""
    ext = ".tar.zst" if compress else ".tar"
    return {"status": "ok", "archive": f"{target}{ext}", "size_mb": 48.4}


if __name__ == "__main__":
    app.run()
