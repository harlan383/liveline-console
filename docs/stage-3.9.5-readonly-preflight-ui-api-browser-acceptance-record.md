# Stage 3.9.5 Readonly Preflight UI API Browser Acceptance Record

## Current Stage Conclusion

Stage 3.9.5 records browser manual acceptance for the Stage 3.9.4 readonly
preflight UI API integration.

Acceptance result: passed.

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

## Acceptance Environment

Browser acceptance environment: local `http://localhost:3000`.

The real username and password were entered only in the browser during manual
acceptance. They were not written to terminal commands, docs, logs,
screenshots, or Git.

## Browser Acceptance Items

| Item | Result |
| --- | --- |
| Login page is shown at `http://localhost:3000` | Passed |
| Correct browser-entered credentials enter the console panel | Passed |
| Single route page opens | Passed |
| Readonly preflight plan area is visible | Passed |
| Clicking the validation button calls the no-op API | Passed |
| `planned_listen_port = 8443` shows blocked / No-Go | Passed |
| `planned_listen_port = 18443` shows blocked / No-Go | Passed |
| `planned_listen_port = 22` shows blocked / No-Go | Passed |
| `planned_listen_port = 20575` shows blocked / No-Go | Passed |
| Safe high port without security group / cloud firewall / server firewall / local backup / user approval / Workbuddy authorization confirmations shows `no_go` | Passed |
| All local confirmations satisfied shows `ready=True` | Passed |
| `ready=True` does not mean remote execution is allowed | Passed |
| `ready=True` does not mean real forwarding can be created | Passed |
| Page displays `checks`, `summary`, `next_action`, `safety_boundary`, and `redacted_summary` | Passed |
| Page does not display complete node links | Passed |
| Page does not display SSH keys, passwords, tokens, or `SESSION_SECRET` values | Passed |
| Page states SSH is not executed | Passed |
| Page states remote commands are not executed | Passed |
| Page states remote servers are not connected | Passed |
| Page states real listening ports are not added | Passed |
| Page states `node.share_link` is not modified | Passed |
| Page states cutover is not performed | Passed |
| Logout returns to the login page | Passed |

## Current UI / API State

- Login gate is active.
- Important APIs remain protected by login.
- The no-op API is called from the readonly preflight UI.
- The no-op API performs only local validation and returns a plan.
- The no-op API does not create tasks.
- The no-op API does not write the database.
- The no-op API does not execute remote operations.

## No-op API Boundary

The UI integration uses:

`POST /api/transit-routes/readonly-preflight-plan`

The API response is displayed as local planning output only. It can report
`blocked`, `no_go`, or `ready`, but none of those states authorizes remote
execution or real forwarding creation in this stage.

## Current Production Link Impact

- `socat` 18443 formal link remains unchanged.
- `gost` 8443 fallback link remains unchanged.
- `node.share_link` was not read or modified in this stage.
- No real listening port was added.
- No real forwarding was created.
- No cutover was performed.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.9.5 because this stage only records browser
manual acceptance for a local UI and local no-op API integration.

Workbuddy or a separately authorized stage is needed for:

- Real SSH login.
- Real remote readonly preflight.
- Real remote port checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real formal cutover or rollback.
- Any real `node.share_link` modification.

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
