# Stage 3.3.37-d Allow Empty LiveLine Xray Directory Hotfix

## Stage Goal

Stage 3.3.37-d fixes the formal landing-node create Worker preflight guard so
the Worker may proceed past an intentionally precreated empty
`/opt/liveline-xray` directory.

This stage is a code and documentation hotfix only. It does not trigger formal
landing-node creation.

## Background

Stage 3.3.37-c updated the Worker installer to precreate:

```text
/opt/liveline-xray
```

This directory is required by the hardened Worker systemd unit:

```text
ReadWritePaths=/opt/liveline-xray /etc/systemd/system /run/systemd
```

The previous formal-create preflight guard still rejected any existing
`/opt/liveline-xray` path. As a result, a safe empty directory created for the
Worker sandbox was treated as a conflict.

## Fix

The Worker preflight now allows `/opt/liveline-xray` only when:

- it is a directory; and
- it is empty; or
- it contains only known empty subdirectories such as `bin` and `config`.

The guard still rejects real Xray artifacts or unknown files.

## Paths That Still Block Execution

The Worker continues to reject formal creation if any of these paths exist:

```text
/opt/liveline-xray/bin/xray
/opt/liveline-xray/config/config.json
/opt/liveline-xray/state
/etc/systemd/system/liveline-xray.service
/usr/local/bin/xray
/usr/bin/xray
/usr/local/etc/xray/config.json
/etc/xray/config.json
/etc/systemd/system/xray.service
/etc/systemd/system/x-ui.service
/etc/systemd/system/3x-ui.service
```

The Worker also refuses `/opt/liveline-xray` when it contains unknown files,
symlinks, non-directory artifacts, or non-empty known subdirectories.

## Worker Version Boundary

The Worker version is raised to:

```text
0.1.6-stage-3.3.37
```

The backend `landing_node_create` minimum Worker version is raised to the same
version so older Workers with the old guard remain ineligible for formal
creation.

## Rollback Boundary

Rollback continues to clean up only artifacts created during the current run.
It must not remove unknown existing files, non-LiveLine files, or files not
tracked as current-run artifacts.

## Safety Boundary

This stage does not:

- execute SSH or remote commands
- connect to the public console VPS
- connect to the landing VPS
- trigger `landing_node_create`
- install Xray
- create nodes
- add listening ports
- modify firewall, cloud firewall, or cloud security group rules
- write `node.share_link`
- generate a real `vless://` link
- perform cutover

Existing historical failed records remain historical state. This stage does not
create a new `landing_node_create` record.

## Modified Files

- `worker/cmd/liveline-worker/main.go`
  - Raises Worker version to `0.1.6-stage-3.3.37`.
  - Allows an empty precreated `/opt/liveline-xray` directory.
  - Rejects real Xray artifacts and unknown files under `/opt/liveline-xray`.
- `worker/cmd/liveline-worker/main_test.go`
  - Adds tests for empty directory allowance and unknown artifact rejection.
- `backend/app/services/worker_targeting.py`
  - Raises the `landing_node_create` minimum Worker version to
    `0.1.6-stage-3.3.37`.
- `backend/worker-binaries/liveline-worker-linux-amd64`
  - Rebuilt Worker binary.
- `README.md`
  - Adds the Stage 3.3.37-d scope and stage status.
- `docs/stage-3.3.37-d-allow-empty-liveline-xray-dir-hotfix.md`
  - Records the issue, fix, validation boundary, and no-execution safety
    constraints.

## Validation Checklist

- `git diff --check`
- `python3 -m compileall backend/app`
- `go test ./...`
- `go build ./...`
- rebuild `backend/worker-binaries/liveline-worker-linux-amd64`
- `docker compose exec -T frontend npm run build`
- `docker compose up --build -d`
- `curl -s http://127.0.0.1:8000/api/health`
- `curl -I http://127.0.0.1:3000`
- Redis `temp_credential:*` remains `0`.
- Pending / running tasks remain `0`.
- `landing_node_create` does not get a new record.
- Sensitive scan finds no real token, password, `SESSION_SECRET`, Reality
  privateKey, complete `vless://` node link, or complete Worker token.
