from __future__ import annotations

import asyncio
import inspect
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Literal

import aiohttp

from .models import (
    BaseModel,
    ButtonGroup,
    EndpointRef,
    EntityDescriptor,
    Envelope,
    ExpressiveCard,
    InlineButton,
    SplitButton,
    ToolDefinition,
    WidgetDefinition,
    extract_tool_schema,
    new_event_id,
)


# =========================================================
# FSM (Finite State Machine)
# =========================================================

class State:
    def __init__(self) -> None:
        self.name: str = ""

    def __set_name__(self, owner: type[Any], name: str) -> None:
        self.name = f"{owner.__name__}.{name}"

    def __str__(self) -> str:
        return self.name


class StatesGroup:
    pass


class MemoryStorage:
    def __init__(self) -> None:
        self._states: dict[str, str | None] = {}
        self._data: dict[str, dict[str, Any]] = {}

    async def set_state(self, key: str, state: State | str | None) -> None:
        self._states[key] = str(state) if state is not None else None

    async def get_state(self, key: str) -> str | None:
        return self._states.get(key)

    async def update_data(self, key: str, **kwargs: Any) -> dict[str, Any]:
        bucket = self._data.setdefault(key, {})
        bucket.update(kwargs)
        return dict(bucket)

    async def get_data(self, key: str) -> dict[str, Any]:
        return dict(self._data.get(key, {}))

    async def clear(self, key: str) -> None:
        self._states.pop(key, None)
        self._data.pop(key, None)


class FSMContext:
    def __init__(self, storage: MemoryStorage, key: str) -> None:
        self._storage = storage
        self._key = key

    async def set_state(self, state: State | str | None) -> None:
        await self._storage.set_state(self._key, state)

    async def get_state(self) -> str | None:
        return await self._storage.get_state(self._key)

    async def update_data(self, **kwargs: Any) -> dict[str, Any]:
        return await self._storage.update_data(self._key, **kwargs)

    async def get_data(self) -> dict[str, Any]:
        return await self._storage.get_data(self._key)

    async def clear(self) -> None:
        await self._storage.clear(self._key)


# =========================================================
# FILTERS (`F`)
# =========================================================

FilterFn = Callable[[dict[str, Any], str | None], bool]


class _CallbackFilter:
    def __call__(self, exact: str) -> FilterFn:
        return lambda payload, _st: payload.get("data") == exact

    def startswith(self, prefix: str) -> FilterFn:
        return lambda payload, _st: str(payload.get("data", "")).startswith(prefix)


class _FilterFactory:
    def __init__(self) -> None:
        self.callback = _CallbackFilter()

    @property
    def text(self) -> FilterFn:
        return lambda payload, _st: bool(payload.get("text"))

    def command(self, name: str) -> FilterFn:
        cmd = "/" + name.lstrip("/")

        def _match(payload: dict[str, Any], _st: str | None) -> bool:
            txt = str(payload.get("text", "")).strip()
            return txt == cmd or txt.startswith(cmd + " ")

        return _match

    def state(self, target_state: State | str) -> FilterFn:
        s = str(target_state)
        return lambda _payload, current_state: current_state == s


F = _FilterFactory()


# =========================================================
# CONTEXT OBJECTS
# =========================================================

