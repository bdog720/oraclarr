# Connecting a client

Oraclarr in Docker serves MCP over HTTP at `http://<host>:7979/mcp`. This page covers Claude Code and Claude Desktop. If you run the Python package instead (Option B in the README), skip this: your client starts the process itself and the JSON snippet in the README is all you need.

Replace `<host>` below with the IP or hostname of the machine running the container.

## Claude Code

Claude Code talks to HTTP MCP servers directly, no bridge needed:

```bash
claude mcp add --transport http oraclarr http://<host>:7979/mcp --scope user
```

`--scope user` makes it available in every project. Leave it off to register for the current project only.

If you have set `ORACLARR_HTTP_TOKEN` (see [Writes](writes.md)), add the header:

```bash
claude mcp add --transport http oraclarr http://<host>:7979/mcp --scope user --header "Authorization: Bearer <the token>"
```

The same thing as a `.mcp.json` entry, with the token kept in an environment variable so it stays out of the file:

```json
{
  "mcpServers": {
    "oraclarr": {
      "type": "http",
      "url": "http://<host>:7979/mcp",
      "headers": { "Authorization": "Bearer ${ORACLARR_HTTP_TOKEN}" }
    }
  }
}
```

A plain `http://` LAN URL works here; Claude Code does not need the `mcp-remote` bridge that Claude Desktop does. `claude mcp list` shows the server as connected once the container is up.

## Claude Desktop

Claude Desktop cannot open an HTTP MCP server on your LAN by itself. Use the `mcp-remote` bridge in `claude_desktop_config.json`. It runs locally as a "local MCP server" and forwards to the container (requires Node.js / `npx`):

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

With a token set, add a `--header` argument and an `env` block:

```json
{
  "mcpServers": {
    "oraclarr": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "http://<host>:7979/mcp", "--allow-http",
               "--header", "Authorization:${AUTH_HEADER}"],
      "env": {"AUTH_HEADER": "Bearer <the token>"}
    }
  }
}
```

There is no space after the colon on purpose. Claude Desktop on Windows breaks arguments that contain spaces, so the space lives in the `env` value instead.

**Why `--allow-http`?** Recent versions of `mcp-remote` reject plain `http://` URLs unless the host is `localhost`. Without the flag the bridge exits immediately and Claude Desktop shows the server as "disconnected", even though the server itself is fine. The traffic stays on your LAN, so the flag is safe here.

**Why not the native "Add custom connector"?** Custom connectors reach your server from Anthropic's cloud, not from your machine. The URL has to be a publicly reachable HTTPS endpoint, and a `http://` LAN or localhost URL is rejected. Pointing one at a homelab box means exposing Oraclarr to the internet. We don't recommend it. If you want it anyway, put a reverse proxy (Caddy, nginx) or a tunnel (Cloudflare Tunnel, Tailscale Funnel) with TLS in front, and set a token.

## Security

With no `ORACLARR_HTTP_TOKEN`, anyone who can reach port 7979 can read your stack's status. Deploy on a trusted LAN only and do not expose the port to the internet.

Writes are off by default. Turning them on requires a token, and once a token is set every request needs it, reads included. The token is a shared secret sent over plain http. It protects against other devices on your LAN, not against someone who can watch the traffic.

## Transport settings (Docker only)

The image sets these already. You normally don't touch them. The Python path always uses stdio and ignores them.

| Variable | Default | What it does |
|---|---|---|
| `ORACLARR_TRANSPORT` | `http` | `http` = long-running service (Docker). `stdio` = the client launches the process (Python). Your install method picks this; you don't set it by hand. |
| `ORACLARR_HTTP_HOST` | `0.0.0.0` | Interface to listen on. `0.0.0.0` means reachable on your LAN. Leave as-is for Docker. |
| `ORACLARR_HTTP_PORT` | `7979` | Port *inside* the container. To change the port you reach it on, edit the `ports:` line in the compose instead. |
| `ORACLARR_CONFIG` | `/config/config.yaml` | Where the container looks for an optional [config file](config-file.md). Leave as-is. |
