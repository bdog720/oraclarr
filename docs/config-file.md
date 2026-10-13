# The config file (optional)

Everything in Oraclarr can be set with `ORACLARR_*` variables, and that is the recommended way. A `config.yaml` is still supported: Oraclarr reads one if it exists at `ORACLARR_CONFIG` (`/config/config.yaml` in the container, `./config.yaml` for the Python path).

[`config.example.yaml`](../config.example.yaml) shows the format. Secrets go in as `${VAR}` references that are read from the environment, so the file itself holds no keys.

If you use both the file and variables, instances from both are loaded, and an `ORACLARR_` variable wins over the same setting in the file.

With Docker, mount the file:

```yaml
    volumes:
      - ./config.yaml:/config/config.yaml:ro
```

If the file does not exist on the host when the container first starts, Docker creates a directory at the mount point and Oraclarr refuses to start with a message that says so. Create the file first, or drop the mount.

## Migrating from config.yaml to .env

Up to 1.2.0 the setup used `config.yaml` plus an `environment:` block in the compose file. That still works. To move to `.env` only:

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
