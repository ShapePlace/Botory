import asyncio
import json
from typing import Literal

import aiohttp
import pytest

from botory import (
    BotoryApp,
    BotoryHub,
    CallbackContext,
    EndpointRef,
    Envelope,
    F,
    FSMContext,
    MessageContext,
    Router,
    SimpleBot,
    State,
    StatesGroup,
    WavyProgress,
)


async def _recv_until(ws: aiohttp.ClientWebSocketResponse, event_type: str, timeout: float = 3.0) -> Envelope:
    async def _loop() -> Envelope:
        while True:
            msg = await ws.receive_str()
            env = Envelope.model_validate_json(msg)
            if env.type == event_type:
                return env

    return await asyncio.wait_for(_loop(), timeout=timeout)


def test_simple_bot_end_to_end():
    async def _run() -> None:
        hub = BotoryHub(host="127.0.0.1", port=0)
        await hub.start()
        hub_ws_url = f"ws://127.0.0.1:{hub.bound_port}"

        bot = SimpleBot(entity_id="simple_echo", name="Simple Echo", hub_url=hub_ws_url)

        @bot.command("start")
        def on_start(ctx):
            ctx.reply("Hello from SimpleBot!", buttons=[[("Ping", "cb:ping")]])

        @bot.callback("cb:ping")
        def on_ping(ctx):
            ctx.answer("Pong!")

        await bot.start()

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"{hub_ws_url}/ws/client?client_id=test_phone") as ws:
                hello = Envelope.model_validate_json(await ws.receive_str())
                assert hello.type == "auth.ok"

                sync = Envelope.model_validate_json(await ws.receive_str())
                assert sync.type == "entity.sync"
                assert any(e["id"] == "simple_echo" for e in sync.payload["entities"])

                # Send /start command
                cmd_env = Envelope(
                    type="message.new",
                    source=EndpointRef(kind="client", id="test_phone"),
                    target=EndpointRef(kind="entity", id="simple_echo"),
                    payload={"text": "/start"},
                )
                await ws.send_str(cmd_env.model_dump_json())

                reply = await _recv_until(ws, "message.new")
                assert reply.payload["text"] == "Hello from SimpleBot!"
                assert reply.payload["components"][0]["items"][0]["callback"] == "cb:ping"

                # Press inline button
                cb_env = Envelope(
                    type="callback.query",
                    source=EndpointRef(kind="client", id="test_phone"),
                    target=EndpointRef(kind="entity", id="simple_echo"),
                    payload={"data": "cb:ping"},
                )
                await ws.send_str(cb_env.model_dump_json())

                ans = await _recv_until(ws, "callback.answer")
                assert ans.payload["text"] == "Pong!"

        await bot.stop()
        await hub.stop()

    asyncio.run(_run())


