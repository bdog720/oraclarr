import pytest
from oraclarr_mcp.config import load_config, ConfigError

YAML = """
server:
  allow_writes: false
  toolsets: [media, downloads, transcode]
defaults:
  timeout_seconds: 7
instances:
  sonarr: { type: sonarr, url: http://h:8989, api_key: ${SONARR_KEY} }
  tdarr:  { type: tdarr,  url: http://h:8265 }
"""

def test_loads_and_interpolates_env(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARR_KEY", "secret123")
    p = tmp_path / "config.yaml"; p.write_text(YAML)
    cfg = load_config(p)
    assert cfg.server.allow_writes is False
    assert cfg.defaults.timeout_seconds == 7
    assert cfg.instances["sonarr"].api_key == "secret123"
    assert cfg.instances["sonarr"].type == "sonarr"

def test_missing_env_var_raises_named_error(tmp_path):
    p = tmp_path / "config.yaml"; p.write_text(YAML)
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert "SONARR_KEY" in str(e.value)

def test_unknown_type_raises(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARR_KEY", "x")
    bad = YAML + "  bogus: { type: nope, url: http://h:1 }\n"
    p = tmp_path / "config.yaml"; p.write_text(bad)
    with pytest.raises(ConfigError):
        load_config(p)

def test_config_path_is_directory_raises_friendly_error(tmp_path):
    # Docker bind-mount footgun: a missing host config.yaml gets created as a
    # directory, so the mount point inside the container is a dir, not a file.
    d = tmp_path / "config.yaml"; d.mkdir()
    with pytest.raises(ConfigError) as e:
        load_config(d)
    msg = str(e.value)
    assert "directory" in msg.lower()
    assert "config.yaml" in msg

def test_missing_config_file_raises_friendly_error(tmp_path):
    p = tmp_path / "config.yaml"  # never created
    with pytest.raises(ConfigError) as e:
        load_config(p)
    assert "not found" in str(e.value).lower()


def test_sportarr_type_is_accepted(tmp_path, monkeypatch):
    monkeypatch.setenv("SONARR_KEY", "x")
    monkeypatch.setenv("SPORTARR_KEY", "y")
    extra = YAML + "  sportarr: { type: sportarr, url: http://h:1867, api_key: ${SPORTARR_KEY} }\n"
    p = tmp_path / "config.yaml"; p.write_text(extra)
    cfg = load_config(p)
    assert cfg.instances["sportarr"].type == "sportarr"
    assert cfg.instances["sportarr"].api_key == "y"


from oraclarr_mcp.config import ServerSettings  # noqa: E402


def test_server_budget_and_cap_defaults():
    s = ServerSettings()
    assert s.tool_budget_seconds == 30
    assert s.max_output_bytes == 200_000


def test_server_budget_and_cap_from_yaml(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "server:\n"
        "  tool_budget_seconds: 12.5\n"
        "  max_output_bytes: 5000\n"
        "instances:\n"
        "  tdarr: { type: tdarr, url: http://h:8265 }\n"
    )
    cfg = load_config(p)
    assert cfg.server.tool_budget_seconds == 12.5
    assert cfg.server.max_output_bytes == 5000


def test_zero_budget_is_rejected(tmp_path):
    p = tmp_path / "config.yaml"
    p.write_text(
        "server:\n"
        "  tool_budget_seconds: 0\n"
        "instances:\n"
        "  tdarr: { type: tdarr, url: http://h:8265 }\n"
    )
    with pytest.raises(ConfigError):
        load_config(p)
