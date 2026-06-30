# Stage 3.4.20 Advanced Debug HAProxy Protected Runtime Readiness

## Scope

Stage 3.4.20 adds a read-only backend runtime readiness gate for the advanced-debug HAProxy TCP real-execution chain.

This stage does not change ordinary product frontend UI. It does not change database schema, Worker binaries, deployment configuration, or live infrastructure.

## Endpoint

New endpoint:

- `POST /api/transit-routes/haproxy-route-real-execution-readiness`

The endpoint:

- Requires an admin session.
- Requires CSRF validation.
- Uses the same request payload shape as the protected HAProxy real execution endpoint.
- Returns readiness status, checks, `final_approval_text`, and dynamic `expected_real_execution_text`.
- Is read-only.
- Does not create Worker commands.
- Does not create `TransitRoute` records.
- Does not commit, flush, refresh, or audit-write database changes.

## Readiness Checks

The readiness gate verifies:

- The dry-run command exists and has status `succeeded`.
- The dry-run command type, server type, server id, command intent, approval stage, and dry-run flags are valid.
- The dry-run Worker matches the current transit Worker.
- Request parameters match the dry-run payload, including planned listen port, approved planned listen port, landing target host/port, forwarding method, route name, route display name when present, and planned service name.
- The transit resource exists and is not deleted.
- The transit Worker is online, has role `transit`, supports HAProxy TCP, and has reported `interface_name`.
- The landing node exists, is not deleted, and is `active`.
- The landing target host matches the current landing VPS IP.
- The landing target port matches the current landing node port.
- The forwarding method is `haproxy_tcp`.
- The planned listen port is not reserved.
- No creating/active HAProxy route already exists for the same transit resource and listen port.
- No duplicate real execution command already exists for the same planned route.
- Cloud security group, cloud firewall, and server firewall confirmations are present.
- No-cutover, no-node-share-link mutation, and no-full-client-link confirmations are present.
- The final approval text is correct.
- The real execution text matches `CONFIRM_REAL_HAPROXY_ROUTE_CREATE_<planned_listen_port>`.

## Safety Boundary

This stage does not:

- Change ordinary product UI.
- SSH to any server.
- Execute remote commands.
- Create Worker commands through the readiness endpoint.
- Create HAProxy routes.
- Create `TransitRoute` active records.
- Install, start, stop, restart, or configure HAProxy.
- Bind listeners.
- Modify firewalls, cloud firewalls, or cloud security groups.
- Read or write `nodes.share_link`.
- Write `transit_routes.share_link`.
- Export a full client link.
- Perform cutover.
- Add database migrations.
- Modify Worker binaries.
- Modify `docker-compose.yml`.

## Validation

Required validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- `PYTHONPATH=backend python3 -m unittest backend.tests.test_stage_3_4_20_haproxy_runtime_readiness`
- Docker backend unittest fallback if local Python dependencies are unavailable and Docker is running
- Staged diff sensitive scan

Frontend build is not required because this stage does not change frontend files.
