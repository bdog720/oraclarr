# Oraclarr

Read-only-by-default diagnostic MCP server (Python/FastMCP) for a self-hosted arr media
stack. Answers operational "why" questions by aggregating across services.
Phased toward full read+write coverage. Reads are the default; writes are opt-in
through one gated tool, `start_job` (since 2.0.0).

## Architecture

Layered. **Clients talk to services; tools answer questions.** Keep the boundary
clean: a tool composes clients, never embeds HTTP/auth detail.

```
config.py    ORACLARR_* env (parse_env) over optional YAML -> typed Config (load_settings)
registry.py  instance.type -> client class; build_clients(cfg)
clients/     async adapters: base, arr, prowlarr, qbittorrent, tdarr, profilarr, jellyfin, cleanuparr,
             netdata (httpx), truenas (JSON-RPC over WebSocket),
             docker (httpx, read-only socket proxy). Clients are read-only; the only writes are
             the command/scan POSTs that `start_job` sends through the plan flow
tools/       outcome tools; each composes clients via fan_out/probe
guards.py    per-tool risk+domain tags; toolset filter; write gate
auth.py      HTTP bearer-token check (ORACLARR_HTTP_TOKEN); startup refuses writes on http without it
plans.py     in-memory single-use plans (10 min) for the two-step write flow
audit.py     `audit event=<planned|executed|refused|failed|unknown>` log lines for every write event
tools/jobs_write.py  start_job: dry-run builds a plan, execute rebuilds it and compares fingerprints
budget.py    per-call deadline ContextVar; probe() reads it (partial results on timeout)
redact.py    Redactor (config secrets + key patterns) + log record-factory redaction
call_guard.py guarded(): deadline, backstop (budget+2s), output cap, redaction, Any return
server.py    FastMCP app; registers only tools whose domain is in cfg.server.toolsets
models.py    InstanceResult envelope; MediaRef (carries tvdb/tmdb/imdb ids)
```

v1 services: `sonarr`, `sonarr-anime`, `radarr`, `sportarr`, `prowlarr`, `qbit`,
`tdarr`, `profilarr`, `jellyfin`, `cleanuparr`, `netdata`, `truenas`, `docker`. Tools: `stack_health`, `get_queues`, `diagnose`,
`explain_decision`, `get_quality_config`, `get_history`, `get_wanted`,
`search_media`, `get_indexers`, `get_transcodes`, `get_upcoming`, `get_library`, `get_cleanup`, `get_host` (toolset `host`), `get_containers`
(toolset `containers`), `get_jobs`, `start_job` (the only write tool; registered only when writes are enabled).

## Invariants (do not violate)

1. **READ-ONLY BY DEFAULT.** Writes go only through the gate: ORACLARR_ALLOW_WRITES and the
   instance's _ALLOW_WRITES, a bearer token on the http transport, and a plan_id from a dry
   run. Only start_job writes. Never add a write that skips the plan flow. Outside
   start_job, no POST/PUT/DELETE that mutates a service. (qbit login + tdarr cruddb *reads*
   are the only other POSTs.)
2. **Few, outcome-oriented tools.** Do not add one-per-endpoint tools. New need
   = extend an existing tool or add one cross-service tool.
3. **Never hard-fail a tool because one service is down.** All fan-out goes
   through `probe`/`fan_out`; a dead instance returns a status envelope, peers
   still return data.
4. **Every tool declares `risk` + `domain`; models carry external IDs.** These
   are the seams for write-safety and cross-service joins in later phases.

## Add-a-service recipe

1. Add `type` to `INSTANCE_TYPES` + `Instance.type` literal in `config.py`.
2. New `clients/<svc>.py` subclassing `BaseClient` (pick/extend an auth strategy).
3. Route it in `registry.py::_make`.
4. Extend the relevant tool(s) or add one. A new tool is three edits in `server.py`: the
   import, a `TOOL_SPECS` entry (`risk`+`domain`), and an `@tool` wrapper named
   `_<tool_name>`. The spec list and the wrappers must match or `build_server` raises.
