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
    raw = Path(path).read_text()
    interpolated = _interpolate(raw)
    data = yaml.safe_load(interpolated)
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(str(e)) from e
