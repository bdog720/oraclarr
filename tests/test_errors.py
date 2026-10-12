import httpx
from oraclarr_mcp.errors import status_for_exception

def test_timeout_maps_unreachable():
    assert status_for_exception(httpx.ConnectTimeout("x")) == "unreachable"

def test_connect_error_maps_unreachable():
    assert status_for_exception(httpx.ConnectError("x")) == "unreachable"

def test_401_maps_auth_failed():
    resp = httpx.Response(401, request=httpx.Request("GET", "http://x"))
    err = httpx.HTTPStatusError("401", request=resp.request, response=resp)
    assert status_for_exception(err) == "auth_failed"

def test_other_maps_error():
    assert status_for_exception(ValueError("boom")) == "error"


def test_read_timeout_maps_timeout():
    assert status_for_exception(httpx.ReadTimeout("x")) == "timeout"


def test_write_timeout_maps_timeout():
    assert status_for_exception(httpx.WriteTimeout("x")) == "timeout"


def test_pool_timeout_maps_timeout():
    assert status_for_exception(httpx.PoolTimeout("x")) == "timeout"


def test_truenas_errors_map_to_statuses():
    from oraclarr_mcp.clients.truenas import (TruenasAuthError, TruenasCallError,
                                              TruenasConnectError)
    assert status_for_exception(TruenasAuthError("x")) == "auth_failed"
    assert status_for_exception(TruenasConnectError("x")) == "unreachable"
    assert status_for_exception(ConnectionRefusedError()) == "unreachable"
    assert status_for_exception(TruenasCallError("x")) == "error"
