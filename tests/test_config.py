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
