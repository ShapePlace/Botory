import asyncio
from botory import (
    BotoryApp,
    CallbackContext,
    ExpressiveCard,
    F,
    FSMContext,
    InlineButton,
    MessageContext,
    Router,
    SplitButton,
    State,
    StatesGroup,
    WavyProgress,
)

app = BotoryApp(entity_id="homelab_bot", name="HomeLab Sentinel", kind="bot")
router = Router()


class DeployFlow(StatesGroup):
    choosing_env = State()


@router.command("status")
async def status_cmd(msg: MessageContext):
    card = ExpressiveCard.from_blocks(
        title="Node Telemetry",
        subtitle="Docker 6/6 up",
        blocks=[
            WavyProgress(label="CPU", value=0.34, display="34% · 49°C"),
            WavyProgress(label="RAM", value=0.58, display="9.3 / 16 GB"),
        ],
    )
    await msg.reply(
        "Home node status:",
        card=card,
        components=[
            SplitButton(
                primary=InlineButton(label="Restart nginx", callback="svc:restart:nginx"),
                menu=[
                    InlineButton(label="Graceful Reload", callback="svc:reload:nginx"),
                    InlineButton(label="Stop Container", callback="svc:stop:nginx", tone="destructive"),
                ],
            )
        ],
    )


@router.command("deploy")
async def deploy_start(msg: MessageContext, state: FSMContext):
    await state.set_state(DeployFlow.choosing_env)
    await msg.reply(
        "Select deployment target:",
        buttons=[[("Staging", "deploy:staging"), ("Production", "deploy:prod")]],
    )


@router.callback(F.callback.startswith("deploy:"), F.state(DeployFlow.choosing_env))
async def deploy_finish(cb: CallbackContext, state: FSMContext):
    env = cb.data.split(":")[1]
    await state.clear()
    await cb.answer(f"Deployment to {env} started!")
    await cb.message.reply(f"Done: deployed to **{env}**.")


@router.message(F.text)
async def ai_like_stream(msg: MessageContext):
    async with msg.stream_reply() as stream:
        for word in ["Local", " streaming", " reply", " via", " Botory", " Hub!"]:
            await stream.write(word)
            await asyncio.sleep(0.05)


app.include_router(router)

if __name__ == "__main__":
    app.run()
