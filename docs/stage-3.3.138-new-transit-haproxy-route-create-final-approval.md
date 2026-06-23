# Stage 3.3.138 New Transit HAProxy Route Create Final Approval

## Stage Goal

Stage 3.3.138 adds the final approval package after a successful HAProxy TCP route create dry-run.

This stage is not real execution. It only reads the Stage 3.3.137 dry-run command summary, rechecks current transit resource / Worker / landing node state, compares planned route fields, and returns a Go / No-Go approval package.

## Prerequisites From Stage 3.3.137

The final approval package depends on:

- Stage 3.3.137 dry-run command exists.
- Dry-run command payload is a HAProxy route create dry-run.
- `dry_run=true`
- `real_execution=false`
- `route_created=false`
- `listener_bound=false`
- Planned service name, listen port, target host/port, forwarding method, and route name match the final approval request.

Recorded dry-run evidence:

- Planned service: `liveline-haproxy-23843.service`
- Planned listen: `23843`
- Target: `64.90.13.19:27939`
- Forwarding method: `haproxy_tcp`
- Route name: `haproxy-tcp-23843`

## Final Approval API / UI Behavior

The backend adds:

- `TransitHaproxyRouteCreateFinalApprovalRequest`
- `POST /api/transit-routes/haproxy-route-create-final-approval`

The endpoint is read-only. It does not call `create_worker_command`, does not add or commit database records, does not create a `TransitRoute`, and does not read or return full client links.

The transit routes advanced panel now shows `HAProxy route 创建最终审批` under the dry-run result. The operator must enter the typed confirmation before generating the approval package.

## Final Approval Typed Confirmation

The required text is:

```text
CONFIRM_HAPROXY_ROUTE_CREATE_FINAL_APPROVAL_ONLY
```

This text authorizes only the final approval package. It does not authorize real execution.

## Go / No-Go Checks

The final approval package checks:

- Dry-run command exists.
- Dry-run command status is readable.
- Dry-run command payload shape is valid.
- Final approval request matches dry-run payload.
- Transit resource exists and is not deleted.
- Transit Worker is online.
- Worker role is `transit`.
- Worker version supports HAProxy TCP.
- Worker `interface_name` is present.
- Landing node exists and is not deleted.
- Landing target host matches the current landing node host.
- Landing target port matches the current landing node port.
- Forwarding method is `haproxy_tcp`.
- Cloud security group confirmation is present.
- Cloud firewall confirmation is present.
- Server firewall confirmation is present.
- No cutover confirmation is present.
- No `nodes.share_link` mutation confirmation is present.
- No full client link export confirmation is present.
- Final typed confirmation matches.

The response returns:

- `ready_for_real_create`
- `blocked`
- `summary`
- `next_action`
- `checks`
- `safety_boundary`
- `next_stage`

When all checks pass, the next stage is:

- `Stage 3.3.139-new-transit-haproxy-route-create-real-execution`

## Port / Firewall / Security Group Final Reminders

Before any future real execution, the operator must still confirm:

- The planned HAProxy TCP listen port is allowed in the cloud security group.
- The planned HAProxy TCP listen port is allowed in the cloud firewall.
- The planned HAProxy TCP listen port is allowed by the server local firewall.

This stage does not perform those remote checks and does not change firewall state.

## Safety Boundary

Stage 3.3.138 does not:

- Create a Worker command
- Create a real execution command
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
- Fake Worker online, HAProxy ready, route active, or line usable status

The response explicitly reports no production mutation:

- `worker_command_created=false`
- `real_execution_command_created=false`
- `route_created=false`
- `transit_route_active_record_created=false`
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
- Backend tests covering dry-run command mismatch, missing confirmations, and read-only success
- Frontend production build
- Sensitive information scan

## Next Recommended Stage

Recommended next stage:

- `Stage 3.3.139-new-transit-haproxy-route-create-real-execution`

That stage must obtain explicit user approval before creating a real Worker execution command or remote HAProxy service.
