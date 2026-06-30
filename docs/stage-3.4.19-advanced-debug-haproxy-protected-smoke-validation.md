# Stage 3.4.19 Advanced Debug HAProxy Protected Smoke Validation

## Scope

Stage 3.4.19 adds backend smoke validation for the advanced-debug HAProxy TCP protected creation chain.

This stage changes only backend tests and documentation. It does not modify ordinary product frontend UI, production backend route logic, database schema, Worker binaries, deployment configuration, or live infrastructure.

## Validation Focus

The smoke validation covers:

- Dynamic real execution confirmation text for non-23843 ports.
- Final approval remains read-only and returns `expected_real_execution_text`.
- Legacy or wrong real execution text blocks dynamic-port real execution.
- Dry-run commands that are not `succeeded` block real execution.
- Existing active HAProxy routes block duplicate real execution.

The smoke uses fake DB/session objects and direct unit-level route calls. It does not call the live public control plane API.

## No Product UI Changes

No ordinary product frontend UI files are changed in this stage.

The product-facing pages remain stable. Any future real execution or technical workflow must stay in the advanced-debug area unless a separate product-stage approval says otherwise.

## No Live Execution

This stage does not:

- Send live API POST requests to create Worker commands.
- SSH to any server.
- Execute remote commands.
- Create HAProxy routes.
- Bind listeners.
- Modify firewalls, cloud firewalls, or cloud security groups.
- Perform cutover.

## Safety Boundary

This stage does not:

- Change ordinary product UI.
- Create real Worker commands in tests.
- Create `TransitRoute` active records.
- Start, stop, restart, or configure HAProxy.
- Bind a listener.
- Mutate firewall, cloud firewall, or cloud security group state.
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
- `PYTHONPATH=backend python3 -m unittest backend.tests.test_stage_3_4_19_haproxy_protected_smoke_validation`
- Docker backend unittest fallback if local Python dependencies are unavailable and Docker is running
- Staged diff sensitive scan

Frontend build is not required because this stage does not change frontend files.
