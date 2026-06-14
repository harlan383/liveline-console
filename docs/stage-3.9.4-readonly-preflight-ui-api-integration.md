# Stage 3.9.4 Readonly Preflight UI API Integration

## Current Stage Conclusion

Stage 3.9.4 connects the frontend readonly preflight planning area to the
Stage 3.9.2 local no-op API.

Implementation result: the UI can request and display the backend no-op
readonly preflight plan. Remote execution remains No-Go.

This stage does not execute SSH, execute remote commands, connect to remote
servers, create real forwarding, add real listening ports, modify
`node.share_link`, trigger backend tasks, or perform cutover. It does not
affect the current `socat` 18443 formal link or the `gost` 8443 fallback link.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## No-op API Path

`POST /api/transit-routes/readonly-preflight-plan`

The endpoint remains login protected and side-effect free. It validates local
planning input and returns a readonly preflight plan only.

## Modified Files

| File | Change |
| --- | --- |
| `frontend/lib/api.ts` | Added readonly preflight request, response, check item types, and a request helper |
| `frontend/components/TransitRoutesPanel.tsx` | Connected the readonly preflight UI to the no-op API and added response rendering |
| `frontend/app/globals.css` | Added small styles for the no-op API result and check cards |
| `README.md` | Added Stage 3.9.4 scope and status |
| `docs/stage-3.9.4-readonly-preflight-ui-api-integration.md` | Added this implementation record |

Backend code was not changed.

## Frontend Display Fields

The readonly preflight area now displays the backend response fields:

- `status`
- `ready`
- `blocked`
- `summary`
- `next_action`
- `checks`
- `safety_boundary`
- `redacted_summary`

The button text is `校验只读预检计划`. It does not use wording that suggests
remote execution, real forwarding creation, line enabling, configuration
application, or formal cutover.

## Checks Display Rules

Each check item displays:

- label
- id
- status
- category
- passed
- message
- evidence_summary
- next_action
- sensitive_output_redacted

Future checks are visually marked as `future check / not executed`. The UI also
states that those checks were not remotely executed in this stage.

## Ready / Blocked / No-Go Display Rules

- `status=blocked` shows a blocked pill and the backend No-Go summary.
- `status=no_go` shows a warning pill and the backend next action.
- `ready=true` shows a ready pill but also warns that Ready only means the
  plan can enter readonly preflight approval.

Ready does not mean remote commands can be executed. Ready does not mean real
forwarding can be created. Ready does not mean `node.share_link` can be
modified.

## Request Mapping

The frontend sends only local planning values:

- selected transit resource id and display name
- selected landing node id and display name
- non-secret host hints already visible in the local UI
- planned listen port
- landing target port
- route purpose
- firewall confirmation booleans
- local backup confirmation
- no-cutover confirmation
- no-`node.share_link`-change confirmation
- future Workbuddy authorization boundary confirmation

The request does not include passwords, SSH keys, passphrases, tokens, complete
node links, or complete `node.share_link` values.

## Safety Boundary

The UI continues to state:

- This stage does not execute SSH.
- This stage does not connect to remote servers.
- This stage does not execute remote commands.
- This stage does not create real forwarding.
- This stage does not add real listening ports.
- This stage does not modify `node.share_link`.
- This stage does not perform cutover.
- This stage does not need Workbuddy.
- Real remote readonly preflight must enter a separately authorized stage.

## Port And Link Protection

The UI continues to remind the operator:

- `8443` is reserved for the `gost` fallback link.
- `18443` is the current `socat` formal link.
- `22` is a management port.
- `20575` and existing internal/system ports must not be reused casually.
- Before adding or changing a listening port, confirm the cloud security group,
  cloud firewall, and server firewall allow the corresponding TCP port.

## No-side-effect Guarantee

This stage preserves the no-op API boundary:

- No database route record is created.
- No task is created.
- No Redis temporary credential is written.
- No SSH is executed.
- No remote command is executed.
- No remote server is connected.
- No real forwarding is created.
- No real listening port is added.
- `node.share_link` is not read or modified.
- No cutover is performed.

## Validation Notes

Required local validation for this stage:

- `npm run build` passes.
- `docker compose up --build -d` passes.
- `/api/health` reports backend, database, redis, and worker healthy.
- `http://localhost:3000` is reachable.
- Unauthenticated access to the no-op API still returns `401`.
- Local no-op planner calls return blocked / No-Go for protected ports.
- Local no-op planner calls can return `ready=true` only when local
  confirmations are present.
- Redis `temp_credential:*` remains `0`.
- pending / running tasks remain `0`.

Browser verification requires entering the real password only in the browser.
The real password must not be written to terminal commands, docs, logs,
screenshots, or Git.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.9.4 because this stage only connects local
UI to a local no-op API.

Workbuddy or a separately authorized stage is needed for:

- Real SSH login.
- Real remote readonly preflight.
- Real remote port checks.
- Real `socat` or `gost` service checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback.

## Impact Summary

| Item | Result |
| --- | --- |
| Business logic modified | No |
| Frontend display modified | Yes |
| Backend interface added or modified | No |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` read or modified | No |
| Complete node link read or output | No |
| SSH or remote command executed | No |
| Remote server connected | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
