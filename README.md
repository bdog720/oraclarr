<!-- mcp-name: io.github.bdog720/oraclarr -->

<div align="center">

# Oraclarr

**Ask your media stack what's going on, in plain language.**

A locally-run, read-only [MCP](https://modelcontextprotocol.io) server that lets an LLM client (Claude Code, Claude Desktop) diagnose a self-hosted *arr media stack.

![License](https://img.shields.io/badge/license-Apache--2.0-blue)
![Python](https://img.shields.io/badge/python-3.12%2B-blue)
![MCP](https://img.shields.io/badge/MCP-server-7b3fe4)
![Mode](https://img.shields.io/badge/mode-read--only-orange)
![Status](https://img.shields.io/badge/phase%201-complete-brightgreen)

</div>

---

## What it does

Oraclarr gives a language model one place to answer the operational "why" questions that normally mean tabbing through six web UIs. It aggregates across your services and returns a single, structured answer without changing anything (it is strictly read-only in this phase).

Covered now: **Sonarr**, **Radarr**, **Sportarr**, **Prowlarr**, **qBittorrent**, **Tdarr**, **Profilarr**, **Jellyfin**, and **Cleanuparr** — including **multiple instances of the same type** (e.g. a separate anime or 4K Sonarr/Radarr). Every tool fans out across all the instances you define and reports each one separately.

## In practice

Once registered, you just ask your MCP client. Oraclarr picks the right tool and answers:

| You ask… | Oraclarr runs | …and tells you |
|----------|---------------|----------------|
| "Is anything in my stack down?" | `stack_health` | which services are unreachable, unhealthy, or low on disk |
| "Why hasn't the new episode of *X* downloaded yet?" | `diagnose` | whether *X* is in your library, sitting in the download queue, or still on the wanted list |
| "Why did a sub-only release get grabbed when I only allow English dubs?" | `explain_decision` | the release that was grabbed, its custom-format score, and the language formats that matched |
| "Why does Profilarr keep upgrading stuff that already looks fine?" | `explain_decision` + `get_quality_config` | the profile's cutoff and upgrade thresholds next to the scores of recent grabs |
| "What's stuck downloading right now?" | `get_queues` | a unified queue with progress and stall flags |
| "Is the Jellyfin library scan finished, and is anyone transcoding?" | `get_library` | scan state and progress per library, failed tasks, and who is playing what (with transcode reasons) |
| "Why is Cleanuparr about to remove this download?" | `get_queues` + `get_cleanup` | the strikes against it and their type, whether it's marked for removal, and the rules that apply |

## Tools

All read-only and outcome-oriented (not one-per-endpoint, which keeps the model accurate):

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

## Install

There are two ways to run Oraclarr. Pick one:

- **🐳 Docker (recommended).** A small always-on container next to your arr stack. Works with Dockge, Portainer, Unraid and plain `docker compose`.
- **🐍 Python (uv).** Runs directly on your machine with no container. Handy for local development, or if you don't use Docker.

Either way, every setting is an environment variable that starts with `ORACLARR_`. With Docker that means one `.env` file next to the compose file, and Dockge and Portainer show both in their editors. Start from [`.env.example`](.env.example). [Configuration](#configuration) lists every variable. Your `.env` is never committed.

---

### Option A — Docker (recommended)

Oraclarr runs as a long-running container that serves MCP over HTTP at `http://<host>:7979/mcp`. You need two files in one folder: `docker-compose.yml` and `.env`.

**Using a stack manager (Dockge, Portainer, etc.):** create a new stack, paste the compose below into the editor, and paste your settings into the stack's `.env`. Hit deploy. Portainer saves the variables from its web editor as `stack.env`, so in Portainer change the compose line to `env_file: stack.env`.

**Using the command line:**

```bash
cp docker-compose.example.yml docker-compose.yml
cp .env.example .env    # then fill in your URLs and keys
docker compose up -d
```

This is the compose file. You don't edit it when you add or remove a service:

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

Then [connect Claude Desktop](#connect-claude-desktop).

---

### Option B — Python (uv)

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

---

### Connect Claude Desktop

*(For Option A / Docker. Option B registers itself with the JSON snippet above.)*

Use the **`mcp-remote` bridge** in `claude_desktop_config.json`. It runs locally as
a Claude Desktop "local MCP server", so it can reach the container on your LAN
(requires Node.js / `npx`):

```json
{
  "mcpServers": {
    "oraclarr": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://<host>:7979/mcp", "--allow-http"]
    }
  }
}
```

Replace `<host>` with the IP or hostname of the machine running the container.

> **Why `--allow-http`?** Recent versions of `mcp-remote` reject plain `http://` URLs
> unless the host is `localhost`. Without this flag the bridge exits immediately and
> Claude Desktop shows the server as "disconnected" — even though the server itself is
> reachable. The flag is safe here: the traffic stays on your trusted LAN.

> **Why not the native "Add custom connector"?** Custom connectors connect to your
> server **from Anthropic's cloud**, not from your machine — so the URL must be a
> publicly reachable **HTTPS** endpoint (a `http://` LAN/localhost URL is rejected).
> Pointing it at a homelab box means exposing this **unauthenticated read-only**
> service to the internet, which we don't recommend until authentication lands (a
> later phase). If you want it anyway, put a reverse proxy (Caddy/nginx) or tunnel
> (Cloudflare Tunnel, Tailscale Funnel) with TLS in front and add your own auth.

> **Security:** the service is unauthenticated read-only MCP. Deploy on a trusted
> LAN only and do not expose port 7979 to the internet. Authentication is a later
> phase.

### Transport settings (Docker only)

These apply to the **Docker** container only. The image already sets sensible
defaults, so **you normally don't touch them** — the table is here for reference.
The Python path (Option B) always uses stdio and ignores these entirely.

| Variable | Default | What it does |
|---|---|---|
| `ORACLARR_TRANSPORT` | `http` | How clients reach the server. `http` = long-running service (Docker). `stdio` = the client launches the process (the Python path). You don't normally set this by hand — your install method picks it. |
| `ORACLARR_HTTP_HOST` | `0.0.0.0` | Which network interface to listen on. `0.0.0.0` means "reachable on your LAN" — leave as-is for Docker. |
| `ORACLARR_HTTP_PORT` | `7979` | Port *inside* the container. To change the port you reach it on, edit the `ports:` line in the compose instead. |
| `ORACLARR_CONFIG` | `/config/config.yaml` | Where the container looks for an optional config.yaml. Leave as-is. |

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
| `_TYPE` | only when the name isn't a service type. Types: `sonarr`, `radarr`, `sportarr`, `prowlarr`, `qbittorrent`, `tdarr`, `profilarr`, `jellyfin`, `cleanuparr` |
| `_API_KEY` | Sonarr, Radarr, Sportarr, Prowlarr, Profilarr, Jellyfin, Cleanuparr |
| `_USERNAME`, `_PASSWORD` | qBittorrent |
| `_ENABLED` | optional; `false` switches an instance off without deleting its lines |

Underscores in the name become dashes in the instance name, so `SONARR_ANIME` shows up as `sonarr-anime`. Blank values count as unset, so you can keep lines for services you don't run. A misspelled `ORACLARR_` variable stops the container with a message that names it, instead of failing quietly later.

Server settings are optional:

| Variable | Default | What it does |
|---|---|---|
| `ORACLARR_TOOLSETS` | `media,downloads,transcode,library` | Which groups of tools are offered |
| `ORACLARR_TOOL_BUDGET_SECONDS` | `30` | Time limit per tool call; slow instances report `status: "timeout"` |
| `ORACLARR_MAX_OUTPUT_BYTES` | `200000` | Safety net for oversized responses |
| `ORACLARR_TIMEOUT_SECONDS` | `10` | Timeout for each request to a service |
| `ORACLARR_ALLOW_WRITES` | `false` | Read-only for now; writes are a future phase |

Jellyfin needs an API key (Dashboard → API Keys). `get_library` only registers when `library` is in the toolsets. Cleanuparr needs its account API key (Settings → Account → API Key).

Every tool call has a time budget, set by `ORACLARR_TOOL_BUDGET_SECONDS`. If an instance doesn't answer in time, it comes back as `status: "timeout"` and the other instances still return their data. List results carry only the useful fields and stop at each tool's `limit`. When there is more, `truncated` and `total` say so. API keys and passwords show up as `***` in responses and log lines (values shorter than four characters are left alone).

### Alternative: a config file

Oraclarr still reads a `config.yaml` if one exists at `ORACLARR_CONFIG` (`/config/config.yaml` in the container); [`config.example.yaml`](config.example.yaml) shows the format. If you use both, instances from both are loaded, and an `ORACLARR_` variable wins over the same setting in the file. With Docker, mount the file with `- ./config.yaml:/config/config.yaml:ro`.

### Migrating from `config.yaml`

Up to 1.2.0 the setup used `config.yaml` plus an `environment:` block in the compose file. That setup still works on 1.3.0 without changes. To move to `.env` only:

1. Add a block per instance to `.env`:

   | `config.yaml` | `.env` |
   |---|---|
   | `sonarr: { type: sonarr, url: …, api_key: … }` | `ORACLARR_SONARR_URL=…` and `ORACLARR_SONARR_API_KEY=…` |
   | `sonarr-anime: { type: sonarr, … }` | `ORACLARR_SONARR_ANIME_TYPE=sonarr`, plus `_URL` and `_API_KEY` |
   | `qbit: { type: qbittorrent, username: …, password: … }` | `ORACLARR_QBIT_TYPE=qbittorrent`, plus `_URL`, `_USERNAME` and `_PASSWORD` |
   | `server: { toolsets: [a, b] }` | `ORACLARR_TOOLSETS=a,b` |

2. In the compose file, replace the `environment:` block and the `config.yaml` volume line with `env_file: .env`.
3. Redeploy (in Dockge: **Update**).
4. Once everything answers, delete `config.yaml`. Keeping it does no harm, because `.env` wins.

## Roadmap

Oraclarr is built in phases. v1 is deliberately read-only; write capability arrives behind explicit safety gates. The architecture (typed clients + outcome tools + config-selectable toolsets) is designed to extend to other self-hosted suites beyond *arr, too.

- ✅ **Phase 1: read-only diagnostics.** Sonarr, Radarr, Sportarr, Prowlarr, qBittorrent, Tdarr, Profilarr, Jellyfin, Cleanuparr.
- 🔜 **Phase 2: more services, still read-only.** Seerr, Gluetun, TrueNAS, Unpackerr, ntfy. The architecture also opens up to non-*arr stacks.
- 🔭 **Phase 3: safe write actions.** Trigger search, retry, refresh/rescan, approve requests, gated behind `allow_writes` with dry-run previews and an audit log.
- 🔭 **Phase 4: destructive actions.** Delete media, blocklist, stack control, behind an explicit confirmation and allowlist.

Have a service you'd like covered? Open an issue.

## 💬 Feedback & Issues

Found a bug or have a feature request? We'd love to hear about it. Please [open an issue](https://github.com/bdog720/oraclarr/issues) here on GitHub.

## 🤝 Contributing

We welcome contributions! Issues and PRs welcome — the codebase is TDD throughout:

```bash
uv run pytest        # tests (respx-mocked, no live services needed)
uv run ruff check .  # lint
```

Adding a service follows a small recipe (new client → register by `type` → extend a tool → write the test). See the project layout under `src/oraclarr_mcp/`.

## 📄 License

This project is licensed under the Apache License 2.0. See the [LICENSE](LICENSE) file for details.

## 💖 Support the Project

If you find Oraclarr useful and it saves you from tabbing through six web UIs to work out why something didn't download, consider buying me a coffee to support future development!

<a href="https://buymeacoffee.com/bdog720" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/v2/default-yellow.png" alt="Buy Me A Coffee" style="height: 50px !important;width: 217px !important;" ></a>
