import pytest

from oraclarr_mcp.config import ConfigError, Instance, env_name, parse_env

KEY = "SECRETKEY12345"
EMPTY = {"server": {}, "defaults": {}}


def test_env_name_round_trips_dashes():
    assert env_name("sonarr-anime", "URL") == "ORACLARR_SONARR_ANIME_URL"


def test_parse_instance_fields_and_name():
    sections, inst = parse_env({"ORACLARR_SONARR_ANIME_URL": "http://h:8990",
                                "ORACLARR_SONARR_ANIME_API_KEY": KEY,
                                "ORACLARR_SONARR_ANIME_TYPE": "Sonarr"})
    assert inst == {"sonarr-anime": {"url": "http://h:8990", "api_key": KEY, "type": "sonarr"}}
    assert sections == EMPTY


def test_parse_username_password_enabled():
    _, inst = parse_env({"ORACLARR_QBIT_URL": "http://h:8080", "ORACLARR_QBIT_USERNAME": "admin",
                         "ORACLARR_QBIT_PASSWORD": KEY, "ORACLARR_QBIT_ENABLED": "No"})
    assert inst["qbit"] == {"url": "http://h:8080", "username": "admin", "password": KEY,
                            "enabled": False}


@pytest.mark.parametrize("raw,val", [("true", True), ("YES", True), ("1", True), ("on", True),
                                     ("false", False), ("no", False), ("0", False),
                                     ("Off", False)])
def test_parse_boolean_forms(raw, val):
    sections, _ = parse_env({"ORACLARR_ALLOW_WRITES": raw})
    assert sections["server"]["allow_writes"] is val


def test_parse_server_settings():
    sections, _ = parse_env({"ORACLARR_TOOLSETS": " media, library ,,",
                             "ORACLARR_TOOL_BUDGET_SECONDS": "12.5",
                             "ORACLARR_MAX_OUTPUT_BYTES": "5000",
                             "ORACLARR_TIMEOUT_SECONDS": "7"})
    assert sections == {"server": {"toolsets": ["media", "library"],
                                   "tool_budget_seconds": 12.5, "max_output_bytes": 5000},
                        "defaults": {"timeout_seconds": 7}}


def test_reserved_and_foreign_variables_are_ignored():
    sections, inst = parse_env({
        "ORACLARR_TRANSPORT": "http", "ORACLARR_HTTP_HOST": "0.0.0.0",
        "ORACLARR_HTTP_PORT": "7979", "ORACLARR_CONFIG": "/config/config.yaml",
        "PATH": "/bin", "SONARR_URL": "http://x", "DATABASE_URL": "postgres://y"})
    assert inst == {} and sections == EMPTY


def test_empty_values_count_as_unset():
    _, inst = parse_env({"ORACLARR_RADARR_URL": "", "ORACLARR_RADARR_API_KEY": "   ",
                         "ORACLARR_SONARR_APIKEY": ""})
    assert inst == {}


def test_values_are_stripped():
    _, inst = parse_env({"ORACLARR_SONARR_URL": "  http://h:8989  "})
    assert inst["sonarr"]["url"] == "http://h:8989"


def test_unknown_variable_names_it_without_value():
    with pytest.raises(ConfigError) as e:
        parse_env({"ORACLARR_SONARR_APIKEY": KEY})
    msg = str(e.value)
    assert "ORACLARR_SONARR_APIKEY" in msg and "_API_KEY" in msg and KEY not in msg


def test_empty_instance_name_is_unknown():
    with pytest.raises(ConfigError) as e:
        parse_env({"ORACLARR_API_KEY": KEY})
    assert "ORACLARR_API_KEY" in str(e.value) and KEY not in str(e.value)


@pytest.mark.parametrize("var", ["ORACLARR_TOOL_BUDGET_SECONDS", "ORACLARR_MAX_OUTPUT_BYTES",
                                 "ORACLARR_TIMEOUT_SECONDS", "ORACLARR_ALLOW_WRITES",
                                 "ORACLARR_SONARR_ENABLED"])
