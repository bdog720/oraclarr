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

Covered now: **Sonarr**, **Radarr**, **Prowlarr**, **qBittorrent**, **Tdarr**, and **Profilarr** — including **multiple instances of the same type** (e.g. a separate anime or 4K Sonarr/Radarr). Every tool fans out across all the instances you define and reports each one separately.

## In practice

Once registered, you just ask your MCP client. Oraclarr picks the right tool and answers:

| You ask… | Oraclarr runs | …and tells you |
|----------|---------------|----------------|
| "Is anything in my stack down?" | `stack_health` | which services are unreachable, unhealthy, or low on disk |
| "Why hasn't the new episode of *X* downloaded yet?" | `diagnose` | where *X* is in the wanted → grab → download → import pipeline |
| "Why did a sub-only release get grabbed when I only allow English dubs?" | `explain_decision` | the release that was grabbed, its custom-format score, and the language formats that matched |
| "Why does Profilarr keep upgrading stuff that already looks fine?" | `explain_decision` + `get_quality_config` | the profile cutoff/upgrade thresholds vs. the current file's score |
| "What's stuck downloading right now?" | `get_queues` | unified queue with progress, ETA, and stall flags |

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

## Install

There are **two ways to run Oraclarr — pick one, you don't need both:**

- **🐳 Docker (recommended)** — a small always-on container that lives next to your
  arr stack. Best for homelabs; works great with Portainer, Dockge, Unraid, etc.
- **🐍 Python (uv)** — run it directly on your machine with no container. Best for
  local development, or if you simply don't use Docker.

Both options need the same two files. Make them from the templates in this repo —
[`config.example.yaml`](config.example.yaml) (your service URLs) and
[`.env.example`](.env.example) (your API keys / passwords):

- **If you cloned the repo:** `cp config.example.yaml config.yaml` and
  `cp .env.example .env`, then edit them.
- **If you're pasting into Dockge/Portainer:** open those two example files above,
  copy their contents into a `config.yaml` and a `.env` in your stack folder, and
  fill in your details.

See [Configuration](#configuration) below for exactly what goes in `config.yaml`.
Your `config.yaml` and `.env` are never committed — your URLs and secrets stay on
your machine. Now follow **one** of the two options below.

---

### Option A — Docker (recommended)

Oraclarr runs as a long-running container that serves MCP over HTTP at
`http://<host>:7979/mcp`. You need three things in one folder: your `config.yaml`,
your `.env`, and a `docker-compose.yml`.

**Using a stack manager (Dockge, Portainer, etc.):** create a new stack, paste the
compose below into the editor, and put your `config.yaml` and `.env` in the same
stack folder. Hit deploy.

**Using the command line:**

```bash
cp docker-compose.example.yml docker-compose.yml
docker compose up -d
```

Either way, this is the compose file — copy/paste it as-is:

```yaml
services:
  oraclarr:
    image: ghcr.io/bdog720/oraclarr-mcp:latest
    container_name: oraclarr
    restart: unless-stopped
    ports:
      - "7979:7979"           # left side is the host port — change it if 7979 is taken
    volumes:
      - ./config.yaml:/config/config.yaml:ro
    environment:
      SONARR_KEY: ${SONARR_KEY}
      SONARR_ANIME_KEY: ${SONARR_ANIME_KEY}
      RADARR_KEY: ${RADARR_KEY}
      PROWLARR_KEY: ${PROWLARR_KEY}
      QBIT_USER: ${QBIT_USER}
      QBIT_PASS: ${QBIT_PASS}
      PROFILARR_KEY: ${PROFILARR_KEY}
```

The keys on the right (`${SONARR_KEY}` …) are read from your `.env` file. Then
[connect Claude Desktop](#connect-claude-desktop).

---

### Option B — Python (uv)

Run Oraclarr directly, no Docker. Requires Python 3.12+ and
[`uv`](https://docs.astral.sh/uv/).

**From PyPI (no clone needed):** the package is published as
[`oraclarr-mcp`](https://pypi.org/project/oraclarr-mcp/). Point `ORACLARR_CONFIG`
at your `config.yaml` and run it with `uvx`:

```bash
ORACLARR_CONFIG=config.yaml uvx oraclarr-mcp
```

**From a clone (for development):**

```bash
uv sync
ORACLARR_CONFIG=config.yaml uv run python -m oraclarr_mcp
```

This speaks MCP over **stdio** — the client launches the process for you, so you
register it in your client's config rather than connecting to a URL:

```json
"oraclarr": {
  "command": "uvx",
  "args": ["oraclarr-mcp"],
  "env": { "ORACLARR_CONFIG": "/absolute/path/to/config.yaml" }
}
```

(From a clone instead of PyPI, use `"command": "uv"`, `"args": ["run", "python",
"-m", "oraclarr_mcp"]`, and add `"cwd"` pointing at the repo.)

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
      "args": ["-y", "mcp-remote", "http://<host>:7979/mcp"]
    }
  }
}
```

Replace `<host>` with the IP or hostname of the machine running the container.

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
| `ORACLARR_CONFIG` | `/config/config.yaml` | Where the container reads `config.yaml`. Leave as-is. |

## Configuration

Instances are named in `config.yaml`; `type` selects the client, so any number of instances of any type (e.g. two Sonarrs) just work. Secrets are referenced as `${ENV_VAR}` and pulled from `.env`:

```yaml
server:
  allow_writes: false              # read-only; writes are a future phase
  toolsets: [media, downloads, transcode]
defaults:
  timeout_seconds: 10
instances:
  sonarr:       { type: sonarr,       url: http://host:8989, api_key: ${SONARR_KEY} }
  sonarr-anime: { type: sonarr,       url: http://host:8990, api_key: ${SONARR_ANIME_KEY} }
  radarr:       { type: radarr,       url: http://host:7878, api_key: ${RADARR_KEY} }
  prowlarr:     { type: prowlarr,     url: http://host:9696, api_key: ${PROWLARR_KEY} }
  qbit:         { type: qbittorrent,  url: http://host:8080, username: ${QBIT_USER}, password: ${QBIT_PASS} }
  tdarr:        { type: tdarr,        url: http://host:8265 }
  profilarr:    { type: profilarr,    url: http://host:6868, api_key: ${PROFILARR_KEY} }
```

## Roadmap

Oraclarr is built in phases. v1 is deliberately read-only; write capability arrives behind explicit safety gates. The architecture (typed clients + outcome tools + config-selectable toolsets) is designed to extend to other self-hosted suites beyond *arr, too.

- ✅ **Phase 1: read-only diagnostics.** Sonarr, Radarr, Prowlarr, qBittorrent, Tdarr, Profilarr.
- 🔜 **Phase 2: more services, still read-only.** Jellyfin, Seerr, Gluetun, TrueNAS, Cleanuparr, ntfy. The architecture also opens up to non-*arr stacks.
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
