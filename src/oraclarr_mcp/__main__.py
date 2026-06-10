import os
from collections.abc import Mapping
from pathlib import Path
from dotenv import load_dotenv
from .config import load_config
from .registry import build_clients
from .server import build_server

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


def main() -> None:
    load_dotenv()
    cfg_path = Path(os.environ.get("ORACLARR_CONFIG", "config.yaml"))
    cfg = load_config(cfg_path)
    clients = build_clients(cfg)
    transport = resolve_transport(os.environ)
    host, port = resolve_bind(os.environ)
    mcp = build_server(cfg, clients, host=host, port=port)
    if transport == "stdio":
        mcp.run()
    else:
        mcp.run(transport=transport)


if __name__ == "__main__":
    main()
