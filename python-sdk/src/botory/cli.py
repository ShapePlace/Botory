from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

from .hub import BotoryHub, _detect_local_ip, default_projects_dir
from .relay import BotoryRelay


def config_path() -> Path:
    return Path.home() / ".config" / "botory" / "config.json"


def load_config() -> dict[str, Any]:
    p = config_path()
    if not p.is_file():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_config(cfg: dict[str, Any]) -> Path:
    p = config_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
    return p


def _is_termux() -> bool:
    return "TERMUX_VERSION" in os.environ or "com.termux" in os.environ.get("PREFIX", "")


def _copy_to_clipboard(text: str) -> bool:
    if shutil.which("termux-clipboard-set"):
        try:
            subprocess.run(["termux-clipboard-set"], input=text.encode("utf-8"), check=True)
            return True
        except Exception:
            return False
    return False


def _print_banner(title: str, lines: list[str]) -> None:
    width = max([len(title), *(len(line) for line in lines), 44]) + 4
    border = "+" + "-" * (width - 2) + "+"
    print(f"\033[95m{border}\033[0m")
    print(f"\033[95m|\033[0m \033[1m{title.ljust(width - 4)}\033[0m \033[95m|\033[0m")
    print(f"\033[95m{border}\033[0m")
    for line in lines:
        print(f"\033[95m|\033[0m {line.ljust(width - 4)} \033[95m|\033[0m")
    print(f"\033[95m{border}\033[0m")


