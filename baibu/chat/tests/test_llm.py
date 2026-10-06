import json
from types import SimpleNamespace
from unittest import mock

import pytest

from baibu.chat import llm
from baibu.chat.models import ModelVariant

SEARCH_TOOL = {"type": "function", "function": {"name": "internet_search", "parameters": {}}}


def _response(content="Hello", tool_calls=None, *, usage=True):
    message = SimpleNamespace(content=content, tool_calls=tool_calls)
    return SimpleNamespace(
        model="provider/model-x",
        choices=[SimpleNamespace(message=message)],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=3) if usage else None,
    )


def test_mock_echoes_last_user_message():
    result = llm.complete(llm.ModelConfig(model="mock"), [{"role": "user", "content": "Good morning"}])
    assert result.content == "You said: Good morning"
    assert result.model == "mock"
    assert result.latency_ms >= 0


def test_mock_can_fail_on_purpose():
    with pytest.raises(llm.ModelError) as excinfo:
        llm.complete(llm.ModelConfig(model="mock"), [{"role": "user", "content": "x [mock-fail]"}])
    assert excinfo.value.code == "mock_failure"


def test_mock_tool_call_and_follow_up():
    config = llm.ModelConfig(model="mock")
    first = llm.complete(
        config, [{"role": "user", "content": "[mock-tool internet_search] rain"}], tools=[SEARCH_TOOL]
    )
    assert first.tool_calls[0].name == "internet_search"
    assert first.tool_calls[0].arguments == {"query": "rain"}
    assert first.raw_message["tool_calls"][0]["id"] == "mock-call-1"
    second = llm.complete(config, [{"role": "tool", "content": "Rain expected"}])
    assert second.content == "Here is what I found: Rain expected"


def test_mock_ignores_tools_it_was_not_offered():
    result = llm.complete(llm.ModelConfig(model="mock"), [{"role": "user", "content": "[mock-tool nope] x"}])
    assert result.tool_calls == []
    assert result.content.startswith("You said:")


def test_litellm_call_passes_config_and_reads_usage():
    config = llm.ModelConfig(
        model="openai/example", api_base="http://llm.example.org/v1", api_key="k", parameters={"temperature": 0.2}
    )
    with mock.patch("litellm.completion", return_value=_response()) as completion:
        result = llm.complete(config, [{"role": "user", "content": "Hi"}], tools=[SEARCH_TOOL])
    kwargs = completion.call_args.kwargs
    assert kwargs["model"] == "openai/example"
    assert kwargs["api_base"] == "http://llm.example.org/v1"
    assert kwargs["api_key"] == "k"
    assert kwargs["temperature"] == 0.2
    assert kwargs["tools"] == [SEARCH_TOOL]
    assert result.content == "Hello"
    assert result.model == "provider/model-x"
    assert result.usage == {"prompt_tokens": 12, "completion_tokens": 3}


def test_litellm_tool_calls_are_parsed():
    call = SimpleNamespace(
        id="c1", function=SimpleNamespace(name="internet_search", arguments=json.dumps({"query": "q"}))
    )
    bad = SimpleNamespace(id="c2", function=SimpleNamespace(name="internet_search", arguments="{not json"))
    with mock.patch("litellm.completion", return_value=_response(content=None, tool_calls=[call, bad], usage=False)):
        result = llm.complete(llm.ModelConfig(model="x"), [{"role": "user", "content": "Hi"}])
    assert [(c.id, c.arguments) for c in result.tool_calls] == [("c1", {"query": "q"}), ("c2", {})]
    assert result.raw_message["tool_calls"][0]["function"]["name"] == "internet_search"
    assert result.content == ""
    assert result.usage == {}


@pytest.mark.parametrize(("error", "code"), [(TimeoutError("slow"), "timeout"), (RuntimeError("no"), "model_error")])
def test_litellm_errors_become_model_errors(error, code):
    with mock.patch("litellm.completion", side_effect=error), pytest.raises(llm.ModelError) as excinfo:
        llm.complete(llm.ModelConfig(model="x"), [{"role": "user", "content": "Hi"}])
    assert excinfo.value.code == code


def test_litellm_without_choices_is_an_error():
    with (
        mock.patch("litellm.completion", return_value=SimpleNamespace(choices=[])),
        pytest.raises(llm.ModelError, match="no choices"),
    ):
        llm.complete(llm.ModelConfig(model="x"), [{"role": "user", "content": "Hi"}])


def test_json_arguments_accepts_dicts_and_rejects_lists():
    assert llm._json_arguments({"a": 1}) == {"a": 1}
    assert llm._json_arguments("[1]") == {}


def test_config_reads_key_from_named_environment_variable(monkeypatch, settings):
    monkeypatch.setenv("EXAMPLE_LLM_KEY", "secret-from-env")
    variant = ModelVariant(model="openai/x", api_base="http://h", api_key_env="EXAMPLE_LLM_KEY", parameters={"a": 1})
    config = llm.ModelConfig.from_variant(variant)
    assert (config.model, config.api_key, config.parameters) == ("openai/x", "secret-from-env", {"a": 1})
    settings.CHAT_MODEL = "mock"
    assert llm.ModelConfig.from_variant(None).model == "mock"
    assert llm.ModelConfig.from_variant(ModelVariant(model="m")).api_key == ""
