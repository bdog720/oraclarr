"""One log line per write event: planned, executed, refused, failed, unknown."""
import logging
import re
import sys

log = logging.getLogger("oraclarr_mcp.audit")

_UNSAFE = re.compile(r"[\s\x00-\x1f\x7f]")


def _safe(value) -> str:
    # A value must never start a new line or add a forged key=value pair.
    return _UNSAFE.sub("_", str(value))


def audit(event: str, **fields) -> None:
    parts = " ".join(f"{k}={_safe(v)}" for k, v in fields.items() if v is not None)
    log.info("audit event=%s %s", _safe(event), parts)


def install_audit_logging() -> None:
    """Give audit events their own plain stderr handler, one physical line each.

    The root logger's Rich handler wraps at 80 columns without a TTY, which
    splits an event over several lines in `docker logs`. stderr only: the stdio
    transport owns stdout.
    """
    if any(getattr(h, "_oraclarr_audit", False) for h in log.handlers):
        return
    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter("%(asctime)s %(message)s"))
    handler._oraclarr_audit = True  # type: ignore[attr-defined]
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False
