import asyncio
import inspect
import time
from typing import Any

import pytest

from oraclarr_mcp.budget import remaining
from oraclarr_mcp.call_guard import guarded
from oraclarr_mcp.redact import Redactor
from oraclarr_mcp.tools._util import fan_out

NO_SECRETS = Redactor([])


def _wrap(fn, budget_s=1.0, max_bytes=100_000, redactor=NO_SECRETS, grace_s=0.05):
    return guarded("t", fn, budget_s=budget_s, max_bytes=max_bytes,
                   redactor=redactor, grace_s=grace_s)


async def test_backstop_returns_tool_timeout():
    async def stuck():
        await asyncio.sleep(5)

    out = await _wrap(stuck, budget_s=0.05, grace_s=0.05)()
    assert out == {"error": "tool_timeout", "tool": "t", "after_s": 0.1}


async def test_tool_sees_deadline_and_it_is_cleared_after():
    async def peek():
        return remaining()

    left = await _wrap(peek, budget_s=1.0)()
    assert 0 < left <= 1.0
    assert remaining() is None


async def test_deadline_is_fresh_for_each_call():
    async def stuck():
        await asyncio.sleep(5)

    async def peek():
        return remaining()

    await _wrap(stuck, budget_s=0.05, grace_s=0.05)()
    left = await _wrap(peek, budget_s=1.0)()
    assert left > 0.5


async def test_timeout_error_raised_by_the_tool_itself_propagates():
    async def boom():
        raise TimeoutError("not the backstop")

    with pytest.raises(TimeoutError):
        await _wrap(boom)()


async def test_output_over_cap_returns_output_too_large():
    async def big():
        return {"blob": "x" * 500}

    out = await _wrap(big, max_bytes=100)()
    assert out["error"] == "output_too_large"
    assert out["tool"] == "t"
    assert out["bytes"] > 100
    assert out["hint"] == "narrow with service= or limit="


async def test_result_is_redacted():
    async def leaky():
        return [{"error": "GET http://h?api_key=SONARRKEY123 failed"}]

    out = await _wrap(leaky, redactor=Redactor(["SONARRKEY123"]))()
    assert "SONARRKEY123" not in repr(out)


def test_wrapper_keeps_params_and_doc_but_returns_any():
    async def tool(service: str | None = None, limit: int = 20) -> list[dict]:
        """Doc line."""
        return []

    w = _wrap(tool)
    sig = inspect.signature(w)
    assert list(sig.parameters) == ["service", "limit"]
    assert sig.parameters["limit"].default == 20
    assert sig.return_annotation is Any
    assert w.__doc__ == "Doc line."


async def test_ten_parallel_calls_overlap():
    class Slow:
        name = "s"
        type = "sonarr"

        async def work(self):
            await asyncio.sleep(0.3)
            return 1

    async def tool():
        return await fan_out({"s": Slow()}, lambda c: c.work())

    w = _wrap(tool, budget_s=5)
    t0 = time.monotonic()
    results = await asyncio.gather(*(w() for _ in range(10)))
    assert time.monotonic() - t0 < 1.0
    assert all(r[0]["status"] == "ok" for r in results)
