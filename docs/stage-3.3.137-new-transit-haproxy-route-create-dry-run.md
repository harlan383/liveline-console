# Stage 3.3.137 New Transit HAProxy Route Create Dry-Run

## Stage Goal

Stage 3.3.137 adds a HAProxy TCP route creation dry-run after the Stage 3.3.136 readiness approval package.

This stage may create a dry-run Worker command so the operator can inspect the planned service name, listen port, landing target, HAProxy TCP config summary, and safety boundary before any real route creation approval.

## Prerequisites From Stage 3.3.136

The dry-run path depends on the HAProxy readiness approval checks from Stage 3.3.136:

- Transit resource exists and is not deleted.
- Transit Worker is present, online, role `transit`, and supports HAProxy TCP mode.
- Worker `interface_name` is present.
- Landing node exists and is not deleted.
- Landing target port matches the selected landing node.
- Planned listen port is valid and not reserved.
- Forwarding method is `haproxy_tcp`.
- Cloud security group, cloud firewall, and server firewall confirmations are present.
- No cutover, no `nodes.share_link` mutation, and no full client link export are confirmed.

## Dry-Run API / UI Behavior

The backend adds:

- `TransitHaproxyRouteCreateDryRunRequest`
- `POST /api/transit-routes/haproxy-route-create-dry-run`

The frontend adds a `HAProxy route 创建 dry-run` panel under the HAProxy readiness approval panel. The panel can create a dry-run Worker command only after readiness is ready.

The UI displays:

- Transit resource
- Transit Worker online/version/interface information
- Landing node
- Planned listen port
- Landing target host/port
- Forwarding method `haproxy_tcp`
- Planned service name
- Safety boundary
- Dry-run command id after creation
- Next stage marker: `Stage 3.3.138-new-transit-haproxy-route-create-final-approval`

No real execution button is enabled in this stage.

## Dry-Run Worker Command Boundary

This stage can create a Worker command with:

- `command_type=transit_route_create`
- `payload.command_intent=haproxy_route_create_dry_run`
- `payload.dry_run=true`
- `payload.approval_required=true`
- `payload.user_approved_real_execution=false`
- `payload.real_execution=false`

The command payload contains only the planned route fields and summarized HAProxy TCP config plan. It does not contain a full client link or a full node share link.

## Planned Route Fields

The dry-run plan records:

- `route_name`
- `planned_service_name`
- `planned_listen_port`
- `landing_target_host`
- `landing_target_port`
- `forwarding_method=haproxy_tcp`
- `haproxy_config_plan.mode=tcp`
- `haproxy_config_plan.frontend_bind`
- `haproxy_config_plan.backend_target`

## Safety Boundary

Stage 3.3.137 does not:

- Create a real HAProxy route
- Create an active `TransitRoute` record
- Install HAProxy
- Start, stop, or restart HAProxy
- Bind a listener
- Modify firewall, cloud firewall, or cloud security group
- Execute SSH or any remote command
- Cut over traffic
- Read, print, or record full `nodes.share_link`
- Write `transit_routes.share_link`
- Generate, show, log, or document a full VLESS/V2Ray client link
- Fake Worker online, HAProxy ready, or route active status

The response explicitly reports:

- `dry_run=true`
- `real_execution=false`
- `route_created=false`
- `haproxy_installed=false`
- `listener_bound=false`
- `firewall_modified=false`
- `share_link_mutated=false`
- `cutover=false`

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- Backend tests covering readiness failures, missing confirmations, and dry-run command creation
- Frontend production build
- Sensitive information scan

## Next Recommended Stage

Recommended next stage:

- `Stage 3.3.138-new-transit-haproxy-route-create-final-approval`

That stage must obtain explicit user approval before any real Worker command or remote HAProxy service creation is allowed.
