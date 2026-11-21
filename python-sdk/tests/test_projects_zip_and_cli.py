import asyncio
import io
import zipfile

import aiohttp

from botory import BotoryHub
from botory.cli import load_config, save_config


def _make_zip(files: dict[str, str]) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for name, content in files.items():
            zf.writestr(name, content)
    return buf.getvalue()


def test_zip_project_import_start_and_stop(tmp_path):
    async def _run() -> None:
        hub = BotoryHub(host="127.0.0.1", port=0, projects_dir=tmp_path / "projects")
        await hub.start()
        http_base = f"http://127.0.0.1:{hub.bound_port}"

        good_zip = _make_zip(
            {
                "my_bot/main.py": (
                    "from botory import SimpleBot\n"
                    "bot = SimpleBot(entity_id='zipped_bot', name='Zipped Bot')\n"
                    "@bot.command('hi')\n"
                    "def hi(ctx):\n"
                    "    ctx.reply('Hello from imported zip!')\n"
                    "bot.run()\n"
                )
            }
        )
        evil_zip = _make_zip({"../../escape.py": "print('bad')"})

        async with aiohttp.ClientSession() as session:
            # 1. Reject path traversal zip
            bad_form = aiohttp.FormData()
            bad_form.add_field("file", evil_zip, filename="evil.zip")
            async with session.post(f"{http_base}/api/v1/projects/import", data=bad_form) as resp:
                assert resp.status == 400

            # 2. Import valid python zip project
            form = aiohttp.FormData()
            form.add_field("file", good_zip, filename="my_cool_bot.zip")
            async with session.post(f"{http_base}/api/v1/projects/import", data=form) as resp:
                assert resp.status == 201
                proj = await resp.json()
                assert proj["project_id"] == "my_cool_bot"
                assert proj["entrypoint"] == "main.py"

            # 3. Start imported project and confirm entity connects automatically via BOTORY_HUB_URL
            async with session.post(f"{http_base}/api/v1/projects/my_cool_bot/start") as resp:
                assert resp.status == 200
                started = await resp.json()
                assert started["running"] is True

            entities = []
            for _ in range(30):
                async with session.get(f"{http_base}/api/v1/entities") as eresp:
                    entities = await eresp.json()
                if any(e["id"] == "zipped_bot" for e in entities):
                    break
                await asyncio.sleep(0.1)
            assert any(e["id"] == "zipped_bot" for e in entities)

            # 4. Stop project cleanly
            async with session.post(f"{http_base}/api/v1/projects/my_cool_bot/stop") as resp:
                assert resp.status == 200
                stopped = await resp.json()
                assert stopped["running"] is False

        await hub.stop()

    asyncio.run(_run())


def test_cli_config_persistence(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    p = save_config({"hub_name": "Termux Test", "host": "127.0.0.1", "port": 8765})
    assert p.is_file()
    loaded = load_config()
    assert loaded["hub_name"] == "Termux Test"
    assert loaded["port"] == 8765
