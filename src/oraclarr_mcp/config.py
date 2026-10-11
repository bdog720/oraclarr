import os
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Literal
import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError

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
    model_config = ConfigDict(hide_input_in_errors=True)
    allow_writes: bool = False
    toolsets: list[str] = ["media", "downloads", "transcode", "library"]
    tool_budget_seconds: float = Field(default=30, gt=0)
    max_output_bytes: int = Field(default=200_000, gt=0)


class Defaults(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    timeout_seconds: int = 10


class Instance(BaseModel):
    # Validation errors must not echo input: an instance dict holds API keys.
    model_config = ConfigDict(hide_input_in_errors=True)
    type: Literal["sonarr", "radarr", "sportarr", "prowlarr", "qbittorrent", "tdarr",
                  "profilarr", "jellyfin"]
    url: str
    enabled: bool = True
    read_only: bool = True
    api_key: str | None = None
    username: str | None = None
    password: str | None = None


class Config(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)
    server: ServerSettings = ServerSettings()
    defaults: Defaults = Defaults()
    instances: dict[str, Instance]


def _interpolate(raw: str, env: Mapping[str, str]) -> str:
    def repl(m: re.Match) -> str:
        var = m.group(1)
        val = env.get(var)
        if val is None:
            raise ConfigError(f"Environment variable {var} referenced in config is not set")
        return val

    return _ENV_RE.sub(repl, raw)


def _read_file(p: Path, env: Mapping[str, str]) -> dict:
    if p.is_dir():
        raise ConfigError(
            f"Config path {p} is a directory, not a file. In Docker this usually means "
            f"the config.yaml file did not exist on the host when the container started, "
            f"so a directory was created at the mount point. Remove that mount (settings "
            f"can live in .env), or create config.yaml as a file and recreate the container."
        )
    if not p.exists():
        return {}
    data = yaml.safe_load(_interpolate(p.read_text(), env)) or {}
    if not isinstance(data, dict):
        raise ConfigError(f"Config file {p} must contain a YAML mapping")
    return data


def _no_instances_message(p: Path | None) -> str:
    if p is None:
        where = "No config file was given"
    elif not p.exists():
        where = f"Config file {p} not found"
    else:
        where = f"Config file {p} lists no instances"
    return (f"No instances configured. {where}, and no ORACLARR_<NAME>_URL variables are "
            f"set. Set ORACLARR_<NAME>_URL (plus _API_KEY) in .env, or copy "
            f"config.example.yaml to config.yaml.")


def load_settings(path: Path | None, env: Mapping[str, str]) -> Config:
    """config.yaml (optional) overlaid with ORACLARR_* variables; env wins per field."""
    p = Path(path) if path is not None else None
    data = _read_file(p, env) if p is not None else {}
    sections, env_instances = parse_env(env)
    for section, values in sections.items():
        if values:
            data[section] = {**(data.get(section) or {}), **values}
    merged: dict[str, dict] = {}
    for name, inst in (data.get("instances") or {}).items():
        if not isinstance(inst, dict):
            raise ConfigError(f"instance '{name}' in {p} must be a mapping of settings")
        merged[name] = dict(inst)
    for name, fields in env_instances.items():
        merged[name] = {**merged.get(name, {}), **fields}
    if not merged:
        raise ConfigError(_no_instances_message(p))
    for name, inst in merged.items():
        if not inst.get("url"):
            raise ConfigError(f"instance '{name}' has no URL: set {env_name(name, 'URL')}")
        if not inst.get("type"):
            if name not in INSTANCE_TYPES:
                raise ConfigError(f"instance '{name}' needs {env_name(name, 'TYPE')} "
                                  f"(one of: {', '.join(sorted(INSTANCE_TYPES))})")
            inst["type"] = name
    data["instances"] = merged
    try:
        return Config.model_validate(data)
    except ValidationError as e:
        raise ConfigError(str(e)) from None


def load_config(path: Path) -> Config:
    return load_settings(path, os.environ)
