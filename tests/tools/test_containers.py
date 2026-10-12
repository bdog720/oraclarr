import json
from pathlib import Path

import pytest

from oraclarr_mcp.tools.containers import (MATCH_WINDOW, MAX_LIMIT, MAX_LINE_BYTES, MAX_LINES,
                                           container_counts, container_row,
                                           find_container, get_containers, parse_since)

FX = Path(__file__).parent.parent / "fixtures"
LISTING = json.loads((FX / "docker_containers.json").read_text(encoding="utf-8"))
INSPECT = {n: json.loads((FX / f"docker_inspect_{n}.json").read_text(encoding="utf-8"))
           for n in ("gluetun", "qbittorrent", "diskusage", "sonarr")}
ZERO = "0001-01-01T00:00:00Z"


def _listing(name):
    return next(x for x in LISTING if x["Names"] == [f"/{name}"])


def _slim(x):
    from oraclarr_mcp.clients.docker import slim_listing
    return slim_listing(x)


def _inspect(name, **state):
    import copy
    from oraclarr_mcp.clients.docker import slim_inspect
    d = slim_inspect(copy.deepcopy(INSPECT[name]))  # tests mutate nested dicts
    d["State"] = {**d["State"], **state}
    return d


class FakeDocker:
    name = "docker"; type = "docker"

    def __init__(self, listing=None, inspects=None):
        self.listing = [_slim(x) for x in (listing if listing is not None else LISTING)]
        by_name = {f"/{n}": d for n, d in (inspects or {}).items()}
        self.inspects = {x["Id"]: by_name.get(x["Names"][0]) for x in self.listing}

    async def containers(self):
        return self.listing

    async def inspect(self, cid):
        return self.inspects.get(cid)

    async def inspect_many(self, ids):
        return [self.inspects.get(i) for i in ids]


def _default_inspects():
    return {n: _inspect(n) for n in INSPECT}


def test_row_projects_running_container_with_inspect():
    row = container_row(_slim(_listing("gluetun")), _inspect("gluetun"))
    assert row["name"] == "gluetun" and row["stack"] == "download"
    assert row["service"] == "gluetun" and row["state"] == "running"
    assert row["health"] == "healthy" and row["restart_count"] == 0
    assert row["exit_code"] is None and row["oom_killed"] is False
    assert row["started_at"] == "2026-10-09T18:45:13Z"
    assert row["finished_at"] == "2026-10-09T11:46:40Z"
    assert row["ports"] == [8080] and "@" not in row["image"]
    assert row["problem"] is False


def test_row_without_inspect_parses_health_and_exit_from_status():
    x = dict(_slim(_listing("sonarr")), State="exited", Status="Exited (255) 3 hours ago")
    row = container_row(x, None)
    assert row["restart_count"] is None and row["exit_code"] == 255
    assert row["problem"] is True
    y = dict(_slim(_listing("prowlarr")), Status="Up 2 minutes (health: starting)")
    assert container_row(y, None)["health"] == "starting"


def test_row_created_container_has_null_times():
    row = container_row(_slim(_listing("diskusage")), _inspect("diskusage"))
    assert row["state"] == "created" and row["started_at"] is None
    assert row["finished_at"] is None and row["problem"] is False


def test_row_strips_image_digest():
    x = dict(_slim(_listing("sonarr")), Image="lscr.io/x/sonarr:latest@sha256:" + "ab" * 32)
    assert container_row(x, None)["image"] == "lscr.io/x/sonarr:latest"


def test_problem_rules():
    base = _slim(_listing("sonarr"))
    cases = [
        (dict(base, State="running", Status="Up 1 hour (unhealthy)"), None, True),
        (dict(base, State="restarting", Status="Restarting (1) 5 seconds ago"), None, True),
        (dict(base, State="dead", Status="Dead"), None, True),
        (dict(base, State="exited", Status="Exited (0) 1 hour ago"), None, False),
        (base, _inspect("sonarr", OOMKilled=True), True),
    ]
    for x, d, expected in cases:
        assert container_row(x, d)["problem"] is expected, x["Status"]


def test_counts_cover_states_unhealthy_and_problems():
    rows = [container_row(_slim(x), None) for x in LISTING]
    c = container_counts(rows)
    assert c["running"] == 23 and c["created"] == 1 and c["unhealthy"] == 0
    assert c["problems"] == 0
    assert "problems" not in container_counts(rows, with_problems=False)


def test_find_by_name_then_service_case_insensitive():
    listing = [_slim(x) for x in LISTING]
    row, err = find_container(listing, "SONARR")
    assert err is None and row["Names"] == ["/sonarr"]
    row, err = find_container(listing, "stackmgr")  # compose service of stacks-stackmgr-1
    assert err is None and row["Names"] == ["/stacks-stackmgr-1"]


def test_find_prefers_container_name_over_service():
    listing = [_slim(_listing("sonarr")), _slim(_listing("radarr"))]
    listing[1] = dict(listing[1], Labels={**listing[1]["Labels"],
                                          "com.docker.compose.service": "sonarr"})
    row, _ = find_container(listing, "sonarr")
    assert row["Names"] == ["/sonarr"]