def test_bad_value_names_variable_without_value(var):
    with pytest.raises(ConfigError) as e:
        parse_env({var: KEY})
    assert var in str(e.value) and KEY not in str(e.value)


import logging  # noqa: E402

from oraclarr_mcp.config import load_config, load_settings  # noqa: E402
from oraclarr_mcp.redact import Redactor  # noqa: E402

YAML = ("server:\n  toolsets: [media]\n  tool_budget_seconds: 20\n"
        "instances:\n"
        "  sonarr: { type: sonarr, url: http://file:8989, api_key: filekey1 }\n"
        "  tdarr:  { type: tdarr,  url: http://file:8265 }\n")


def _file(tmp_path, text=YAML):
    p = tmp_path / "config.yaml"
    p.write_text(text)
    return p


def test_env_only_without_a_file(tmp_path):
    cfg = load_settings(tmp_path / "missing.yaml",
                        {"ORACLARR_SONARR_URL": "http://h:8989", "ORACLARR_SONARR_API_KEY": KEY})
    assert cfg.instances["sonarr"].type == "sonarr"
    assert cfg.instances["sonarr"].api_key == KEY


def test_file_only(tmp_path):
    cfg = load_settings(_file(tmp_path), {})
    assert set(cfg.instances) == {"sonarr", "tdarr"}
    assert cfg.server.tool_budget_seconds == 20 and cfg.server.toolsets == ["media"]


def test_env_overrides_file_per_field(tmp_path):
    cfg = load_settings(_file(tmp_path), {"ORACLARR_SONARR_API_KEY": KEY,
                                          "ORACLARR_TOOL_BUDGET_SECONDS": "5"})
    s = cfg.instances["sonarr"]
    assert s.api_key == KEY and s.url == "http://file:8989"
    assert cfg.server.tool_budget_seconds == 5 and cfg.server.toolsets == ["media"]


def test_env_and_file_instances_combine(tmp_path):
    cfg = load_settings(_file(tmp_path), {"ORACLARR_JELLYFIN_URL": "http://h:8096",
                                          "ORACLARR_JELLYFIN_API_KEY": KEY})
    assert set(cfg.instances) == {"sonarr", "tdarr", "jellyfin"}


def test_env_can_disable_file_instance(tmp_path):
    cfg = load_settings(_file(tmp_path), {"ORACLARR_TDARR_ENABLED": "false"})
    assert cfg.instances["tdarr"].enabled is False


def test_missing_type_names_the_variable():
    with pytest.raises(ConfigError) as e:
        load_settings(None, {"ORACLARR_DOWNLOADER_URL": "http://h"})
    msg = str(e.value)
    assert "ORACLARR_DOWNLOADER_TYPE" in msg and "qbittorrent" in msg


def test_fields_without_url_name_the_url_variable():
    with pytest.raises(ConfigError) as e:
        load_settings(None, {"ORACLARR_RADARR_API_KEY": KEY})
    assert "ORACLARR_RADARR_URL" in str(e.value) and KEY not in str(e.value)


