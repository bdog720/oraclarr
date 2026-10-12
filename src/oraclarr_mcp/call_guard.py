"""Wrap every registered tool: deadline, backstop, output cap, redaction."""
import asyncio
import inspect
import json
import logging
from typing import Any, Awaitable, Callable
from .budget import reset_deadline, set_deadline
from .redact import _ACTIVE, Redactor

log = logging.getLogger("oraclarr_mcp.call_guard")

BACKSTOP_GRACE_S = 2.0


def guarded(name: str, fn: Callable[..., Awaitable[Any]], *, budget_s: float,
            max_bytes: int, redactor: Redactor,
            grace_s: float = BACKSTOP_GRACE_S) -> Callable[..., Awaitable[Any]]:
    async def wrapper(**kwargs: Any) -> Any:
        token = set_deadline(budget_s)
        active = _ACTIVE.set(redactor)
        try:
            cm = asyncio.timeout(budget_s + grace_s)
            try:
                async with cm:
                    result = await fn(**kwargs)
            except TimeoutError:
                if not cm.expired():
                    raise
                result = {"error": "tool_timeout", "tool": name,
                          "after_s": round(budget_s + grace_s, 2)}
        except Exception as exc:  # noqa: BLE001 - FastMCP would echo it unredacted
            log.exception("tool %s failed", name)
            result = {"error": "tool_error", "tool": name, "message": str(exc)}
        finally:
            reset_deadline(token)
            _ACTIVE.reset(active)
        size = len(json.dumps(result, default=str))
        if size > max_bytes:
            log.warning("tool %s output is %d bytes, over the %d cap", name, size, max_bytes)
            result = {"error": "output_too_large", "tool": name, "bytes": size,
                      "hint": "narrow with service= or limit="}
        return redactor.scrub_obj(result)

    wrapper.__name__ = getattr(fn, "__name__", name)
    wrapper.__doc__ = fn.__doc__
    # FastMCP builds the argument model and output schema from the signature.
    # Keep fn's parameters but return Any, so error objects pass output validation.
    wrapper.__signature__ = inspect.signature(fn).replace(return_annotation=Any)
    return wrapper
