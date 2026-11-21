# Botory Protocol Specification (`v1`)

Botory communicates over **WebSocket** for real-time events and **HTTP REST** for file transfers, pairing metadata, and ZIP project management.

## 1. Pairing URI (`botory://pair`)

```text
botory://pair?v=1&hub=hub_9f2a1c&name=HomeHub&lan=192.168.1.42:8765&relay=wss://relay.example.com&token=secret
```

## 2. WebSocket Envelope

All WebSocket messages follow a unified JSON envelope:

```json
{
  "id": "evt_01ab23cd45ef",
  "v": 1,
  "type": "message.new",
  "ts": "2026-11-21T14:22:08.120Z",
  "source": { "kind": "bot", "id": "homelab_bot", "name": "HomeLab Sentinel" },
  "target": { "kind": "client", "id": "android_app" },
  "payload": {}
}
```

### Event Types

| Event `type` | Direction | Description |
| :--- | :--- | :--- |
| `auth.ok` | Hub -> Client | Connection greeting with `hub_id`, `hub_name`, `client_id` |
| `entity.register` | Entity -> Hub | Registers bot/tool/IoT/AI descriptor, commands, tools, widgets |
| `entity.sync` | Hub -> Client | Broadcasts active entities list |
| `message.new` | Both | Text/Markdown message with optional inline components or embedded card |
| `stream.start` / `stream.delta` / `stream.end` | Entity -> Client | Streaming response chunks |
| `callback.query` / `callback.answer` | Client <-> Entity | Inline button / split button interactions |
| `widget.state` / `widget.action` | Entity <-> Client | Live Bento widget updates and switch/slider actions |
| `tool.call` / `tool.result` | Client <-> Entity | Remote Python function execution (RPC) |
| `file.offer` | Entity -> Client | File metadata pointing to `/api/v1/files/{file_id}` |

## 3. HTTP Endpoints

- `GET /api/v1/health` — Hub status, connected entities, clients, and projects count.
- `GET /api/v1/entities` — Connected Python entities and their schemas.
- `GET /api/v1/pair` — Pairing URI and WebSocket endpoint info.
- `POST /api/v1/files/upload` / `GET /api/v1/files/{file_id}` — Binary file upload/download.
- `GET /api/v1/projects` — List imported Python projects.
- `POST /api/v1/projects/import` — Multipart `.zip` upload and safe extraction.
- `POST /api/v1/projects/{project_id}/start` / `stop` — Start or terminate a managed project subprocess.
