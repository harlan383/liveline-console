# Stage 3.3.163 HAProxy Delete Cleanup Risk Runbook

## Goal

Stage 3.3.163 records the risk checklist and rollback plan required before any future delete or remote cleanup test for the active HAProxy TCP route.

This stage is documentation only. It does not click delete, create cleanup commands, connect to any VPS, stop services, modify firewall rules, or change share links.

## Current Production Context

Current public controller:

- Path: `/opt/liveline-console`
- Frontend: `http://my-con.golirong.xyz:3200`
- Backend: `http://my-con.golirong.xyz:8200`
- Main commit at the snapshot time: `7b356e2`

Current active transit route:

- Route id: `28a9d585-4377-46f1-a1f3-dfd78c08616e`
- Name: `haproxy-tcp-23843`
- Status: `active`
- Forwarding method: `haproxy_tcp`
- Entry: `109.244.79.147:23843`
- Target: `64.90.13.19:27939`
- Service name: `liveline-haproxy-23843.service`
- Service path: `/etc/systemd/system/liveline-haproxy-23843.service`
- `transit_routes.share_link_present`: `false`
- `deleted_at`: empty

Current landing node:

- Node id: `7cf3ec9c-8e76-418e-97c1-5ee3ddb28e31`
- Node name: `liveline-reality-27939`
- Status: `active`
- Service status: `active`
- Connectivity status: `not_checked`
- Xray port: `27939`
- `nodes.share_link_present`: `true`
- `share_link_length`: `250`
- `deleted_at`: empty

Current Workers:

- Transit Worker: `e38707e2-20d5-4111-bbf1-b63adc767f3d`, hostname `MKiepl`, interface `eth0`, version `0.1.28-stage-3.3.152-haproxy-cleanup-support`, expected display status `online`
- Landing Worker: `bf7f9a90-e010-490b-8927-b2341d16485a`, hostname `ser685297596046`, interface `ens17`, version `0.1.22-stage-3.3.107`, expected display status `online`

## Why Delete Must Not Be Tested Directly Yet

`haproxy-tcp-23843` is the current real usable transit route. The user has verified that it can provide working client connectivity.

If remote cleanup succeeds, `109.244.79.147:23843` will stop working. A delete or cleanup test is therefore destructive and must not be attempted without a recovery plan, fresh read-only snapshots, and explicit user approval that temporary interruption of port `23843` is acceptable.

## Pre-Delete Snapshot Checklist

Before any future delete or remote cleanup test, collect the following read-only snapshots on the public controller.

```bash
cd /opt/liveline-console

docker compose exec -T postgres psql -U livelines -d livelines -c "
SELECT
  id,
  name,
  status,
  forwarding_method,
  listen_port,
  target_host,
  target_port,
  service_name,
  service_path,
  share_link IS NOT NULL AS share_link_present,
  updated_at,
  deleted_at
FROM transit_routes
WHERE id = '28a9d585-4377-46f1-a1f3-dfd78c08616e';
"

docker compose exec -T postgres psql -U livelines -d livelines -c "
SELECT
  id,
  command_type,
  status,
  server_type,
  server_id,
  created_at,
  claimed_at,
  completed_at
FROM worker_commands
WHERE status IN ('created','pending','claimed','running')
ORDER BY created_at DESC;
"

docker compose exec -T postgres psql -U livelines -d livelines -c "
SELECT
  id,
  role,
  status,
  server_id,
  hostname,
  interface_name,
  worker_version,
  last_heartbeat_at
FROM workers
ORDER BY last_heartbeat_at DESC NULLS LAST;
"
```

The snapshots must not select or print complete `nodes.share_link`, complete transient client links, Worker tokens, SSH keys, or other secrets.

## Future Remote Read-Only Checklist

This stage does not SSH or execute remote commands. Before a future destructive cleanup test, use a separately approved read-only stage to confirm the following objects exist on the transit VPS:

