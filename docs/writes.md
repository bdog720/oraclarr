# Writes (opt-in)

Oraclarr only reads unless you turn writes on. With writes on, one tool, `start_job`, can start a refresh, rescan, search or rename on a single series or movie in Sonarr or Radarr, or start a library scan in Jellyfin. It cannot delete anything, and it does nothing to Sportarr, which has no command API. If you leave the settings below alone, Oraclarr behaves exactly as before.

## Turning it on

Two switches must both be on: `ORACLARR_ALLOW_WRITES=true` for the server, and `ORACLARR_<NAME>_ALLOW_WRITES=true` for each instance you want it to act on. Instances without their own switch stay read-only.

Over http, writes also need a token, and the container refuses to start with writes on and no token. Make one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Add the token and both switches to `.env`:

```
ORACLARR_HTTP_TOKEN=<the token>
ORACLARR_ALLOW_WRITES=true
ORACLARR_SONARR_ALLOW_WRITES=true
```

If your compose file lists variables in an `environment:` block and uses `.env` only for substitution, write `ORACLARR_HTTP_TOKEN: ${ORACLARR_HTTP_TOKEN}` there instead, and the same for the two switches.

Once a token is set, every request needs it, reads included. [Connecting a client](connect.md) shows where the token goes for Claude Code and Claude Desktop.

## How a write runs

A write takes two calls. The first call has no `plan_id`. It changes nothing and returns a preview of what would happen, with a `plan_id` that is good for 10 minutes. The second call passes only that `plan_id`, and the job runs once.

Each plan covers one target. To act on ten shows, you make ten plans.

Plans live in memory, so a restart drops them. Nothing is retried: if a request times out after it was sent, the result says `outcome: unknown` and you check with `get_jobs`.

## Audit log

Every write event is one line on stderr:

```
<timestamp> audit event=<event> key=value ...
```

The event is `planned`, `executed`, `refused`, `failed` or `unknown`. Lines are never wrapped, so this finds every event with its `plan_id`, `target` and `command_id`:

```bash
docker logs oraclarr 2>&1 | grep "audit event="
```

Whitespace inside values is replaced by `_`, so a value cannot start a new line.
