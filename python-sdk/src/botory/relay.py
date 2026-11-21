from __future__ import annotations

from dataclasses import dataclass, field

import aiohttp
from aiohttp import web


@dataclass
class BotoryRelay:
    """Lightweight optional Relay tunnel connecting Android clients to a remote Botory Hub."""

    host: str = "0.0.0.0"
    port: int = 8766

    _hubs: dict[str, web.WebSocketResponse] = field(default_factory=dict, init=False)
    _clients: dict[str, set[web.WebSocketResponse]] = field(default_factory=dict, init=False)
    _runner: web.AppRunner | None = field(default=None, init=False)
    _site: web.TCPSite | None = field(default=None, init=False)
    _bound_port: int = field(default=0, init=False)

    @property
    def bound_port(self) -> int:
        return self._bound_port or self.port

    def build_app(self) -> web.Application:
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/ws/hub/{hub_id}", self._hub_ws)
        app.router.add_get("/ws/client/{hub_id}", self._client_ws)
        return app

    async def start(self) -> None:
        self._runner = web.AppRunner(self.build_app())
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, self.host, self.port)
        await self._site.start()
        if self._site._server and self._site._server.sockets:
            self._bound_port = self._site._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        for ws in list(self._hubs.values()):
            await ws.close()
        for clients in self._clients.values():
            for ws in list(clients):
                await ws.close()
        if self._runner:
            await self._runner.cleanup()

    async def _health(self, _: web.Request) -> web.Response:
        return web.json_response({"status": "ok", "connected_hubs": list(self._hubs.keys())})

    async def _hub_ws(self, request: web.Request) -> web.WebSocketResponse:
        hub_id = request.match_info["hub_id"]
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        self._hubs[hub_id] = ws
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                for client_ws in list(self._clients.get(hub_id, set())):
                    if not client_ws.closed:
                        await client_ws.send_str(msg.data)
        finally:
            if self._hubs.get(hub_id) is ws:
                self._hubs.pop(hub_id, None)
        return ws

    async def _client_ws(self, request: web.Request) -> web.WebSocketResponse:
        hub_id = request.match_info["hub_id"]
        ws = web.WebSocketResponse(heartbeat=25)
        await ws.prepare(request)
        self._clients.setdefault(hub_id, set()).add(ws)
        hub_ws = self._hubs.get(hub_id)
        if hub_ws and not hub_ws.closed:
            await hub_ws.send_str(
                '{"type":"relay.client_joined","source":{"kind":"relay","id":"relay"},"target":{"kind":"hub","id":"'
                + hub_id
                + '"},"payload":{}}'
            )
        try:
            async for msg in ws:
                if msg.type != aiohttp.WSMsgType.TEXT:
                    continue
                hub_ws = self._hubs.get(hub_id)
                if hub_ws and not hub_ws.closed:
                    await hub_ws.send_str(msg.data)
        finally:
            self._clients.get(hub_id, set()).discard(ws)
        return ws
