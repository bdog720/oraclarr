import pytest

from oraclarr_mcp.config import ConfigError, env_name, parse_env

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
