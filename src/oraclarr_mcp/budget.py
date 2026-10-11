"""Per-tool-call deadline, carried in a ContextVar.

The call_guard wrapper sets it once per tool call; probe() reads it so every
instance in a fan-out shares one budget. ContextVars are copied per asyncio
task, so concurrent calls from different agents never share a deadline.
"""
import contextvars
import time

_deadline: contextvars.ContextVar[float | None] = contextvars.ContextVar(
    "oraclarr_deadline", default=None)


def set_deadline(seconds: float) -> contextvars.Token:
    return _deadline.set(time.monotonic() + seconds)


def reset_deadline(token: contextvars.Token) -> None:
    _deadline.reset(token)


def remaining() -> float | None:
    d = _deadline.get()
    return None if d is None else d - time.monotonic()
