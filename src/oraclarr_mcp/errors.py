import httpx
from .models import InstanceStatus

def status_for_exception(exc: Exception) -> InstanceStatus:
    if isinstance(exc, (httpx.ConnectError, httpx.ConnectTimeout)):
        return "unreachable"
    if isinstance(exc, (httpx.ReadTimeout, httpx.WriteTimeout, httpx.PoolTimeout)):
        return "timeout"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code in (401, 403):
            return "auth_failed"
        return "error"
    return "error"
