# Stage 3.9.2 Readonly Preflight No-op API Scaffold

## Current Stage Conclusion

Stage 3.9.2 adds a local no-op backend API scaffold for the future single-route
readonly preflight flow.

Implementation result: scaffold added; remote execution remains No-Go.

The new API validates local input and returns a readonly preflight plan with
Go / No-Go state, redacted summary text, check items, and safety boundaries. It
does not create database records, create tasks, write temporary credentials,
execute SSH, execute remote commands, connect to remote servers, create real
forwarding, add real listening ports, modify `node.share_link`, or perform
cutover.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Modified Files

| File | Change |
| --- | --- |
| `backend/app/schemas/transit_route.py` | Added request, response, and check item schemas for the no-op readonly preflight plan |
| `backend/app/api/routes/transit_routes.py` | Added `POST /api/transit-routes/readonly-preflight-plan` and pure in-memory plan builder helpers |
| `README.md` | Added Stage 3.9.2 scope and status |
| `docs/stage-3.9.2-readonly-preflight-noop-api-scaffold.md` | Added this implementation record |

## API Path

`POST /api/transit-routes/readonly-preflight-plan`

The endpoint is protected by the existing admin session check. Unauthenticated
requests return `401`.

The endpoint does not require SSH credentials, does not write Redis temporary
credentials, and does not enqueue Worker/RQ tasks.

## Request Schema

`ReadonlyPreflightPlanRequest` fields:

| Field | Required | Notes |
| --- | --- | --- |
| `transit_resource_id` | No | Selected transit resource id |
| `transit_resource_name` | No | Display name for redacted summary |
| `transit_host_hint` | No | Display hint only; never used as a real connection target |
| `landing_node_id` | No | Selected landing node id |
| `landing_node_name` | No | Display name for redacted summary |
| `landing_host_hint` | No | Display hint only; never used as a real connection target |
| `landing_target_port` | No | Integer-like TCP port, validated locally |
| `planned_listen_port` | No | Integer-like TCP port, validated locally |
| `route_purpose` | No | Local summary text |
| `firewall_security_group_confirmed` | Yes | Defaults to `false` |
| `cloud_firewall_confirmed` | Yes | Defaults to `false` |
| `server_firewall_confirmed` | Yes | Defaults to `false` |
| `local_backup_confirmed` | Yes | Defaults to `false` |
| `user_approved_readonly_preflight` | Yes | Defaults to `false` |
| `workbuddy_authorized` | Yes | Defaults to `false` |
| `no_cutover_confirmed` | Yes | Defaults to `false` |
| `no_node_share_link_change_confirmed` | Yes | Defaults to `false` |

The request must not include real passwords, tokens, SSH keys, passphrases,
complete node links, or complete `node.share_link` values.

## Response Schema

`ReadonlyPreflightPlanResponse` fields:

| Field | Meaning |
| --- | --- |
| `ready` | `true` only when all required local checks pass |
| `blocked` | `true` when the local plan is not ready |
| `status` | One of `ready`, `blocked`, or `no_go` |
| `summary` | Redacted human-readable summary |
| `next_action` | Redacted next step for the operator |
| `checks` | List of local and future check items |
| `safety_boundary` | Explicit no-side-effect safety boundary list |
| `redacted_summary` | Copyable redacted approval summary |

## Check Item Structure

Each check item contains:

- `id`
- `label`
- `category`
- `status`
- `passed`
- `message`
- `evidence_summary`
- `next_action`
- `sensitive_output_redacted`

Future remote checks are returned with `status=skipped`, `passed=false`, and a
message stating `future check / not executed in this stage`.

## Checks List

The endpoint returns at least these checks:

- `transit_resource_selected`
- `landing_node_selected`
- `planned_port_valid`
- `planned_port_not_reserved`
- `landing_target_port_valid`
- `firewall_confirmations_present`
- `local_backup_confirmed`
- `user_approved_readonly_preflight`
- `no_cutover_confirmed`
- `no_node_share_link_change_confirmed`
- `workbuddy_authorization_status`
- `future_transit_reachable`
- `future_planned_port_available`
- `future_formal_socat_18443_preserved`
- `future_fallback_gost_8443_preserved`
- `future_transit_to_landing_tcp_connectivity`

## Port Protection Rules

The endpoint keeps the same protected-port intent as the single-route create
safety gates:

- `planned_listen_port` must be an integer TCP port from `1` to `65535`.
- `8443` is blocked because it is retained for the `gost` fallback route.
- `18443` is blocked because it is the current formal `socat` route.
- `22` is blocked because it is a management port.
- `20575` is blocked because it is a historical/problem or existing-service
  port.
- Invalid or missing ports return a blocked / No-Go plan instead of triggering
  remote execution.

## Go / No-Go Rules

`ready=true` only when all required local checks pass:

- Transit resource is selected.
- Landing node is selected.
- Planned listen port is valid.
- Planned listen port is not protected.
- Landing target port is valid.
- Cloud security group is confirmed.
- Cloud firewall is confirmed.
- Server firewall is confirmed.
- Local database backup is confirmed.
- User has approved readonly preflight.
- Workbuddy authorization is present for a later execution stage.
- No-cutover boundary is confirmed.
- No-`node.share_link`-change boundary is confirmed.

Even when `ready=true`, the response text states that this only means
`Ready for readonly preflight approval / execution stage`. It does not mean
real forwarding can be created.

## No-side-effect Guarantee

This stage guarantees:

- No SSH execution.
- No remote command execution.
- No remote server connection.
- No task creation.
- No Redis temporary credential write.
- No database write.
- No route creation.
- No systemd service creation.
- No firewall modification.
- No real listening port creation.
- No complete node link generation.
- No `node.share_link` read or modification.
- No cutover.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.9.2 because the endpoint is local and
no-op.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login.
- Real remote read-only preflight.
- Real remote port checks.
- Real `socat` or `gost` service checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

## Safety Boundary

This stage maintains the following boundaries:

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH keys.
- Do not write passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not commit real database backup files.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not connect to remote servers.
- Do not trigger backend tasks.
- Do not modify firewall rules.
- Do not create real forwarding.
- Do not let `socat` take over 8443.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Validation Notes

Required validation for this stage:

- `python compileall backend/app` passes.
- `docker compose up --build -d` passes.
- `/api/health` reports backend, database, redis, and worker healthy.
- Unauthenticated `POST /api/transit-routes/readonly-preflight-plan` returns
  `401`.
- Logged-in test calls return blocked / No-Go for `8443`, `18443`, `22`, and
  `20575`.
- Logged-in test calls return No-Go when firewall / backup / authorization
  confirmations are missing.
- Logged-in test calls can return `ready=true` only for a safe port with all
  local confirmations present, and only as readiness for a later readonly
  preflight execution stage.

## Impact Summary

| Item | Result |
| --- | --- |
| Business logic modified | No |
| Backend interface added | Yes, no-op local plan endpoint |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` read or modified | No |
| Complete node link read or output | No |
| SSH or remote command executed | No |
| Remote server connected | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
