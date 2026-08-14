import httpx
import pytest

from reczone.http import HttpxTransport


class FakeSleep:
    def __init__(self):
        self.delays: list[float] = []

    async def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)


async def test_transport_retries_429_then_returns_payload():
    attempts = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        attempts["n"] += 1
        if attempts["n"] == 1:
            return httpx.Response(429, headers={"Retry-After": "0"})
        return httpx.Response(200, json={"code": 200, "data": [{"id": 1}]})

    sleeper = FakeSleep()
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://reczone.test",
    ) as http:
        transport = HttpxTransport(http, sleeper=sleeper)
        payload = await transport.get("/timeslots")

    assert payload["data"][0]["id"] == 1
    assert attempts["n"] == 2
    assert sleeper.delays == [0.0]


async def test_transport_gives_up_after_429_retries():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429)

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler),
        base_url="https://reczone.test",
    ) as http:
        transport = HttpxTransport(http, retries=2, backoff=0.01, sleeper=FakeSleep())
        with pytest.raises(httpx.HTTPStatusError) as err:
            await transport.get("/timeslots")
    assert err.value.response.status_code == 429
