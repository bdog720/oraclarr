import json

from oraclarr_mcp.tools.host import GPU_CONTEXTS, dataset_row, get_host

SERIAL = "SERIAL-CANARY-1"
HOST = "nas-private-host"
GPU_UUID = "ffffffff-ffff-ffff-ffff-ffffffffffff"

NETDATA = {
    "system.cpu": {"user": 1.0, "system": 2.0, "nice": 6.0, "iowait": 0.6, "irq": 0.0,
                   "softirq": 0.1, "steal": 0.0, "guest": 0.0, "guest_nice": 0.0},
    "system.load": {"load1": 2.364, "load5": 2.1, "load15": 1.825},
    "system.io_some_pressure": {"some 10": 1.8, "some 60": 2.9, "some 300": 1.9},
    "system.ram": {"free": 9339.5, "used": 7081.0, "cached": 15599.1, "buffers": 0.0},
    "mem.available": {"avail": 19523.0},
    "mem.swap": {"free": 5677.4, "used": 2514.6},
    "zfs.arc_size": {"arcsz": 12166.9, "target": 12288.0, "min (hard limit)": 1000.6,
                     "max (high water)": 12288.0},
}
GPU = {
    "nvidia_smi.gpu_temperature": [{"temperature": 34}],
    "nvidia_smi.gpu_power_draw": [{"power_draw": 10}],
    "nvidia_smi.gpu_frame_buffer_memory_usage": [{"free": 8161067000, "used": 0,
                                                  "reserved": 429916200}],
    "nvidia_smi.gpu_utilization": [{"gpu": 3}],
    "nvidia_smi.gpu_encoder_utilization": [{"encoder": 0}],
}


class FakeNd:
    name = "netdata"; type = "netdata"

    def __init__(self, gpu=True):
        self.gpu = gpu

    async def latest(self, ctx):
        return NETDATA.get(ctx, {})

    async def latest_by_instance(self, ctx):
        return GPU.get(ctx, []) if self.gpu else []


POOLS = [{"name": "HDDs", "status": "ONLINE", "healthy": True, "size": 11991548690432,
          "allocated": 9562807992320, "free": 2428740698112, "fragmentation": "43",
          "scan": {"function": "SCRUB", "state": "FINISHED", "errors": 0,
                   "end_time": {"$date": 1791082840000}}}]
DATASETS = [
    {"id": "HDDs/configs", "used": {"parsed": 8860423968}, "available": {"parsed": 1480143186768},
     "quota": {"parsed": None}},
    {"id": "HDDs/media", "used": {"parsed": 6000000000000}, "available": {"parsed": 1480143186768},
     "quota": {"parsed": 7000000000000}},
]
ALERTS = [
    {"level": "INFO", "formatted": "App update available", "klass": "AppUpdate",
     "dismissed": False, "datetime": {"$date": 1791744348000}, "args": {"x": SERIAL}},
    {"level": "WARNING", "formatted": "Pool HDDs is 80% full", "klass": "ZpoolCapacity",
     "dismissed": False, "datetime": {"$date": 1791750000000}},
    {"level": "CRITICAL", "formatted": "old", "klass": "X", "dismissed": True,
     "datetime": {"$date": 1700000000000}},
]
DISKS = [{"identifier": f"sda | Type: HDD | Model: ST4000VN006-3CW1 | Serial: {SERIAL}",
          "temp_c": 38}]


class FakeTn:
    name = "truenas"; type = "truenas"

    def __init__(self):
        self.calls = []

    async def system_info(self):
        self.calls.append("system_info")
        return {"version": "25.10.7", "uptime_seconds": 208095.8,
                "system_serial": SERIAL, "hostname": HOST, "model": "AMD Ryzen 7 3700X"}

    async def pools(self):
        return POOLS

    async def datasets(self):
        self.calls.append("datasets")
        return DATASETS

    async def alerts(self):
        return ALERTS

    async def disk_temps(self):
        return DISKS

    async def summary(self):
        return await self.system_info(), await self.pools(), await self.alerts()


async def test_netdata_summary_blocks():
    d = (await get_host({"netdata": FakeNd()}))[0]["data"]
    assert d["cpu"] == {"busy_pct": 9.1, "iowait_pct": 0.6, "load": [2.36, 2.1, 1.82],
                        "io_pressure_pct": 2.9}
    assert d["memory"] == {"total_gib": 31.3, "free_gib": 9.1, "used_gib": 6.9,
                           "cached_gib": 15.2, "available_gib": 19.1}
    assert d["swap"] == {"used_gib": 2.5, "free_gib": 5.5}
    assert d["arc"] == {"size_gib": 11.9, "target_gib": 12.0, "max_gib": 12.0,
                        "min_gib": 1.0, "at_max": True}
    assert d["gpu"] == [{"temp_c": 34, "power_w": 10, "vram_used_gib": 0.0,
                         "vram_free_gib": 7.6, "util_pct": 3, "encoder_pct": 0}]


