# Stage 3.3.190 Remove Fixed HAProxy Real-Create Parameter Gate

## Goal

Remove the residual HAProxy TCP `real_create` fixed approved parameter gate.
The old gate only allowed the historical fixed route:

```text
planned_listen_port = 23843
landing_target_port = 27939
route_name = haproxy-tcp-23843
```

That conflicts with the dynamic approval model introduced in Stage 3.3.188 and
Stage 3.3.189.

## New Dynamic Approval Gate

The backend gate now validates the dynamic dry-run approval loop instead of
fixed values. Real execution is allowed only when all of the following hold:

- dry-run command status is `succeeded`
- dry-run command type is `transit_route_create`
- dry-run command intent is `haproxy_route_create_dry_run`
- dry-run forwarding method is `haproxy_tcp`
- dry-run flags show `dry_run=true`, `approval_required=true`, and `real_execution=false`
- dry-run Worker matches the current online transit Worker
- `planned_listen_port == approved_planned_listen_port`
- `landing_target_host == approved_landing_target_host`
- `landing_target_port == approved_landing_target_port`
- `approved_firewall_confirmation == true`
- request forwarding method is `haproxy_tcp`
- request firewall confirmations are present
- request no-cutover / no-share-link / no-full-link confirmations are present

The gate no longer requires the legacy `23843 -> 27939` route. Dynamic examples
such as `25867 -> 28917` can pass when the dry-run payload and real request
match exactly.

## Blocked Response

The blocked summary is now dynamic:

```text
HAProxy TCP real execution blocked by dynamic approval gate
```

The response check list identifies the specific dynamic approval mismatch, such
as missing `approved_planned_listen_port`, mismatched landing target port, missing
firewall confirmation, or a dry-run Worker mismatch.

## Worker Boundary

This stage does not modify Worker code, Worker version, or the bundled Worker
binary. Worker remains:

```text
0.1.36-stage-3.3.188-transit-port-approval
```

## Safety Boundary

This stage does not:

- create a real transit route
- add a real listener
- modify real HAProxy config
- start, stop, or restart HAProxy
- run SSH or remote commands
- cut over traffic
- write `transit_routes.share_link`
- output a full share link
- modify firewall, cloud security group, or cloud firewall
- modify `docker-compose.yml`
- commit `.bak` files
- modify Worker code
- upgrade Worker version
- rebuild the Worker binary

## Validation

Required validation:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
```
