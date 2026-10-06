import json
from unittest import mock

import pytest
from django.urls import reverse

from baibu.chat import llm
from baibu.chat import search
from baibu.chat import services
from baibu.chat import tools
from baibu.chat.models import ConversationEvent
from baibu.chat.models import Run
from baibu.chat.models import ToolInvocation
from baibu.users.consent import record_consent
from baibu.users.models import ConsentRecord

MOCK_PROVIDER = "baibu.chat.search.MockSearchProvider"


@pytest.fixture
def search_on(settings):
    settings.CHAT_SEARCH_PROVIDER = MOCK_PROVIDER
    settings.CHAT_SEARCH_MAX_RESULTS = 2
    return settings


@pytest.fixture
def conversation(user):
    record_consent(user=user, tier=ConsentRecord.Tier.EVAL_ONLY, source="test", scope="chat")
    return services.start_conversation(user=user, language_code="en")


def _ask(conversation, content):
    _message, run = services.send_message(conversation=conversation, content=content, idempotency_key="k")
    return services.execute(run.pk)


# --- Providers and the tool -------------------------------------------------


def test_mock_provider():
    provider = search.MockSearchProvider()
    results = provider.search("rain", max_results=3)
    assert [r.url for r in results] == [f"https://example.org/search/{n}" for n in (1, 2, 3)]
    assert results[0].as_dict()["snippet"] == "Made-up text about rain, number 1."
    assert provider.search("x [search-empty]", max_results=3) == []
    with pytest.raises(search.SearchError):
        provider.search("x [search-fail]", max_results=3)


def test_base_classes_are_abstract():
    with pytest.raises(NotImplementedError):
        search.SearchProvider().search("q", max_results=1)
    with pytest.raises(NotImplementedError):
        tools.Tool().run({})
    assert tools.Tool().is_available()


def test_search_is_offered_only_with_a_provider(settings):
    settings.CHAT_SEARCH_PROVIDER = ""
    assert tools.available_tools() == []
    assert search.get_provider() is None
    settings.CHAT_SEARCH_PROVIDER = MOCK_PROVIDER
    (tool,) = tools.available_tools()
    schema = tool.schema()
    assert schema["function"]["name"] == "internet_search"
    assert schema["function"]["parameters"]["required"] == ["query"]


def test_search_tool_returns_results_and_sources(search_on):
    result = tools.TOOLS["internet_search"].run({"query": "  market days  "})
    payload = json.loads(result.content)
    assert payload["query"] == "market days"
    assert len(payload["results"]) == 2
    assert result.sources == [
        {"title": "Result 1 for market days", "url": "https://example.org/search/1"},
        {"title": "Result 2 for market days", "url": "https://example.org/search/2"},
    ]
    assert result.provider == "mock"


def test_search_tool_drops_unsafe_links_and_extra_results(search_on):
    class Provider(search.SearchProvider):
        name = "custom"

        def search(self, query, *, max_results):
            return [
                search.SearchResult("Bad", "javascript:alert(1)"),
                search.SearchResult("Good", "https://example.org/a"),
                search.SearchResult("Too many", "https://example.org/b"),
            ]

    with mock.patch("baibu.chat.search.get_provider", return_value=Provider()):
        result = tools.TOOLS["internet_search"].run({"query": "q"})
    assert result.sources == [{"title": "Good", "url": "https://example.org/a"}]


@pytest.mark.parametrize(
    ("arguments", "message"),
    [({}, "query is required"), ({"query": "x [search-fail]"}, "Mock search failure")],
)
def test_search_tool_errors(search_on, arguments, message):
    with pytest.raises(tools.ToolError, match=message):
        tools.TOOLS["internet_search"].run(arguments)


def test_search_tool_wraps_unexpected_provider_errors(search_on):
    with (
        mock.patch.object(search.MockSearchProvider, "search", side_effect=ConnectionError("down")),
        pytest.raises(tools.ToolError, match="ConnectionError"),
    ):
        tools.TOOLS["internet_search"].run({"query": "q"})


