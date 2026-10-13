import os
from collections.abc import Mapping
from pathlib import Path
from dotenv import load_dotenv
from .config import load_config
from .registry import build_clients
from .server import build_server
from .audit import install_audit_logging
from .redact import Redactor, install_log_redaction

_TRANSPORT_MAP = {"stdio": "stdio", "http": "streamable-http"}


def resolve_transport(env: Mapping[str, str]) -> str:
    raw = env.get("ORACLARR_TRANSPORT", "stdio").strip().lower()
    try:
        return _TRANSPORT_MAP[raw]
    except KeyError:
        raise SystemExit(
            f"Invalid ORACLARR_TRANSPORT={raw!r}; expected one of {sorted(_TRANSPORT_MAP)}"
        )


def resolve_bind(env: Mapping[str, str]) -> tuple[str, int]:
    host = env.get("ORACLARR_HTTP_HOST", "127.0.0.1")
    raw_port = env.get("ORACLARR_HTTP_PORT", "7979")
    try:
        port = int(raw_port)
    except ValueError:
        raise SystemExit(f"Invalid ORACLARR_HTTP_PORT={raw_port!r}; expected an integer")
    return host, port


def check_write_safety(cfg, transport: str) -> None:
    if transport == "streamable-http" and cfg.server.allow_writes and not cfg.server.http_token:
        raise SystemExit("ORACLARR_ALLOW_WRITES needs ORACLARR_HTTP_TOKEN on the http "
                         "transport: without it anyone who can reach the port could write")


def serve_http(mcp, token: str | None) -> None:
    import uvicorn
    from .auth import BearerTokenMiddleware
    app = mcp.streamable_http_app()
    if token:
        app = BearerTokenMiddleware(app, token)
    uvicorn.run(app, host=mcp.settings.host, port=mcp.settings.port,
                log_level=mcp.settings.log_level.lower())


def main() -> None:
    load_dotenv()
    cfg_path = Path(os.environ.get("ORACLARR_CONFIG", "config.yaml"))
    cfg = load_config(cfg_path)
    install_log_redaction(Redactor.from_config(cfg))
    install_audit_logging()
    clients = build_clients(cfg)
    transport = resolve_transport(os.environ)
    check_write_safety(cfg, transport)
    host, port = resolve_bind(os.environ)
    mcp = build_server(cfg, clients, host=host, port=port)
    if transport == "stdio":
        mcp.run()
    else:
        serve_http(mcp, cfg.server.http_token)


if __name__ == "__main__":
    main()
