# Upgrading

Oraclarr follows semver. A minor release adds services or tools and keeps existing settings working. Notes that only matter when you cross a particular version live here.

## 2.0.0

Writes arrive, off by default. Nothing changes unless you set `ORACLARR_ALLOW_WRITES`. See [Writes](writes.md).

`ORACLARR_HTTP_TOKEN` is new. With it set, every request needs `Authorization: Bearer <token>`, so add the header to your client config in the same step. Setting `ORACLARR_ALLOW_WRITES=true` over http without a token is a startup error.

## 1.7.0

`get_jobs` is added to the `media` toolset. No settings change.

## 1.6.0

The `docker` instance type and the `containers` toolset arrive, and `containers` joins the default `ORACLARR_TOOLSETS`. The image must be 1.6.0 or later before you add `ORACLARR_DOCKER_URL`: an older image does not know the type and refuses to start. Add the proxy and the variable in the same step as the image update. See [Containers](containers.md).

## 1.5.0

The `netdata` and `truenas` types and the `host` toolset arrive, and `host` joins the default `ORACLARR_TOOLSETS`. If you set `ORACLARR_TOOLSETS` explicitly, add `host` to get `get_host`. See [Host metrics](host-metrics.md).

## 1.3.0

Settings move to `ORACLARR_*` variables. `config.yaml` keeps working; the migration steps are in [The config file](config-file.md).
