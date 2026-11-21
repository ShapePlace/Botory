import asyncio

import aiohttp

from botory import BotoryHub, BotoryRelay, EndpointRef, Envelope, SimpleBot


def test_hub_to_client_via_relay_tunnel():
    async def _run() -> None:
        relay = BotoryRelay(host="127.0.0.1", port=0)
        await relay.start()
        relay_ws_url = f"ws://127.0.0.1:{relay.bound_port}"

        hub = BotoryHub(host="127.0.0.1", port=0, relay_url=relay_ws_url)
        await hub.start()

        bot = SimpleBot(
            entity_id="relay_bot",
            name="Relay Bot",
            hub_url=f"ws://127.0.0.1:{hub.bound_port}",
        )

        @bot.command("ping")
        def on_ping(ctx):
            ctx.reply("Pong over Relay!")

        await bot.start()
        await asyncio.sleep(0.25)

        async with aiohttp.ClientSession() as session:
            async with session.ws_connect(f"{relay_ws_url}/ws/client/{hub.hub_id}") as ws:
                # First sync frame forwarded from hub
                sync_raw = await asyncio.wait_for(ws.receive_str(), timeout=3.0)
                sync_env = Envelope.model_validate_json(sync_raw)
                assert sync_env.type == "entity.sync"

                await ws.send_str(
                    Envelope(
                        type="message.new",
                        source=EndpointRef(kind="client", id="remote_phone"),
                        target=EndpointRef(kind="entity", id="relay_bot"),
                        payload={"text": "/ping"},
                    ).model_dump_json()
                )

                async def _wait_msg() -> Envelope:
                    while True:
                        env = Envelope.model_validate_json(await ws.receive_str())
                        if env.type == "message.new":
                            return env

                reply = await asyncio.wait_for(_wait_msg(), timeout=3.0)
                assert reply.payload["text"] == "Pong over Relay!"

        await bot.stop()
        await hub.stop()
        await relay.stop()

    asyncio.run(_run())