5. Fixture + tests first (TDD). Capture a real payload, then scrub it as
   "Public repo hygiene" says before it goes into `tests/fixtures/`.

## Workflow

- **TDD is mandatory.** Test order: write failing test → confirm fail → minimal
  impl → confirm pass → commit.
- Frequent small commits, one behavior each.
- Secrets via env (`.env`, gitignored) referenced as `${VAR}` in `config.yaml`.
  `config.yaml` is gitignored; only `*.example` files are committed.

## Commands

```bash
uv sync                                   # install
uv run pytest -v                          # tests
uv run ruff check .                       # lint
ORACLARR_CONFIG=config.yaml uv run python -m oraclarr_mcp   # run (stdio)
```

- Docker (HTTP service): `docker compose up -d` → MCP at `http://host:7979/mcp`.
  `ORACLARR_TRANSPORT=http` (image default) vs `stdio` (code default).
- Release: push a `v*` tag → CI publishes the GHCR image **and** the PyPI package
  (`oraclarr-mcp`, Trusted Publishing/OIDC) + MCP Registry entry
  (`io.github.bdog720/oraclarr`, via `server.json`). Keep `pyproject.toml` `version`
  and the tag in lockstep — the publish workflow fails on mismatch. The PyPI README
  carries the registry ownership marker (`<!-- mcp-name: io.github.bdog720/oraclarr -->`).

## Gotchas

- **qBittorrent**: cookie auth — `POST /api/v2/auth/login` sets SID; re-login
  once on 403. Join to arr queue is `downloadId` (arr) ↔ `hash` (qbit),
  case-insensitive.
- **Tdarr**: non-standard API (`/api/v2/status`, `/api/v2/get-nodes`, queue via
  `POST /api/v2/cruddb`). Confirm payload shapes against the live instance.
- **Profilarr**: REST API confirmed live (v2.0.x, SvelteKit rewrite). Base path
  `/api/v1/`. Profiles/custom-formats are **not** per-arr — sync state is a single
  `/api/v1/status` (databases[] counts + arrs[] sync + drift); `/api/v1/arr` lists
  instances. `POST /api/v1/databases/{id}/sync` exists but is a write — never call (v1).
- **Sportarr**: serves a full Sonarr-compatible `/api/v3` (its `system/status`
  reports `appName: "Sonarr"`, `instanceName: "Sportarr"`), so it routes to
  `ArrClient` with no subclass. League = series, game = episode, season = year.
  Its native `/api/v1` has only `system/status`; every other `/api/v1` path
  returns the SPA `index.html`. `/api/health` and `/ping` need no key. Never fan
  out `/api/v3/episode` — one league is 2.3 MB. Its `/api/v3/qualityprofile` drops
  `formatItems` and both format-score fields: `ArrClient.quality_profiles` reads the
  unversioned `/api/qualityprofile` (`formatId`, `format: null`, `upgradesAllowed`,
  `cutoffQuality`) and maps it to the v3 shape.
- **Arr-family types** live in one constant, `models.ARR_TYPES`. Adding a new
  one without updating it drops the instance from a tool *silently*, with no
  error. `tests/tools/test_arr_selection.py` guards all four selectors.
- **`get_upcoming`**: Radarr calendar records carry up to four release dates and
  no `airDate`. Report the date inside the requested window, not the first one
  present, or past dates appear in an "upcoming" list.
- **Several instances of one type** (for example, two Sonarr instances for TV and
  anime) are expected; routing is by `type`, so same-type duplicates need no
  special-casing.
- `explain_decision` uses `customFormatScore`, `formatItems`, `cutoffFormatScore`,
  and grab history `customFormats` — all confirmed live. Grab history is fetched
  **per item** via `/api/v3/history/{series|movie}?{seriesId|movieId}=` (plain
  list), **not** the global `/api/v3/history` window — that window rarely contains
  a given title's grabs, so it returned empty. Use `ArrClient.item_history`.