def test_no_instances_names_both_methods(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_settings(tmp_path / "missing.yaml", {})
    msg = str(e.value)
    assert "ORACLARR_<NAME>_URL" in msg and "not found" in msg and "config.yaml" in msg


def test_file_values_still_interpolate_from_env(tmp_path):
    p = _file(tmp_path, "instances:\n  sonarr: { type: sonarr, url: http://h, api_key: ${MY_KEY} }\n")
    assert load_settings(p, {"MY_KEY": KEY}).instances["sonarr"].api_key == KEY


def test_validation_error_does_not_print_secret(tmp_path):
    p = _file(tmp_path, "instances:\n  sonarr: { type: sonarr, url: http://h, api_key: ["
              + KEY + "] }\n")
    with pytest.raises(ConfigError) as e:
        load_settings(p, {})
    assert KEY not in str(e.value)


def test_non_mapping_instance_is_a_config_error(tmp_path):
    with pytest.raises(ConfigError) as e:
        load_settings(_file(tmp_path, "instances:\n  sonarr: just-a-string\n"), {})
    assert "sonarr" in str(e.value)


def test_directory_path_still_errors(tmp_path):
    d = tmp_path / "config.yaml"
    d.mkdir()
    with pytest.raises(ConfigError) as e:
        load_settings(d, {"ORACLARR_SONARR_URL": "http://h"})
    assert "directory" in str(e.value).lower()


def test_load_config_wrapper_reads_os_environ(tmp_path, monkeypatch):
    monkeypatch.setenv("ORACLARR_SONARR_URL", "http://h:8989")
    assert "sonarr" in load_config(tmp_path / "missing.yaml").instances


def test_env_key_is_redacted():
    cfg = load_settings(None, {"ORACLARR_SONARR_URL": "http://h", "ORACLARR_SONARR_API_KEY": KEY})
    assert KEY not in Redactor.from_config(cfg).scrub(f"401 for {KEY}")


def test_main_starts_from_env_only(monkeypatch, tmp_path):
    import os
    import oraclarr_mcp.__main__ as entry
    seen = {}

    class Dummy:
        def run(self, **kw):
            pass

    def fake_build(cfg):
        seen["cfg"] = cfg
        return {}

    for k in list(os.environ):
        if k.startswith("ORACLARR_"):
            monkeypatch.delenv(k)
    monkeypatch.setenv("ORACLARR_CONFIG", str(tmp_path / "absent.yaml"))
    monkeypatch.setenv("ORACLARR_SONARR_URL", "http://h:8989")
    monkeypatch.setenv("ORACLARR_SONARR_API_KEY", KEY)
    monkeypatch.setattr(entry, "load_dotenv", lambda: None)
    monkeypatch.setattr(entry, "build_clients", fake_build)
    monkeypatch.setattr(entry, "build_server", lambda *a, **k: Dummy())
    before = logging.getLogRecordFactory()
    try:
        entry.main()
    finally:
        logging.setLogRecordFactory(before)
    assert seen["cfg"].instances["sonarr"].api_key == KEY


def test_yaml_special_characters_in_a_secret_load_literally(tmp_path):
    secret = "*leak-SECRET99 #x a: b"
    p = _file(tmp_path, "instances:\n  qbit: { type: qbittorrent, url: http://h, "
                        "username: u, password: ${QBIT_PASS} }\n")
    cfg = load_settings(p, {"QBIT_PASS": secret})
    assert cfg.instances["qbit"].password == secret


def test_yaml_syntax_error_is_config_error_without_secret(tmp_path):
    p = _file(tmp_path, "instances:\n  sonarr: { type: sonarr, url: http://h, api_key: ${K}\n")
    with pytest.raises(ConfigError) as e:
        load_settings(p, {"K": KEY})
    assert KEY not in str(e.value)


def test_kubernetes_service_link_variables_are_ignored():
    sections, inst = parse_env({
        "ORACLARR_SERVICE_HOST": "10.0.0.1", "ORACLARR_SERVICE_PORT": "7979",
        "ORACLARR_SERVICE_PORT_HTTP": "7979", "ORACLARR_PORT": "tcp://10.0.0.1:7979",
        "ORACLARR_PORT_7979_TCP": "tcp://10.0.0.1:7979",
        "ORACLARR_PORT_7979_TCP_ADDR": "10.0.0.1", "ORACLARR_PORT_7979_TCP_PROTO": "tcp"})
    assert inst == {} and sections == EMPTY


def test_env_matches_file_name_with_underscores_or_case(tmp_path):
    p = _file(tmp_path, "instances:\n"
                        "  sonarr_anime: { type: sonarr, url: http://h:8990 }\n"
                        "  Radarr: { type: radarr, url: http://h:7878 }\n")
    cfg = load_settings(p, {"ORACLARR_SONARR_ANIME_ENABLED": "false",
                            "ORACLARR_RADARR_API_KEY": KEY})
    assert set(cfg.instances) == {"sonarr_anime", "Radarr"}
    assert cfg.instances["sonarr_anime"].enabled is False
    assert cfg.instances["Radarr"].api_key == KEY


def test_file_disabled_placeholder_without_url_still_loads(tmp_path):
    p = _file(tmp_path, "instances:\n"
                        "  sonarr: { type: sonarr, url: http://h }\n"
                        "  spare: { type: radarr, enabled: false }\n"
                        "  blank: { type: tdarr, url: '' }\n")
    cfg = load_settings(p, {})
    assert cfg.instances["spare"].enabled is False
    assert cfg.instances["blank"].url == ""


def test_verify_tls_suffix_parses_boolean():
    _, inst = parse_env({"ORACLARR_TRUENAS_URL": "https://h", "ORACLARR_TRUENAS_VERIFY_TLS": "false"})
    assert inst["truenas"] == {"url": "https://h", "verify_tls": False}


def test_bad_verify_tls_names_variable_without_value():
    with pytest.raises(ConfigError) as e:
        parse_env({"ORACLARR_TRUENAS_VERIFY_TLS": KEY})
    assert "ORACLARR_TRUENAS_VERIFY_TLS" in str(e.value) and KEY not in str(e.value)


def test_netdata_and_truenas_types_inferred():
    cfg = load_settings(None, {"ORACLARR_NETDATA_URL": "http://h:20999",
                               "ORACLARR_TRUENAS_URL": "https://h",
                               "ORACLARR_TRUENAS_API_KEY": KEY})
    assert cfg.instances["netdata"].type == "netdata"
    assert cfg.instances["truenas"].type == "truenas"
    assert cfg.instances["truenas"].verify_tls is True


def test_truenas_requires_https():
    with pytest.raises(ConfigError) as e:
        load_settings(None, {"ORACLARR_TRUENAS_URL": "http://h", "ORACLARR_TRUENAS_API_KEY": KEY})
    msg = str(e.value)
    assert "ORACLARR_TRUENAS_URL" in msg and "https://" in msg and KEY not in msg


def test_docker_type_inferred_without_key():
    cfg = load_settings(None, {"ORACLARR_DOCKER_URL": "http://docker-proxy:2375"})
    inst = cfg.instances["docker"]
    assert inst.type == "docker" and inst.url == "http://docker-proxy:2375"
    assert inst.api_key is None


TOKEN = "t" * 24


def test_http_token_and_instance_allow_writes_from_env():
    cfg = load_settings(None, {"ORACLARR_HTTP_TOKEN": TOKEN, "ORACLARR_ALLOW_WRITES": "true",
                               "ORACLARR_SONARR_URL": "http://h:8989",
                               "ORACLARR_SONARR_API_KEY": KEY,
                               "ORACLARR_SONARR_ALLOW_WRITES": "true",
                               "ORACLARR_RADARR_URL": "http://h:7878",
                               "ORACLARR_RADARR_API_KEY": KEY})
    assert cfg.server.http_token == TOKEN and cfg.server.allow_writes is True
    assert cfg.instances["sonarr"].allow_writes is True
    assert cfg.instances["radarr"].allow_writes is False


def test_short_http_token_is_rejected_without_echo():
    with pytest.raises(ConfigError) as e:
        load_settings(None, {"ORACLARR_HTTP_TOKEN": "short-secret"})
    assert "short-secret" not in str(e.value) and "24" in str(e.value)


def test_instance_allow_writes_must_be_boolean():
    with pytest.raises(ConfigError) as e:
        load_settings(None, {"ORACLARR_SONARR_URL": "http://h", "ORACLARR_SONARR_API_KEY": KEY,
                             "ORACLARR_SONARR_ALLOW_WRITES": "maybe"})
    assert "ORACLARR_SONARR_ALLOW_WRITES" in str(e.value)


def test_read_only_field_is_gone():
    assert "read_only" not in Instance.model_fields
