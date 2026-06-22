# Stage 3.3.134 New Transit Worker Install Command Generation Execution

## Stage Goal

Stage 3.3.134 adds the approved generation path for a one-time Transit Worker
token and real install command for `pending_worker` transit resources.

This is command generation only. The generated command is displayed to the
logged-in operator for manual copy. This stage does not install Worker, does not
SSH into any VPS, does not create Worker command, and does not create HAProxy
routes.

## Implemented UI/API Changes

Backend:

- Added `POST /api/transit-resources/{resource_id}/worker-install-command`.
- The endpoint requires admin session, CSRF, and the typed confirmation:
  `CONFIRM_REAL_WORKER_INSTALL_COMMAND_GENERATION_NEXT_STAGE`.
- The endpoint only accepts non-deleted `server` transit resources with
  `status=pending_worker`.
- The endpoint requires `entry_host`.
- The endpoint uses the configured public controller URL and rejects localhost /
  127.0.0.1 through the existing Worker public URL guardrail.
- The endpoint revokes existing active transit Worker tokens for the resource
  before creating a new one-time token.
- The endpoint returns the install command in the response and stores only the
  token hash in the database through the existing Worker token model.

Frontend:

- Added a `生成一次性 Worker 安装命令` action after the Stage 3.3.133 final
  approval gate.
- The action is enabled only after the Stage 3.3.131 and Stage 3.3.133 typed
  confirmations are both satisfied for a `pending_worker` resource.
- The result panel shows resource name, status, controller URL, role, token
  expiry, the install command, and a copy action.
- The install command is held only in React state for the current page view. It
  is not written to localStorage, docs, README, PR, or logs.

## Generation Conditions

The UI and API require:

- resource status is `pending_worker`
- resource type is `server`
- resource has an `entry_host`
- public controller URL is configured and is not localhost / 127.0.0.1
- typed confirmation is exactly
  `CONFIRM_REAL_WORKER_INSTALL_COMMAND_GENERATION_NEXT_STAGE`
- no online transit Worker is already bound to the resource

## One-Time Token / Install Command Safety

Allowed in this stage:

- one-time Worker token generation after explicit approval
- real install command generation after explicit approval
- returning the command to the current logged-in operator for manual copy

Still forbidden in this stage:

- automatic Worker installation
- SSH or remote command execution
- Worker command creation
- HAProxy route creation
- HAProxy installation
- firewall / security group / cloud firewall mutation
- cutover
- full share_link exposure
- `transit_routes.share_link` write

The generated command contains a one-time token. It must not be copied into
README, docs, PR, chat, logs, notes, or screenshots.

## Safety Boundary

This stage did not:

- deploy the public controller
- install Worker
- execute SSH or any remote command
- create Worker command
- create a HAProxy route
- install HAProxy
- stop, restart, or delete socat
- modify Xray
- modify firewall, cloud security group, or cloud firewall
- cutover
- read, print, or record full `nodes.share_link`
- write `transit_routes.share_link`
- output full VLESS/V2Ray links
- fake Worker online state
- fake HAProxy readiness
- fake route active or line usable state

## Validation

Local validation for this PR:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- backend unit tests were attempted with system Python and bundled Python, but
  the local Python environments lack FastAPI / SQLAlchemy dependencies
- Docker-based backend unit tests were attempted, but the Docker daemon was not
  running
- frontend production build through the local bundled Node runtime because the
  Docker daemon was not running
- sensitive information scan for real tokens, SSH private keys, database
  passwords, full candidate links, full node links, and real `nodes.share_link`
  values

## Next Recommended Stage

Stage 3.3.135-new-transit-worker-manual-install-and-heartbeat-acceptance

In that later stage, the operator can manually copy the generated command to the
real test VPS, run it there, and then verify Worker heartbeat, version, role,
and server binding. That later stage still must not create HAProxy routes,
mutate firewall rules, cutover, or fake route readiness.
