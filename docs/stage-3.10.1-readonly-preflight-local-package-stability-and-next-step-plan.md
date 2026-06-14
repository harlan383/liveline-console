# Stage 3.10.1 Readonly Preflight Local Package Stability And Next-step Plan

## Current Stage Conclusion

Stage 3.10.1 archives the Stage 3.9 readonly preflight local package and
records the next-step plan.

Current conclusion: local readonly preflight capabilities are archived; remote
execution remains No-Go.

This stage is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, connect to remote servers, create
real forwarding, perform cutover, let `socat` take over 8443, or stop,
downgrade, or replace `gost` 8443.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Stage 3.9 Completed Capabilities

| Stage | Completed capability |
| --- | --- |
| Stage 3.9.1 Readonly preflight execution contract | Future request / response / result_data / checks contract archived |
| Stage 3.9.2 Readonly preflight no-op API scaffold | Local no-op API scaffold added for readonly preflight planning |
| Stage 3.9.3 Readonly preflight no-op API acceptance record | Local no-op API acceptance recorded |
| Stage 3.9.4 Readonly preflight UI API integration | Frontend readonly preflight area integrated with the no-op API |
| Stage 3.9.5 Readonly preflight UI API browser acceptance record | Browser manual acceptance recorded |

## Readonly Preflight Local Stability Baseline

The current local baseline includes:

- Future readonly preflight request, response, result_data, and checks contract
  exists.
- No-op API exists: `POST /api/transit-routes/readonly-preflight-plan`.
- No-op API is protected by login.
- No-op API returns `401` when unauthenticated.
- No-op API performs only local validation and plan generation.
- No-op API does not create tasks.
- No-op API does not write the database.
- No-op API does not execute SSH.
- No-op API does not connect to remote servers.
- No-op API does not create real forwarding.
- No-op API does not add real listening ports.
- No-op API does not modify `node.share_link`.
- Frontend is integrated with the no-op API.
- Frontend can display `ready`, `blocked`, and `no_go`.
- Frontend can display `checks`, `summary`, `next_action`,
  `safety_boundary`, and `redacted_summary`.
- Browser acceptance is recorded as passed.
- Real remote execution remains No-Go.

## Port Safety Baseline

- `8443` is reserved for the `gost` fallback link.
- `18443` is the current `socat` formal link.
- `22` and other management ports must not be used for business forwarding.
- `20575` and existing internal or system service ports must not be reused
  casually.
- A new listening port must be a valid TCP port from `1` to `65535`.
- Before adding or changing a listening port, the cloud security group must be
  confirmed to allow the corresponding TCP port.
- Before adding or changing a listening port, the cloud firewall must be
  confirmed to allow the corresponding TCP port.
- Before adding or changing a listening port, the server firewall must be
  confirmed to allow the corresponding TCP port.
- If port allowance is not confirmed, the project must not enter a real remote
  creation stage.

## Current Link Stability Baseline

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.10.1 does not modify `node.share_link`.
- Stage 3.10.1 does not add real listening ports.
- Stage 3.10.1 does not close, stop, downgrade, or replace `gost` 8443.
- Stage 3.10.1 does not let `socat` take over 8443.
- Stage 3.10.1 does not overwrite `socat` 18443.
- Stage 3.10.1 does not perform cutover.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.10.1 because this stage only archives local
readonly preflight capabilities and next-step planning.

Stage 3.9.1 through Stage 3.9.5 did not use Workbuddy to execute remote
commands.

Workbuddy or a separately authorized remote execution stage is required for:

- Real SSH login to a VPS or transit server.
- Real remote readonly preflight.
- Real remote port occupancy checks.
- Real `socat` or `gost` installation or service checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

## Future Stage Simplification Rules

To improve local development efficiency:

- Low-risk local code, UI, no-op API, and documentation archive work may be
  grouped into larger stages.
- Browser acceptance may be recorded in the same stage output when the work is
  local and low-risk.
- Stability archive content may be included at the end of a larger local stage.

The following work must continue to be split into explicit approval and
execution stages:

- Real remote operations.
- SSH execution.
- Remote readonly preflight.
- Real forwarding creation.
- Real diagnosis.
- Rollback.
- Any `node.share_link` modification.
- Any formal cutover.

When a stage involves adding or changing a listening port, it must remind the
operator to confirm the cloud security group, cloud firewall, and server
firewall for the corresponding TCP port.

When a stage involves `node.share_link`, it must enter a separate approval
stage.

When a stage involves `gost` 8443 or `socat` 18443, the fallback boundary must
remain explicit.

## Next-step Route A: No Real New Route For Now

If the user is not ready to create a real new route:

- Enter local system final stability acceptance.
- Archive local long-term usage instructions.
- Pause the remote execution line.
- Keep real remote execution No-Go.
- Keep `socat` 18443 as the formal link.
- Keep `gost` 8443 as the fallback link.

## Next-step Route B: Future Real New Route

If the user later wants to create a real new route:

- Specify the target transit server.
- Specify the target landing VPS or node.
- Specify the planned new listening port.
- Confirm the new port avoids `8443`, `18443`, `22`, and `20575`.
- Confirm the cloud security group allows the planned TCP port.
- Confirm the cloud firewall allows the planned TCP port.
- Confirm the server firewall allows the planned TCP port.
- Run a local database backup first.
- Obtain explicit user authorization for Workbuddy readonly preflight.
- Enter a remote readonly preflight execution stage.
- Only after readonly preflight passes, enter a real forwarding creation
  approval stage.
- Record candidate link acceptance separately.
- Approve any formal `node.share_link` cutover separately.

## Current No-Go Conclusion

- Stage 3.10.1 archives readonly preflight local capabilities and the next-step
  plan.
- The user is not ready to create a real new route.
- The project does not enter remote execution.
- SSH is not allowed.
- Remote commands are not allowed.
- Remote server connections are not allowed.
- Real forwarding creation is not allowed.
- New listening ports are not allowed.
- `node.share_link` modification is not allowed.
- Cutover is not allowed.
- Current status remains No-Go until the user later provides a target route,
  target port, firewall confirmations, and explicit authorization.

## Safety Boundary

This stage maintains the following boundaries:

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH keys.
- Do not write passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not commit real database backup files.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not connect to remote servers.
- Do not trigger backend tasks.
- Do not modify firewall rules.
- Do not create real forwarding.
- Do not let `socat` take over 8443.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Impact Summary

| Item | Result |
| --- | --- |
| Code modified | No |
| Frontend function modified | No |
| Backend logic modified | No |
| Script added | No |
| Real backup file generated | No |
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
