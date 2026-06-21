# Stage 3.3.100 Protected Cleanup Final Approval

## Stage Goal

Stage 3.3.100 records the final approval checklist before any protected remote cleanup execution.

Stage 3.3.97 added the protected remote cleanup delete flow. Stage 3.3.99 upgraded both remote Workers to the required version:

```text
0.1.21-stage-3.3.97
```

The system is now technically ready to create cleanup Worker commands, but this stage does not create those commands and does not delete resources.

This stage only records:

- final cleanup target list
- readonly preflight results
- impact confirmation
- recommended execution order
- safety boundary
- next-stage execution conditions

## Planned Cleanup Targets

### Transit Route

```text
route_name = hk-socat-live-23843
route_id = d10d3dcc-679f-4f85-ae37-9e5dfa37e6af
entry = 163.223.216.108:23843
target = 64.90.13.19:27939
forwarding_method = socat
service_name = liveline-socat-23843.service
service_path = /etc/systemd/system/liveline-socat-23843.service
```

### Direct Landing Node

```text
node_name = liveline-reality-27939
node_id = a71472c6-f62c-43b5-a223-9f5f070ae4ef
landing_ip = 64.90.13.19
xray_port = 27939
```

### Transit Server

```text
transit_ip = 163.223.216.108
transit_resource_id = 1e222459-9fa2-4c62-800f-a3b35edb7df8
transit_worker_id = f2e16197-e953-46dd-90af-66f64759a2a9
transit_worker_version = 0.1.21-stage-3.3.97
```

### Landing Server

```text
landing_ip = 64.90.13.19
landing_server_id = 968519b3-9017-4b27-a9a0-d5731033f84f
landing_worker_id = 3d7c1bfa-7af6-4f16-848a-08ea6beb9990
landing_worker_version = 0.1.21-stage-3.3.97
```

## Readonly Preflight Result

Readonly preflight data for this approval record shows:

- landing Worker is online at `0.1.21-stage-3.3.97`
- transit Worker is online at `0.1.21-stage-3.3.97`
- target transit route is the LiveLine-managed socat route on `23843/TCP`
- target direct node is the LiveLine-managed landing Reality node on `27939/TCP`
- target transit server and landing server records are still the intended managed resources
- no complete node link was queried or recorded
- no `nodes.share_link` value was selected or exported
- no `transit_routes.share_link` value was selected or written

The expected safe readonly SQL shapes for any future re-check are:

```sql
SELECT id, role, status, server_id, hostname, interface_name, worker_version, last_heartbeat_at
FROM workers
ORDER BY role, last_heartbeat_at DESC;
```

```sql
SELECT id, name, status, deleted_at, transit_resource_id, listen_port, target_host, target_port, forwarding_method, service_name, service_path,
       (share_link IS NOT NULL) AS has_share_link
FROM transit_routes
WHERE id = 'd10d3dcc-679f-4f85-ae37-9e5dfa37e6af';
```

```sql
SELECT id, node_name, status, deleted_at, vps_id, xray_port, service_status, connectivity_status,
       (share_link IS NOT NULL) AS has_share_link,
       length(share_link) AS share_link_length
FROM nodes
WHERE id = 'a71472c6-f62c-43b5-a223-9f5f070ae4ef';
```

These queries intentionally avoid selecting complete share links.

## Recommended Execution Order

If the final goal is to clean all current formal resources, the recommended execution order is:

```text
1. Delete the transit server record through the protected remote cleanup flow.
   - This should cascade cleanup of hk-socat-live-23843.
   - This should clean the transit Worker.
   - This should soft-delete the transit route and transit resource records only after successful Worker cleanup.

2. Delete the landing server record through the protected remote cleanup flow.
   - This should cascade cleanup of liveline-reality-27939.
   - This should clean the landing Worker.
   - This should soft-delete the node and landing server records only after successful Worker cleanup.
```

This order avoids separately deleting the child route and node first, because server-level cleanup already owns those cascades.

## Real Cleanup Impact

If a later approved stage executes the cleanup:

- `163.223.216.108:23843` will stop working.
- `64.90.13.19:27939` will stop working.
- client-imported transit configurations will stop working.
- client-imported direct-node configurations will stop working.
- the Hong Kong transit VPS will no longer be managed by a LiveLine Worker.
- the landing VPS will no longer be managed by a LiveLine Worker.
- LiveLine Console will stop showing these resources after successful cleanup and soft-delete.

Remote VPS instances are not destroyed. Cloud servers are not released. Cloud security group, cloud firewall, and server firewall rules are not automatically removed by this cleanup plan.

## Safety Boundary

Stage 3.3.100 did not perform these actions:

- No cleanup Worker command was created.
- No `CONFIRM_REMOTE_DELETE` confirmation was entered.
- No delete confirmation was clicked.
- No remote cleanup was executed.
- No formal production resource was deleted.
- No Xray service was stopped.
- No Xray configuration was deleted.
- No socat service was stopped.
- No Worker was cleaned up.
- No cutover occurred.
- No complete `nodes.share_link` was read.
- No complete client link was exported.
- No `nodes.share_link` was modified.
- No `transit_routes.share_link` was written.
- No firewall, cloud firewall, or cloud security group was modified.
- No physical database record was deleted.

## Next Stage Execution Conditions

Any real cleanup execution must be a separate stage and must require explicit user approval.

The next stage should be named separately, for example:

```text
Stage 3.3.101-protected-cleanup-execution
```

Before execution, the operator must explicitly confirm:

- which server-level cleanup to run first
- that client connectivity through the current direct and transit paths may be broken
- that remote services may be stopped and removed by the protected cleanup Worker
- that cloud firewall and security group cleanup remains manual
- that no complete share links should be printed, logged, or documented

Without that explicit approval, cleanup remains No-Go.

## Validation

Required local validation for this documentation-only stage:

```text
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app
```

Full backend unittest, frontend build, and Worker Go tests are not required because this stage only changes README and documentation.
