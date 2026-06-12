import os
import re
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ValidationError

INSTANCE_TYPES = {"sonarr", "radarr", "prowlarr", "qbittorrent", "tdarr", "profilarr"}
_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ConfigError(Exception):
    pass


class ServerSettings(BaseModel):
    allow_writes: bool = False
    toolsets: list[str] = ["media", "downloads", "transcode"]


class Defaults(BaseModel):
    timeout_seconds: int = 10


class Instance(BaseModel):
    type: Literal["sonarr", "radarr", "prowlarr", "qbittorrent", "tdarr", "profilarr"]
    url: str
    enabled: bool = True
    read_only: bool = True
    api_key: str | None = None
    username: str | None = None
    password: str | None = None


class Config(BaseModel):
    server: ServerSettings = ServerSettings()
    defaults: Defaults = Defaults()
    instances: dict[str, Instance]


def _interpolate(raw: str) -> str:
    def repl(m: re.Match) -> str:
        var = m.group(1)
        val = os.environ.get(var)
        if val is None:
            raise ConfigError(f"Environment variable {var} referenced in config is not set")
        return val

    return _ENV_RE.sub(repl, raw)


def load_config(path: Path) -> Config:
    p = Path(path)
    if p.is_dir():
        raise ConfigError(
            f"Config path {p} is a directory, not a file. In Docker this usually means "
            f"the config.yaml file did not exist on the host when the container started, "
            f"so a directory was created at the mount point. Create config.yaml as a file "
            f"(copy config.example.yaml) and recreate the container."
        )
    if not p.exists():
        raise ConfigError(
            f"Config file not found: {p}. Copy config.example.yaml to config.yaml and "
            f"point ORACLARR_CONFIG at it (or mount it into the container at this path)."
        )
    raw = p.read_text()
    interpolated = _interpolate(raw)
    data = yaml.safe_load(interpolated)
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(str(e)) from e
