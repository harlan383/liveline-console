# Stage 3.3.191 Transit Route Result Processor Dynamic Approval Fix

## Background

Stage 3.3.190 replaced the HAProxy TCP real-create API gate with dynamic approval
fields, so a real execution command can carry a user-approved listen port and
landing target instead of the old fixed `23843 -> 27939` pair.

Production testing then showed the real-create Worker command was generated with
matching dynamic approval fields, but the backend result processor still rejected
the command with `LISTEN_PORT_APPROVAL_MISMATCH`. The remaining fixed check lived
in `persist_successful_transit_route_create_result`.

## Fix

The result processor now validates the HAProxy TCP real-create command through a
dynamic approval loop:

- `command_intent == haproxy_route_create_real_execution`
- `execution_mode == real_create`
- `dry_run == false`
- `real_execution == true`
- `approved_real_execution == true`
- `planned_listen_port == approved_planned_listen_port`
- `landing_target_host == approved_landing_target_host`
- `landing_target_port == approved_landing_target_port`
- `approved_firewall_confirmation == true`

Worker result fields are then matched against the approved command payload:

- result listen port matches `planned_listen_port`
- result target port matches `landing_target_port`
- result forwarding method matches `haproxy_tcp`
- route name and LiveLine-managed service paths match the derived values

The processor no longer requires the legacy fixed `23843 -> 27939` route for
HAProxy TCP result persistence.

## Safety

The fix keeps the existing persistence safety boundary:

- successful Worker result is still required
- route persistence still requires matching command and result fields
- `transit_routes.share_link` remains `NULL`
- `nodes.share_link` is not modified
- no cutover is performed
- full client links are not logged or documented

This stage does not modify Worker code, Worker version, or the bundled Worker
binary.

## Validation

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`

No frontend files were changed, so frontend build was not required.

## Non-Actions

This stage did not:

- create a real transit route
- add a real listener
- modify HAProxy configuration
- start, stop, or restart HAProxy
- execute SSH or remote commands
- perform cutover
- write `transit_routes.share_link`
- output a full share link
- modify firewall, cloud security group, or cloud firewall rules
- modify `docker-compose.yml`
- modify Worker code
- rebuild the Worker binary
