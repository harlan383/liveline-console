# Stage 3.7.5 Single Route Local Plan Builder

## Current Stage Conclusion

Stage 3.7.5 adds a local dry-run plan builder to the single-route page. The
builder is frontend-only and helps prepare a future single-route approval
summary without touching remote systems.

This stage explicitly does not:

- Execute SSH.
- Execute remote commands.
- Create real forwarding.
- Add real listening ports.
- Modify `node.share_link`.
- Perform cutover.
- Trigger backend tasks.
- Require Workbuddy.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Modified Files

| File | Change |
| --- | --- |
| `frontend/components/TransitRoutesPanel.tsx` | Added local dry-run planning state, validation, Go/No-Go result, and redacted approval summary UI |
| `frontend/app/globals.css` | Added local plan builder layout and summary styles |
| `README.md` | Added Stage 3.7.5 scope and status |
| `docs/stage-3.7.5-single-route-local-plan-builder.md` | Added this implementation record |

No backend dry-run / validate endpoint was added. The current implementation
uses frontend-only local validation and does not persist a plan.

## Local Plan / Dry-run Purpose

The local plan builder lets the operator prepare a future route plan by
selecting or entering:

- Transit resource.
- Landing VPS / active node.
- Planned listening port.
- Landing target port.
- Target platform / purpose.
- Cloud security group confirmation state.
- Cloud firewall confirmation state.
- Server firewall confirmation state.
- Local database backup confirmation state.

The builder is local-only. It does not connect to remote servers, does not
write remote configuration, does not create systemd services, does not add
listening ports, does not create tasks, and does not modify `node.share_link`.

## Port Validation Rules

The local plan builder enforces:

- Listening port must be an integer in the range `1` to `65535`.
- `8443` is forbidden because it is retained for the `gost` fallback route.
- `18443` is forbidden because it is the current formal `socat` route.
- `22` is forbidden because it is a management port.
- `20575` is forbidden because it is a historical problem / existing service
  port.
- Empty, non-numeric, decimal, negative, and out-of-range ports are No-Go.
- Landing target port must also be an integer in the range `1` to `65535`.

## Go / No-Go Rules

The plan shows `No-Go` if any required condition is missing:

- Transit resource is not selected.
- Landing node is not selected.
- Planned listen port is invalid or protected.
- Landing target port is invalid.
- Target platform / purpose is empty.
- Cloud security group confirmation is missing.
- Cloud firewall confirmation is missing.
- Server firewall confirmation is missing.
- Local database backup confirmation is missing.

The plan shows `Ready for readonly preflight approval` only when all local
checks pass. That Ready status means only that the operator may enter the next
read-only preflight approval stage. It does not authorize SSH, remote commands,
real forwarding creation, `node.share_link` modification, or cutover.

## Approval Summary Redaction Boundary

The generated local approval summary may include:

- Transit resource name.
- Landing node name.
- Planned listen port.
- Landing target port.
- Target purpose.
- Firewall confirmation status.
- Local backup confirmation status.
- Go / No-Go result.

The summary must not include:

- Complete node links.
- SSH keys.
- Passwords.
- Tokens.
- Real `SESSION_SECRET` values.
- Complete sensitive command output.

## Current Link Protection

The page continues to show and protect the current link state:

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Local planning does not modify `node.share_link`.
- Local planning does not close, downgrade, or replace `gost` 8443.
- Local planning does not let `socat` take over 8443.
- Local planning does not overwrite `socat` 18443.

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

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.7.5 because the builder is local-only and
does not execute remote checks.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login to a VPS or transit server.
- Real remote read-only preflight.
- Real remote port occupancy checks.
- Real `socat` or `gost` installation checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

## Future Recommendations

- Stage 3.7.6 can record browser acceptance for the local plan builder.
- A later stage can request Workbuddy for remote read-only preflight only after
  explicit authorization.
- Real forwarding creation must be separately approved.
- Candidate link acceptance should be recorded separately after client testing.
- Formal `node.share_link` cutover must enter a separate approval stage.

## Impact Summary

| Item | Result |
| --- | --- |
| Business logic modified | No |
| Frontend display modified | Yes |
| Backend dry-run / validate endpoint added | No |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` read or modified | No |
| Complete node link read or output | No |
| SSH or remote command executed | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
