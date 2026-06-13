# Stage 3.8.2 Readonly Preflight Framework Browser Acceptance Record

## Current Stage Conclusion

Stage 3.8.2 records browser manual acceptance for the Stage 3.8.1 single-route
readonly preflight local framework.

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

- Environment: local browser.
- Console URL: `http://localhost:3000`.
- Real password handling: the password was entered only in the browser by the
  user. It was not written to terminal commands, docs, logs, screenshots, or
  Git.

## Browser Acceptance Items

| Item | Result |
| --- | --- |
| Login page is shown at `http://localhost:3000` | Passed |
| Correct username/password enters the system panel | Passed |
| Single-route page opens | Passed |
| Readonly preflight plan area is visible | Passed |
| Incomplete target information shows No-Go | Passed |
| Entering `8443` shows No-Go and explains that it is retained for the `gost` fallback route | Passed |
| Entering `18443` shows No-Go and explains that it is the current formal `socat` route and cannot be overwritten | Passed |
| Entering `22` shows No-Go and explains that management ports cannot be used for business forwarding | Passed |
| Entering `20575` shows No-Go and explains that historical/problem or existing-service ports must not be reused casually | Passed |
| A valid high port still shows No-Go until cloud security group, cloud firewall, server firewall, and local database backup confirmations are checked | Passed |
| After all local confirmations are checked, the framework shows only `Ready for readonly preflight approval` | Passed |
| Ready means only readiness for a read-only preflight approval stage, not permission to execute remotely | Passed |
| The page does not say that remote execution is allowed | Passed |
| The page does not say that real forwarding can be created | Passed |
| The page clearly says it will not execute SSH | Passed |
| The page clearly says it will not execute remote commands | Passed |
| The page clearly says it will not connect to remote servers | Passed |
| The page clearly says it will not create real forwarding | Passed |
| The page clearly says it will not add real listening ports | Passed |
| The page clearly says it will not modify `node.share_link` | Passed |
| The page clearly says it will not perform cutover | Passed |
| Complete node links are not displayed | Passed |
| SSH Key / password / token / `SESSION_SECRET` values are not displayed | Passed |
| Logout returns to the login page | Passed |

## Current UI / Auth State

- Login gate is active.
- Important backend APIs are protected by login.
- The single-route readonly preflight local framework is active.
- The framework performs only local Go / No-Go checks.
- The framework can generate only a redacted approval summary.
- The framework does not authorize SSH, remote commands, remote server
  connections, real forwarding creation, `node.share_link` modification, or
  cutover.

## Current Production Link Impact

| Item | Result |
| --- | --- |
| `socat` 18443 formal link | Unchanged |
| `gost` 8443 fallback link | Unchanged |
| `node.share_link` | Not modified |
| Real listening port added | No |
| Remote server connected | No |
| Real forwarding created | No |
| Cutover performed | No |

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.8.2 because this stage only records browser
manual acceptance.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login.
- Real remote read-only preflight.
- Real remote port checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Formal `node.share_link` cutover or rollback.

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
| Script added | No |
| Real backup file generated | No |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` modified | No |
| SSH or remote command executed | No |
| Remote server connected | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