async def test_gpu_not_available_without_nvidia_contexts():
    d = (await get_host({"netdata": FakeNd(gpu=False)}))[0]["data"]
    assert d["gpu"] == "not_available"
    assert d["cpu"]["iowait_pct"] == 0.6


async def test_truenas_summary_blocks():
    d = (await get_host({"truenas": FakeTn()}))[0]["data"]
    assert d["system"] == {"version": "25.10.7", "uptime_hours": 57.8}
    assert d["pools"] == [{"name": "HDDs", "status": "ONLINE", "healthy": True,
                           "used_pct": 79.7, "free_tib": 2.21, "fragmentation_pct": 43,
                           "last_scrub": {"state": "FINISHED", "errors": 0,
                                          "finished": "2026-10-04T03:00:40Z"}}]
    assert d["alerts"]["counts"] == {"INFO": 1, "WARNING": 1}
    assert [a["level"] for a in d["alerts"]["recent"]] == ["WARNING", "INFO"]
    assert d["alerts"]["recent"][0] == {"level": "WARNING", "text": "Pool HDDs is 80% full",
                                        "since": "2026-10-11T20:20:00Z"}


async def test_datasets_section_sorted_and_bounded():
    row = (await get_host({"truenas": FakeTn()}, section="datasets", limit=1))[0]
    assert row["data"] == [{"name": "HDDs/media", "used_gib": 5587.9, "available_gib": 1378.5,
                            "quota_gib": 6519.3}]
    assert row["total"] == 2 and row["truncated"] is True
    assert dataset_row(DATASETS[0])["quota_gib"] is None


async def test_disks_section_drops_serial():
    d = (await get_host({"truenas": FakeTn()}, section="disks"))[0]["data"]
    assert d == [{"device": "sda", "type": "HDD", "model": "ST4000VN006-3CW1", "temp_c": 38}]


async def test_alerts_section():
    d = (await get_host({"truenas": FakeTn()}, section="alerts"))[0]["data"]
    assert d[0] == {"level": "WARNING", "text": "Pool HDDs is 80% full",
                    "class": "ZpoolCapacity", "since": "2026-10-11T20:20:00Z"}
    assert len(d) == 2


async def test_sections_query_only_truenas():
    out = await get_host({"netdata": FakeNd(), "truenas": FakeTn()}, section="disks")
    assert [r["instance"] for r in out] == ["truenas"]


async def test_no_serial_or_hostname_in_any_output():
    clients = {"netdata": FakeNd(), "truenas": FakeTn()}
    text = json.dumps([await get_host(clients, section=s)
                       for s in (None, "datasets", "disks", "alerts")])
    for private in (SERIAL, HOST, GPU_UUID, "system_serial", "hostname"):
        assert private not in text


async def test_invalid_section_without_upstream_calls():
    tn = FakeTn()
    out = await get_host({"truenas": tn}, section="processes")
    assert out == {"error": "invalid_section", "valid": ["alerts", "datasets", "disks"]}
    assert tn.calls == []


async def test_limit_is_clamped():
    row = (await get_host({"truenas": FakeTn()}, section="datasets", limit=0))[0]
    assert len(row["data"]) == 1


def test_gpu_contexts_constant():
    assert "nvidia_smi.gpu_temperature" in GPU_CONTEXTS


class SparseNd(FakeNd):
    async def latest(self, ctx):
        if ctx == "system.load":
            return {"load1": 1.0}
        if ctx == "system.cpu":
            return {"system": 2.0, "iowait": 0.5}
        return await super().latest(ctx)


async def test_partial_netdata_values_do_not_fail_the_summary():
    row = (await get_host({"netdata": SparseNd()}))[0]
    assert row["status"] == "ok"
    assert row["data"]["cpu"]["load"] == [1.0, None, None]
    assert row["data"]["cpu"]["busy_pct"] == 2.0


class BatchTn(FakeTn):
    async def summary(self):
        self.calls.append("summary")
        return ({"version": "25.10.7", "uptime_seconds": 3600.0}, POOLS, ALERTS)

    async def system_info(self):
        raise AssertionError("summary must use one batch")


async def test_truenas_summary_uses_one_batch():
    tn = BatchTn()
    row = (await get_host({"truenas": tn}))[0]
    assert row["status"] == "ok" and tn.calls == ["summary"]
