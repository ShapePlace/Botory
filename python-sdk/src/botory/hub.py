from __future__ import annotations

import asyncio
import hashlib
import io
import json
import os
import secrets
import shutil
import socket
import subprocess
import sys
import zipfile
from collections import deque
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

import aiohttp
from aiohttp import web

from .models import EndpointRef, EntityDescriptor, Envelope, new_event_id


def _detect_local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def default_projects_dir() -> Path:
    return Path.home() / ".botory" / "projects"


@dataclass
class StoredFile:
    file_id: str
    filename: str
    content_type: str
    data: bytes
    sha256: str


@dataclass
class ConnectedEntity:
    descriptor: EntityDescriptor
    ws: web.WebSocketResponse


@dataclass
class ManagedProject:
    project_id: str
    name: str
    path: Path
    entrypoint: str
    process: asyncio.subprocess.Process | None = None
    logs: deque[str] = field(default_factory=lambda: deque(maxlen=80))
    _log_tasks: list[asyncio.Task[Any]] = field(default_factory=list)

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "name": self.name,
            "path": str(self.path),
            "entrypoint": self.entrypoint,
            "running": self.running,
            "pid": self.process.pid if self.running and self.process else None,
            "logs": list(self.logs),
        }


def _safe_extract_zip(zip_bytes: bytes, dest_dir: Path) -> list[str]:
    dest_root = dest_dir.resolve()
    dest_root.mkdir(parents=True, exist_ok=True)
    extracted: list[str] = []

    with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
        for info in zf.infolist():
            rel_name = info.filename.replace("\\", "/")
            if not rel_name or rel_name.startswith("/"):
                raise ValueError(f"Unsafe absolute path in zip: {info.filename}")
            target = (dest_root / rel_name).resolve()
            if target != dest_root and dest_root not in target.parents:
                raise ValueError(f"Path traversal detected in zip: {info.filename}")
            if info.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info, "r") as src, open(target, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                extracted.append(rel_name)

    # Flatten single top-level wrapper folder if present
    top_entries = list(dest_root.iterdir())
    if len(top_entries) == 1 and top_entries[0].is_dir():
        wrapper = top_entries[0]
        for child in list(wrapper.iterdir()):
            shutil.move(str(child), str(dest_root / child.name))
        wrapper.rmdir()

    return extracted


def _detect_entrypoint(project_dir: Path) -> str:
    manifest = project_dir / "botory.json"
    if manifest.is_file():
        try:
            cfg = json.loads(manifest.read_text(encoding="utf-8"))
            if isinstance(cfg, dict) and cfg.get("entrypoint"):
                return str(cfg["entrypoint"])
        except Exception:
            pass

    for candidate in ("main.py", "bot.py", "app.py", "run.py"):
        if (project_dir / candidate).is_file():
            return candidate

    py_files = sorted(p.relative_to(project_dir).as_posix() for p in project_dir.rglob("*.py"))
    return py_files[0] if py_files else ""


@dataclass
class BotoryHub:
    """Local Botory Hub server: WebSocket router + HTTP files + ZIP project runner + optional Relay."""

    hub_name: str = "Botory Hub"
    hub_id: str = field(default_factory=lambda: f"hub_{secrets.token_hex(4)}")
    host: str = "0.0.0.0"
    port: int = 8765
    pairing_token: str = field(default_factory=lambda: secrets.token_urlsafe(16))
    relay_url: str | None = None
    projects_dir: Path = field(default_factory=default_projects_dir)

    _entities: dict[str, ConnectedEntity] = field(default_factory=dict, init=False)
    _clients: dict[str, web.WebSocketResponse] = field(default_factory=dict, init=False)
    _files: dict[str, StoredFile] = field(default_factory=dict, init=False)
    _projects: dict[str, ManagedProject] = field(default_factory=dict, init=False)
    _runner: web.AppRunner | None = field(default=None, init=False)
    _site: web.TCPSite | None = field(default=None, init=False)
    _relay_task: asyncio.Task[Any] | None = field(default=None, init=False)
    _relay_ws: aiohttp.ClientWebSocketResponse | None = field(default=None, init=False)
    _bound_port: int = field(default=0, init=False)

    @property
    def bound_port(self) -> int:
        return self._bound_port or self.port

    def build_pairing_uri(self, advertise_host: str | None = None) -> str:
        ip = advertise_host or _detect_local_ip()
        params: dict[str, str] = {
            "v": "1",
            "hub": self.hub_id,
            "name": self.hub_name,
            "lan": f"{ip}:{self.bound_port}",
            "token": self.pairing_token,
        }
        if self.relay_url:
            params["relay"] = self.relay_url
        return f"botory://pair?{urlencode(params)}"

    def build_app(self) -> web.Application:
        app = web.Application(client_max_size=128 * 1024 * 1024)
        app.router.add_get("/", self._handle_web_ui)
        app.router.add_get("/api/v1/health", self._handle_health)
        app.router.add_get("/api/v1/entities", self._handle_entities)
        app.router.add_get("/api/v1/pair", self._handle_pair_info)
        app.router.add_post("/api/v1/files/upload", self._handle_file_upload)
        app.router.add_get("/api/v1/files/{file_id}", self._handle_file_download)
        app.router.add_get("/api/v1/projects", self._handle_projects_list)
        app.router.add_post("/api/v1/projects/import", self._handle_project_import)
        app.router.add_post("/api/v1/projects/{project_id}/start", self._handle_project_start)
        app.router.add_post("/api/v1/projects/{project_id}/stop", self._handle_project_stop)
        app.router.add_get("/ws/entity", self._handle_entity_ws)
        app.router.add_get("/ws/client", self._handle_client_ws)
        return app

    def _scan_existing_projects(self) -> None:
        if not self.projects_dir.exists():
            return
        for entry in sorted(self.projects_dir.iterdir()):
            if not entry.is_dir():
                continue
            pid = entry.name
            if pid not in self._projects:
                ep = _detect_entrypoint(entry)
                if ep:
                    self._projects[pid] = ManagedProject(
                        project_id=pid,
                        name=pid,
                        path=entry,
                        entrypoint=ep,
                    )

    async def start(self) -> None:
        self.projects_dir.mkdir(parents=True, exist_ok=True)
        self._scan_existing_projects()
        app = self.build_app()
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        if self._site._server and self._site._server.sockets:
            self._bound_port = self._site._server.sockets[0].getsockname()[1]
        if self.relay_url:
            self._relay_task = asyncio.create_task(self._relay_bridge_loop())

    async def stop(self) -> None:
        for proj in list(self._projects.values()):
            await self.stop_project(proj.project_id)
        if self._relay_task:
            self._relay_task.cancel()
            try:
                await self._relay_task
            except asyncio.CancelledError:
                pass
        if self._relay_ws and not self._relay_ws.closed:
            await self._relay_ws.close()
        for ws in list(self._clients.values()):
            await ws.close()
        for ent in list(self._entities.values()):
            await ent.ws.close()
        if self._runner:
            await self._runner.cleanup()

    def import_project_zip(self, zip_bytes: bytes, filename: str) -> ManagedProject:
        base_name = Path(filename).stem or f"project_{secrets.token_hex(3)}"
        safe_name = "".join(ch if ch.isalnum() or ch in ("-", "_") else "_" for ch in base_name).strip("_") or "project"
        project_id = safe_name
        dest_dir = self.projects_dir / project_id
        if dest_dir.exists():
            shutil.rmtree(dest_dir)
        _safe_extract_zip(zip_bytes, dest_dir)
        entrypoint = _detect_entrypoint(dest_dir)
        if not entrypoint:
            raise ValueError("No Python entrypoint (.py) found inside zip archive")
        proj = ManagedProject(project_id=project_id, name=safe_name, path=dest_dir, entrypoint=entrypoint)
        self._projects[project_id] = proj
        return proj

    async def start_project(self, project_id: str) -> ManagedProject:
        proj = self._projects.get(project_id)
        if proj is None:
            raise KeyError(project_id)
        if proj.running:
            return proj
        proj.logs.clear()
        env = os.environ.copy()
        env["BOTORY_HUB_URL"] = f"ws://127.0.0.1:{self.bound_port}"
        env["PYTHONUNBUFFERED"] = "1"
        src_dir = proj.path / "src"
        if src_dir.is_dir():
            prev_pp = env.get("PYTHONPATH", "")
            env["PYTHONPATH"] = f"{src_dir}{os.pathsep}{prev_pp}" if prev_pp else str(src_dir)

        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            proj.entrypoint,
            cwd=str(proj.path),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.STDOUT,
        )
        proj.process = proc

        async def _pump() -> None:
            assert proc.stdout is not None
            try:
                while True:
                    line = await proc.stdout.readline()
                    if not line:
                        break
                    proj.logs.append(line.decode("utf-8", errors="replace").rstrip())
            except asyncio.CancelledError:
                pass

        proj._log_tasks = [asyncio.create_task(_pump())]
        return proj

    async def stop_project(self, project_id: str) -> ManagedProject | None:
        proj = self._projects.get(project_id)
        if proj is None:
            return None
        if proj.process and proj.process.returncode is None:
            proj.process.terminate()
            try:
                await asyncio.wait_for(proj.process.wait(), timeout=2.5)
            except asyncio.TimeoutError:
                proj.process.kill()
                await proj.process.wait()
        for t in proj._log_tasks:
            t.cancel()
        proj._log_tasks.clear()
        return proj

    async def _broadcast_to_clients(self, env: Envelope) -> None:
        raw = env.model_dump_json()
        dead: list[str] = []
        for cid, ws in self._clients.items():
            if ws.closed:
                dead.append(cid)
                continue
            try:
                await ws.send_str(raw)
            except Exception:
                dead.append(cid)
        for cid in dead:
            self._clients.pop(cid, None)

        if self._relay_ws and not self._relay_ws.closed:
            try:
                await self._relay_ws.send_str(raw)
            except Exception:
                pass

    async def _send_entity_sync(self, target_ws: web.WebSocketResponse | None = None) -> None:
        entities_payload = [e.descriptor.model_dump() for e in self._entities.values()]
        env = Envelope(
            type="entity.sync",
            source=EndpointRef(kind="hub", id=self.hub_id, name=self.hub_name),
            target=EndpointRef(kind="client", id="*"),
            payload={"hub_name": self.hub_name, "entities": entities_payload},
        )
        if target_ws is not None:
            await target_ws.send_str(env.model_dump_json())
        else:
            await self._broadcast_to_clients(env)

    async def _route_client_envelope(self, raw_data: str) -> None:
        env = Envelope.model_validate_json(raw_data)
        target_id = env.target.id
        ent = self._entities.get(target_id)
        if ent and not ent.ws.closed:
            await ent.ws.send_str(env.model_dump_json())
        else:
            err = Envelope(
                type="hub.error",
                source=EndpointRef(kind="hub", id=self.hub_id),
                target=env.source,
                payload={"code": "entity_offline", "target": target_id, "reply_to": env.id},
            )
            await self._broadcast_to_clients(err)

    async def _handle_entity_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        registered_id: str | None = None

        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                env = Envelope.model_validate_json(msg.data)
                if env.type == "entity.register":
                    desc = EntityDescriptor.model_validate(env.payload)
                    registered_id = desc.id
                    self._entities[desc.id] = ConnectedEntity(descriptor=desc, ws=ws)
                    ack = Envelope(
                        type="entity.registered",
                        source=EndpointRef(kind="hub", id=self.hub_id, name=self.hub_name),
                        target=EndpointRef(kind=desc.kind, id=desc.id),
                        payload={"ok": True, "hub_id": self.hub_id},
                    )
                    await ws.send_str(ack.model_dump_json())
                    await self._send_entity_sync()
                else:
                    await self._broadcast_to_clients(env)
        finally:
            if registered_id and self._entities.get(registered_id, None) and self._entities[registered_id].ws is ws:
                self._entities.pop(registered_id, None)
                await self._send_entity_sync()

        return ws

    async def _handle_client_ws(self, request: web.Request) -> web.WebSocketResponse:
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        client_id = request.query.get("client_id") or f"client_{uuid4().hex[:8]}"
        self._clients[client_id] = ws

        hello = Envelope(
            type="auth.ok",
            source=EndpointRef(kind="hub", id=self.hub_id, name=self.hub_name),
            target=EndpointRef(kind="client", id=client_id),
            payload={"hub_id": self.hub_id, "hub_name": self.hub_name, "client_id": client_id},
        )
        await ws.send_str(hello.model_dump_json())
        await self._send_entity_sync(ws)

        try:
            async for msg in ws:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    await self._route_client_envelope(msg.data)
        finally:
            self._clients.pop(client_id, None)

        return ws

    async def _relay_bridge_loop(self) -> None:
        assert self.relay_url is not None
        base = self.relay_url.rstrip("/")
        url = f"{base}/ws/hub/{self.hub_id}?token={self.pairing_token}"
        while True:
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.ws_connect(url, heartbeat=25) as ws:
                        self._relay_ws = ws
                        await self._send_entity_sync(ws)  # type: ignore[arg-type]
                        async for msg in ws:
                            if msg.type == aiohttp.WSMsgType.TEXT:
                                env = Envelope.model_validate_json(msg.data)
                                if env.type in ("relay.client_joined", "auth.hello"):
                                    await self._send_entity_sync(ws)  # type: ignore[arg-type]
                                else:
                                    await self._route_client_envelope(msg.data)
            except asyncio.CancelledError:
                raise
            except Exception:
                await asyncio.sleep(2.0)
            finally:
                self._relay_ws = None

    async def _handle_health(self, _: web.Request) -> web.Response:
        return web.json_response(
            {
                "status": "ok",
                "hub_id": self.hub_id,
                "hub_name": self.hub_name,
                "entities": len(self._entities),
                "clients": len(self._clients),
                "projects": len(self._projects),
                "relay_connected": bool(self._relay_ws and not self._relay_ws.closed),
            }
        )

    async def _handle_entities(self, _: web.Request) -> web.Response:
        return web.json_response([e.descriptor.model_dump() for e in self._entities.values()])

    async def _handle_pair_info(self, request: web.Request) -> web.Response:
        host_hdr = request.host.split(":")[0] if request.host else None
        return web.json_response(
            {
                "hub_id": self.hub_id,
                "hub_name": self.hub_name,
                "pair_uri": self.build_pairing_uri(advertise_host=host_hdr),
                "ws_client": f"ws://{host_hdr or _detect_local_ip()}:{self.bound_port}/ws/client",
            }
        )

    async def _handle_file_upload(self, request: web.Request) -> web.Response:
        reader = await request.multipart()
        field_part = await reader.next()
        if field_part is None:
            return web.json_response({"error": "missing file field"}, status=400)
        filename = field_part.filename or "upload.bin"
        content_type = field_part.headers.get("Content-Type", "application/octet-stream")
        data = await field_part.read(decode=False)
        file_id = new_event_id("file")
        sha = hashlib.sha256(data).hexdigest()
        self._files[file_id] = StoredFile(
            file_id=file_id,
            filename=filename,
            content_type=content_type,
            data=data,
            sha256=sha,
        )
        return web.json_response(
            {
                "file_id": file_id,
                "filename": filename,
                "size": len(data),
                "sha256": sha,
                "url": f"/api/v1/files/{file_id}",
            }
        )

    async def _handle_file_download(self, request: web.Request) -> web.Response:
        file_id = request.match_info["file_id"]
        stored = self._files.get(file_id)
        if not stored:
            return web.json_response({"error": "not found"}, status=404)
        return web.Response(
            body=stored.data,
            content_type=stored.content_type,
            headers={"Content-Disposition": f'attachment; filename="{stored.filename}"'},
        )

    async def _handle_projects_list(self, _: web.Request) -> web.Response:
        self._scan_existing_projects()
        return web.json_response([p.to_dict() for p in self._projects.values()])

    async def _handle_project_import(self, request: web.Request) -> web.Response:
        reader = await request.multipart()
        part = await reader.next()
        if part is None:
            return web.json_response({"error": "missing zip file field"}, status=400)
        filename = part.filename or "project.zip"
        data = await part.read(decode=False)
        try:
            proj = self.import_project_zip(data, filename)
        except Exception as exc:
            return web.json_response({"error": str(exc)}, status=400)
        return web.json_response(proj.to_dict(), status=201)

    async def _handle_project_start(self, request: web.Request) -> web.Response:
        project_id = request.match_info["project_id"]
        try:
            proj = await self.start_project(project_id)
        except KeyError:
            return web.json_response({"error": "project not found"}, status=404)
        return web.json_response(proj.to_dict())

    async def _handle_project_stop(self, request: web.Request) -> web.Response:
        project_id = request.match_info["project_id"]
        proj = await self.stop_project(project_id)
        if proj is None:
            return web.json_response({"error": "project not found"}, status=404)
        return web.json_response(proj.to_dict())

    async def _handle_web_ui(self, _: web.Request) -> web.Response:
        html = f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="utf-8"><title>{self.hub_name} — Botory Web Console</title>
