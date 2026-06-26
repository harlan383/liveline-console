# Stage 3.3.189 Transit Route Real-Create Follow-Up Flow Fix

## Goal

Fix the HAProxy TCP transit route create flow after Stage 3.3.188. A successful
dry-run command must not be treated as a create failure. The UI now stops at an
explicit confirmation point:

```text
dry-run succeeded + final approval ready
=> 预检成功，等待确认真实创建
=> user clicks 确认真实创建
=> backend creates haproxy_route_create_real_execution Worker command
```

## Frontend Flow

- The simplified transit route create modal runs readiness approval, dry-run,
  and final approval.
- When final approval returns `ready_for_real_create=true`, the modal displays
  `预检成功，等待确认真实创建`.
- The modal shows a `确认真实创建` action.
- The real execution API is called only after that explicit action.
- The previous `HAProxy TCP 真实创建命令未返回` state is no longer used for a
  successful dry-run / final approval checkpoint.

## Backend Real-Create Contract

The real execution endpoint creates a new `transit_route_create` Worker command
only when the source dry-run command is valid:

- `status == succeeded`
- `command_intent == haproxy_route_create_dry_run`
- dry-run command worker matches the current selected transit Worker
- `planned_listen_port` matches the real request
- `approved_planned_listen_port == planned_listen_port`
- `landing_target_port` matches the real request
- `approved_landing_target_port == landing_target_port`
- `approved_firewall_confirmation == true`

The generated real command payload explicitly includes:

```text
command_intent = haproxy_route_create_real_execution
execution_mode = real_create
dry_run = false
real_execution = true
approved_real_execution = true
forwarding_method = haproxy_tcp
approved_planned_listen_port = planned_listen_port
approved_firewall_confirmation = true
approved_landing_target_host = landing_target_host
approved_landing_target_port = landing_target_port
route_created = false
listener_bound = false
share_link_mutated = false
cutover = false
```

## Safety Boundary

This stage does not:

- modify Worker code
- change Worker version
- rebuild the bundled Worker binary
- create a real transit route during development
- add a real listener
- modify HAProxy config
- start, stop, or restart HAProxy
- run SSH or remote commands
- cut over traffic
- write `transit_routes.share_link`
- output a full share link
- modify firewall, cloud security group, or cloud firewall
- modify `docker-compose.yml`
- commit `.bak` files

## Validation

Required validation:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
cd frontend && node node_modules/next/dist/bin/next build
```
