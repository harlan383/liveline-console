# Stage 3.3.99 Remote Worker Upgrade To 0.1.21

## Stage Goal

Stage 3.3.99 records the remote LiveLine Worker upgrade required after Stage 3.3.97 protected remote cleanup support.

The target Worker version is:

```text
0.1.21-stage-3.3.97
```

This stage is a result record only. It does not create cleanup commands, does not run protected cleanup, and does not delete production resources.

## Public Console Version

The public console main commit used for this stage:

```text
4012e738d71d8251283a7b489ade4c825f3369dd
```

## Upgrade Targets

### Landing Worker

```text
worker_id = 3d7c1bfa-7af6-4f16-848a-08ea6beb9990
server_id = 968519b3-9017-4b27-a9a0-d5731033f84f
hostname = ser685297596046
interface_name = ens17
role = landing
```

Upgrade result:

```text
before = 0.1.6-stage-3.3.37
after = 0.1.21-stage-3.3.97
status = online
last_heartbeat_at = 2026-06-20 15:59:37.476242+00
```

### Transit Worker

```text
worker_id = f2e16197-e953-46dd-90af-66f64759a2a9
server_id = 1e222459-9fa2-4c62-800f-a3b35edb7df8
hostname = WEPC202605221223335
interface_name = eth0
role = transit
```

Upgrade result:

```text
before = 0.1.20-stage-3.3.73
after = 0.1.21-stage-3.3.97
status = online
last_heartbeat_at = 2026-06-20 15:59:52.68498+00
```

## Upgrade Actions Already Completed

The upgrade was completed manually before this record stage:

- Old Worker binaries were backed up.
- `/usr/local/bin/liveline-worker` was replaced on both Worker hosts.
- `liveline-worker.service` was restarted on both Worker hosts.
- Both Workers sent heartbeats successfully.
- Heartbeat submission returned `response_status=200`.

## Protected Cleanup Readiness

Both remote Workers now satisfy the Stage 3.3.97 minimum version gate for:

```text
cleanup_landing_node
cleanup_landing_server
cleanup_transit_route
cleanup_transit_resource
```

This only records version readiness. It does not authorize or execute cleanup.

## Safety Boundary

Stage 3.3.99 did not perform these actions:

- No cleanup Worker command was created.
- No remote cleanup was executed.
- No production resource was deleted.
- No node record was deleted.
- No transit route record was deleted.
- No landing VPS or transit resource record was deleted.
- No Xray service was stopped or deleted.
- No Xray configuration was deleted.
- No socat service was stopped or deleted.
- No Worker was cleaned up or deleted.
- No cutover occurred.
- No complete `nodes.share_link` was read or exported.
- No `nodes.share_link` was modified.
- No `transit_routes.share_link` was written.
- No complete client link was generated or recorded.
- No firewall, cloud firewall, or cloud security group was modified.

This record stage only updates documentation and README status.

## Validation

Required local validation for this documentation-only stage:

```text
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app
```

Full backend unittest, frontend build, and Worker Go tests are not required for this stage because no backend, frontend, Worker, or database code was changed.
