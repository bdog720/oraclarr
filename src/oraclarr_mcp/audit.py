"""One log line per write event: planned, executed, refused, failed, unknown."""
import logging

log = logging.getLogger("oraclarr_mcp.audit")


def audit(event: str, **fields) -> None:
    parts = " ".join(f"{k}={v}" for k, v in fields.items() if v is not None)
    log.info("audit event=%s %s", event, parts)
