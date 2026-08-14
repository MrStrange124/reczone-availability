import pytest

from reczone.server import RESPONSE_CACHE


@pytest.fixture(autouse=True)
def empty_response_cache():
    """The response cache is process-wide by design, so tests must not inherit
    each other's entries."""
    RESPONSE_CACHE.clear()
    yield
    RESPONSE_CACHE.clear()
