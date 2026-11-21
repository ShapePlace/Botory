from botory import SimpleBot

bot = SimpleBot(entity_id="hello_bot", name="Hello Bot", hub_url="ws://127.0.0.1:8765")


@bot.command("start")
def cmd_start(ctx):
    ctx.reply(
        "Hello! I am a local Botory bot running without Telegram.",
        buttons=[[("Check Status", "cb:status"), ("Ping", "cb:ping")]],
    )


@bot.callback("cb:status")
def cb_status(ctx):
    ctx.answer("Everything is running smoothly!")


@bot.callback("cb:ping")
def cb_ping(ctx):
    ctx.reply("Pong from local Hub!")


@bot.on_message()
def echo(ctx):
    ctx.reply(f"Echo: {ctx.text}")


if __name__ == "__main__":
    bot.run()
