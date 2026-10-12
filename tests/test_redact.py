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


def test_log_redaction_keeps_uvicorn_access_args():
    import httpx
    from uvicorn.logging import AccessFormatter
    previous = install_log_redaction(Redactor(["SONARRKEY123"]))
    try:
        rec = logging.getLogger("uvicorn.access").makeRecord(
            "uvicorn.access", logging.INFO, __file__, 1, '%s - "%s %s HTTP/%s" %d',
            ("1.2.3.4:5", "GET", "/mcp?api_key=SONARRKEY123", "1.1", 200), None)
        url_rec = logging.getLogger("httpx").makeRecord(
            "httpx", logging.INFO, __file__, 1, "HTTP Request: %s %s",
            ("GET", httpx.URL("http://h/x?api_key=SONARRKEY123")), None)
    finally:
        logging.setLogRecordFactory(previous)
    out = AccessFormatter(fmt="%(message)s", use_colors=False).format(rec)
    assert "SONARRKEY123" not in out
    assert '"GET' in out and "200" in out
    assert "SONARRKEY123" not in url_rec.getMessage()


def test_scrub_masks_mediabrowser_token_header():
    out = Redactor([]).scrub('Authorization: MediaBrowser Token="JFKEY999", Client="x"')
    assert "JFKEY999" not in out
    assert 'MediaBrowser Token="***"' in out


def test_scrub_masks_password_and_secret_assignments():
    r = Redactor([])
    out = r.scrub('login password=Hunter2x passwd: Pw2 pwd=P3 client_secret=S4, "ok"')
    for secret in ("Hunter2x", "Pw2", "P3", "S4"):
        assert secret not in out
    assert out.startswith("login password=***") and out.endswith(', "ok"')


def test_scrub_masks_url_credentials_and_keeps_host():
    out = Redactor([]).scrub("connect https://vpnuser:VpnPass77@vpn.example:443/x")
    assert "VpnPass77" not in out
    assert "https://vpnuser:***@vpn.example:443/x" in out


def test_scrub_masks_portainer_style_tokens():
    out = Redactor([]).scrub("token ptr_AbCdEf123456+/= seen")
    assert "AbCdEf123456" not in out and "ptr_***" in out


def test_new_patterns_leave_ordinary_text_alone():
    text = "Password reset page loaded; secrets manager ok; see http://host:8989/path"
    assert Redactor([]).scrub(text) == text


def test_scrub_masks_json_password_fields():
    out = Redactor([]).scrub('{"user":"bob","password":"hunter2x","client_secret": "S9"}')
    assert "hunter2x" not in out and "S9" not in out and '"user":"bob"' in out


def test_url_credential_pattern_is_linear_on_dotted_text():
    import time
    t0 = time.monotonic()
    Redactor([]).scrub("a." * 25000)
    assert time.monotonic() - t0 < 1.0
