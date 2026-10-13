import httpx
from starlette.applications import Starlette
from starlette.responses import PlainTextResponse
from starlette.routing import Route

from oraclarr_mcp.auth import BearerTokenMiddleware

TOKEN = "s3cret-token-" + "x" * 20


def _app():
    async def ok(request):
        return PlainTextResponse("ok")
    return BearerTokenMiddleware(Starlette(routes=[Route("/mcp", ok, methods=["GET", "POST"])]),
                                 TOKEN)


async def _get(headers=None):
    transport = httpx.ASGITransport(app=_app())
    async with httpx.AsyncClient(transport=transport, base_url="http://t") as c:
        return await c.post("/mcp", headers=headers or {})


async def test_missing_token_is_401():
    r = await _get()
    assert r.status_code == 401 and r.json() == {"error": "unauthorized"}
    assert r.headers["www-authenticate"] == "Bearer"


async def test_wrong_token_is_401():
    assert (await _get({"Authorization": "Bearer nope"})).status_code == 401


async def test_right_token_passes():
    r = await _get({"Authorization": f"Bearer {TOKEN}"})
    assert r.status_code == 200 and r.text == "ok"


async def test_scheme_is_case_insensitive():
    assert (await _get({"Authorization": f"bearer {TOKEN}"})).status_code == 200
    assert (await _get({"Authorization": f"Basic {TOKEN}"})).status_code == 401


async def test_401_does_not_echo_the_sent_value():
    r = await _get({"Authorization": "Bearer guess-123"})
    assert "guess-123" not in r.text


async def test_lifespan_passes_through():
    seen = []

    async def inner(scope, receive, send):
        seen.append(scope["type"])

    await BearerTokenMiddleware(inner, TOKEN)({"type": "lifespan"}, None, None)
    assert seen == ["lifespan"]
