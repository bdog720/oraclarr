import os
from pathlib import Path
from dotenv import load_dotenv
from .config import load_config
from .registry import build_clients
from .server import build_server


def main() -> None:
    load_dotenv()
    cfg_path = Path(os.environ.get("ORACLARR_CONFIG", "config.yaml"))
    cfg = load_config(cfg_path)
    clients = build_clients(cfg)
    mcp = build_server(cfg, clients)
    mcp.run()  # stdio


if __name__ == "__main__":
    main()
