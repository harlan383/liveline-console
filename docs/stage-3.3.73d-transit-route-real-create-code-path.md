# Stage 3.3.73d Transit Route Real Create Code Path

## Stage Goal

Stage 3.3.73d implements the controlled code path for the approved Hong Kong
`socat` transit route real-create command.

This stage only adds the backend API, Worker handler, result-ingest persistence,
tests, and Worker binary needed for a later production execution stage. It does
not trigger the command and does not create the real transit route.

## Approved Route

The code path is locked to the approved route parameters:

| Field | Value |
| --- | --- |
| transit resource id | `1e222459-9fa2-4c62-800f-a3b35edb7df8` |
| Worker id | `f2e16197-e953-46dd-90af-66f64759a2a9` |
| Worker interface | `eth0` |
| landing node id | `a71472c6-f62c-43b5-a223-9f5f070ae4ef` |
| listen port | `23843/TCP` |
| landing target | `64.90.13.19:27939` |
| forwarding method | `socat` |
| route name | `hk-socat-live-23843` |
| service name | `liveline-socat-23843.service` |
| service path | `/etc/systemd/system/liveline-socat-23843.service` |

## Backend Changes

The backend adds a real-create request schema and a dedicated endpoint:

```text
POST /api/transit-routes/worker-create-execute
```

The endpoint requires all explicit confirmations:

- `dry_run=false`
- `approval_required=false`
- `user_approved_real_execution=true`
- cloud security group confirmation
- cloud firewall confirmation
- server firewall confirmation
- no `nodes.share_link` read or modification confirmation
- no full client link confirmation
- no cutover confirmation

The endpoint validates the approved resource, node, Worker, interface, Worker
version, duplicate route state, successful readonly preflight evidence, and
absence of pending/running/claimed `transit_route_create` commands. It creates
only a Worker command. It does not create a `transit_routes` row directly.

## Worker Changes

The Worker version is upgraded to:

```text
0.1.19-stage-3.3.73
```

`transit_route_create` now branches by `dry_run`:

- `dry_run=true`: existing dry-run plan behavior.
- `dry_run=false`: approved real-create behavior.

The real-create branch revalidates the fixed route parameters, rejects unsafe
payload keys such as shell commands or systemd unit content, checks that
`23843/TCP` is not already listening, checks TCP reachability to the landing
target, writes only the fixed LiveLine-managed systemd service, starts it, and
verifies both service active state and listener state.

The Worker does not install `socat` or `gost`; `socat` must already exist. The
Worker does not modify firewall rules, Xray, landing node configuration, or
`nodes.share_link`.

## Result Ingest

When a `transit_route_create` Worker command returns:

```text
execution_mode=real_create
real_execution=true
status=succeeded
```

the backend creates exactly one `transit_routes` record for the approved route.
The persisted `share_link` field remains `NULL`; no node share link is read,
generated, exported, or modified.

If the approved `23843` route already exists, result ingest is idempotent and
does not insert a duplicate route.

## Safety Boundary

Stage 3.3.73d keeps these boundaries:

- no SSH or direct remote command execution from Codex
- no production deployment
- no Worker upgrade
- no Worker command trigger
- no real transit route creation in this stage
- no listener binding by this stage
- no firewall, cloud firewall, or cloud security group change
- no Xray modification
- no landing node configuration modification
- no `nodes.share_link` read or modification
- no full client link generation or display
- no cutover

## Next Stage

The real production deployment, Hong Kong Worker upgrade, and approved command
trigger must happen only in:

```text
Stage 3.3.73e-production-deploy-worker-upgrade-and-execute
```

That later stage requires explicit user authorization again.

## Validation Checklist

- `git diff --check`
- `git diff --cached --check`
- backend compileall for `backend/app`
- backend compileall for `backend/tests`
- backend unit tests
- `go test ./...`
- `go build ./...`
- Linux amd64 Worker binary rebuilt
- frontend build if frontend files change
- sensitive scan for Worker secrets, tokens, database passwords, SSH private
  keys, complete proxy links, and real `nodes.share_link` values