- **Every tool is wrapped by `call_guard.guarded()`**. Per-instance work must go
  through `probe`/`fan_out` to get the deadline; a bare `await` in a tool only has
  the backstop. Bounded lists return `Bounded`/`bounded()` so `probe` sets
  `total`/`truncated` on the envelope. Registered functions return `Any` on
  purpose: a typed return builds a FastMCP output schema that rejects the
  `tool_timeout`/`output_too_large` error objects.
- **Projections**: tools return compact snake_case fields, never raw arr objects.
  A new tool needs a projection and a `limit` (clamped via `clamp`).
- **Max limits are sized to fit the 200 KB cap** with four arr instances at the
  largest observed row size: history 80, search 100, wanted 200, upcoming 200,
  queues 400 (total, not per instance; worst row 448 B with qbit + Cleanuparr join). `tests/tools/test_limit_budget.py` pins
  this; if a projection grows, lower the max rather than raise the cap.

- **Jellyfin (tested on 12.2)**: auth is `Authorization: MediaBrowser Token="<key>"` only;
  `X-Emby-Token` returns 401. `/Items` works with the API key and no `userId`.
  `/Items` has no path filter, so `get_library` searches by name; paths come from
  arr `search_media`. `diagnose` joins Jellyfin by provider id (tvdb/tmdb/imdb,
  strings in `ProviderIds`), never by name; arr id `0` means unknown and is skipped.
  `get_library` registers only with the `library` toolset. Library `items` counts
  are recursive (series + seasons + episodes). The library scan (`POST /Library/Refresh`)
  is a write: send it only through `start_job`'s plan flow, never from another tool.

- **Config sources**: `load_settings(path, env)` reads the optional `config.yaml`, then
  overlays `ORACLARR_<NAME>_<FIELD>` variables field by field (env wins). Suffixes are
  matched longest first; names map `_` -> `-`. `ORACLARR_TRANSPORT/HTTP_HOST/HTTP_PORT/
  CONFIG` are reserved. Any other unknown `ORACLARR_*` variable is a startup error, so
  a new setting needs an entry in `_SERVER_ENV` or `_FIELDS`. Error messages must never
  echo a value; the models use `hide_input_in_errors=True` for the same reason.
- **Add-a-service recipe, step 1** also means: the new type is inferred from an
  `ORACLARR_<TYPE>_URL` name automatically (via `INSTANCE_TYPES`); add its example
  lines to `.env.example`.

- **Cleanuparr**: built-in accounts; oraclarr uses the account API key as `X-Api-Key`.
  Its config endpoints return the download client's host/username/password and an
  `auth` block, so every `tools/cleanup.py` projection is an allowlist. Never call
  `/api/jobs/{id}/start|trigger` (writes), `/api/configuration/notification_providers`,
  `/api/configuration/{arr}/instances` or `/api/account/*` (secrets). Strike
  `downloadId` is the torrent hash; `get_queues` joins it case-insensitively and
  reports `cleanuparr: null` when the 500-row strike page was truncated and nothing
  matched, or when any Cleanuparr failed. Job `status` is `Scheduled`, `Running` or
  `Not Scheduled` (no failure state).

