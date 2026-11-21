from __future__ import annotations

import inspect
import json
from dataclasses import asdict, dataclass, field, fields, is_dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Literal, TypeVar, get_args, get_origin, get_type_hints
from uuid import uuid4


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def new_event_id(prefix: str = "evt") -> str:
    return f"{prefix}_{uuid4().hex[:12]}"


T = TypeVar("T", bound="BaseModel")


class BaseModel:
    """Zero-dependency stdlib dataclass-based model (Termux-friendly, no Rust pydantic-core needed)."""

    def model_dump(self) -> dict[str, Any]:
        return asdict(self)  # type: ignore[arg-type]

    def model_dump_json(self) -> str:
        return json.dumps(self.model_dump(), ensure_ascii=False)

    @classmethod
    def model_validate(cls: type[T], data: dict[str, Any] | T) -> T:
        if isinstance(data, cls):
            return data
        if not is_dataclass(cls):
            raise TypeError(f"{cls} must be a dataclass")
        try:
            hints = get_type_hints(cls)
        except Exception:
            hints = {}

        kwargs: dict[str, Any] = {}
        for f in fields(cls):
            if f.name not in data:
                continue
            val = data[f.name]
            ann = hints.get(f.name, f.type)
            origin = get_origin(ann)
            args = get_args(ann)

            if isinstance(ann, type) and issubclass(ann, BaseModel) and isinstance(val, dict):
                val = ann.model_validate(val)
            elif origin is list and args and isinstance(args[0], type) and issubclass(args[0], BaseModel) and isinstance(val, list):
                val = [args[0].model_validate(item) if isinstance(item, dict) else item for item in val]
            kwargs[f.name] = val
        return cls(**kwargs)

    @classmethod
    def model_validate_json(cls: type[T], raw: str | bytes) -> T:
        return cls.model_validate(json.loads(raw))


@dataclass
class EndpointRef(BaseModel):
    kind: str
    id: str
    name: str | None = None


@dataclass
class Envelope(BaseModel):
    type: str
    source: EndpointRef
    target: EndpointRef
    payload: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=new_event_id)
    v: int = 1
    ts: str = field(default_factory=utc_now_iso)


# =========================================================
# UI COMPONENTS (Material 3 Expressive compatible)
# =========================================================

@dataclass
class InlineButton(BaseModel):
    label: str
    callback: str
    id: str = field(default_factory=lambda: new_event_id("btn"))
    icon: str | None = None
    tone: Literal["default", "tonal", "primary", "destructive"] = "default"


@dataclass
class ButtonGroup(BaseModel):
    items: list[InlineButton]
    kind: str = "button_group"
    connected: bool = True


@dataclass
class SplitButton(BaseModel):
    primary: InlineButton
    menu: list[InlineButton] = field(default_factory=list)
    kind: str = "split_button"


@dataclass
class WavyProgress(BaseModel):
    label: str
    value: float  # 0.0 .. 1.0
    display: str | None = None
    kind: str = "wavy_progress"


@dataclass
class ToggleSwitch(BaseModel):
    id: str
    label: str
    checked: bool = False
    kind: str = "toggle_row"


@dataclass
class SliderBlock(BaseModel):
    id: str
    label: str
    min: float = 0.0
    max: float = 100.0
    value: float = 50.0
    unit: str = "%"
    kind: str = "slider"


@dataclass
class ExpressiveCard(BaseModel):
    title: str
    subtitle: str | None = None
    blocks: list[dict[str, Any]] = field(default_factory=list)
    kind: str = "card"

    @classmethod
    def from_blocks(
        cls,
        title: str,
        blocks: list[BaseModel | dict[str, Any]],
        subtitle: str | None = None,
    ) -> "ExpressiveCard":
        serialized = [b.model_dump() if isinstance(b, BaseModel) else b for b in blocks]
        return cls(title=title, subtitle=subtitle, blocks=serialized)


# =========================================================
# TOOL SCHEMA EXTRACTION ("Not just bots")
# =========================================================

@dataclass
class ToolParam(BaseModel):
    name: str
    label: str
    type: Literal["string", "integer", "number", "boolean", "select"] = "string"
    required: bool = True
    default: Any = None
    options: list[Any] | None = None


@dataclass
class ToolDefinition(BaseModel):
    tool_id: str
    title: str
    description: str = ""
    icon: str = "bolt"
    params: list[ToolParam] = field(default_factory=list)


@dataclass
class WidgetDefinition(BaseModel):
    widget_id: str
    title: str
    interval: float = 5.0


@dataclass
class EntityDescriptor(BaseModel):
    id: str
    name: str
    kind: Literal["bot", "iot", "ai", "tool"] = "bot"
    description: str = ""
    commands: list[str] = field(default_factory=list)
    tools: list[ToolDefinition] = field(default_factory=list)
    widgets: list[WidgetDefinition] = field(default_factory=list)
    online: bool = True


def extract_tool_schema(
    fn: Callable[..., Any],
    tool_id: str,
    title: str | None = None,
    description: str | None = None,
    icon: str = "bolt",
) -> ToolDefinition:
    sig = inspect.signature(fn)
    try:
        hints = get_type_hints(fn)
    except Exception:
        hints = {}

    params: list[ToolParam] = []
    for name, param in sig.parameters.items():
        if name in ("self", "ctx"):
            continue
        ann = hints.get(name, str)
        origin = get_origin(ann)
        has_default = param.default is not inspect.Parameter.empty
        default_val = param.default if has_default else None

        param_type: Literal["string", "integer", "number", "boolean", "select"] = "string"
        options: list[Any] | None = None

        if origin is Literal:
            param_type = "select"
            options = list(get_args(ann))
        elif ann is bool:
            param_type = "boolean"
        elif ann is int:
            param_type = "integer"
        elif ann is float:
            param_type = "number"
        else:
            param_type = "string"

        params.append(
            ToolParam(
                name=name,
                type=param_type,
                label=name.replace("_", " ").capitalize(),
                required=not has_default,
                default=default_val,
                options=options,
            )
        )

    doc = (description or inspect.getdoc(fn) or "").strip()
    return ToolDefinition(
        tool_id=tool_id,
        title=title or tool_id,
        description=doc,
        icon=icon,
        params=params,
    )
