import httpx
from websockets.exceptions import ConnectionClosed, InvalidHandshake, InvalidURI

from .clients.truenas import TruenasAuthError, TruenasConnectError
from .models import InstanceStatus


def status_for_exception(exc: Exception) -> InstanceStatus:
    if isinstance(exc, TruenasAuthError):
        return "auth_failed"
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout, TruenasConnectError,
                        InvalidHandshake, InvalidURI, ConnectionClosed)):
        return "unreachable"
    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "auth_failed"
        return "error"
    if isinstance(exc, OSError):  # socket refused/reset; TimeoutError is caught earlier by probe
        return "unreachable"
    return "error"
