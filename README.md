<!-- mcp-name: io.github.bdog720/oraclarr -->

<div align="center">

# Oraclarr

**Ask your media stack what's going on, in plain language.**

A locally-run [MCP](https://modelcontextprotocol.io) server that lets an LLM client (Claude Code, Claude Desktop) diagnose a self-hosted *arr media stack. It only reads by default. Writes are opt-in and need a token.

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![MCP](https://img.shields.io/badge/MCP-server-7b3fe4)
![Mode](https://img.shields.io/badge/mode-read--only%20by%20default-orange)
![Status](https://img.shields.io/badge/phase%201-complete-brightgreen)

</div>

---

## What it does

Oraclarr gives a language model one place to answer the operational "why" questions that normally mean tabbing through six web UIs. It aggregates across your services and returns a single, structured answer without changing anything. One opt-in tool, `start_job`, can start a refresh, rescan, search or rename. See [Writes](https://github.com/bdog720/oraclarr/blob/main/docs/writes.md).

Covered now: **Sonarr**, **Radarr**, **Sportarr**, **Prowlarr**, **qBittorrent**, **Tdarr**, **Profilarr**, **Jellyfin**, **Cleanuparr**, **Netdata**, **TrueNAS** and **Docker**, including multiple instances of the same type (a separate anime or 4K Sonarr/Radarr, say). Every tool fans out across all the instances you define and reports each one separately.

## In practice

Once connected, you just ask. Oraclarr picks the right tool and answers:

| You ask… | Oraclarr runs | …and tells you |
|----------|---------------|----------------|
| "Is anything in my stack down?" | `stack_health` | which services are unreachable, unhealthy, or low on disk, and for one that's down, its container's state and exit code |
| "Why hasn't the new episode of *X* downloaded yet?" | `diagnose` | whether *X* is in your library, sitting in the download queue, or still on the wanted list |
| "Why did a sub-only release get grabbed when I only allow English dubs?" | `explain_decision` | the release that was grabbed, its custom-format score, and the language formats that matched |
| "Why is Cleanuparr about to remove this download?" | `get_queues` + `get_cleanup` | the strikes against it and their type, whether it's marked for removal, and the rules that apply |
| "Is the box under I/O pressure, and how much RAM is actually free?" | `get_host` | CPU busy and iowait, I/O pressure, free and available memory, swap, ARC against its max, GPU heat and VRAM |
| "What errors has Sonarr logged today?" | `get_containers` | the matching log lines with timestamps, from the container's logs |
| "Is the Sonarr rename still running?" | `get_jobs` | running and queued commands with their progress and the shows they cover, plus any that failed |

## Tools

Read-only by default, and outcome-oriented rather than one-per-endpoint, which keeps the model accurate. Only `start_job` writes, and only when you switch writes on:

| Tool | Answers |
|------|---------|
| `stack_health` | Is anything down / unhealthy / low on disk? |
| `get_queues` | Unified active downloads (arr queue ↔ qBittorrent), stalls |
| `diagnose` | Where is *X* in the pipeline / why isn't it here yet? |
| `explain_decision` | Why was *X* grabbed or being upgraded? (profile, custom formats, grab history) |
| `get_quality_config` | Quality profiles, custom formats, release profiles, Profilarr sync state |
| `get_history` | Recent grabs / imports / failures |
| `get_wanted` | What's missing / cutoff-unmet? |
| `search_media` | Do I have *X*, what's its status? |
| `get_indexers` | Which indexers are failing? |
| `get_transcodes` | What's transcoding / stuck? |
| `get_upcoming` | What's airing or releasing soon, and will it land? (up to 90 days) |
| `get_library` | Jellyfin libraries, scan progress, tasks, playback and transcodes, recent additions, name search |
| `get_cleanup` | Cleanuparr dry-run state, cleaner schedules, seeding and stall rules, strikes |
| `get_host` | Host CPU/iowait, memory, swap, ARC, GPU, pools, datasets, disk temperatures, TrueNAS alerts |
| `get_containers` | Docker containers: state, health, restart counts, exit codes, and a filtered log tail |
| `get_jobs` | What the arrs and Jellyfin are running, queued, failed or scheduled |
| `start_job` | Start a refresh, rescan, search or rename on one series or movie, or a Jellyfin scan (opt-in, two-step) |

## Install

Two ways to run it. Pick one:

- **🐳 Docker (recommended).** A small always-on container next to your arr stack. Works with Dockge, Portainer, Unraid and plain `docker compose`.
- **🐍 Python (uv).** Runs directly on your machine with no container. Handy for local development, or if you don't use Docker.

Either way, every setting is an environment variable that starts with `ORACLARR_`. With Docker that means one `.env` file next to the compose file, and Dockge and Portainer show both in their editors. Start from [`.env.example`](https://github.com/bdog720/oraclarr/blob/main/.env.example). [Configuration](#configuration) lists every variable. Your `.env` is never committed.

### Option A: Docker (recommended)

Oraclarr runs as a long-running container that serves MCP over HTTP at `http://<host>:7979/mcp`. You need two files in one folder: `docker-compose.yml` and `.env`.

**Using a stack manager (Dockge, Portainer, etc.):** create a new stack, paste the compose below into the editor, and paste your settings into the stack's `.env`. Hit deploy. Portainer saves the variables from its web editor as `stack.env`, so in Portainer change the compose line to `env_file: stack.env`.

**Using the command line:**

```bash
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env    # then fill in your URLs and keys
docker compose up -d
```

This is the whole compose file. You don't edit it when you add or remove a service; that happens in `.env`:

```yaml
services:
  oraclarr:
    image: ghcr.io/bdog720/oraclarr-mcp:latest
    container_name: oraclarr
    restart: unless-stopped
    ports:
      - "7979:7979"           # left side is the host port; change it if 7979 is taken
    env_file: .env
```

Want container state and logs too (`get_containers`)? Use [`docker-compose.full.example.yml`](https://github.com/bdog720/oraclarr/blob/main/docker-compose.full.example.yml) instead. It adds the read-only Docker socket proxy, the one sidecar that has to live in the same stack. [Containers](https://github.com/bdog720/oraclarr/blob/main/docs/containers.md) explains it.

Then [connect your client](https://github.com/bdog720/oraclarr/blob/main/docs/connect.md): one command for Claude Code, a small JSON block for Claude Desktop, Cursor, Codex, VS Code, Gemini CLI or Windsurf.

### Option B: Python (uv)

Run Oraclarr directly, no Docker. Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

The package is on PyPI as [`oraclarr-mcp`](https://pypi.org/project/oraclarr-mcp/). It speaks MCP over **stdio**, so your client starts the process and passes the settings in its `env` block:

```json
"oraclarr": {
  "command": "uvx",
  "args": ["oraclarr-mcp"],
  "env": {
    "ORACLARR_SONARR_URL": "http://192.168.1.10:8989",
    "ORACLARR_SONARR_API_KEY": "your-key",
    "ORACLARR_RADARR_URL": "http://192.168.1.10:7878",
    "ORACLARR_RADARR_API_KEY": "your-key"
  }
}
```

**From a clone (for development):** put the same `ORACLARR_*` lines in a `.env` in the repo folder (it's read at startup), then:

```bash
uv sync
uv run python -m oraclarr_mcp
```

In a client config, use `"command": "uv"`, `"args": ["run", "python", "-m", "oraclarr_mcp"]` and a `"cwd"` pointing at the repo.

## Configuration

Each service is an *instance* with a name you choose. Its settings are variables named `ORACLARR_<NAME>_<FIELD>`, and an instance exists as soon as its `_URL` is set:

```
ORACLARR_SONARR_URL=http://192.168.1.10:8989
ORACLARR_SONARR_API_KEY=your-key

ORACLARR_SONARR_ANIME_TYPE=sonarr           # a second Sonarr, named sonarr-anime
ORACLARR_SONARR_ANIME_URL=http://192.168.1.10:8990
ORACLARR_SONARR_ANIME_API_KEY=your-key

ORACLARR_QBITTORRENT_URL=http://192.168.1.10:8080
ORACLARR_QBITTORRENT_USERNAME=admin
ORACLARR_QBITTORRENT_PASSWORD=your-password
```

| Field | Needed for |
|---|---|
| `_URL` | every instance |
| `_TYPE` | only when the name isn't a service type. Types: `sonarr`, `radarr`, `sportarr`, `prowlarr`, `qbittorrent`, `tdarr`, `profilarr`, `jellyfin`, `cleanuparr`, `netdata`, `truenas`, `docker` |
| `_API_KEY` | Sonarr, Radarr, Sportarr, Prowlarr, Profilarr, Jellyfin, Cleanuparr, TrueNAS |
| `_USERNAME`, `_PASSWORD` | qBittorrent |
| `_ENABLED` | optional; `false` switches an instance off without deleting its lines |
| `_VERIFY_TLS` | optional; `false` accepts a self-signed certificate (TrueNAS) |
| `_ALLOW_WRITES` | optional; `true` lets `start_job` act on this instance. See [Writes](https://github.com/bdog720/oraclarr/blob/main/docs/writes.md) |

Underscores in the name become dashes in the instance name, so `SONARR_ANIME` shows up as `sonarr-anime`. Blank values count as unset, so you can keep lines for services you don't run. A misspelled `ORACLARR_` variable stops the container with a message that names it, instead of failing quietly later.

Jellyfin needs an API key (Dashboard → API Keys). Cleanuparr needs its account API key (Settings → Account → API Key). TrueNAS, Netdata and Docker each have a short setup guide, linked below.

Server settings are optional:

| Variable | Default | What it does |
|---|---|---|
| `ORACLARR_TOOLSETS` | `media,downloads,transcode,library,host,containers` | Which groups of tools are offered |
| `ORACLARR_TOOL_BUDGET_SECONDS` | `30` | Time limit per tool call; slow instances report `status: "timeout"` |
| `ORACLARR_MAX_OUTPUT_BYTES` | `200000` | Safety net for oversized responses |
| `ORACLARR_TIMEOUT_SECONDS` | `10` | Timeout for each request to a service |
| `ORACLARR_ALLOW_WRITES` | `false` | Turns on `start_job`. Each instance also needs its own `_ALLOW_WRITES=true` |
| `ORACLARR_HTTP_TOKEN` | unset | At least 24 characters. When set, every HTTP request needs `Authorization: Bearer <token>`. Required to turn writes on over http |

Every tool call has a time budget. If an instance doesn't answer in time, it comes back as `status: "timeout"` and the other instances still return their data. List results carry only the useful fields and stop at each tool's `limit`; when there is more, `truncated` and `total` say so. API keys and passwords show up as `***` in responses and log lines.

## Guides

- [Connecting a client](https://github.com/bdog720/oraclarr/blob/main/docs/connect.md): Claude Code, Claude Desktop, Cursor, Codex CLI, VS Code, Gemini CLI and Windsurf, the token header, and why not to use a cloud connector.
- [Host metrics](https://github.com/bdog720/oraclarr/blob/main/docs/host-metrics.md): the TrueNAS read-only user and the Netdata container for `get_host`.
- [Containers](https://github.com/bdog720/oraclarr/blob/main/docs/containers.md): the Docker socket proxy for `get_containers`, and what it lets through.
- [Writes](https://github.com/bdog720/oraclarr/blob/main/docs/writes.md): the two switches, the token, the two-step plan flow, and the audit log.
- [The config file](https://github.com/bdog720/oraclarr/blob/main/docs/config-file.md): using `config.yaml` instead of (or as well as) `.env`, and migrating off it.
- [Upgrading](https://github.com/bdog720/oraclarr/blob/main/docs/upgrading.md): what to change when you cross a particular version.

## Roadmap

Oraclarr is built in phases. It is read-only by default, and write capability arrives behind explicit safety gates. The architecture (typed clients + outcome tools + config-selectable toolsets) is designed to extend to other self-hosted suites beyond *arr, too.

- ✅ **Phase 1: read-only diagnostics.** Sonarr, Radarr, Sportarr, Prowlarr, qBittorrent, Tdarr, Profilarr, Jellyfin, Cleanuparr, TrueNAS, Netdata, Docker.
- 🔜 **Phase 2: more services, still read-only.** Seerr, Gluetun, Unpackerr, ntfy. The architecture also opens up to non-*arr stacks.
- 🚧 **Phase 3: safe write actions.** Started in 2.0.0 with `start_job` (refresh, rescan, search, rename and Jellyfin scans), gated behind two switches, a token, dry-run previews and an audit log. Retry and request approval come later.
- 🔭 **Phase 4: destructive actions.** Delete media, blocklist, stack control and Cleanuparr changes, behind an explicit confirmation and allowlist.

Have a service you'd like covered? Open an issue.

## 💬 Feedback & Issues

Found a bug or have a feature request? Please [open an issue](https://github.com/bdog720/oraclarr/issues) on GitHub.

## 🤝 Contributing

Issues and PRs welcome. The codebase is TDD throughout:

```bash
uv run pytest        # tests (respx-mocked, no live services needed)
uv run ruff check .  # lint
```

Adding a service follows a small recipe (new client → register by `type` → extend a tool → write the test). See the project layout under `src/oraclarr_mcp/`.

## 📄 License

Apache License 2.0. See [LICENSE](https://github.com/bdog720/oraclarr/blob/main/LICENSE).

## 💖 Support the Project

If Oraclarr saves you from tabbing through six web UIs to work out why something didn't download, consider buying me a coffee.

<a href="https://buymeacoffee.com/bdog720" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 50px !important;width: 217px !important;" ></a>
