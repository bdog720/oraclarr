"""server.json is validated by the MCP Registry at publish time, after PyPI has the release.

A registry rejection leaves PyPI and GHCR on the new version and the registry on the old
one, and the tag cannot simply be re-run (PyPI refuses a second upload). Check here instead.
"""
import json
import tomllib
from pathlib import Path

ROOT = Path(__file__).parent.parent
REGISTRY_DESCRIPTION_MAX = 100


def _server_json() -> dict:
    return json.loads((ROOT / "server.json").read_text(encoding="utf-8"))


def test_description_fits_the_registry_limit():
    assert len(_server_json()["description"]) <= REGISTRY_DESCRIPTION_MAX


def test_versions_match_pyproject():
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    data = _server_json()
    assert data["version"] == version
    assert all(p["version"] == version for p in data.get("packages", []))
