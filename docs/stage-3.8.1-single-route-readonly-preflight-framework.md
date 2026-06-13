# Stage 3.8.1 Single Route Readonly Preflight Framework

## Current Stage Conclusion

Stage 3.8.1 adds a local frontend framework for future single-route remote
read-only preflight planning. The framework generates a future check list,
local Go / No-Go state, and a redacted approval summary from the existing local
dry-run plan inputs.

This stage does not execute SSH, execute remote commands, connect to remote
servers, create real forwarding, add real listening ports, modify
`node.share_link`, trigger backend tasks, or perform cutover.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Modified Files

| File | Change |
| --- | --- |
| `frontend/components/TransitRoutesPanel.tsx` | Added readonly preflight framework state, future check list, No-Go / Ready logic, and redacted summary UI |
| `frontend/app/globals.css` | Added readonly preflight plan layout styles |
| `README.md` | Added Stage 3.8.1 scope and status |
| `docs/stage-3.8.1-single-route-readonly-preflight-framework.md` | Added this implementation record |

No backend `readonly-preflight-plan` endpoint was added. The current
implementation is frontend-only and has no side effects.

## Readonly Preflight Framework Purpose

The framework helps prepare a future remote read-only preflight approval. It
uses the local dry-run plan inputs and adds two local confirmations:

- Local health has been checked and pending / running tasks are `0`.
- The operator acknowledges that this is only a read-only preflight plan and
  will not create real forwarding, modify `node.share_link`, or perform
  cutover.

The framework does not persist a plan, create a task, store credentials, or
connect to any remote host.

## Future Read-only Check Items

The framework displays these future checks, all marked as not executed in this
stage:

- Transit server basic connectivity.
- Planned listen port occupancy.
- Current `socat` 18443 formal route ownership.
- Current `gost` 8443 fallback route ownership.
- `gost` service / process status, read-only.
- `socat` service / process status, read-only.
- Transit server to landing VPS target TCP connectivity.
- Server firewall status, read-only.
- Task history and local health state.
- Cloud security group / cloud firewall / server firewall confirmation state.

These items are only a plan. Stage 3.8.1 does not run `ssh`, `systemctl`, `ss`,
`lsof`, `nc`, `curl`, `iptables`, `nft`, or any remote command.

## Go / No-Go Rules

The framework shows `No-Go` if any required condition is missing:

- Transit resource is not selected.
- Landing VPS / active node is not selected.
- Planned listen port is empty, invalid, decimal, negative, or out of range.
- Planned listen port is `8443`, `18443`, `22`, or `20575`.
- Landing target port is invalid.
- Target platform / purpose is empty.
- Cloud security group confirmation is missing.
- Cloud firewall confirmation is missing.
- Server firewall confirmation is missing.
- Local database backup confirmation is missing.
- Local health confirmation is missing.
- The read-only-only boundary acknowledgment is missing.

The framework shows `Ready for readonly preflight approval` only when all local
conditions pass. Ready means only that a later approval stage may be prepared.
It does not authorize SSH, remote commands, real forwarding creation, real
listening ports, `node.share_link` modification, or cutover.

## Redacted Summary Rules

The copied preflight summary may include:

- Transit resource name.
- Landing node name.
- Planned listen port.
- Landing target port.
- Target purpose.
- Firewall confirmation status.
- Local database backup confirmation status.
- Local health confirmation status.
- Go / No-Go result.
- Future read-only check item names and scopes.

The summary must not include:

- Complete node links.
- SSH keys.
- Passwords.
- Tokens.
- Real `SESSION_SECRET` values.
- Real `ADMIN_PASSWORD_HASH` values.
- Cookie or session content.
- Complete `node.share_link` values.
- Complete sensitive command output.

## Current Link Protection

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.8.1 does not modify `node.share_link`.
- Stage 3.8.1 does not add real listening ports.
- Stage 3.8.1 does not close, stop, downgrade, or replace `gost` 8443.
- Stage 3.8.1 does not let `socat` take over 8443.
- Stage 3.8.1 does not overwrite `socat` 18443.
- Stage 3.8.1 does not perform cutover.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.8.1 because the framework is local-only and
does not execute remote checks.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login.
- Real remote read-only preflight.
- Real remote port occupancy checks.
- Real `socat` or `gost` service checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback.

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

## Future Recommendations

- Stage 3.8.2 can record browser acceptance for the readonly preflight
  framework.
- A later stage can request Workbuddy for real remote read-only preflight only
  after explicit authorization.
- Real forwarding creation must be separately approved.
- Candidate link acceptance should be recorded separately after client testing.
- Formal `node.share_link` cutover must enter a separate approval stage.

## Impact Summary

| Item | Result |
| --- | --- |
| Business logic modified | No |
| Frontend display modified | Yes |
| Backend readonly-preflight-plan endpoint added | No |
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
