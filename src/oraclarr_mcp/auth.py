"""Bearer-token check for the whole HTTP endpoint (reads included)."""
import hmac
import json

_BODY = json.dumps({"error": "unauthorized"}).encode()


class BearerTokenMiddleware:
    def __init__(self, app, token: str):
        self.app = app
        self._token = token.encode()

    def _ok(self, scope) -> bool:
        for name, value in scope.get("headers") or []:
            if name == b"authorization":
                scheme, _, sent = value.partition(b" ")
                return (scheme.lower() == b"bearer"
                        and hmac.compare_digest(sent.strip(), self._token))
        return False

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or self._ok(scope):
            await self.app(scope, receive, send)
            return
        await send({"type": "http.response.start", "status": 401,
                    "headers": [(b"content-type", b"application/json"),
                                (b"www-authenticate", b"Bearer"),
                                (b"content-length", str(len(_BODY)).encode())]})
        await send({"type": "http.response.body", "body": _BODY})
