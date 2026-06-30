# Stage 3.4.18 Transit HAProxy Backend Generalization

## Scope

Stage 3.4.18 generalizes the protected HAProxy TCP real-create backend approval flow so it is not bound to the historical `23843` test route confirmation text.

This stage is backend and documentation only. It does not change ordinary product UI pages, frontend layouts, Worker code, database schema, deployment configuration, or any real route execution behavior.

## Backend Change

The historical constant remains available for old runbooks:

- `HAPROXY_ROUTE_CREATE_REAL_EXECUTION_TEXT = "CONFIRM_REAL_HAPROXY_ROUTE_CREATE_23843"`

New HAProxy TCP real execution now uses a dynamic helper:

- `haproxy_real_execution_confirmation_text(planned_listen_port)`
- Expected text format: `CONFIRM_REAL_HAPROXY_ROUTE_CREATE_<planned_listen_port>`

The final approval endpoint now returns a non-secret expected text for the next step:

- `final_approval_text`
- `expected_real_execution_text`

The real execution endpoint validates `real_execution_text` against the dynamic text generated from the request `planned_listen_port`. A request for a non-23843 route no longer accepts the historical `CONFIRM_REAL_HAPROXY_ROUTE_CREATE_23843` text.

## Preserved Checks

The real execution endpoint keeps the existing strict safety gates:

- Dry-run command exists.
- Dry-run command status is `succeeded`.
- Dry-run command type and intent match HAProxy TCP dry-run.
- Dry-run Worker matches the current online transit Worker.
- Transit resource exists and is not deleted.
- Transit Worker is online, has transit role, and supports HAProxy TCP.
- Landing node exists, is active, and is not deleted.
- Landing target host and port match the selected landing node.
- `planned_listen_port` matches `approved_planned_listen_port`.
- `landing_target_host` matches `approved_landing_target_host`.
- `landing_target_port` matches `approved_landing_target_port`.
- Firewall confirmations are present.
- Final approval text is correct.
- Dynamic real execution text is correct.
- No active or creating duplicate HAProxy route exists for the same port.
- No duplicate real execution command exists for the same planned route.

## Safety Boundary

This stage does not:

- Create a real transit route.
- Create or bind a listener.
- Start, stop, or restart HAProxy.
- Modify HAProxy config.
- SSH to any server.
- Execute remote commands.
- Modify cloud security groups, cloud firewalls, or server firewalls.
- Modify `nodes.share_link`.
- Write `transit_routes.share_link`.
- Export a full client link.
- Perform cutover.
- Modify Worker code or rebuild Worker binaries.
- Add database migrations.
- Modify `docker-compose.yml`.
- Change ordinary product frontend UI.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- Targeted backend tests for HAProxy final approval and real execution approval gates

Frontend build is not required when no frontend files are changed.