# --- In a conversation ------------------------------------------------------


@pytest.mark.django_db
def test_reply_uses_search_and_cites_sources(search_on, conversation):
    run = _ask(conversation, "[mock-tool internet_search] bus times")
    assert run.status == Run.Status.COMPLETED
    assert run.reply.content.startswith("Here is what I found:")
    assert run.reply.sources[0]["url"] == "https://example.org/search/1"
    invocation = ToolInvocation.objects.get()
    assert invocation.run == run
    assert invocation.status == ToolInvocation.Status.COMPLETED
    assert invocation.arguments == {"query": "bus times"}
    assert (invocation.provider, invocation.result_count) == ("mock", 2)
    assert ConversationEvent.objects.filter(type="tool_completed").exists()
    assert str(invocation) == "internet_search (completed)"


@pytest.mark.django_db
def test_failed_search_still_gets_an_answer(search_on, conversation):
    run = _ask(conversation, "[mock-tool internet_search] [search-fail]")
    assert run.status == Run.Status.COMPLETED
    assert "Mock search failure" in run.reply.content
    assert run.reply.sources == []
    invocation = ToolInvocation.objects.get()
    assert invocation.status == ToolInvocation.Status.FAILED
    assert invocation.error == "Mock search failure."


@pytest.mark.django_db
def test_without_provider_no_tool_is_offered(settings, conversation):
    settings.CHAT_SEARCH_PROVIDER = ""
    run = _ask(conversation, "[mock-tool internet_search] bus times")
    assert run.reply.content.startswith("You said:")
    assert not ToolInvocation.objects.exists()


@pytest.mark.django_db
def test_unknown_tool_call_is_recorded_as_failed(search_on, conversation):
    calls = [
        llm.Completion(
            content="",
            model="m",
            tool_calls=[llm.ToolCall(id="1", name="launch_rocket", arguments={})],
            raw_message={"role": "assistant", "content": ""},
        ),
        llm.Completion(content="I cannot do that.", model="m"),
    ]
    with mock.patch("baibu.chat.llm.complete", side_effect=calls):
        run = _ask(conversation, "Do something odd")
    assert run.reply.content == "I cannot do that."
    assert ToolInvocation.objects.get().error == "Unknown tool 'launch_rocket'."


@pytest.mark.django_db
def test_tool_rounds_are_limited(search_on, conversation):
    search_on.CHAT_MAX_TOOL_ROUNDS = 2
    offered = []

    def model(config, messages, *, tools=None):
        offered.append(bool(tools))
        if tools:
            call = llm.ToolCall(id=f"c{len(offered)}", name="internet_search", arguments={"query": "again"})
            return llm.Completion(content="", model="m", tool_calls=[call], raw_message={"role": "assistant"})
        return llm.Completion(content="Final answer", model="m")

    with mock.patch("baibu.chat.llm.complete", side_effect=model):
        run = _ask(conversation, "Keep searching")
    assert offered == [True, True, False]
    assert run.reply.content == "Final answer"
    assert ToolInvocation.objects.count() == 2
    # The same source found twice is listed once.
    assert len(run.reply.sources) == 2


@pytest.mark.django_db
def test_sources_are_shown_under_the_reply(client, search_on, conversation):
    client.force_login(conversation.user)
    _ask(conversation, "[mock-tool internet_search] bus times")
    page = client.get(reverse("chat:conversation", args=[conversation.pk])).content.decode()
    assert "Sources" in page
    assert 'href="https://example.org/search/1" rel="nofollow noopener noreferrer"' in page


@pytest.mark.django_db
def test_admin_shows_tool_invocations(client, search_on, conversation, admin_user):
    run = _ask(conversation, "[mock-tool internet_search] bus times")
    client.force_login(admin_user)
    page = client.get(reverse("admin:chat_run_change", args=[run.pk])).content.decode()
    assert "internet_search" in page
