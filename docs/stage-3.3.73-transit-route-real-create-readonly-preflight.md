# Stage 3.3.73 Transit Route Real Create Readonly Preflight

## Stage Goal

Stage 3.3.73 is the final readonly preflight and approval packet before any
future real creation of the approved Hong Kong `socat` transit route.

This stage intentionally does not create the real route. It records the exact
production baseline, the required readonly checks, and the explicit approval
boundary that must be satisfied before a later execution stage can trigger a
non-dry-run `transit_route_create` command.

## Current Baseline

The current production and repository baseline is:

| Field | Value |
| --- | --- |
| GitHub main commit before this stage | `66c95c5896e8794e2a9ac796de5906b4f074cdd2` |
| Latest completed stage before this preflight | `Stage 3.3.72d-worker-result-large-post-timeout-hotfix` |
| Public console directory | `/opt/liveline-console` |
| Public frontend | `http://my-con.golirong.xyz:3200` |
| Public backend | `http://my-con.golirong.xyz:8200` |
| Worker binary version | `0.1.18-stage-3.3.72` |
| Hong Kong Worker id | `f2e16197-e953-46dd-90af-66f64759a2a9` |
| Hong Kong Worker role | `transit` |
| Hong Kong Worker interface | `eth0` |
| Hong Kong Worker status | `online` |

The public console still keeps local deployment-only `docker-compose.yml` port
mapping changes and a backup file. These local deployment changes must not be
restored or deleted by this stage.

## Approved Route Context

The only route candidate covered by this stage is the existing approved Hong
Kong transit route candidate:

| Field | Value |
| --- | --- |
| transit resource id | `1e222459-9fa2-4c62-800f-a3b35edb7df8` |
| transit hostname | `WEPC202605221223335` |
| transit role | `transit` |
| transit interface | `eth0` |
| landing node id | `a71472c6-f62c-43b5-a223-9f5f070ae4ef` |
| landing target host | `64.90.13.19` |
| landing target port | `27939` |
| planned listen port | `23843/TCP` |
| forwarding method | `socat` |
| route name | `hk-socat-live-23843` |
| purpose | `直播` |

## Prior Evidence

Stage 3.3.72d production validation confirmed:

| Check | Result |
| --- | --- |
| Hong Kong Worker upgraded | `0.1.18-stage-3.3.72` |
| Worker heartbeat | success |
| Worker command polling | success |
| `transit_route_create` dry-run command | `succeeded` |
| dry-run attempts | `1` |
| dry-run command id | `1bb45bd1-5e4f-4ae2-b4a2-02ba793edbec` |
| dry-run execution mode | `dry_run` |
| dry-run real execution | `false` |
| dry-run planned listen port | `23843` |
| dry-run target | `64.90.13.19:27939` |
| dry-run forwarding method | `socat` |
| `transit_routes` row for `23843` | `0 rows` |

The Worker-to-console result path was also validated after compacting the
dry-run result payload. The Hong Kong to public console path showed a practical
large POST body threshold around `1.2 KB`; Stage 3.3.72d keeps
`transit_route_create` result and failure payloads compact enough for that path.

## Readonly Checks Required In This Stage

Before any later real creation stage, the operator must re-check all of the
following in readonly mode:

1. No pending, running, or claimed `worker_commands` exist for the Hong Kong
   transit Worker.
2. No active or creating `transit_routes` row exists for transit resource
   `1e222459-9fa2-4c62-800f-a3b35edb7df8` on listen port `23843`.
3. The Hong Kong Worker is still `online`.
4. The Hong Kong Worker version is still `0.1.18-stage-3.3.72` or newer.
5. The Hong Kong Worker role is still `transit`.
6. The Hong Kong Worker interface is still `eth0`.
7. The Hong Kong machine still has no local listener occupying `23843/TCP`.
8. The Hong Kong machine can still reach `64.90.13.19:27939` over TCP.
9. Cloud security group for the Hong Kong transit server allows `23843/TCP`.
10. Cloud firewall for the Hong Kong transit server allows `23843/TCP`.
11. Local server firewall allows `23843/TCP`, or there is no blocking rule.
12. The public console backend and frontend health checks still pass.

## Suggested Readonly SQL Checks

Run these from the public console environment only. They are readonly selects.

```sql
SELECT id, command_type, status, worker_id, server_type, server_id, attempts,
       created_at, claimed_at, completed_at
FROM worker_commands
WHERE status IN ('pending', 'running', 'claimed')
ORDER BY created_at DESC;
```

```sql
SELECT id, role, status, server_id, hostname, interface_name,
       worker_version, last_heartbeat_at
FROM workers
WHERE id = 'f2e16197-e953-46dd-90af-66f64759a2a9';
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

## Suggested Transit Host Readonly Checks

Run these on the Hong Kong transit server only. They must not start, stop,
restart, install, write, or delete anything.

```bash
hostname
systemctl is-active liveline-worker
/usr/local/bin/liveline-worker --version
ss -lntp | grep ':23843 ' || true
nc -vz -w 5 64.90.13.19 27939
```

The expected readonly result before execution approval is:

- Worker service is active.
- Worker version is `0.1.18-stage-3.3.72` or newer.
- `23843/TCP` is not listening.
- TCP reachability to `64.90.13.19:27939` succeeds.

## Explicit No-Go Conditions

Do not proceed to a later real execution stage if any of these are true:

- `23843/TCP` is already occupied on the Hong Kong server.
- Any active or creating `transit_routes` row already uses port `23843` for the
  approved transit resource.
- Any `worker_commands` row is pending, running, or claimed unexpectedly.
- The Hong Kong Worker is offline or reports the wrong role/interface.
- The Hong Kong Worker version is older than `0.1.18-stage-3.3.72`.
- The Hong Kong host cannot reach `64.90.13.19:27939`.
- Cloud security group, cloud firewall, or local firewall status for `23843/TCP`
  is not confirmed.
- The operator has not explicitly approved the next real execution stage.

## Safety Boundary

This stage does not:

- trigger a Worker command,
- create a real transit route,
- insert a `transit_routes` row,
- bind `23843/TCP`,
- create or edit systemd service files,
- install, start, stop, restart, or enable `socat` / `gost`,
- modify Xray,
- modify firewall, cloud firewall, or cloud security group rules,
- read, output, or modify `nodes.share_link`,
- generate or display a full client link,
- perform cutover,
- change deployment port mappings,
- restore or delete the public console's local `docker-compose.yml` changes.

## Sensitive Information Policy

Do not paste or commit:

- Worker secrets,
- API tokens,
- database passwords,
- SSH private keys,
- cloud provider credentials,
- full `vless://` or other client links,
- `nodes.share_link` values,
- screenshots containing complete node links.

## Approval Handoff

If every readonly check passes, the next possible stage is:

`Stage 3.3.73b-transit-route-real-create-approved-execution`

That later stage still requires a fresh explicit user approval before any
non-dry-run Worker command, service creation, listener binding, route
persistence, post-create verification, or client-side validation is allowed.
