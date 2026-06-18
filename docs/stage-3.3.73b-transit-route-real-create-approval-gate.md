# Stage 3.3.73b Transit Route Real Create Approval Gate

## Stage Goal

Stage 3.3.73b records the real-create approval gate for the approved Hong Kong
`socat` transit route candidate. It is intentionally an execution gate and not a
real execution.

The current code still blocks non-dry-run `transit_route_create` commands at
both the backend API and Worker layers. This stage keeps that safety boundary in
place until the operator provides the Stage 3.3.73 readonly evidence and then
explicitly approves real execution.

## Current Decision

Current status: **No-Go for real creation**.

Reason: Stage 3.3.73 requires fresh readonly evidence before any real creation
stage. The operator has asked to enter 3.3.73b, but the readonly evidence bundle
has not yet been recorded in this repository.

## Approved Route Candidate

The only candidate covered by this gate is:

| Field | Value |
| --- | --- |
| transit resource id | `1e222459-9fa2-4c62-800f-a3b35edb7df8` |
| transit hostname | `WEPC202605221223335` |
| transit Worker id | `f2e16197-e953-46dd-90af-66f64759a2a9` |
| transit Worker role | `transit` |
| transit interface | `eth0` |
| landing node id | `a71472c6-f62c-43b5-a223-9f5f070ae4ef` |
| landing target host | `64.90.13.19` |
| landing target port | `27939` |
| planned listen port | `23843/TCP` |
| forwarding method | `socat` |
| route name | `hk-socat-live-23843` |

## Required Evidence Before Go

All of the following must be captured before a later stage may create a
non-dry-run command:

### Public Console Database Checks

Expected evidence from the public console PostgreSQL database:

```sql
SELECT id, command_type, status, worker_id, server_type, server_id, attempts,
       created_at, claimed_at, completed_at
FROM worker_commands
WHERE status IN ('pending', 'running', 'claimed')
ORDER BY created_at DESC;
```

Expected result:

```text
0 rows
```

```sql
SELECT id, role, status, server_id, hostname, interface_name,
       worker_version, last_heartbeat_at
FROM workers
WHERE id = 'f2e16197-e953-46dd-90af-66f64759a2a9';
```

Expected result:

```text
role = transit
status = online
server_id = 1e222459-9fa2-4c62-800f-a3b35edb7df8
hostname = WEPC202605221223335
interface_name = eth0
worker_version >= 0.1.18-stage-3.3.72
last_heartbeat_at is fresh
```

```sql
SELECT id, name, listen_port, target_host, target_port, forwarding_method,
       status, created_at
FROM transit_routes
WHERE transit_resource_id = '1e222459-9fa2-4c62-800f-a3b35edb7df8'
  AND listen_port = 23843
  AND deleted_at IS NULL
ORDER BY created_at DESC;
```

Expected result:

```text
0 rows
```

### Hong Kong Transit Host Readonly Checks

Expected evidence from the Hong Kong transit server:

```bash
hostname
systemctl is-active liveline-worker
/usr/local/bin/liveline-worker --version
ss -lntp | grep ':23843 ' || true
nc -vz -w 5 64.90.13.19 27939
```

Expected result:

```text
hostname = WEPC202605221223335
liveline-worker = active
liveline-worker --version = 0.1.18-stage-3.3.72 or newer
23843/TCP = not listening
64.90.13.19:27939 = TCP reachable
```

### Firewall / Cloud Confirmation

The operator must explicitly confirm all three of these before Go:

```text
cloud security group allows 23843/TCP
cloud firewall allows 23843/TCP
server firewall allows 23843/TCP or has no blocking rule
```

## Required Human Approval Phrase

A later execution stage must not proceed unless the operator explicitly provides
this approval phrase after all readonly evidence is captured:

```text
批准执行真实创建 23843/TCP 香港 socat 中转链路；不读取或修改 nodes.share_link；不生成完整节点链接；不 cutover。
```

## Code Boundary Observed At Entry

At entry to this stage, real creation remains blocked by code:

- Backend `/api/transit-routes/worker-create-plan` requires `dry_run=true`.
- Worker `transit_route_create` validation rejects `dry_run=false`.
- Worker dry-run returns `real_execution=false` and does not write systemd
  service files, start `socat`, bind a listener, or create a real route.

This stage does not change those code boundaries.

## No-Go Conditions

Do not proceed to real execution if any of the following is true:

- any pending/running/claimed command exists unexpectedly,
- a `transit_routes` row already exists for `23843`,
- Hong Kong Worker is offline,
- Worker role, interface, hostname, or version is not as expected,
- `23843/TCP` is already occupied,
- `64.90.13.19:27939` is not reachable from Hong Kong,
- any firewall confirmation is missing,
- the exact human approval phrase has not been provided,
- the requested action includes reading/modifying `nodes.share_link`, generating
  a full client link, modifying Xray, or performing cutover.

## Safety Boundary

This stage does not:

- trigger any Worker command,
- create a real transit route,
- create a `transit_routes` row,
- bind `23843/TCP`,
- create or edit systemd service files,
- install, start, stop, restart, or enable `socat` / `gost`,
- modify firewall, cloud firewall, or cloud security group rules,
- modify Xray,
- read, output, or modify `nodes.share_link`,
- generate or display a full client link,
- perform cutover,
- deploy the public console,
- rebuild containers,
- change public console local `docker-compose.yml` port mappings.

## Next Stage

If all readonly evidence is provided and the exact human approval phrase is
recorded, the next possible stage is:

`Stage 3.3.73c-transit-route-real-create-implementation-gate`

That later stage may add the minimum non-dry-run code path or trigger a real
execution only after the Go evidence is complete. It must still preserve the
boundaries: no `nodes.share_link` read/write, no full client link generation, no
Xray mutation, and no cutover.