def run_setup_wizard() -> int:
    existing = load_config()
    termux = _is_termux()
    local_ip = _detect_local_ip()

    _print_banner(
        "Botory Interactive Setup",
        [
            f"Environment : {'Termux (Android)' if termux else sys.platform}",
            f"Detected IP : {local_ip}",
            f"Projects Dir: {default_projects_dir()}",
        ],
    )

    default_name = existing.get("hub_name", "Termux Hub" if termux else "Botory HomeHub")
    default_host = existing.get("host", "127.0.0.1" if termux else "0.0.0.0")
    default_port = int(existing.get("port", 8765))
    default_relay = existing.get("relay_url") or ""

    print("\nSelect Hub network binding:")
    print("  1) Same-device Termux / Localhost (127.0.0.1)")
    print("  2) Local Wi-Fi / LAN (0.0.0.0)")
    choice = input(f"Choice [{'1' if default_host == '127.0.0.1' else '2'}]: ").strip()
    if choice == "1":
        host = "127.0.0.1"
    elif choice == "2":
        host = "0.0.0.0"
    else:
        host = default_host

    hub_name = input(f"Hub name [{default_name}]: ").strip() or default_name
    port_raw = input(f"Port [{default_port}]: ").strip()
    port = int(port_raw) if port_raw.isdigit() else default_port
    relay_raw = input(f"Optional Relay URL [{default_relay or 'none'}]: ").strip()
    relay_url = None if relay_raw.lower() in ("", "none", "-") else relay_raw

    cfg = {
        "hub_name": hub_name,
        "host": host,
        "port": port,
        "relay_url": relay_url,
    }
    saved_at = save_config(cfg)

    preview_hub = BotoryHub(hub_name=hub_name, host=host, port=port, relay_url=relay_url)
    adv_host = "127.0.0.1" if host == "127.0.0.1" else local_ip
    pair_uri = preview_hub.build_pairing_uri(advertise_host=adv_host)
    copied = _copy_to_clipboard(pair_uri)

    print()
    _print_banner(
        "Setup Complete",
        [
            f"Config saved : {saved_at}",
            f"WebSocket URL: ws://{adv_host}:{port}",
            f"Clipboard    : {'Copied pairing URI!' if copied else 'Copy URI below'}",
        ],
    )
    print(f"\nPairing URI:\n  {pair_uri}\n")
    print("Next steps:")
    print("  1) Start Hub:  botory hub")
    print("  2) Import zip: botory import my_bot_project.zip")
    print("  3) Open the Botory Android app and paste the URL/URI in Hub Setup.\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="botory", description="Botory local Hub, Relay & Project CLI")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("setup", help="Interactive setup wizard (desktop & Termux)")

    p_hub = sub.add_parser("hub", help="Start the local Botory Hub server")
    p_hub.add_argument("--name", default=None)
    p_hub.add_argument("--host", default=None)
    p_hub.add_argument("--port", type=int, default=None)
    p_hub.add_argument("--relay", default=None, help="Optional Relay URL (e.g. wss://relay.example.com)")

    p_relay = sub.add_parser("relay", help="Start an optional Botory Relay tunnel server")
    p_relay.add_argument("--host", default="0.0.0.0")
    p_relay.add_argument("--port", type=int, default=8766)

    p_imp = sub.add_parser("import", help="Import a Python project .zip into ~/.botory/projects")
    p_imp.add_argument("zip_path", help="Path to the .zip archive")

    sub.add_parser("projects", help="List imported Python projects")
    sub.add_parser("doctor", help="Inspect Python & Termux environment readiness")

    args = parser.parse_args(argv)

    if args.cmd == "setup":
        return run_setup_wizard()

    if args.cmd == "doctor":
        import aiohttp

        print(f"Python  : {sys.version.split()[0]}")
        print(f"aiohttp : {aiohttp.__version__}")
        print(f"Termux  : {'yes' if _is_termux() else 'no'}")
        print(f"Projects: {default_projects_dir()}")
        print("Environment OK (zero Rust/C build dependencies).")
        return 0

    if args.cmd == "import":
        zpath = Path(args.zip_path).expanduser()
        if not zpath.is_file():
            print(f"File not found: {zpath}", file=sys.stderr)
            return 1
        hub = BotoryHub()
        proj = hub.import_project_zip(zpath.read_bytes(), zpath.name)
        print(f"Imported project '{proj.name}' -> {proj.path} (entrypoint: {proj.entrypoint})")
        return 0

    if args.cmd == "projects":
        hub = BotoryHub()
        hub._scan_existing_projects()
        if not hub._projects:
            print("No imported projects yet. Use `botory import <file.zip>` or import from the Android app.")
            return 0
        for p in hub._projects.values():
            print(f"- {p.project_id}: {p.entrypoint} ({p.path})")
        return 0

    if args.cmd == "hub":
        cfg = load_config()
        name = args.name or cfg.get("hub_name", "Botory Hub")
        host = args.host or cfg.get("host", "0.0.0.0")
        port = args.port if args.port is not None else int(cfg.get("port", 8765))
        relay = args.relay if args.relay is not None else cfg.get("relay_url")

        hub = BotoryHub(hub_name=name, host=host, port=port, relay_url=relay)

        async def _run_hub() -> None:
            await hub.start()
            adv_host = "127.0.0.1" if host == "127.0.0.1" else _detect_local_ip()
            pair_uri = hub.build_pairing_uri(advertise_host=adv_host)
            _print_banner(
                f"{hub.hub_name} ({hub.hub_id})",
                [
                    f"Listening   : http://{host}:{hub.bound_port}",
                    f"WebSocket   : ws://{adv_host}:{hub.bound_port}/ws/client",
                    f"Projects dir: {hub.projects_dir}",
                    f"Loaded projs: {len(hub._projects)}",
                ],
            )
            print(f"\nPairing URI:\n  {pair_uri}\n")
            try:
                while True:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                pass
            finally:
                await hub.stop()

        try:
            asyncio.run(_run_hub())
        except KeyboardInterrupt:
            pass
        return 0

    if args.cmd == "relay":
        relay = BotoryRelay(host=args.host, port=args.port)

        async def _run_relay() -> None:
            await relay.start()
            print(f"[Botory Relay] listening on ws://{args.host}:{relay.bound_port}")
            try:
                while True:
                    await asyncio.sleep(1.0)
            except asyncio.CancelledError:
                pass
            finally:
                await relay.stop()

        try:
            asyncio.run(_run_relay())
        except KeyboardInterrupt:
            pass
        return 0

    return 1


if __name__ == "__main__":
    raise SystemExit(main())
