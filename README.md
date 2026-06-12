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

Covered now: **Sonarr** (plus a second anime instance), **Radarr**, **Prowlarr**, **qBittorrent**, **Tdarr**, and **Profilarr**.

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

## Setup

Requires Python 3.12+ and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync
cp config.example.yaml config.yaml   # edit URLs to match your stack
cp .env.example .env                  # fill in API keys / credentials
```

`config.yaml` and `.env` are gitignored, so your URLs and secrets stay local.

## Run

```bash
ORACLARR_CONFIG=config.yaml uv run python -m oraclarr_mcp
```

The server speaks MCP over stdio.

### Register with Claude Code / Desktop

```json
"oraclarr": {
  "command": "uv",
  "args": ["run", "python", "-m", "oraclarr_mcp"],
  "cwd": "E:\\Development\\Oraclarr",
  "env": { "ORACLARR_CONFIG": "E:\\Development\\Oraclarr\\config.yaml" }
}
```

## Docker (homelab)

Run Oraclarr as a long-running HTTP MCP service next to your arr stack. Images
are published to `ghcr.io/bdog720/oraclarr-mcp` (amd64).

```bash
cp docker-compose.example.yml docker-compose.yml
cp config.example.yaml config.yaml   # edit URLs to match your stack
cp .env.example .env                  # fill in API keys / credentials
docker compose up -d
```

The container serves MCP over streamable HTTP at `http://<host>:7979/mcp`
(`config.yaml` mounted read-only; secrets injected from `.env`).

### Connect Claude Desktop

Use the **`mcp-remote` stdio bridge** in `claude_desktop_config.json`. It runs
locally as a Claude Desktop "local MCP server", so it can reach the container on
your LAN (requires Node.js / `npx`):

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

### Transport env vars

| Var | Default (image) | Meaning |
|---|---|---|
| `ORACLARR_TRANSPORT` | `http` | `stdio` or `http` |
| `ORACLARR_HTTP_HOST` | `0.0.0.0` | bind host |
| `ORACLARR_HTTP_PORT` | `7979` | bind port |
| `ORACLARR_CONFIG` | `/config/config.yaml` | config path inside container |

Outside Docker the code default is `stdio` on `127.0.0.1`.

## Configuration

Instances are named in `config.yaml`; `type` selects the client, so multiple instances of the same type (e.g. two Sonarrs) just work. Secrets are referenced as `${ENV_VAR}` and pulled from `.env`:

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
