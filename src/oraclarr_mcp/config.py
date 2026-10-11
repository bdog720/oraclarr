import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, Field, ValidationError

INSTANCE_TYPES = {"sonarr", "radarr", "sportarr", "prowlarr", "qbittorrent", "tdarr", "profilarr",
                  "jellyfin"}
_ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")


class ConfigError(Exception):
    pass


ENV_PREFIX = "ORACLARR_"
# Read by __main__ for transport and the config path; never instance settings.
RESERVED_ENV = {"TRANSPORT", "HTTP_HOST", "HTTP_PORT", "CONFIG"}
_TRUE = {"true", "yes", "1", "on"}
_FALSE = {"false", "no", "0", "off"}
# Longest suffix first, so SONARR_ANIME_API_KEY splits as SONARR_ANIME + API_KEY.
_FIELDS = sorted({"_URL": "url", "_TYPE": "type", "_API_KEY": "api_key",
                  "_USERNAME": "username", "_PASSWORD": "password",
                  "_ENABLED": "enabled"}.items(), key=lambda kv: -len(kv[0]))
_FIELD_HELP = "_TYPE, _URL, _API_KEY, _USERNAME, _PASSWORD, _ENABLED"


def _parse_bool(value: str) -> bool:
    s = value.lower()
    if s in _TRUE:
        return True
    if s in _FALSE:
        return False
    raise ValueError


def _parse_list(value: str) -> list[str]:
    return [x.strip() for x in value.split(",") if x.strip()]


_SERVER_ENV = {
    "TOOLSETS": ("server", "toolsets", _parse_list, "a comma-separated list"),
    "ALLOW_WRITES": ("server", "allow_writes", _parse_bool, "true or false"),
    "TOOL_BUDGET_SECONDS": ("server", "tool_budget_seconds", float, "a number"),
    "MAX_OUTPUT_BYTES": ("server", "max_output_bytes", int, "a whole number"),
    "TIMEOUT_SECONDS": ("defaults", "timeout_seconds", int, "a whole number"),
}


def env_name(instance: str, field: str) -> str:
    return f"{ENV_PREFIX}{instance.upper().replace('-', '_')}_{field}"


def parse_env(env: Mapping[str, str]) -> tuple[dict, dict]:
    """Split ORACLARR_* variables into settings sections and per-instance fields.

    Messages name the variable but never echo its value: values are secrets.
    """
    sections: dict[str, dict] = {"server": {}, "defaults": {}}
    instances: dict[str, dict] = {}
    for key, raw in env.items():
        if not key.startswith(ENV_PREFIX):
            continue
        rest = key[len(ENV_PREFIX):]
        value = raw.strip()
        if rest in RESERVED_ENV or not value:
            continue
        if rest in _SERVER_ENV:
            section, field, parse, kind = _SERVER_ENV[rest]
            try:
                sections[section][field] = parse(value)
            except ValueError:
                raise ConfigError(f"{key} must be {kind}") from None
            continue
        for suffix, field in _FIELDS:
            if rest.endswith(suffix) and len(rest) > len(suffix):
                name = rest[: -len(suffix)].lower().replace("_", "-")
                if field == "enabled":
                    try:
                        value = _parse_bool(value)
                    except ValueError:
                        raise ConfigError(f"{key} must be true or false") from None
                elif field == "type":
                    value = value.lower()
                instances.setdefault(name, {})[field] = value
                break
        else:
            raise ConfigError(f"unknown variable {key}; instance fields are {_FIELD_HELP}")
    return sections, instances


class ServerSettings(BaseModel):
    allow_writes: bool = False
    toolsets: list[str] = ["media", "downloads", "transcode", "library"]
    tool_budget_seconds: float = Field(default=30, gt=0)
    max_output_bytes: int = Field(default=200_000, gt=0)


class Defaults(BaseModel):
    timeout_seconds: int = 10


class Instance(BaseModel):
    type: Literal["sonarr", "radarr", "sportarr", "prowlarr", "qbittorrent", "tdarr",
                  "profilarr", "jellyfin"]
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
