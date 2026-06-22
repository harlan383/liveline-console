# Stage 3.3.135 New Transit Worker Manual Install And Heartbeat Acceptance

## Stage Goal

Stage 3.3.135 adds read-only acceptance checks for a transit Worker after the
operator manually installs it on a real test transit VPS.

Stage 3.3.134 added the protected path for generating a one-time Worker token
and install command. The actual command content is not included in this
document. The command must be copied only by the operator from the authenticated
console page and executed manually on the intended test transit VPS.

## Manual Install Boundary

This stage does not install Worker. It records and implements only the
acceptance check after a user-performed install.

The expected human process is:

1. Generate the one-time Worker install command from the authenticated console.
2. Copy it only to the real test transit VPS terminal.
3. Do not execute it on the public controller VPS.
4. Do not paste it into README, docs, PRs, chat, logs, screenshots, or notes.
5. Return to the console and click `刷新 Worker 验收状态`.

## Acceptance API / UI

Backend:

- Adds `GET /api/transit-resources/{resource_id}/worker-acceptance`.
- Requires an admin session.
- Accepts only non-deleted `server` transit resources with status
  `pending_worker`, `worker_online`, or `worker_offline`.
- Reads the latest Worker bound to the transit resource.
- Returns role, version, heartbeat, binding, checklist, summary, and next action.

Frontend:

- Adds `手动安装与心跳验收` to the Worker install approval modal.
- Adds `刷新 Worker 验收状态`.
- Displays expected role `transit`.
- Displays expected Worker version `0.1.24-stage-3.3.122`.
- Displays found Worker details, heartbeat state, binding state, and acceptance
  result.

## Acceptance Checks

The acceptance result includes:

- `manual_install_command_was_user_executed`
- `worker_record_found`
- `server_binding_ok`
- `role_ok`
- `heartbeat_ok`
- `version_ok`
- `interface_detected`
- `token_not_exposed`
- `remote_execution_not_performed`
- `worker_command_not_created`
- `haproxy_not_created`

## Accepted Criteria

The acceptance is marked passed only when all of these are true:

- a Worker record is found for the transit resource
- `Worker.server_id` equals the current transit resource id
- `Worker.role` is `transit`
- `worker_runtime_status(worker)` is `online`
- `Worker.worker_version` exactly equals `0.1.24-stage-3.3.122`

The version comparison is intentionally conservative in this stage: exact match
only. Later stages can generalize version comparison if needed.

## Safety Boundary

This stage does not:

- include the install command content
- record Worker token
- SSH into any VPS
- execute remote commands
- install Worker
- create Worker command
- create HAProxy route
- install HAProxy
- modify socat
- modify Xray
- modify firewall, cloud security group, or cloud firewall
- cutover
- read, print, or record full `nodes.share_link`
- write `transit_routes.share_link`
- output full VLESS/V2Ray links
- fake Worker online state
- fake HAProxy ready state
- fake route active or line usable state

## Validation

Local validation for this PR:

- `git diff --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- frontend production build through the local bundled Node runtime because
  `npm` is not available in the local shell
- backend unit tests were attempted with system Python, but the local Python
  environment lacks FastAPI / SQLAlchemy dependencies
- Docker-based backend tests were attempted, but the Docker daemon was not
  running
- sensitive scan for real tokens, private keys, full proxy links, install
  commands, and full share links

## Next Recommended Stage

Stage 3.3.136-new-transit-haproxy-readiness-and-route-create-approval
