"""Calling a language model.

Every call goes through :func:`complete`. Real models are reached through
LiteLLM, so a deployment can use any model and endpoint LiteLLM supports.
The model name ``mock`` answers locally (see :func:`_mock_completion`), so
the platform runs and can be tested without any model.
"""

import json
import os
import time
from dataclasses import dataclass
from dataclasses import field

from django.conf import settings


class ModelError(Exception):
    """The model call failed. ``code`` is safe to show and store."""

    def __init__(self, message: str, *, code: str = "model_error"):
        super().__init__(message)
        self.code = code


@dataclass
class ModelConfig:
    model: str
    api_base: str = ""
    api_key: str = ""
    parameters: dict = field(default_factory=dict)

    @classmethod
    def from_variant(cls, variant) -> ModelConfig:
        if variant is None:
            return cls(model=settings.CHAT_MODEL)
        api_key = os.environ.get(variant.api_key_env, "") if variant.api_key_env else ""
        return cls(
            model=variant.model, api_base=variant.api_base, api_key=api_key, parameters=dict(variant.parameters)
        )


@dataclass
class ToolCall:
    id: str
    name: str
    arguments: dict


@dataclass
class Completion:
    content: str
    model: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    # The assistant turn as the model sent it, for replaying tool calls.
    raw_message: dict = field(default_factory=dict)


def complete(config: ModelConfig, messages: list[dict], *, tools: list[dict] | None = None) -> Completion:
    started = time.monotonic()
    if config.model == "mock":
        result = _mock_completion(messages, tools=tools)
    else:
        result = _litellm_completion(config, messages, tools=tools)
    result.latency_ms = int((time.monotonic() - started) * 1000)
    return result


def _litellm_completion(config: ModelConfig, messages, *, tools):
    import litellm

    kwargs = {
        **config.parameters,
        "model": config.model,
        "messages": messages,
        "timeout": settings.CHAT_MODEL_TIMEOUT,
    }
    if config.api_base:
        kwargs["api_base"] = config.api_base
    if config.api_key:
        kwargs["api_key"] = config.api_key
    if tools:
        kwargs["tools"] = tools
    try:
        response = litellm.completion(**kwargs)
    except Exception as exc:
        code = "timeout" if "timeout" in type(exc).__name__.lower() else "model_error"
        msg = f"Model call failed: {type(exc).__name__}"
        raise ModelError(msg, code=code) from exc
    try:
        message = response.choices[0].message
    except (AttributeError, IndexError) as exc:
        msg = "Model returned no choices."
        raise ModelError(msg, code="empty_response") from exc
    tool_calls = [
        ToolCall(id=call.id, name=call.function.name, arguments=_json_arguments(call.function.arguments))
        for call in (getattr(message, "tool_calls", None) or [])
    ]
    usage = getattr(response, "usage", None)
    return Completion(
        content=message.content or "",
        model=getattr(response, "model", None) or config.model,
        tool_calls=tool_calls,
        usage={
            "prompt_tokens": getattr(usage, "prompt_tokens", None),
            "completion_tokens": getattr(usage, "completion_tokens", None),
        }
        if usage
        else {},
        raw_message={
            "role": "assistant",
            "content": message.content or "",
            **(
                {
                    "tool_calls": [
                        {
                            "id": c.id,
                            "type": "function",
                            "function": {"name": c.name, "arguments": json.dumps(c.arguments)},
                        }
                        for c in tool_calls
                    ]
                }
                if tool_calls
                else {}
            ),
        },
    )


def _json_arguments(arguments) -> dict:
    if isinstance(arguments, dict):
        return arguments
    try:
        value = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


MOCK_FAIL = "[mock-fail]"
MOCK_TOOL_PREFIX = "[mock-tool "


def _mock_completion(messages, *, tools):
    """Deterministic replies for development and tests.

    - A user message containing ``[mock-fail]`` makes the call fail.
    - ``[mock-tool name] text`` asks for tool ``name`` with ``{"query": text}``,
      if that tool is offered; the reply after the tool result quotes it.
    - Otherwise the reply echoes the last user message.
    """
    last = messages[-1]
    if last["role"] == "tool":
        reply = f"Here is what I found: {last['content'][:500]}"
        return Completion(content=reply, model="mock", raw_message={"role": "assistant", "content": reply})
    text = last.get("content") or ""
    if MOCK_FAIL in text:
        msg = "Mock model failure."
        raise ModelError(msg, code="mock_failure")
    if text.startswith(MOCK_TOOL_PREFIX) and "]" in text:
        name, _, query = text[len(MOCK_TOOL_PREFIX) :].partition("]")
        if any(tool["function"]["name"] == name for tool in tools or []):
            call = ToolCall(id="mock-call-1", name=name, arguments={"query": query.strip()})
            raw = {
                "role": "assistant",
                "content": "",
                "tool_calls": [
                    {
                        "id": call.id,
                        "type": "function",
                        "function": {"name": name, "arguments": json.dumps(call.arguments)},
                    }
                ],
            }
            return Completion(content="", model="mock", tool_calls=[call], raw_message=raw)
    reply = f"You said: {text}"
    return Completion(content=reply, model="mock", raw_message={"role": "assistant", "content": reply})