def test_find_not_found_has_suggestions():
    row, err = find_container([_slim(x) for x in LISTING], "sonar")
    assert row is None and err["error"] == "not_found" and "sonarr" in err["suggestions"]


async def test_summary_sorts_problems_first_and_counts():
    listing = [dict(x) for x in LISTING]
    i = next(k for k, x in enumerate(listing) if x["Names"] == ["/radarr"])
    listing[i] = dict(listing[i], State="exited", Status="Exited (255) 2 hours ago")
    out = await get_containers({"docker": FakeDocker(listing, _default_inspects())})
    data = out[0]["data"]
    assert out[0]["status"] == "ok" and data["containers"][0]["name"] == "radarr"
    assert data["counts"]["problems"] == 1 and data["counts"]["exited"] == 1
    names = [r["name"] for r in data["containers"][1:]]
    assert names == sorted(names)


async def test_summary_is_bounded():
    out = await get_containers({"docker": FakeDocker()}, limit=5)
    assert len(out[0]["data"]["containers"]) == 5
    assert out[0]["total"] == 24 and out[0]["truncated"] is True
    out = await get_containers({"docker": FakeDocker()}, limit=10**6)
    assert len(out[0]["data"]["containers"]) == min(24, MAX_LIMIT)


async def test_detail_adds_health_policy_and_resolved_network():
    inspects = _default_inspects()
    inspects["qbittorrent"]["State"]["Health"]["Log"][-1]["Output"] = "x" * 1000
    out = await get_containers({"docker": FakeDocker(None, inspects)}, name="qbittorrent")
    d = out[0]["data"]
    assert d["name"] == "qbittorrent" and d["network"] == "container:gluetun"
    assert d["restart_policy"] == "unless-stopped"
    assert d["health_detail"]["status"] == "healthy"
    assert len(d["health_detail"]["last_output"]) == 300


async def test_network_unknown_target_hides_id():
    inspects = _default_inspects()
    inspects["qbittorrent"]["HostConfig"]["NetworkMode"] = "container:" + "ee" * 32
    out = await get_containers({"docker": FakeDocker(None, inspects)}, name="qbittorrent")
    assert out[0]["data"]["network"] == "container:unknown"
    assert "ee" * 32 not in json.dumps(out)


async def test_detail_for_vanished_container_is_not_found():
    out = await get_containers({"docker": FakeDocker(None, {})}, name="sonarr")
    assert out[0]["data"]["error"] == "not_found"


async def test_invalid_section_and_name_required():
    assert (await get_containers({}, section="bogus"))["error"] == "invalid_section"
    assert (await get_containers({}, section="logs"))["error"] == "name_required"


async def test_only_docker_instances_are_used():
    class Other:
        name = "sonarr"; type = "sonarr"
    out = await get_containers({"docker": FakeDocker(), "sonarr": Other()})
    assert [r["instance"] for r in out] == ["docker"]


async def test_no_canary_reaches_output():
    canary = "ENV-CANARY-SECRET"
    from oraclarr_mcp.clients.docker import slim_inspect, slim_listing
    raw = dict(INSPECT["sonarr"], Mounts=[{"Source": canary}], Args=[canary])
    raw["Config"] = {**raw["Config"], "Env": [f"K={canary}"], "Labels": {"x": canary}}
    listing = [dict(_listing("sonarr"), Mounts=[{"Source": canary}], Labels={"x": canary})]
    fake = FakeDocker([])
    fake.listing = [slim_listing(x) for x in listing]
    fake.inspects = {fake.listing[0]["Id"]: slim_inspect(raw)}
    for kwargs in ({}, {"name": "sonarr"}):
        assert canary not in json.dumps(await get_containers({"docker": fake}, **kwargs))


def _frame(stream: int, payload: bytes) -> bytes:
    return bytes([stream, 0, 0, 0]) + len(payload).to_bytes(4, "big") + payload


def _log_bytes(lines):
    return b"".join(_frame(s, f"2026-10-12T06:00:{i % 60:02d}.123456789Z {t}\n".encode())
                    for i, (s, t) in enumerate(lines))


class FakeLogs(FakeDocker):
    def __init__(self, raw, tty=False):
        super().__init__(None, _default_inspects())
        self.raw = raw
        self.calls = []
        for d in self.inspects.values():
            if d:
                d["Config"]["Tty"] = tty

    async def logs(self, cid, tail, since=None):
        self.calls.append({"tail": tail, "since": since})
        return self.raw


def test_parse_since_relative_and_iso():
    now = 1_000_000.0
    assert parse_since("15m", now) == 1_000_000 - 900
    assert parse_since("2h", now) == 1_000_000 - 7200
    assert parse_since("1d", now) == 1_000_000 - 86400
    assert parse_since("2026-10-12T06:00:00Z", now) == 1791784800
    assert parse_since("2026-10-12T06:00:00", now) == 1791784800  # naive = UTC
    for bad in ("yesterday", "15x", ""):
        with pytest.raises(ValueError):
            parse_since(bad, now)


