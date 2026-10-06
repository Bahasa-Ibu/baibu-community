"""Web search providers for the ``internet_search`` tool.

No provider is bundled. A deployment writes a subclass of
:class:`SearchProvider` for the search service it uses and names it in
``CHAT_SEARCH_PROVIDER``. :class:`MockSearchProvider` returns made-up results
for development and tests.
"""

from dataclasses import asdict
from dataclasses import dataclass
from functools import cache

from django.conf import settings
from django.utils.module_loading import import_string


class SearchError(Exception):
    """The search failed. The message is stored with the tool invocation."""


@dataclass(frozen=True)
class SearchResult:
    title: str
    url: str
    snippet: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


class SearchProvider:
    name = "provider"

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        raise NotImplementedError


class MockSearchProvider(SearchProvider):
    """Deterministic results under example.org. A query containing
    ``[search-fail]`` fails; ``[search-empty]`` finds nothing."""

    name = "mock"

    def search(self, query: str, *, max_results: int) -> list[SearchResult]:
        if "[search-fail]" in query:
            msg = "Mock search failure."
            raise SearchError(msg)
        if "[search-empty]" in query:
            return []
        return [
            SearchResult(
                title=f"Result {n} for {query}",
                url=f"https://example.org/search/{n}",
                snippet=f"Made-up text about {query}, number {n}.",
            )
            for n in range(1, max_results + 1)
        ]


@cache
def _provider_class(path: str) -> type[SearchProvider]:
    return import_string(path)


def get_provider() -> SearchProvider | None:
    path = settings.CHAT_SEARCH_PROVIDER
    return _provider_class(path)() if path else None
