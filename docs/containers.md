# Containers: the Docker socket proxy

`get_containers` answers "which containers are down, and what did they exit with?" and "what errors has Sonarr logged today?". `stack_health` uses the same data to show the container behind an unreachable service.

Oraclarr never gets the Docker socket. It reads Docker through [socket-proxy](https://github.com/wollomatic/socket-proxy), a small container that sits in front of the socket and passes on only the requests you allow. The rules below allow GET requests for the container list, one container's details, its logs, the Docker version and a ping. The proxy refuses everything else, including start, stop, `exec`, and the `archive` and `export` endpoints that can copy files out of a container.

## Setup

The proxy has to be in the same compose stack as Oraclarr: it publishes no port, and its `-allowfrom=oraclarr` rule only works on the stack's shared network. [`docker-compose.full.example.yml`](../docker-compose.full.example.yml) has both services ready to go. The proxy part:

```yaml
  docker-proxy:
    image: wollomatic/socket-proxy:1.13.1
    container_name: docker-proxy
    restart: unless-stopped
    user: "65534:<docker group id>"
    read_only: true
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    mem_limit: 64M
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
    command:
      - '-loglevel=info'
      - '-listenip=0.0.0.0'
      - '-allowfrom=oraclarr'
      - '-allowGET=(/v1\.[0-9]+)?/(version|_ping|containers/json|containers/[a-zA-Z0-9][a-zA-Z0-9_.-]*/(json|logs))'
      - '-allowhealthcheck'
      - '-watchdoginterval=3600'
      - '-stoponwatchdog'
    healthcheck:
      test: ["CMD", "./healthcheck"]
      interval: 30s
      timeout: 5s
      retries: 2
```

Three things to get right:

- Get the Docker group ID with `stat -c '%g' /var/run/docker.sock` and put it in `user:`.
- Keep the single quotes around the `command` items, or the backslash in the regex is lost.
- `-allowfrom=oraclarr` has to match your Oraclarr service name.

Then point Oraclarr at the proxy in `.env`:

```
ORACLARR_DOCKER_URL=http://docker-proxy:2375
```

## What leaves the container, and what doesn't

A container's details include its environment variables, which usually hold API keys. Oraclarr drops them, along with mounts and most labels, as soon as the response arrives, so they never reach a tool result or the cache.

Log lines get the same redaction as every other response, plus patterns for passwords and credentials inside URLs. A service that prints a secret in plain prose can still get through, so treat log output with some care.

## How stack_health finds a container

When a service is unreachable, its row shows the container behind its URL, plus any container sharing that container's network (qBittorrent behind Gluetun, for example). Oraclarr matches the URL's hostname against container names first, then an explicit port against published ports. A URL with neither, such as a reverse-proxy name on the default port, gets no container rather than a guess.
