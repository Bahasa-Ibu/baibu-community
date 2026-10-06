"""Tools the assistant can call during a reply.

A tool has a stable name, a description and a JSON schema for its arguments
(the format LiteLLM passes to models), and returns text for the model plus
optional sources to show under the reply. Tools are offered only when they
are configured; with none, replies are plain model calls.
"""

import json
from dataclasses import dataclass
from dataclasses import field

from django.conf import settings

from . import search


class ToolError(Exception):
    """The tool failed. The model is told, and may answer without it."""


@dataclass
class ToolResult:
    content: str
    sources: list[dict] = field(default_factory=list)
    provider: str = ""


class Tool:
    name = ""
    description = ""
    parameters: dict = {}

    def is_available(self) -> bool:
        return True

    def schema(self) -> dict:
        return {
            "type": "function",
            "function": {"name": self.name, "description": self.description, "parameters": self.parameters},
        }

    def run(self, arguments: dict) -> ToolResult:
        raise NotImplementedError


class InternetSearchTool(Tool):
    name = "internet_search"
    description = (
        "Search the web for current or local information. Use it when the answer depends on recent events, "
        "places, opening times, prices or facts you are not sure of. Cite the sources you use."
    )
    parameters = {
        "type": "object",
        "properties": {"query": {"type": "string", "description": "What to search for."}},
        "required": ["query"],
    }

    def is_available(self) -> bool:
        return bool(settings.CHAT_SEARCH_PROVIDER)

    def run(self, arguments: dict) -> ToolResult:
        query = str(arguments.get("query") or "").strip()[:300]
        if not query:
            msg = "A search query is required."
            raise ToolError(msg)
        provider = search.get_provider()
        try:
            results = provider.search(query, max_results=settings.CHAT_SEARCH_MAX_RESULTS)
        except search.SearchError as exc:
            raise ToolError(str(exc)) from exc
        except Exception as exc:
            msg = f"Search failed: {type(exc).__name__}"
            raise ToolError(msg) from exc
        results = results[: settings.CHAT_SEARCH_MAX_RESULTS]
        payload = [r.as_dict() for r in results]
        content = json.dumps({"query": query, "results": payload}, ensure_ascii=False)
        sources = [{"title": r.title, "url": r.url} for r in results if r.url.startswith(("https://", "http://"))]
        return ToolResult(content=content, sources=sources, provider=provider.name)


TOOLS: dict[str, Tool] = {tool.name: tool for tool in (InternetSearchTool(),)}


def available_tools() -> list[Tool]:
    return [tool for tool in TOOLS.values() if tool.is_available()]
