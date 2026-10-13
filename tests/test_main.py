import pytest
from oraclarr_mcp.__main__ import resolve_transport, resolve_bind


def test_transport_defaults_to_stdio():
    assert resolve_transport({}) == "stdio"


def test_transport_http_maps_to_streamable_http():
    assert resolve_transport({"ORACLARR_TRANSPORT": "http"}) == "streamable-http"


def test_transport_is_case_insensitive():
    assert resolve_transport({"ORACLARR_TRANSPORT": "HTTP"}) == "streamable-http"


def test_transport_invalid_value_exits():
    with pytest.raises(SystemExit):
        resolve_transport({"ORACLARR_TRANSPORT": "grpc"})


def test_bind_defaults():
    assert resolve_bind({}) == ("127.0.0.1", 7979)


def test_bind_env_overrides():
    env = {"ORACLARR_HTTP_HOST": "0.0.0.0", "ORACLARR_HTTP_PORT": "8123"}
    assert resolve_bind(env) == ("0.0.0.0", 8123)


def test_bind_invalid_port_exits():
    with pytest.raises(SystemExit):
        resolve_bind({"ORACLARR_HTTP_PORT": "notaport"})


import logging  # noqa: E402

import oraclarr_mcp.__main__ as entry  # noqa: E402
from oraclarr_mcp.config import Config, Instance  # noqa: E402


def test_main_installs_log_redaction(monkeypatch):
    cfg = Config(instances={"sonarr": Instance(type="sonarr", url="http://h",
                                               api_key="SONARRKEY123")})

    class Dummy:
        def run(self, **kw):
            pass

    monkeypatch.delenv("ORACLARR_TRANSPORT", raising=False)
    monkeypatch.setattr(entry, "load_dotenv", lambda: None)
    monkeypatch.setattr(entry, "load_config", lambda p: cfg)
    monkeypatch.setattr(entry, "build_clients", lambda c: {})
    monkeypatch.setattr(entry, "build_server", lambda *a, **k: Dummy())
    before = logging.getLogRecordFactory()
    try:
        entry.main()
        rec = logging.getLogger("t").makeRecord(
            "t", logging.INFO, __file__, 1, "key %s", ("SONARRKEY123",), None)
        assert "SONARRKEY123" not in rec.getMessage()
    finally:
        logging.setLogRecordFactory(before)


from oraclarr_mcp.config import ServerSettings  # noqa: E402


def _cfg(allow_writes=False, token=None):
    return Config(server=ServerSettings(allow_writes=allow_writes, http_token=token),
                  instances={})


def test_writes_on_http_without_token_exit():
    with pytest.raises(SystemExit) as e:
        entry.check_write_safety(_cfg(allow_writes=True), "streamable-http")
    assert "ORACLARR_HTTP_TOKEN" in str(e.value)


def test_writes_allowed_on_stdio_or_with_token():
    entry.check_write_safety(_cfg(allow_writes=True), "stdio")
    entry.check_write_safety(_cfg(allow_writes=True, token="t" * 24), "streamable-http")
    entry.check_write_safety(_cfg(), "streamable-http")


def test_serve_http_wraps_app_only_when_token_set(monkeypatch):
    calls = []

    class FakeMcp:
        class settings:
            host, port, log_level = "0.0.0.0", 7979, "INFO"

        def streamable_http_app(self):
            return "APP"

    import uvicorn
    monkeypatch.setattr(uvicorn, "run", lambda app, **kw: calls.append((app, kw)))
    entry.serve_http(FakeMcp(), None)
    entry.serve_http(FakeMcp(), "t" * 24)
    assert calls[0][0] == "APP"
    assert type(calls[1][0]).__name__ == "BearerTokenMiddleware"
    assert calls[1][1] == {"host": "0.0.0.0", "port": 7979, "log_level": "info"}
