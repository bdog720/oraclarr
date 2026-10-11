"""Remove secrets from tool output and log records.

Two layers: every configured secret value is replaced wherever it appears,
and common key/token patterns are masked even when the value is unknown
(e.g. a key echoed by an upstream in an error URL).
"""
import logging
import re
from typing import Any, Callable, Iterable
from .config import Config

MASK = "***"
_SECRET_FIELDS = ("api_key", "password", "token")
_MIN_LEN = 4  # shorter values would mangle ordinary text; patterns still cover them
_PATTERNS = (
    re.compile(r"(?i)((?:api_?key|token)=)[^&\s\"']+"),
    re.compile(r"(?i)((?:x-api-key|x-emby-token):\s*)\S+"),
    re.compile(r"(?i)(authorization:\s*bearer\s+)\S+"),
)


class Redactor:
    def __init__(self, secrets: Iterable[str]):
        # Longest first so a secret that contains another is replaced whole.
        self._secrets = sorted({s for s in secrets if s and len(s) >= _MIN_LEN},
                               key=len, reverse=True)

    @classmethod
    def from_config(cls, cfg: Config) -> "Redactor":
        values = []
        for inst in cfg.instances.values():
            for field in _SECRET_FIELDS:
                v = getattr(inst, field, None)
                if isinstance(v, str):
                    values.append(v)
        return cls(values)

    def scrub(self, text: str) -> str:
        for s in self._secrets:
            text = text.replace(s, MASK)
        for p in _PATTERNS:
            text = p.sub(lambda m: m.group(1) + MASK, text)
        return text

    def scrub_obj(self, obj: Any) -> Any:
        if isinstance(obj, str):
            return self.scrub(obj)
        if isinstance(obj, dict):
            return {k: self.scrub_obj(v) for k, v in obj.items()}
        if isinstance(obj, (list, tuple)):
            return [self.scrub_obj(v) for v in obj]
        return obj


def _scrub_arg(redactor: Redactor, value: Any) -> Any:
    # Numbers stay numbers so %d placeholders keep working; anything else
    # (str, httpx.URL, exceptions) is rendered and scrubbed.
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return redactor.scrub(str(value))


def install_log_redaction(redactor: Redactor) -> Callable:
    """Scrub every log record at creation. Returns the previous factory.

    A filter on the root logger would miss records that propagate from child
    loggers such as httpx; the record factory sees all of them. Args keep their
    shape: uvicorn's AccessFormatter unpacks record.args positionally.
    """
    previous = logging.getLogRecordFactory()
    formatter = logging.Formatter()

    def factory(*args, **kwargs):
        record = previous(*args, **kwargs)
        try:
            if isinstance(record.msg, str):
                record.msg = redactor.scrub(record.msg)
            if isinstance(record.args, tuple):
                record.args = tuple(_scrub_arg(redactor, a) for a in record.args)
            elif isinstance(record.args, dict):
                record.args = {k: _scrub_arg(redactor, v) for k, v in record.args.items()}
            if record.exc_info:
                record.exc_text = redactor.scrub(formatter.formatException(record.exc_info))
        except Exception:  # noqa: BLE001 - logging must never raise
            pass
        return record

    logging.setLogRecordFactory(factory)
    return previous
