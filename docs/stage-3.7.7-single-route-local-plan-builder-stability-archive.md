# Stage 3.7.7 Single Route Local Plan Builder Stability Archive

## Current Stage Conclusion

Stage 3.7.7 archives the stable baseline for Stage 3.7 remote-execution
readiness, approval templates, target / port planning, read-only preflight
approval, the local dry-run plan builder, and browser acceptance.

This stage is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, create real forwarding, perform
cutover, let `socat` take over 8443, or stop, downgrade, or replace `gost`
8443.

Current Stage 3.7 conclusion: stable baseline archived; remote execution
remains No-Go.

## Stage 3.7 Completed Capabilities

| Stage | Capability |
| --- | --- |
| Stage 3.7.1 | Remote-execution readiness checklist documented |
| Stage 3.7.2 | Remote-execution approval template documented |
| Stage 3.7.3 | Target and port selection template documented |
| Stage 3.7.4 | Remote read-only preflight approval template documented |
| Stage 3.7.5 | Single-route local dry-run plan builder added |
| Stage 3.7.6 | Local dry-run plan builder browser acceptance recorded |

## Current Stage 3.7 Stable Baseline

- Remote-execution readiness checklist exists.
- Remote-execution approval template exists.
- Target and port selection template exists.
- Remote read-only preflight approval template exists.
- Local dry-run plan builder exists on the single-route page.
- Local dry-run plan builder browser acceptance is recorded.
- All remote execution remains No-Go.
- SSH is not authorized.
- Remote commands are not authorized.
- Workbuddy execution is not authorized.
- Real forwarding has not been created.
- Real listening ports have not been added.
- `node.share_link` has not been modified by Stage 3.7.
- Cutover has not been performed by Stage 3.7.

## Local Dry-run Plan Builder Stable Baseline

- The single-route page opens.
- The local dry-run plan builder is visible.
- `8443` shows No-Go and is retained for the `gost` fallback route.
- `18443` shows No-Go because it is the current formal `socat` route and must
  not be overwritten.
- `22` shows No-Go because management ports must not be used for business
  forwarding.
- `20575` shows No-Go because historical/problem or existing-service ports must
  not be reused casually.
- A valid high port still shows No-Go until cloud security group, cloud
  firewall, server firewall, and local database backup confirmations are all
  checked.
- After all local confirmations are checked, the builder shows only
  `Ready for readonly preflight approval`.
- Ready means only readiness for a read-only preflight approval stage. It does
  not mean real forwarding can be created.
- The page does not say that real forwarding can be created.
- The page does not display complete node links.
- The page does not display SSH Key / password / token / `SESSION_SECRET`
  values.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.7.7 because this stage only archives the
local planning baseline. Stage 3.7.1 through Stage 3.7.7 did not use Workbuddy
to execute remote commands.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login to a VPS or transit server.
- Real remote read-only preflight.
- Real remote port occupancy checks.
- Real `socat` or `gost` installation checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

## Current Link Stable Baseline

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.7 does not modify `node.share_link`.
- Stage 3.7 does not add real listening ports.
- Stage 3.7 does not close, stop, downgrade, or replace `gost` 8443.
- Stage 3.7 does not let `socat` take over 8443.
- Stage 3.7 does not overwrite `socat` 18443.
- Stage 3.7 does not perform cutover.

## Port Safety Baseline

- `8443` is retained for the `gost` fallback route.
- `18443` is the current formal `socat` route.
- `22` and other management ports must not be used for business forwarding.
- `20575` and other historical/problem or existing-service ports must not be
  reused casually.
- A new listen port must be a valid TCP port from `1` to `65535`.
- Before adding or changing any listen port, the cloud security group must be
  confirmed to allow the corresponding TCP port.
- The cloud firewall must be confirmed to allow the corresponding TCP port.
- The server firewall must be confirmed to allow the corresponding TCP port.
- Real remote creation must not begin until port allowance is confirmed.

## Current No-Go Conclusion

- Stage 3.7 stable baseline is archived.
- Remote-execution preparation, local planning, and approval templates are
  complete.
- The user is not currently preparing to add a real new route.
- Remote execution is not started.
- SSH is not allowed.
- Remote commands are not allowed.
- Real forwarding creation is not allowed.
- New listening ports are not allowed.
- `node.share_link` modification is not allowed.
- Cutover is not allowed.
- Current state remains No-Go until the user later provides a target route,
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
- Do not trigger backend tasks.
- Do not modify firewall rules.
- Do not create real forwarding.
- Do not let `socat` take over 8443.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Future Recommendations

- If the user later prepares a real new route, first collect the target transit
  server, landing node, and new listen port.
- Confirm cloud security group, cloud firewall, and server firewall allowance
  for the selected TCP port before any real remote creation.
- Run a local database backup before any remote execution stage.
- Stage 3.8 may start remote read-only preflight execution preparation.
- Real remote read-only preflight requires Workbuddy or a separately authorized
  remote-execution stage.
- Real forwarding creation must be separately approved.
- Candidate link acceptance must be recorded separately after client testing.
- Formal `node.share_link` cutover must enter a separate approval stage.

## Impact Summary

| Item | Result |
| --- | --- |
| Code modified | No |
| Frontend function modified | No |
| Script added | No |
| Real backup file generated | No |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` modified | No |
| SSH or remote command executed | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
