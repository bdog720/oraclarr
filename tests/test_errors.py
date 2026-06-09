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
