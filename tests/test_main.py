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