def test_router_fsm_streaming_tools_widgets_and_files(tmp_path):
    async def _run() -> None:
        hub = BotoryHub(host="127.0.0.1", port=0)
        await hub.start()
        hub_ws_url = f"ws://127.0.0.1:{hub.bound_port}"
        http_base = f"http://127.0.0.1:{hub.bound_port}"

        app = BotoryApp(entity_id="omni_node", name="Omni Node", kind="tool", hub_url=hub_ws_url)
        router = Router()

        class Flow(StatesGroup):
            waiting_confirm = State()

        @router.command("deploy")
        async def cmd_deploy(msg: MessageContext, state: FSMContext):
            await state.set_state(Flow.waiting_confirm)
            await msg.reply("Confirm?", buttons=[[("Yes", "confirm:yes")]])

        @router.callback("confirm:yes", F.state(Flow.waiting_confirm))
        async def cb_confirm(cb: CallbackContext, state: FSMContext):
            await state.clear()
            await cb.answer("Confirmed!")

        @router.message(F.text)
        async def stream_handler(msg: MessageContext):
            async with msg.stream_reply() as stream:
                await stream.write("chunk1 ")
                await stream.write("chunk2")

        app.include_router(router)

        @app.tool(id="math.add", title="Add numbers")
        def add_nums(a: int, b: int = 10, mode: Literal["fast", "safe"] = "fast", flag: bool = True):
            return {"sum": a + b, "mode": mode, "flag": flag}

        widget_state = {"lamp": False}

        @app.widget(id="telemetry", title="Telemetry", interval=0.15)
        async def telemetry():
            return [WavyProgress(label="CPU", value=0.42, display="42%")]

        @app.on_widget_action("lamp")
        async def toggle_lamp(checked: bool):
            widget_state["lamp"] = checked
            return {"lamp": checked}

        await app.start()

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"{hub_ws_url}/ws/client?client_id=android_1") as ws:
                _ = await ws.receive_str()  # auth.ok
                sync = Envelope.model_validate_json(await ws.receive_str())
                ent = sync.payload["entities"][0]
                # Verify auto-extracted tool schema
                assert ent["tools"][0]["tool_id"] == "math.add"
                params = {p["name"]: p for p in ent["tools"][0]["params"]}
                assert params["a"]["type"] == "integer" and params["a"]["required"] is True
                assert params["mode"]["type"] == "select" and params["mode"]["options"] == ["fast", "safe"]
                assert params["flag"]["type"] == "boolean"

                # 1. Verify live widget periodic broadcast
                w_env = await _recv_until(ws, "widget.state")
                assert w_env.payload["widget_id"] == "telemetry"
                assert w_env.payload["blocks"][0]["value"] == 0.42

                # 2. Verify widget action callback
                await ws.send_str(
                    Envelope(
                        type="widget.action",
                        source=EndpointRef(kind="client", id="android_1"),
                        target=EndpointRef(kind="entity", id="omni_node"),
                        payload={"widget_id": "lamp", "checked": True},
                    ).model_dump_json()
                )
                w_ack = await _recv_until(ws, "widget.state")
                assert widget_state["lamp"] is True
                assert w_ack.payload.get("result") == {"lamp": True} or w_ack.payload["widget_id"] == "telemetry"

                # 3. Verify RPC tool.call
                await ws.send_str(
                    Envelope(
                        type="tool.call",
                        source=EndpointRef(kind="client", id="android_1"),
                        target=EndpointRef(kind="entity", id="omni_node"),
                        payload={"tool_id": "math.add", "args": {"a": 5, "b": 7}},
                    ).model_dump_json()
                )
                t_res = await _recv_until(ws, "tool.result")
                assert t_res.payload["status"] == "ok"
                assert t_res.payload["result"] == {"sum": 12, "mode": "fast", "flag": True}

                # 4. Verify FSM flow
                await ws.send_str(
                    Envelope(
                        type="message.new",
                        source=EndpointRef(kind="client", id="android_1"),
                        target=EndpointRef(kind="entity", id="omni_node"),
                        payload={"text": "/deploy"},
                    ).model_dump_json()
                )
                fsm_msg = await _recv_until(ws, "message.new")
                assert fsm_msg.payload["text"] == "Confirm?"

                await ws.send_str(
                    Envelope(
                        type="callback.query",
                        source=EndpointRef(kind="client", id="android_1"),
                        target=EndpointRef(kind="entity", id="omni_node"),
                        payload={"data": "confirm:yes"},
                    ).model_dump_json()
                )
                fsm_ans = await _recv_until(ws, "callback.answer")
                assert fsm_ans.payload["text"] == "Confirmed!"

                # 5. Verify streaming reply
                await ws.send_str(
                    Envelope(
                        type="message.new",
                        source=EndpointRef(kind="client", id="android_1"),
                        target=EndpointRef(kind="entity", id="omni_node"),
                        payload={"text": "explain"},
                    ).model_dump_json()
                )
                s_start = await _recv_until(ws, "stream.start")
                d1 = await _recv_until(ws, "stream.delta")
                d2 = await _recv_until(ws, "stream.delta")
                s_end = await _recv_until(ws, "stream.end")
                assert d1.payload["delta"] + d2.payload["delta"] == "chunk1 chunk2"
                assert s_start.payload["message_id"] == s_end.payload["message_id"]

            # 6. Verify HTTP File Upload & Download + Pairing API
            sample = tmp_path / "hello.txt"
            sample.write_text("Botory LAN file transfer!", encoding="utf-8")
            form = aiohttp.FormData()
            form.add_field("file", sample.read_bytes(), filename="hello.txt")
            async with session.post(f"{http_base}/api/v1/files/upload", data=form) as up_resp:
                assert up_resp.status == 200
                up_json = await up_resp.json()
            async with session.get(f"{http_base}{up_json['url']}") as dl_resp:
                assert dl_resp.status == 200
                assert await dl_resp.read() == b"Botory LAN file transfer!"

            async with session.get(f"{http_base}/api/v1/pair") as pair_resp:
                pair_data = await pair_resp.json()
                assert pair_data["pair_uri"].startswith("botory://pair?")

        await app.stop()
        await hub.stop()

    asyncio.run(_run())