<style>
  body {{ font-family: system-ui, sans-serif; background: #141218; color: #ece6f0; margin: 0; padding: 24px; }}
  .wrap {{ max-width: 920px; margin: 0 auto; display: grid; gap: 16px; }}
  .card {{ background: #211f26; border: 1px solid #3b3842; border-radius: 20px; padding: 16px; }}
  .row {{ display: flex; gap: 8px; flex-wrap: wrap; align-items: center; }}
  button, input, select {{ font: inherit; border-radius: 999px; border: 1px solid #4f4b57; padding: 8px 14px; background: #2b2930; color: #fff; }}
  button {{ background: #d0bcff; color: #381e72; font-weight: 700; cursor: pointer; border: none; }}
  #log {{ font-family: monospace; font-size: 12.5px; max-height: 280px; overflow: auto; white-space: pre-wrap; background: #0f0d13; padding: 12px; border-radius: 14px; }}
</style></head>
<body><div class="wrap">
  <div class="card">
    <h2 style="margin:0 0 6px;">{self.hub_name} <small style="opacity:.7;">({self.hub_id})</small></h2>
    <div>Pairing URI: <code id="pairUri">{self.build_pairing_uri()}</code></div>
  </div>
  <div class="card">
    <div class="row">
      <select id="entSelect" style="border-radius:14px;"></select>
      <input id="msgInput" placeholder="Send a message or /command..." style="flex:1;">
      <button onclick="sendMsg()">Send</button>
    </div>
  </div>
  <div class="card">
    <div class="row">
      <strong>Import Python Project (.zip):</strong>
      <input type="file" id="zipFile" accept=".zip">
      <button onclick="uploadZip()">Import &amp; Register</button>
    </div>
    <div id="projectsList" style="margin-top:10px; font-size:13px;"></div>
  </div>
  <div class="card"><div id="log">Connecting to WebSocket...</div></div>
</div>
<script>
  const ws = new WebSocket((location.protocol==='https:'?'wss://':'ws://') + location.host + '/ws/client?client_id=web_console');
  const logEl = document.getElementById('log');
  const sel = document.getElementById('entSelect');
  function append(txt) {{ logEl.textContent = txt + "\\n\\n" + logEl.textContent; }}
  ws.onmessage = e => {{
    const d = JSON.parse(e.data);
    if (d.type === 'entity.sync') {{
      sel.innerHTML = d.payload.entities.map(x => `<option value="${{x.id}}">${{x.name}} (${{x.kind}})</option>`).join('');
    }}
    append(`[${{d.type}}] ` + JSON.stringify(d.payload));
  }};
  function sendMsg() {{
    const target = sel.value;
    const text = document.getElementById('msgInput').value;
    if (!target || !text) return;
    ws.send(JSON.stringify({{
      type: 'message.new',
      source: {{ kind: 'client', id: 'web_console' }},
      target: {{ kind: 'entity', id: target }},
      payload: {{ text }}
    }}));
    document.getElementById('msgInput').value = '';
  }}
  async function loadProjects() {{
    const res = await fetch('/api/v1/projects');
    const items = await res.json();
    document.getElementById('projectsList').innerHTML = items.map(p =>
      `<div style="margin:6px 0;"><b>${{p.name}}</b> (${{p.entrypoint}}) — ${{p.running ? 'RUNNING' : 'STOPPED'}} ` +
      `<button onclick="projAction('${{p.project_id}}','start')">Start</button> ` +
      `<button onclick="projAction('${{p.project_id}}','stop')">Stop</button></div>`
    ).join('') || 'No imported projects yet.';
  }}
  async function uploadZip() {{
    const f = document.getElementById('zipFile').files[0];
    if (!f) return;
    const fd = new FormData();
    fd.append('file', f);
    await fetch('/api/v1/projects/import', {{ method: 'POST', body: fd }});
    await loadProjects();
  }}
  async function projAction(id, act) {{
    await fetch(`/api/v1/projects/${{id}}/${{act}}`, {{ method: 'POST' }});
    await loadProjects();
  }}
  loadProjects();
</script></body></html>"""
        return web.Response(text=html, content_type="text/html")
