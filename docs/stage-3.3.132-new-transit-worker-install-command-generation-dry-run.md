# Stage 3.3.132 New Transit Worker Install Command Generation Dry-Run

## Goal

Stage 3.3.132 adds a no-real-VPS dry-run result view to the pending_worker
Transit Worker install approval preview.

The operator can type the Stage 3.3.131 confirmation phrase and then inspect a
structured dry-run result for a future Worker install command generation stage.
The result is deliberately limited to placeholders and checks.

## Implemented UI/API Changes

UI changes:

- The pending_worker Worker install approval preview now shows a
  typed-confirmation-gated dry-run area.
- The dry-run area appears only after the operator enters
  `CONFIRM_GENERATE_WORKER_INSTALL_COMMAND_LATER`.
- The dry-run area includes a structured result card, Go / No-Go checks, the
  placeholder command template, a copy dry-run result action, and a copy
  placeholder command template action.

API changes:

- None. This stage intentionally avoids backend changes.
- No token/bootstrap endpoint is called.
- No Worker command endpoint is called.
- No remote execution endpoint is called.

## Dry-Run Scope

The dry-run view records:

- `mode=dry_run`
- transit resource id, name, and status
- `role=transit`
- public controller URL: `http://my-con.golirong.xyz:8200`
- target Worker version: `0.1.24-stage-3.3.122`
- bundled Worker binary checksum:
  `cf7990f3ba0f85348fa714edb69a94d36b8752323fe9c843fa676cf50f38fcce`
- token status: `not_generated`
- install command status: `placeholder_only`
- remote execution: `disabled`
- Worker command created: `false`

The dry-run checks include typed confirmation, `pending_worker` status,
entry host presence, SSH metadata completeness or pending state, public
controller URL use, placeholder token retention, localhost/127.0.0.1 blocking,
and real token output blocking.

## Placeholder Command

The UI continues to show only the placeholder command template. The token remains
`<generated-in-later-stage>`, and the command is clearly marked as not executable
in this stage.

Allowed actions in this stage:

- copy dry-run result
- copy placeholder command template
- close preview

Not allowed in this stage:

- generate Worker token
- generate a real Worker install command
- install Worker
- create Worker command
- execute SSH or any remote command

## Backend Boundary

No backend API was added for this stage. The dry-run result is generated in the
frontend from already loaded resource metadata and fixed safety constants.

The UI does not call:

- `createTransitWorkerBootstrap`
- `regenerateTransitWorkerBootstrap`
- any Worker token/bootstrap API

## Safety Boundary

This stage did not:

- deploy the public controller
- require a real VPS
- run Docker Compose deployment commands
- SSH into any VPS
- execute remote commands
- generate Worker token
- generate a real Worker install command
- install Worker
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
- fake route availability

## Next Recommended Stage

Stage 3.3.133-new-transit-worker-install-command-generation-real-approval

If there is still no real VPS, the next stage should continue in dry-run mode.
If the operator wants to generate a real one-time Worker token and install
command, that must be approved explicitly in a separate stage, and it still must
not automatically SSH into or install Worker on a VPS.

## Validation

Local validation for this PR:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- frontend production build through the local bundled Node runtime because the
  Docker daemon was not running
- sensitive information scan for real tokens, SSH private keys, database
  passwords, full candidate links, full node links, and real `nodes.share_link`
  values
