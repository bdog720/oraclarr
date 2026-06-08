# Oraclarr

A locally-run, **read-only** diagnostic [MCP](https://modelcontextprotocol.io)
server for a self-hosted *arr media stack. It gives an LLM client (Claude Code,
Claude Desktop) one place to ask operational "why" questions — *"is anything
down?"*, *"why isn't this episode here yet?"*, *"why did a sub-only release get
grabbed?"* — by aggregating across services.

Covers, in this phase: **Sonarr** (incl. a second anime instance), **Radarr**,
**Prowlarr**, **qBittorrent**, **Tdarr**, and **Profilarr**. Read-only — no
mutations.

## Tools

All read-only, outcome-oriented (not one-per-endpoint):

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

`config.yaml` and `.env` are gitignored — your URLs and secrets stay local.

## Run

```bash
ORACLARR_CONFIG=config.yaml uv run python -m oraclarr_mcp
```

The server speaks MCP over stdio.

## Register with Claude Code / Desktop

Add to your MCP client config:

```json
"oraclarr": {
  "command": "uv",
  "args": ["run", "python", "-m", "oraclarr_mcp"],
  "cwd": "E:\\Development\\arrSuiteMCP",
  "env": { "ORACLARR_CONFIG": "E:\\Development\\arrSuiteMCP\\config.yaml" }
}
```

## Configuration

Instances are named in `config.yaml`; `type` selects the client, so multiple
instances of the same type (e.g. two Sonarrs) just work. Secrets are referenced
as `${ENV_VAR}` and pulled from `.env`:

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

## Development

```bash
uv run pytest        # tests (respx-mocked, no live services needed)
uv run ruff check .  # lint
```

## License

[Apache-2.0](LICENSE).