async def test_logs_tail_parses_time_stream_and_text():
    fake = FakeLogs(_log_bytes([(1, "Starting Sonarr"), (2, "Warn: slow disk")]))
    out = await get_containers({"docker": fake}, name="sonarr", section="logs", lines=10)
    d = out[0]["data"]
    assert d["container"] == "sonarr" and fake.calls == [{"tail": 10, "since": None}]
    assert d["lines"] == [
        {"t": "2026-10-12T06:00:00Z", "stream": "stdout", "text": "Starting Sonarr"},
        {"t": "2026-10-12T06:00:01Z", "stream": "stderr", "text": "Warn: slow disk"}]
    assert d["truncated"] is False and "matched_of" not in d


async def test_logs_truncated_when_tail_is_full():
    fake = FakeLogs(_log_bytes([(1, f"line {i}") for i in range(5)]))
    out = await get_containers({"docker": fake}, name="sonarr", section="logs", lines=5)
    assert out[0]["data"]["truncated"] is True


async def test_logs_since_is_passed_as_unix_time():
    fake = FakeLogs(b"")
    await get_containers({"docker": fake}, name="sonarr", section="logs",
                         since="2026-10-12T06:00:00Z")
    assert fake.calls[0]["since"] == 1791784800


async def test_logs_invalid_since():
    out = await get_containers({"docker": FakeLogs(b"")}, name="sonarr", section="logs",
                               since="yesterday")
    assert out["error"] == "invalid_since"


async def test_logs_match_filters_a_wider_window():
    lines = [(1, f"info {i}") for i in range(10)] + [(2, "ERROR one"), (1, "x"),
                                                     (2, "error two"), (2, "Error three")]
    fake = FakeLogs(_log_bytes(lines))
    out = await get_containers({"docker": fake}, name="sonarr", section="logs", lines=2,
                               match="error")
    d = out[0]["data"]
    assert fake.calls[0]["tail"] == MATCH_WINDOW
    assert [r["text"] for r in d["lines"]] == ["error two", "Error three"]
    assert d["matched_of"] == 3 and d["truncated"] is True


async def test_logs_match_ignores_timestamp_prefix():
    fake = FakeLogs(_log_bytes([(1, "plain")]))
    out = await get_containers({"docker": fake}, name="sonarr", section="logs", match="2026")
    assert out[0]["data"]["lines"] == []


async def test_logs_tty_container():
    fake = FakeLogs(b"2026-10-12T06:00:00.1Z tty line\n", tty=True)
    out = await get_containers({"docker": fake}, name="sonarr", section="logs")
    assert out[0]["data"]["lines"][0]["text"] == "tty line"


async def test_logs_lines_clamped():
    fake = FakeLogs(b"")
    await get_containers({"docker": fake}, name="sonarr", section="logs", lines=10**6)
    assert fake.calls[0]["tail"] == MAX_LINES


async def test_logs_strip_ansi_and_cap_escaped_size():
    fake = FakeLogs(_log_bytes([(1, "\x1b[32mINFO\x1b[0m ready"), (1, "─" * 1000),
                                (1, "\U0001F600" * 1000)]))
    out = await get_containers({"docker": fake}, name="sonarr", section="logs")
    texts = [r["text"] for r in out[0]["data"]["lines"]]
    assert texts[0] == "INFO ready"
    assert all(len(json.dumps(t)) <= MAX_LINE_BYTES for t in texts)


async def test_logs_unknown_container_is_not_found():
    out = await get_containers({"docker": FakeLogs(b"")}, name="nope", section="logs")
    assert out[0]["data"]["error"] == "not_found"


SECRET = "0123456789abcdef0123456789abcdef"


def _guarded_tool():
    from oraclarr_mcp.call_guard import guarded
    from oraclarr_mcp.redact import Redactor
    return guarded("get_containers", get_containers, budget_s=5, max_bytes=200_000,
                   redactor=Redactor([SECRET]))


async def test_logs_redact_secrets_before_cutting():
    fake = FakeLogs(_log_bytes([(1, "x" * 380 + " " + SECRET)]))
    out = await _guarded_tool()(clients={"docker": fake}, name="sonarr", section="logs")
    assert SECRET[:8] not in json.dumps(out)


async def test_logs_match_runs_on_redacted_text():
    fake = FakeLogs(_log_bytes([(1, "API_KEY=" + SECRET), (1, "plain " + SECRET)]))
    out = await _guarded_tool()(clients={"docker": fake}, name="sonarr", section="logs",
                                match=SECRET[:6])
    assert out[0]["data"]["matched_of"] == 0


async def test_health_output_redacted_before_cutting():
    inspects = _default_inspects()
    inspects["qbittorrent"]["State"]["Health"]["Log"][-1]["Output"] = "y" * 290 + SECRET
    out = await _guarded_tool()(clients={"docker": FakeDocker(None, inspects)},
                                name="qbittorrent")
    assert SECRET[:8] not in json.dumps(out)
