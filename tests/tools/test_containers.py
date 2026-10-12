import json
from pathlib import Path

from oraclarr_mcp.tools.containers import (MAX_LIMIT, container_counts, container_row,
                                           find_container, get_containers)

FX = Path(__file__).parent.parent / "fixtures"
LISTING = json.loads((FX / "docker_containers.json").read_text(encoding="utf-8"))
INSPECT = {n: json.loads((FX / f"docker_inspect_{n}.json").read_text(encoding="utf-8"))
           for n in ("gluetun", "qbittorrent", "qdirstat", "sonarr")}
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
    row = container_row(_slim(_listing("qdirstat")), _inspect("qdirstat"))
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
    row, err = find_container(listing, "dockge")  # compose service of ix-dockge-dockge-1
    assert err is None and row["Names"] == ["/ix-dockge-dockge-1"]


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
