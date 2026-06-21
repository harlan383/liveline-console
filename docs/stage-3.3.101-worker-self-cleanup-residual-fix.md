# Stage 3.3.101 Worker Self-Cleanup Residual Fix

## Stage Background

Stage 3.3.97 implemented protected remote cleanup delete flows. Stage 3.3.99 upgraded the landing and transit Workers to:

```text
0.1.21-stage-3.3.97
```

Stage 3.3.100 recorded the final cleanup approval checklist. After that approval, the user executed protected delete actions from the page for the transit server and landing server.

This stage fixes a residual Worker state issue observed after the real cleanup flow. It does not execute SSH, does not stop remote Workers manually, and does not create new cleanup commands.

## Successfully Cleaned Resources

### Transit Route

```text
route_id = d10d3dcc-679f-4f85-ae37-9e5dfa37e6af
name = hk-socat-live-23843
status = deleted
deleted_at = 2026-06-21 04:31:33.602957+00
listen_port = 23843
has_share_link = false
```

### Transit Server

```text
transit_resource_id = 1e222459-9fa2-4c62-800f-a3b35edb7df8
name = 香港中转服务器
entry_host = 163.223.216.108
status = deleted
deleted_at = 2026-06-21 04:31:33.61448+00
```

### Direct Landing Node

```text
node_id = a71472c6-f62c-43b5-a223-9f5f070ae4ef
node_name = liveline-reality-27939
xray_port = 27939
status = deleted
deleted_at = 2026-06-21 04:35:38.323332+00
has_share_link = true
share_link_length = 250
```

The full node link was not read or recorded.

### Landing Server

```text
vps_id = 968519b3-9017-4b27-a9a0-d5731033f84f
name = 香港15m落地
ip = 64.90.13.19
status = deleted
```

## Worker Command Results

### Transit Resource Cleanup

```text
command_id = 8c9956d9-2410-4c8e-b044-6416c771642b
command_type = cleanup_transit_resource
status = succeeded
result_status = succeeded
cleanup_type = cleanup_transit_resource
system_record_deleted = true
completed_at = 2026-06-21 04:31:33.614773+00
```

### Landing Server Cleanup

```text
command_id = d96c2857-13ec-4d8e-b205-293df6ff0d10
command_type = cleanup_landing_server
status = succeeded
result_status = succeeded
cleanup_type = cleanup_landing_server
system_record_deleted = true
completed_at = 2026-06-21 04:35:38.326711+00
```

## Residual Worker Problem

Although both server-level cleanup commands succeeded and their system records were soft-deleted, both remote Workers continued to send heartbeats afterwards.

Observed residual state:

```text
transit Worker = online, systemd active, worker_version = 0.1.21-stage-3.3.97
landing Worker = online, systemd active, worker_version = 0.1.21-stage-3.3.97
```

The cleanup command results did not include explicit Worker self-cleanup status:

```text
worker_cleanup_status = empty
worker_self_cleanup_status = empty
```

This created two related problems:

- a Worker already marked `deleted` or expected to go offline could heartbeat and be revived to `online`
- a server-level cleanup result could look fully successful even when Worker self-cleanup evidence was missing

## Cause Assessment

The backend heartbeat route always set authenticated Workers to:

```text
status = online
```

That was correct for ordinary Workers, but unsafe after protected cleanup because a deleted or cleanup-expected Worker should not become a normal online Worker again.

The remote cleanup result normalizer also returned an empty `worker_self_cleanup` object when the Worker result did not include self-cleanup details. That made missing self-cleanup evidence too easy to overlook.

## Code Fixes

### Heartbeat State Guard

The heartbeat route now detects either condition:

```text
worker.status = deleted
metadata_json.cleanup_status = cleanup_expected_offline
```

When either condition is true:

- `worker.status` is preserved
- `last_heartbeat_at` may still update
- redacted `latest_status` is recorded
- `metadata_json.unexpected_heartbeat_after_cleanup = true` is recorded
- `metadata_json.unexpected_heartbeat_at` is recorded
- bound resource status is not synced back to online

Ordinary active Workers still heartbeat normally and become `online`.

### Cleanup Result Normalization

For server-level cleanup command types:

```text
cleanup_landing_server
cleanup_transit_resource
```

the normalized result now includes Worker self-cleanup status:

```text
worker_cleanup_status
worker_self_cleanup_status
```

If Worker self-cleanup information is absent, both fields are marked:

```text
missing
```

If Worker self-cleanup was explicitly scheduled, both fields are marked:

```text
scheduled
```

This does not rewrite historical command results. It applies to newly ingested results after this fix.

## Tests Added

New backend tests cover:

- deleted Worker heartbeat does not revive the Worker to `online`
- `cleanup_expected_offline` Worker heartbeat does not become ordinary `online`
- normal Worker heartbeat still sets `online` and syncs the bound resource
- server-level cleanup missing Worker self-cleanup data is marked `missing`
- server-level cleanup with scheduled self-cleanup data is marked `scheduled`
- persisted landing-server cleanup results retain the missing Worker cleanup status when evidence is absent

## Safety Boundary

Stage 3.3.101 did not perform these actions:

- No SSH was executed.
- No remote VPS was logged into.
- No remote Worker was manually stopped.
- No Worker service was manually deleted.
- No new cleanup command was created.
- No resource was deleted or restored.
- No deleted resource was revived.
- No Xray service was stopped.
- No socat service was stopped.
- No complete `nodes.share_link` was read.
- No complete client link was generated or recorded.
- No `nodes.share_link` was modified.
- No `transit_routes.share_link` was written.
- No firewall, cloud firewall, or cloud security group was modified.
- No physical database record was deleted.

## Follow-Up Manual Residual Cleanup Conditions

Manual residual Worker cleanup should be a separate explicitly approved stage.

Before any manual residual cleanup:

- confirm both server records remain deleted
- confirm no cleanup command is pending, claimed, or running
- confirm no new LiveLine resource has been attached to the same Worker
- confirm the operator accepts that the Worker service may be stopped or removed
- do not print Worker secrets, tokens, private keys, full node links, or database passwords

Until then, the backend should treat post-cleanup heartbeat as an unexpected residual signal, not as a normal online managed Worker.

## Validation

Validation performed for this code/documentation stage:

```text
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
docker compose run --rm backend python -m unittest discover -s tests
```

Frontend build and Worker Go tests are not required because this stage does not change frontend code or Worker code.
