# Host metrics: Netdata and TrueNAS

`get_host` answers "is the box under I/O pressure?", "how much RAM is actually free?", and "how full are the pools?". It reads two sources. You can set up one or both.

## TrueNAS

TrueNAS supplies pools, datasets, disk temperatures and alerts through its API.

1. Create a dedicated user in the read-only administrators group.
2. Give it an API key.
3. Add to `.env`:

```
ORACLARR_TRUENAS_URL=https://192.168.1.10
ORACLARR_TRUENAS_API_KEY=your-key
ORACLARR_TRUENAS_VERIFY_TLS=false
```

The URL must be `https://`. TrueNAS revokes an API key that is ever sent over plain http, and Oraclarr refuses an `http://` URL for the same reason.

TrueNAS's default certificate is self-signed, so `ORACLARR_TRUENAS_VERIFY_TLS=false` is needed unless you have installed a trusted one. With verification off, a device on your LAN could intercept the key.

## Netdata

Netdata supplies what the TrueNAS API does not: CPU and iowait, free and available memory, swap, the ARC maximum, and GPU stats.

TrueNAS ships its own Netdata, but it only listens on localhost. Run a separate Netdata container next to your stack. It does not need to be in the Oraclarr compose; Oraclarr reaches it over a URL.

```yaml
services:
  netdata:
    image: netdata/netdata:stable
    container_name: netdata
    hostname: truenas
    restart: unless-stopped
    pid: host
    cap_add: [SYS_PTRACE, SYS_ADMIN]
    security_opt: [apparmor:unconfined]
    ports:
      - 20999:19999
    environment:
      DO_NOT_TRACK: "1"
      NVIDIA_VISIBLE_DEVICES: all
      NVIDIA_DRIVER_CAPABILITIES: all
    volumes:
      - netdataconfig:/etc/netdata
      - netdatalib:/var/lib/netdata
      - netdatacache:/var/cache/netdata
      - /etc/passwd:/host/etc/passwd:ro
      - /etc/group:/host/etc/group:ro
      - /etc/localtime:/etc/localtime:ro
      - /etc/os-release:/host/etc/os-release:ro
      - /proc:/host/proc:ro
      - /sys:/host/sys:ro
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: all
              capabilities: [gpu, utility]
volumes:
  netdataconfig:
  netdatalib:
  netdatacache:
```

No NVIDIA GPU? Leave out the `NVIDIA_*` lines and the `deploy:` block. `get_host` then reports the GPU as not available.

Then point Oraclarr at it:

```
ORACLARR_NETDATA_URL=http://192.168.1.10:20999
```

Netdata's API has no login, so keep that port on your LAN.

## What you get

| Ask | Section | Source |
|---|---|---|
| CPU busy, iowait, load, I/O pressure | default | Netdata |
| Free vs available memory, swap, ARC size against its max | default | Netdata |
| GPU temperature, power, VRAM | default | Netdata |
| Pool capacity, fragmentation, scrub state | default | TrueNAS |
| Biggest datasets | `section="datasets"` | TrueNAS |
| Disk temperatures | `section="disks"` | TrueNAS |
| Alerts | `section="alerts"` | TrueNAS |

Identifiers that could tie a report to your hardware (disk serials, GPU UUIDs, node GUIDs) are never returned.
