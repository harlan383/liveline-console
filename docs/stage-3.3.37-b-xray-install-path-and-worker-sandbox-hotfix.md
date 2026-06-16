# Stage 3.3.37-b Xray Install Path And Worker Sandbox Hotfix

## Stage Goal

Stage 3.3.37-b fixes the formal landing-node create Xray install path and the
`liveline-worker.service` sandbox write boundary.

This is a hotfix stage only. It does not retry formal creation and does not
trigger `landing_node_create`.

## Failure Context

The first formal create attempt failed safely:

```text
open /usr/local/bin/xray: read-only file system
```

The Worker systemd unit used:

```text
User=root
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true
```

With `ProtectSystem=full`, `/usr` and `/etc` are mounted read-only for the
Worker process unless explicitly allowed. The root filesystem itself was not
read-only; the failure came from the Worker sandbox.

Post-failure checks confirmed there was no unsafe residue:

- `27939/TCP` was not listening
- `liveline-xray.service` did not exist
- `/usr/local/bin/xray` did not exist
- `/usr/local/etc/liveline-xray` did not exist
- `/etc/systemd/system/liveline-xray.service` did not exist
- no node row was created
- `node.share_link` was not written

## Hotfix

The Worker no longer writes Xray to `/usr/local/bin` or LiveLine config to
`/usr/local/etc/liveline-xray`.

The new LiveLine-owned paths are:

```text
/opt/liveline-xray/bin/xray
/opt/liveline-xray/config/config.json
/opt/liveline-xray/state
```

The managed service remains:

```text
/etc/systemd/system/liveline-xray.service
```

Its `ExecStart` is now:

```text
/opt/liveline-xray/bin/xray run -config /opt/liveline-xray/config/config.json
```

## Worker Sandbox

The Worker install script keeps the existing hardening:

```text
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true
```

It adds only the minimum write allowance needed for this controlled flow:

```text
ReadWritePaths=/opt/liveline-xray /etc/systemd/system /run/systemd
```

It does not broadly open `/usr`, `/etc`, or `/`.

## Preflight / Guard Changes

Formal creation still requires all Stage 3.3.37 guards:

- approved server only
- approved port `27939/TCP` only
- all second confirmations
- clean `landing_preflight`
- `27939/TCP` not listening
- Xray absent
- no existing Xray config
- Worker role `landing`
- Worker interface `ens17`
- Worker version supporting `landing_node_create`

Stage 3.3.37-b also checks the new LiveLine paths before execution:

```text
/opt/liveline-xray
/opt/liveline-xray/bin
/opt/liveline-xray/bin/xray
/opt/liveline-xray/config
/opt/liveline-xray/config/config.json
/opt/liveline-xray/state
/etc/systemd/system/liveline-xray.service
```

The Worker still checks legacy / existing Xray paths:

```text
/usr/local/bin/xray
/usr/bin/xray
/usr/local/etc/liveline-xray/config.json
/usr/local/etc/liveline-xray
/usr/local/etc/xray/config.json
/etc/xray/config.json
/etc/systemd/system/xray.service
/etc/systemd/system/x-ui.service
/etc/systemd/system/3x-ui.service
```

If any of those paths already exist before the current run, the Worker refuses
to execute.

## Rollback Boundary

Rollback may remove only files and directories created by the current run:

- `/opt/liveline-xray/bin/xray`
- `/opt/liveline-xray/config/config.json`
- `/opt/liveline-xray/state` if created by the current run
- empty `/opt/liveline-xray/config`, `/opt/liveline-xray/bin`, and
  `/opt/liveline-xray` directories only if created by the current run
- `/etc/systemd/system/liveline-xray.service` if created by the current run

Rollback must not remove unknown Xray files, unknown service files, non-LiveLine
managed files, or any user-managed config.

## Modified Files

- `worker/cmd/liveline-worker/main.go`
  - upgrades Worker version to `0.1.5-stage-3.3.37`
  - moves Xray binary/config paths to `/opt/liveline-xray`
  - checks new and legacy paths in preflight
  - writes service `ExecStart` with the new binary/config paths
  - limits rollback to current-run artifacts
- `backend/app/api/routes/workers.py`
  - adds minimal Worker unit `ReadWritePaths`
- `backend/app/services/landing_node_create.py`
  - updates backend-managed Xray config path
- `backend/app/services/worker_targeting.py`
  - requires Worker version `0.1.5-stage-3.3.37` for `landing_node_create`
- `backend/worker-binaries/liveline-worker-linux-amd64`
  - rebuilt Linux amd64 Worker binary
- `README.md`
  - records Stage 3.3.37-b scope

## Safety Boundary

This stage does not:

- execute SSH
- execute remote commands
- deploy the public console
- connect to the landing VPS
- trigger `landing_node_create`
- install Xray
- create nodes
- add listening ports
- modify firewall / cloud security group rules
- modify `node.share_link`
- generate a real node link
- perform cutover

## Validation Checklist

- `git diff --check`
- `python3 -m compileall backend/app`
- `go test ./...`
- `go build ./...`
- `docker compose exec -T frontend npm run build`
- `docker compose up --build -d`
- `curl -s http://127.0.0.1:8000/api/health`
- `curl -I http://127.0.0.1:3000`
- Redis `temp_credential:*` count is `0`
- pending / running tasks count is `0`
- `landing_node_create` command count does not increase during this stage
- sensitive scan finds no real token, password, `SESSION_SECRET`,
  Reality privateKey, complete `vless://` node link, or complete Worker token

## Conclusion

Stage 3.3.37-b prepares a safer Worker execution environment by moving
LiveLine-managed Xray files to `/opt/liveline-xray` and by giving the Worker
only the minimum systemd sandbox write paths required for a future explicitly
approved formal create retry.
