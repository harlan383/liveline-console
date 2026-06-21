# Stage 3.3.113 Generalize Protected Transit Route Create Approval

## Goal

Stage 3.3.113 generalizes the protected `transit_route_create` approval path so it no longer depends on the historical Hong Kong transit resource id, landing node id, or Worker id.

The route create path is still protected. This stage does not turn transit creation into an arbitrary remote execution feature.

## Production Symptom Recorded

Stage 3.3.111 made the UI run:

```text
transit_readonly_preflight -> worker-create-execute -> poll -> refresh -> transient export
```

The current production test reached a successful `transit_readonly_preflight`, but no new `transit_route_create` command was created. The likely blocker was backend approval code still locked to the historical transit resource, landing node, route name, and Worker id while the current records use a new `worker_online` transit resource and a new active landing node.

## Guard Changes

The backend now allows a protected transit create approval when all of these conditions are true:

- The transit resource exists, is not deleted, has `resource_type=server`, and is `active` or `worker_online`.
- The landing node exists, is not deleted, is `active`, has target port `27939`, and already has a generated share link.
- The planned listen port is still the protected approved port `23843/TCP`.
- The forwarding method is still `socat`.
- The requested target host and port match the active landing node.
- A recent successful `transit_readonly_preflight` exists for the same transit resource, landing node, listen port, target host, target port, and forwarding method.
- The selected transit Worker is online, supports `transit_route_create`, is bound to the selected transit resource, has role `transit`, and its interface matches the successful preflight result.
- There is no existing non-deleted `creating` or `active` transit route using the same transit resource and listen port.
- There is no pending/running/claimed `transit_route_create` command for the same transit resource.

## What Changed

- `worker-create-execute` now validates the current resource, node, Worker binding, and matching readonly preflight dynamically.
- The result persistence path now creates the `transit_routes` row from the command payload and Worker result instead of hardcoded historical ids.
- The route name can be dynamic, but it is limited to safe characters: letters, numbers, dots, underscores, and hyphens.
- The persisted route still stores `share_link=NULL`.
- Frontend error copy now explains dynamic preflight, Worker binding, and interface mismatch failures more clearly.

## What Did Not Change

- No SSH was executed.
- No remote command was executed.
- No Worker command was created by this stage.
- No transit route was created by this stage.
- No socat/gost/Xray service was installed, restarted, stopped, or deleted.
- No firewall, cloud firewall, or security group was modified.
- No `nodes.share_link` value was read into docs, logs, tests, or PR text.
- No `nodes.share_link` or `transit_routes.share_link` value was mutated.
- No full VLESS/V2Ray client link was generated or recorded.
- No cutover occurred.

## Safety Boundary

The generalized approval remains intentionally narrow:

- Protected listen port: `23843/TCP`.
- Protected target port: `27939/TCP`.
- Forwarding method: `socat` only.
- Worker command type: `transit_route_create`.
- Worker payload: structured fields only, no arbitrary shell and no arbitrary systemd unit.
- Route persistence: only after Worker reports `execution_mode=real_create`, `real_execution=true`, and `status=succeeded`.
- Link storage: `transit_routes.share_link` remains `NULL`; candidate links remain transient export only.

## Validation

Planned validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- `docker compose build backend frontend`
- `docker compose run --rm backend python -m unittest discover tests`
- `docker compose exec -T frontend npm run build`

This stage changes backend approval logic, frontend error copy, tests, and documentation. It does not modify Worker source or Worker binaries.