- **TrueNAS (tested on 25.10)**: REST `/api/v2.0` returns 403 for API keys; use JSON-RPC 2.0 over
  `wss://…/api/current` (`TruenasClient`, `websockets`): login per batch with
  `auth.login_with_api_key`. **https only** — TrueNAS revokes a key sent over http;
  config rejects `http://`. Error replies carry `data.trace` with server locals: keep
  `message`/`reason` only. `system.info` has the serial/hostname (its `version` is
  a bare number such as `25.10.x`, no `TrueNAS-` prefix) and `disktemp` identifiers carry disk serials —
  allowlist. Reporting lacks iowait, MemFree, ARC c_max, swap and GPU (hence Netdata).
  `reporting.netdata_get_data` valid names differ from `netdata_graphs` (`processes`
  raises); `disktemp` needs one identifier per disk.
  Use `summary()` (one login) for system/pools/alerts; never let websockets log at DEBUG
  (frame repr keeps the key's tail).
- **Netdata**: a separate container (TrueNAS's own Netdata is localhost-only), v2
  `/api/v2/data?contexts=…&format=json2`; labels are `<dim>,<chart>@<node>` and carry the
  GPU UUID/node GUID — never emit them. A missing context is 200 with no data.
- **Docker (proxy)**: `wollomatic/socket-proxy` allowlist, regex matched on the path only;
  POST/PUT/DELETE → 405, other paths → 403 (`DockerProxyRefused` → `auth_failed`).
  Portainer CE was rejected: non-admin users do not see containers that another tool
  created, and admin tokens can exec. `DockerClient` slims list/inspect to an allowlist *before* caching (inspect
  `Config.Env` holds every service's secrets). A running container's `ExitCode` is 0;
  `FinishedAt` keeps the last stop. `/events` is useless for exit history (256-event
  buffer flooded by health-check execs). Logs are 8-byte-header frames unless
  `Config.Tty`. A container on another container's network (`network_mode: container:<vpn>`,
  for example a download client behind a VPN container) publishes no ports; the
  `stack_health` join reports both containers for that port. Log lines are cut by
  JSON-escaped size (`MAX_LINE_BYTES`), not chars: emoji/ANSI expand up to 12x.
  Errors name `/containers/<id>/…`, never the ID. Log text is redacted *before* `match`
  and the cut (`redact.scrub_text`; `guarded` sets the active redactor). The join matches
  URL hostname → container name/service, then explicit port; never implicit 80/443.
- **Arr commands (`get_jobs`)**: `GET /api/v3/command` keeps finished commands for minutes
  only (no history); `RefreshMonitoredDownloads`/`ProcessMonitoredDownloads` run every
  60–90 s and are hidden as routine. `message` is absent unless set. Bodies carry ids
  (`seriesIds`, `movieIds`, `episodeIds`, `files`): titles come from `/series|movie/{id}`,
  first 5, cached 5 min, 5 s title budget. Sportarr serves its SPA for `/command` and
  `/system/task`: never request them (note instead). `limit` caps total rows per
  instance (active → failed → recent). Starting a command is a write: only `start_job`'s plan flow may do it.
- **Writes (`start_job`)**: plans are in memory (restart drops them), single use, 10 min;
  the execute path rebuilds the plan and compares fingerprints (rename = hash of the arr's
  rename preview). Never retry a write: a send timeout is `outcome: unknown`. Sportarr has
  no command API. `/api/v3/rename` returns `[]` when nothing changes; its row keys were not
  seen live at design time (code uses `.get`). The HTTP token guards the whole endpoint;
  `ORACLARR_ALLOW_WRITES` on http without it is a startup error.

## Public repo hygiene

This repository, its git history and the PyPI sdist are public. Nothing in them may
identify the maintainer or describe a real installation.

- Fixtures come from live captures, so scrub every capture before you commit it.
  Replace hosts and IPs (use `192.0.2.x` or `host`), serials, UUIDs, GUIDs, item ids,
  usernames, emails, timezones and UTC offsets, country codes, hardware models, pool
  and dataset names, container names and images that are not Oraclarr services, plugin
  names, and library paths.
- Media titles, release names, release groups, leagues and games must be invented. A
  real title shows what the maintainer watches; a real release name ties them to a
  specific torrent.
- Test canaries only: never paste a real serial, UUID or key from a probe into a test.
- Commit with the GitHub noreply email, not a personal address.

## Docs

- User guides (public): `docs/*.md` (connect, host-metrics, containers, writes, config-file,
  upgrading). The README links them with absolute GitHub URLs because it is also the PyPI
  page. Version-pinned notes go in `docs/upgrading.md`, not the README.
- Design specs and plans are local-only (`docs/superpowers/`, gitignored). A checkout
  may not have them.
- Roadmap: Phase 1 read-only (this) → Phase 2 read expansion (Jellyfin, Seerr,
  Gluetun, TrueNAS, Cleanuparr, ntfy) → Phase 3 safe writes (started: `start_job`) → Phase 4 destructive.
