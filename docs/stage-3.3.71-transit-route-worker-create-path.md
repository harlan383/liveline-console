# Stage 3.3.71 Transit Route Worker Create Path

## Stage Goal

Add the controlled Worker/API path required before creating the approved Hong
Kong transit route. This stage intentionally stops at dry-run planning and does
not create the real route.

Stage 3.3.70 recorded the approval packet. Stage 3.3.71 adds the missing safe
code path so a future execution stage can use Worker/API guardrails instead of
legacy SSH/RQ or manual remote commands.

## Why This Stage Exists

The existing `POST /api/transit-routes` route is a legacy SSH/RQ path. It
requires temporary SSH credentials, relies on `resource.status == active`, and
is bound to older accepted-resource constraints. It is not suitable for the
current Worker-online transit resource:

`1e222459-9fa2-4c62-800f-a3b35edb7df8`

Direct SSH or manual systemd commands would bypass LiveLine's API, Worker,
audit, database state, and rollback model. This stage therefore adds a
dedicated Worker command type and backend entry point for the Worker-online
flow.

## Implemented Scope

- Added Worker command type: `transit_route_create`.
- Added backend endpoint: `POST /api/transit-routes/worker-create-plan`.
- Added backend validation for the Stage 3.3.70 approved parameters.
- Added a Worker dry-run handler for `transit_route_create`.
- Added tests for command registration, schema boundaries, Worker dry-run
  output, and Worker rejection of unsafe or non-approved payloads.
- Updated README stage status.

## Approved Context

The dry-run create path is locked to the approved Stage 3.3.70 values:

| Field | Value |
| --- | --- |
| transit resource id | `1e222459-9fa2-4c62-800f-a3b35edb7df8` |
| transit resource name | `香港中转服务器` |
| transit host | `163.223.216.108` |
| transit hostname | `WEPC202605221223335` |
| transit interface | `eth0` |
| landing node id | `a71472c6-f62c-43b5-a223-9f5f070ae4ef` |
| landing node name | `liveline-reality-27939` |
| landing target host | `64.90.13.19` |
| landing target port | `27939` |
| planned listen port | `23843/TCP` |
| forwarding method | `socat` |
| purpose | `直播` |

## Backend Guardrails

The backend dry-run endpoint requires:

- admin session and CSRF validation,
- `dry_run=true`,
- `approval_required=true`,
- explicit confirmation that this stage does not read or modify
  `nodes.share_link`,
- explicit confirmation that this stage is not cutover,
- exact approved transit resource id,
- exact approved landing node id,
- exact approved listen port `23843`,
- exact approved landing target `64.90.13.19:27939`,
- forwarding method `socat`,
- an online transit Worker that supports `transit_route_create`,
- an active landing node with matching IP and port,
- no existing creating/active route on the same transit resource and port,
- a matching successful `transit_readonly_preflight` record.

The generic admin Worker command endpoint rejects `transit_route_create`, so
operators cannot bypass this dedicated validation path with arbitrary payloads.

## Worker Guardrails

The Worker dry-run handler:

- requires transit role,
- requires the approved Stage 3.3.71 approval stage,
- requires `dry_run=true`,
- requires `approval_required=true`,
- rejects arbitrary shell fields,
- rejects arbitrary command arguments,
- rejects arbitrary systemd unit content,
- rejects non-approved ports,
- rejects non-approved landing targets,
- rejects non-`socat` forwarding methods,
- returns only planned actions and safety boundaries.

The Worker dry-run does not:

- write systemd service files,
- install, start, stop, restart, or enable `socat` / `gost`,
- bind `23843/TCP`,
- modify firewall, cloud firewall, or cloud security group rules,
- modify Xray,
- read or modify `nodes.share_link`,
- generate or display a real client link,
- perform cutover.

## Dry-Run Result Shape

The Worker dry-run returns a compact result containing:

- `execution_mode= dry_run`,
- `real_execution=false`,
- planned service name,
- planned service path,
- planned listen port,
- target host and port,
- forwarding method,
- planned action list,
- passed guardrail checks,
- safety boundary,
- next stage suggestion.

It deliberately does not include full client links, `nodes.share_link`, Worker
secrets, tokens, SSH private keys, or provider credentials.

## No Real Creation Statement

This stage does not create a transit route. It does not create a database
`transit_routes` row for the planned route, does not create a systemd service,
does not start `socat`, does not add a listener, and does not change firewall
rules.

## Next Stage

The next possible stage is:

`Stage 3.3.72-transit-route-create-execution`

That stage must require fresh explicit user authorization before any real
Worker execution, route persistence, service creation, listener binding, or
post-create verification.