- systemd service: `liveline-haproxy-23843.service`
- service path: `/etc/systemd/system/liveline-haproxy-23843.service`
- config path: `/etc/haproxy/liveline/routes/liveline-haproxy-23843.cfg`
- listener: `0.0.0.0:23843` or `109.244.79.147:23843`

Do not proceed if the local database and remote read-only state disagree.

## UI Button Risk Guide

### Remote Cleanup Delete

Remote cleanup delete is destructive. It attempts to:

- stop the remote HAProxy service,
- delete the LiveLine-managed systemd unit,
- delete the LiveLine-managed HAProxy route config,
- release the remote listening port,
- soft-delete the system record only after cleanup succeeds.

Use this only when the user explicitly accepts that `109.244.79.147:23843` may become unavailable.

### Offline Local Remove

Offline local remove only changes the local LiveLine Console database record. It does not connect to the remote VPS, stop HAProxy, delete remote files, or release port `23843`.

If this is used while the remote service is still running, the remote listener may continue to exist while the local route record disappears. Recovery then requires careful read-only verification before any re-create or re-adoption step.

### Temporary Client Link Export

Temporary client link export only derives a client link for manual testing. It does not write `transit_routes.share_link`, does not modify `nodes.share_link`, does not create a Worker command, and does not cutover.

## Post-Delete Acceptance Criteria

If a future approved remote cleanup test is executed, success requires all of the following:

- the `transit_routes` record has `deleted_at` set and `status` is `deleted` or an equivalent deleted state,
- the corresponding cleanup Worker command is `succeeded`,
- the remote systemd service no longer exists or is inactive,
- remote port `23843` is no longer listening,
- `transit_routes.share_link` remains unwritten,
- `nodes.share_link` is unchanged.

If any item cannot be verified, treat the cleanup test as incomplete and stop.

## Failure Branches

Known failure causes include:

- Transit Worker offline
- Worker version too old
- Worker lacks write permission for `/etc/haproxy`
- systemd service missing
- HAProxy config missing
- port `23843` occupied by another process
- database record and remote state mismatch
- cleanup command timeout

Failure must not be papered over by local soft deletion unless the user explicitly chooses the offline local remove path after understanding that remote HAProxy may still be running.

## Recovery Plan

### Route A: Local Record Was Removed But Remote Service Still Exists

If only the local record was removed and the remote HAProxy service still exists:

- do not blindly create a new route on the same port,
- first confirm whether remote `23843` is still listening,
- decide whether to carefully restore or re-adopt the database record in a separately approved stage,
- avoid duplicate active records for the same transit resource and port.

### Route B: Remote Service Was Cleaned Up

If remote cleanup removed the service and config:

- recreate the HAProxy TCP route through the protected route creation flow,
- if reusing listen port `23843`, confirm cloud security group, cloud firewall, and server firewall still allow TCP `23843`,
- before create, confirm the same transit resource does not already have an active or creating `23843` route.

## Stop-Test Conditions

Stop immediately if any of the following is true:

- `worker_commands` has running, claimed, pending, or created commands,
- transit Worker is not online,
- `haproxy-tcp-23843` is not active before the test,
- `share_link` state is unexpected,
- UI button text does not clearly distinguish remote cleanup from offline local remove,
- the operator cannot confirm whether the action is remote cleanup or local remove,
- the user has not confirmed that temporary interruption of `23843` is acceptable.

## Safety Boundary

Stage 3.3.163 did not:

- click delete, remote cleanup, or offline local remove,
- create a new transit route,
- delete the existing `23843` route,
- modify the HAProxy route,
- create a Worker command,
- SSH or execute remote commands,
- cutover,
- write `transit_routes.share_link`,
- modify `nodes.share_link`,
- output a complete share link,
- modify firewall, cloud security group, or cloud firewall rules,
- add a listener,
- install or restart HAProxy, Xray, socat, or gost,
- modify public-controller `docker-compose.yml`,
- commit `.bak` files.
