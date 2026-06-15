# Stage 3.3.24 LiveLine Worker Minimal Binary

## Stage Goal

Stage 3.3.24 implements the first minimal LiveLine Worker binary and upgrades the Worker bootstrap script from a safe placeholder to a real installation script.

This stage makes the `curl | bash` command capable of installing `liveline-worker` on a VPS when a future operator runs the command manually. This stage did not install the Worker on any real VPS and did not execute SSH or remote commands.

## Worker V1 Capability

Worker v1 is intentionally small:

- Register with the console through `POST /api/workers/register`.
- Store `worker_id` and `worker_secret` locally in `/etc/liveline-worker/config.yaml`.
- Run as a systemd service named `liveline-worker.service`.
- Send periodic heartbeat requests to `POST /api/workers/heartbeat`.
- Report basic read-only system status.
- Support `landing` and `transit` roles.
- Report Worker status through the existing `/api/workers` and `/api/workers/{worker_id}` APIs.

## Worker V1 Does Not Do

Worker v1 does not:

- Create real nodes.
- Create transit routes.
- Modify Xray configuration.
- Modify `socat` or `gost` configuration.
- Clean remote Xray, `socat`, or `gost`.
- Add listening ports.
- Modify firewall rules.
- Modify cloud security groups.
- Modify `node.share_link`.
- Execute cutover.
- Add HAProxy.
- Receive or execute task commands from the console.

## Implementation Summary

新增 / 修改内容：

- `worker/cmd/liveline-worker/main.go`
  - Adds the minimal Go Worker.
  - Supports `register`, `run`, and `version`.
  - Uses only the Go standard library.
- `worker/go.mod`
  - Adds the Go module for the Worker.
- `backend/worker-binaries/liveline-worker-linux-amd64`
  - Stores the locally built Linux amd64 Worker binary used by the backend image.
- `backend/app/api/routes/workers.py`
  - Upgrades `/worker_setup_script/{token}` to return a real install script.
  - Adds `/worker_binary/liveline-worker-linux-amd64`.
  - Keeps token and Worker secret storage hashed in the database.
- `backend/app/schemas/workers.py`
  - Allows heartbeat payloads to include the Worker role.
- `frontend/components/ServerManagementPanel.tsx`
  - Updates the landing server add modal copy from placeholder-script wording to real Worker v1 install wording.
- `frontend/components/TransitRoutesPanel.tsx`
  - Updates the transit server add modal copy from placeholder-script wording to real Worker v1 install wording.
- `.gitignore`
  - Ignores local Worker build output under `worker/bin/`.

The backend Docker build does not depend on pulling a Go builder image. The Worker is compiled with the local Go toolchain before the Docker build, then copied as part of the normal backend build context.

## Install Script Behavior

`GET /worker_setup_script/{token}` now returns a bash install script. The intended operator command is still:

```bash
curl -s https://<console-domain>/worker_setup_script/<one-time-token> | bash -s eth0 landing
```

or:

```bash
curl -s https://<console-domain>/worker_setup_script/<one-time-token> | bash -s eth0 transit
```

The script:

1. Validates `interface_name`.
2. Validates role as `landing` or `transit`.
3. Requires root privileges.
4. Checks for `curl`.
5. Checks for systemd.
6. Creates `/etc/liveline-worker` with restricted permissions.
7. Downloads `liveline-worker` from `/worker_binary/liveline-worker-linux-amd64`.
8. Installs the binary to `/usr/local/bin/liveline-worker`.
9. Registers the Worker with the console.
10. Writes `/etc/liveline-worker/config.yaml` with mode `600`.
11. Writes `/etc/systemd/system/liveline-worker.service`.
12. Runs `systemctl daemon-reload`.
13. Runs `systemctl enable liveline-worker`.
14. Runs `systemctl restart liveline-worker`.
15. Prints the journal command for log viewing.

The script does not print the complete token or Worker secret.

## Systemd Service Design

The service runs:

```text
/usr/local/bin/liveline-worker run --config /etc/liveline-worker/config.yaml
```

It uses:

- `Restart=always`
- `RestartSec=10`
- `NoNewPrivileges=true`
- `ProtectSystem=full`
- `ProtectHome=read-only`
- `PrivateTmp=true`

## Worker Config File

The remote config path is:

```text
/etc/liveline-worker/config.yaml
```

The config contains:

- `console_url`
- `worker_id`
- `worker_secret`
- `role`
- `interface_name`
- `heartbeat_interval_seconds`

`worker_secret` is allowed in the remote Worker config file because it is the Worker runtime credential. It must not be written to README, docs, task logs, backend logs, API normal responses, or browser UI.

## Registration Flow

1. The console creates a one-time Worker token through `POST /api/worker-tokens`.
2. The operator runs the install command on a future VPS.
3. The install script downloads the Worker binary.
4. The install script runs:

```text
liveline-worker register --config /etc/liveline-worker/config.yaml --console-url <console-url> --token <token> --role <role> --interface <interface>
```

5. The Worker sends token, role, interface, hostname, version, and read-only system info to `POST /api/workers/register`.
6. The backend marks the token as used.
7. The backend returns `worker_id`, `worker_secret`, and heartbeat interval.
8. The Worker writes the local config with mode `600`.

## Heartbeat Flow

The systemd service runs the Worker in long-running mode. The Worker sends a heartbeat immediately on startup, then repeats every configured interval.

Heartbeat authentication uses:

- `X-Worker-Id`
- `X-Worker-Secret`

The backend stores only `worker_secret_hash`.

## Status Report Content

Worker v1 reports only read-only data:

- Worker version.
- Role.
- Interface name.
- Hostname.
- Interface IPv4 address when available.
- OS summary.
- Kernel version.
- Uptime seconds.
- CPU model and core count.
- Memory summary from `/proc/meminfo`.
- Disk summary for `/`.
- Service state summary.

For `landing`, service summary includes:

- `liveline_worker`
- `xray`

For `transit`, service summary includes:

- `liveline_worker`
- `socat`
- `gost`

Service checks are read-only and use local binary lookup plus `systemctl is-active`.

## Security Boundary

This stage:

- Does not install Worker onto a real VPS.
- Does not execute SSH.
- Does not execute remote commands.
- Does not create real nodes.
- Does not create transit routes.
- Does not add listening ports.
- Does not modify firewall rules.
- Does not modify Xray.
- Does not modify `socat`.
- Does not modify `gost`.
- Does not clean remote services.
- Does not modify `node.share_link`.
- Does not perform formal cutover.
- Does not add HAProxy.
- Does not delete SSH source code.
- Does not delete existing node creation logic.
- Does not delete existing transit route logic.

## Validation Checklist

| Check | Result |
| --- | --- |
| `go version` | Passed with local Go toolchain |
| `go test ./...` in `worker/` | Passed |
| `go build -o /tmp/liveline-worker ./cmd/liveline-worker` | Passed |
| Linux amd64 Worker build | Passed |
| `git diff --check` | Passed |
| `python3 -m compileall backend/app` | Passed |
| `docker compose exec -T frontend npm run build` | Passed |
| `docker compose up --build -d` | Passed |
| `http://localhost:3000` | HTTP 200 |
| `/api/health` | backend / database / redis / worker ok |
| Redis `temp_credential:*` | 0 |
| pending / running tasks | 0 |
| Sensitive information scan | Passed |

## Stage Result

Stage 3.3.24 implements the minimal LiveLine Worker binary and real Worker bootstrap install script. It keeps Worker v1 limited to registration, heartbeat, and read-only status reporting. No real VPS install, SSH execution, remote command, new listener, node creation, route creation, `node.share_link` change, or cutover was performed.
