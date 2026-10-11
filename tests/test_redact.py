import logging

from oraclarr_mcp.config import Config, Instance
from oraclarr_mcp.redact import MASK, Redactor, install_log_redaction


def _cfg():
    return Config(instances={
        "sonarr": Instance(type="sonarr", url="http://h:8989", api_key="SONARRKEY123"),
        "qbit": Instance(type="qbittorrent", url="http://h:8080",
                         username="admin", password="QbitPass99"),
        "short": Instance(type="sonarr", url="http://h:1", api_key="abc"),
    })


def test_scrub_removes_configured_secret_values():
    r = Redactor.from_config(_cfg())
    out = r.scrub("401 for key SONARRKEY123 and pass QbitPass99")
    assert "SONARRKEY123" not in out and "QbitPass99" not in out
    assert out.count(MASK) == 2


def test_short_secret_is_not_value_scrubbed():
    r = Redactor.from_config(_cfg())
    assert r.scrub("abc is a common word") == "abc is a common word"


def test_scrub_masks_query_and_header_patterns():
    r = Redactor([])
    text = ("GET http://h/Items?api_key=JFKEY1&x=1 apikey=Z2 token=T3 "
            "X-Api-Key: H4 X-Emby-Token: E5 Authorization: Bearer B6")
    out = r.scrub(text)
    for secret in ("JFKEY1", "Z2", "T3", "H4", "E5", "B6"):
        assert secret not in out
    assert "&x=1" in out


def test_scrub_obj_walks_nested_structures():
    r = Redactor(["SONARRKEY123"])
    obj = [{"instance": "sonarr", "error": "bad SONARRKEY123",
            "data": {"urls": ["http://h?api_key=SONARRKEY123"]}}, 5, None]
    out = r.scrub_obj(obj)
    assert "SONARRKEY123" not in repr(out)
    assert out[1] == 5 and out[2] is None


def test_log_redaction_covers_child_loggers_and_tracebacks(caplog):
    previous = install_log_redaction(Redactor(["SONARRKEY123"]))
    try:
        with caplog.at_level(logging.INFO):
            logging.getLogger("httpx").info("HTTP Request: GET %s", "http://h?k=SONARRKEY123")
            try:
                raise ValueError("boom SONARRKEY123")
            except ValueError:
                logging.getLogger("oraclarr_mcp.test").exception("failed")
    finally:
        logging.setLogRecordFactory(previous)
    assert "SONARRKEY123" not in caplog.text
    assert MASK in caplog.text