def _normalize_buttons(
    buttons: list[list[tuple[str, str] | InlineButton]] | None,
    components: list[BaseModel | dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if buttons:
        for row in buttons:
            items = [
                btn if isinstance(btn, InlineButton) else InlineButton(label=btn[0], callback=btn[1])
                for btn in row
            ]
            result.append(ButtonGroup(items=items).model_dump())
    if components:
        for comp in components:
            result.append(comp.model_dump() if isinstance(comp, BaseModel) else comp)
    return result


class StreamWriter:
    def __init__(self, app: "BotoryApp", target: EndpointRef) -> None:
        self._app = app
        self._target = target
        self.message_id = new_event_id("msg")

    async def __aenter__(self) -> "StreamWriter":
        await self._app._emit(
            "stream.start",
            self._target,
            {"message_id": self.message_id},
        )
        return self

    async def write(self, delta: str) -> None:
        await self._app._emit(
            "stream.delta",
            self._target,
            {"message_id": self.message_id, "delta": delta},
        )

    async def __aexit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
        await self._app._emit(
            "stream.end",
            self._target,
            {"message_id": self.message_id},
        )


class MessageContext:
    def __init__(self, app: "BotoryApp", env: Envelope) -> None:
        self._app = app
        self.envelope = env
        self.text: str = str(env.payload.get("text", ""))
        self.source = env.source

    async def reply(
        self,
        text: str,
        buttons: list[list[tuple[str, str] | InlineButton]] | None = None,
        components: list[BaseModel | dict[str, Any]] | None = None,
        card: ExpressiveCard | dict[str, Any] | None = None,
        parse_mode: str = "markdown",
    ) -> None:
        payload: dict[str, Any] = {
            "text": text,
            "parse_mode": parse_mode,
            "components": _normalize_buttons(buttons, components),
        }
        if card is not None:
            payload["card"] = card.model_dump() if isinstance(card, BaseModel) else card
        await self._app._emit("message.new", self.source, payload)

    def stream_reply(self) -> StreamWriter:
        return StreamWriter(self._app, self.source)

    async def send_file(self, file_path: str | Path, caption: str = "") -> dict[str, Any]:
        info = await self._app.upload_file(file_path)
        await self._app._emit(
            "file.offer",
            self.source,
            {**info, "caption": caption},
        )
        return info


class CallbackContext:
    def __init__(self, app: "BotoryApp", env: Envelope) -> None:
        self._app = app
        self.envelope = env
        self.data: str = str(env.payload.get("data", ""))
        self.source = env.source
        self.message = MessageContext(app, env)

    async def answer(self, text: str = "", toast: bool = True) -> None:
        await self._app._emit(
            "callback.answer",
            self.source,
            {"callback_id": self.envelope.id, "text": text, "toast": toast},
        )


class SimpleContext:
    """Sync-friendly context for SimpleBot handlers (callable without await)."""

    def __init__(self, inner: MessageContext | CallbackContext) -> None:
        self._inner = inner
        self.text = getattr(inner, "text", "")
        self.data = getattr(inner, "data", "")
        self._pending: list[Any] = []

    def reply(
        self,
        text: str,
        buttons: list[list[tuple[str, str] | InlineButton]] | None = None,
        card: ExpressiveCard | dict[str, Any] | None = None,
    ) -> None:
        target = self._inner.message if isinstance(self._inner, CallbackContext) else self._inner
        self._pending.append(target.reply(text, buttons=buttons, card=card))

    def answer(self, text: str = "", toast: bool = True) -> None:
        if isinstance(self._inner, CallbackContext):
            self._pending.append(self._inner.answer(text=text, toast=toast))

    async def flush(self) -> None:
        for coro in self._pending:
            await coro
        self._pending.clear()


# =========================================================
# ROUTER & HYBRID APP
# =========================================================

@dataclass
class _HandlerEntry:
    filters: tuple[FilterFn, ...]
    fn: Callable[..., Any]


class Router:
    def __init__(self) -> None:
        self._message_handlers: list[_HandlerEntry] = []
        self._callback_handlers: list[_HandlerEntry] = []
        self._commands: set[str] = set()

    def message(self, *filters: FilterFn) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._message_handlers.append(_HandlerEntry(filters=filters, fn=fn))
            return fn

        return decorator

    def command(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        cmd = "/" + name.lstrip("/")
        self._commands.add(cmd)
        return self.message(F.command(cmd))

    def callback(self, *filters_or_str: FilterFn | str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        normalized: list[FilterFn] = []
        for item in filters_or_str:
            if isinstance(item, str):
                normalized.append(F.callback(item))
            else:
                normalized.append(item)

        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._callback_handlers.append(_HandlerEntry(filters=tuple(normalized), fn=fn))
            return fn

        return decorator


async def _invoke(fn: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    if inspect.iscoroutinefunction(fn):
        return await fn(*args, **kwargs)
    return fn(*args, **kwargs)


class BotoryApp:
    """Hybrid async client for Botory Hub: bots (Router/FSM) + Tools + Live Widgets."""

    def __init__(
        self,
        entity_id: str,
        name: str,
        kind: Literal["bot", "iot", "ai", "tool"] = "bot",
        description: str = "",
        hub_url: str | None = None,
    ) -> None:
        self.entity_id = entity_id
        self.name = name
        self.kind = kind
        self.description = description
        resolved_hub = hub_url or os.environ.get("BOTORY_HUB_URL") or "ws://127.0.0.1:8765"
        self.hub_url = resolved_hub.rstrip("/")

        self.storage = MemoryStorage()
        self.routers: list[Router] = [Router()]
        self._tools: dict[str, tuple[ToolDefinition, Callable[..., Any]]] = {}
        self._widgets: dict[str, tuple[WidgetDefinition, Callable[..., Any]]] = {}
        self._widget_actions: dict[str, Callable[..., Any]] = {}

        self._session: aiohttp.ClientSession | None = None
        self._ws: aiohttp.ClientWebSocketResponse | None = None
        self._tasks: list[asyncio.Task[Any]] = []
        self._connected_event = asyncio.Event()

    @property
    def router(self) -> Router:
        return self.routers[0]

    def include_router(self, router: Router) -> None:
        self.routers.append(router)

    def tool(
        self,
        id: str,
        title: str | None = None,
        description: str | None = None,
        icon: str = "bolt",
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            schema = extract_tool_schema(fn, tool_id=id, title=title, description=description, icon=icon)
            self._tools[id] = (schema, fn)
            return fn

        return decorator

    def widget(
        self,
        id: str,
        title: str,
        interval: float = 5.0,
    ) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._widgets[id] = (WidgetDefinition(widget_id=id, title=title, interval=interval), fn)
            return fn

        return decorator

    def on_widget_action(self, widget_id: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            self._widget_actions[widget_id] = fn
            return fn

        return decorator

    def build_descriptor(self) -> EntityDescriptor:
        cmds: list[str] = sorted({c for r in self.routers for c in r._commands})
        return EntityDescriptor(
            id=self.entity_id,
            name=self.name,
            kind=self.kind,
            description=self.description,
            commands=cmds,
            tools=[t[0] for t in self._tools.values()],
            widgets=[w[0] for w in self._widgets.values()],
            online=True,
        )

    async def _emit(self, event_type: str, target: EndpointRef, payload: dict[str, Any]) -> None:
        if not self._ws or self._ws.closed:
            return
        env = Envelope(
            type=event_type,
            source=EndpointRef(kind=self.kind, id=self.entity_id, name=self.name),
            target=target,
            payload=payload,
        )
        await self._ws.send_str(env.model_dump_json())

    async def upload_file(self, file_path: str | Path) -> dict[str, Any]:
        p = Path(file_path)
        http_base = self.hub_url.replace("ws://", "http://").replace("wss://", "https://")
        assert self._session is not None
        data = aiohttp.FormData()
        data.add_field("file", p.read_bytes(), filename=p.name)
        async with self._session.post(f"{http_base}/api/v1/files/upload", data=data) as resp:
            resp.raise_for_status()
            return await resp.json()

    async def start(self) -> None:
        self._session = aiohttp.ClientSession()
        self._ws = await self._session.ws_connect(f"{self.hub_url}/ws/entity", heartbeat=25)
        await self._emit(
            "entity.register",
            EndpointRef(kind="hub", id="*"),
            self.build_descriptor().model_dump(),
        )
        # Wait for registration ack before signaling ready
        ack_msg = await self._ws.receive_str()
        _ = Envelope.model_validate_json(ack_msg)
        self._connected_event.set()

        self._tasks.append(asyncio.create_task(self._listen_loop()))
        for wid, (wdef, wfn) in self._widgets.items():
            self._tasks.append(asyncio.create_task(self._widget_loop(wid, wdef, wfn)))

    async def stop(self) -> None:
        for t in self._tasks:
            t.cancel()
        for t in self._tasks:
            try:
                await t
            except asyncio.CancelledError:
                pass
        self._tasks.clear()
        if self._ws and not self._ws.closed:
            await self._ws.close()
        if self._session and not self._session.closed:
            await self._session.close()

    def run(self) -> None:
        async def _runner() -> None:
            await self.start()
            try:
                while any(not t.done() for t in self._tasks):
                    await asyncio.sleep(0.5)
            finally:
                await self.stop()

        try:
            asyncio.run(_runner())
        except KeyboardInterrupt:
            pass

    async def _widget_loop(self, widget_id: str, wdef: WidgetDefinition, wfn: Callable[..., Any]) -> None:
        while True:
            try:
                blocks = await _invoke(wfn)
                serialized = [b.model_dump() if isinstance(b, BaseModel) else b for b in blocks]
                await self._emit(
                    "widget.state",
                    EndpointRef(kind="client", id="*"),
                    {"widget_id": widget_id, "title": wdef.title, "blocks": serialized},
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                pass
            await asyncio.sleep(wdef.interval)

    async def _listen_loop(self) -> None:
        assert self._ws is not None
        async for msg in self._ws:
            if msg.type != aiohttp.WSMsgType.TEXT:
                continue
            env = Envelope.model_validate_json(msg.data)
            await self._dispatch(env)

    async def _call_handler_with_di(
        self,
        fn: Callable[..., Any],
        ctx_obj: Any,
        fsm: FSMContext,
    ) -> Any:
        sig = inspect.signature(fn)
        kwargs: dict[str, Any] = {}
        if "state" in sig.parameters:
            kwargs["state"] = fsm
        return await _invoke(fn, ctx_obj, **kwargs)

    async def _dispatch(self, env: Envelope) -> None:
        fsm_key = f"{env.source.id}:{self.entity_id}"
        fsm = FSMContext(self.storage, fsm_key)
        current_state = await fsm.get_state()

        if env.type == "message.new":
            ctx = MessageContext(self, env)
            for router in self.routers:
                for entry in router._message_handlers:
                    if all(f(env.payload, current_state) for f in entry.filters):
                        await self._call_handler_with_di(entry.fn, ctx, fsm)
                        return

        elif env.type == "callback.query":
            ctx_cb = CallbackContext(self, env)
            for router in self.routers:
                for entry in router._callback_handlers:
                    if all(f(env.payload, current_state) for f in entry.filters):
                        await self._call_handler_with_di(entry.fn, ctx_cb, fsm)
                        return

        elif env.type == "tool.call":
            tool_id = str(env.payload.get("tool_id", ""))
            args = dict(env.payload.get("args", {}))
            entry = self._tools.get(tool_id)
            if not entry:
                await self._emit(
                    "tool.result",
                    env.source,
                    {"tool_id": tool_id, "call_id": env.id, "status": "error", "error": "Unknown tool"},
                )
                return
            _, fn = entry
            try:
                res = await _invoke(fn, **args)
                await self._emit(
                    "tool.result",
                    env.source,
                    {"tool_id": tool_id, "call_id": env.id, "status": "ok", "result": res},
                )
            except Exception as exc:
                await self._emit(
                    "tool.result",
                    env.source,
                    {"tool_id": tool_id, "call_id": env.id, "status": "error", "error": str(exc)},
                )

        elif env.type == "widget.action":
            widget_id = str(env.payload.get("widget_id", ""))
            action_fn = self._widget_actions.get(widget_id)
            if action_fn:
                action_args = {k: v for k, v in env.payload.items() if k != "widget_id"}
                res = await _invoke(action_fn, **action_args)
                await self._emit(
                    "widget.state",
                    env.source,
                    {"widget_id": widget_id, "ack": True, "result": res},
                )


class SimpleBot:
    """Minimalist sync/async API (telebot-style) built on top of BotoryApp."""

    def __init__(
        self,
        entity_id: str,
        name: str,
        hub_url: str | None = None,
        kind: Literal["bot", "iot", "ai", "tool"] = "bot",
    ) -> None:
        self.app = BotoryApp(entity_id=entity_id, name=name, kind=kind, hub_url=hub_url)

    def command(self, name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            async def wrapper(msg: MessageContext) -> None:
                sctx = SimpleContext(msg)
                await _invoke(fn, sctx)
                await sctx.flush()

            self.app.router.command(name)(wrapper)
            return fn

        return decorator

    def on_message(self) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            async def wrapper(msg: MessageContext) -> None:
                sctx = SimpleContext(msg)
                await _invoke(fn, sctx)
                await sctx.flush()

            self.app.router.message(F.text)(wrapper)
            return fn

        return decorator

    def callback(self, data: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
        def decorator(fn: Callable[..., Any]) -> Callable[..., Any]:
            async def wrapper(cb: CallbackContext) -> None:
                sctx = SimpleContext(cb)
                await _invoke(fn, sctx)
                await sctx.flush()

            self.app.router.callback(data)(wrapper)
            return fn

        return decorator

    async def start(self) -> None:
        await self.app.start()

    async def stop(self) -> None:
        await self.app.stop()

    def run(self) -> None:
        self.app.run()
