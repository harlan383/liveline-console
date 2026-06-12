# Stage 3.7.1 Single Route Remote Execution Readiness

## Current Stage Conclusion

Stage 3.7.1 documents the readiness checklist before any future real remote
single-route creation. This stage is a preparation check, not an execution
stage.

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

## Objects To Confirm Before Remote Execution

Before requesting a real remote execution stage, the operator must identify:

| Item | Required Confirmation |
| --- | --- |
| Target transit server | Which transit server will host the new route |
| Target landing VPS / node | Which landing VPS or active node receives traffic |
| Planned new listen port | Exact TCP port for the new route |
| Protected fallback port | New port must not be `8443` |
| Protected formal port | New port must not be `18443` |
| Existing formal link | New port must not overwrite the current formal route |
| Existing fallback link | New port must not occupy the `gost` fallback route |
| Active node | Active node must be confirmed |
| Landing node port | Landing node port must be confirmed |
| Target platform purpose | Intended use must be clear before creation |

The new port must not cover, replace, or implicitly migrate the current formal
route or fallback route.

## Port Planning Requirements

Port planning must follow these rules:

- `8443` is retained for the `gost` fallback route and cannot be used for a new
  `socat` forwarding route.
- `18443` is the current formal `socat` route and cannot be overwritten or
  reused by a new route.
- `22` and other management ports cannot be used for business forwarding.
- `20575` and other system, historical problem, or existing service ports must
  not be reused without separate review.
- Before any new or changed listening port is used, confirm the cloud security
  group allows the corresponding TCP port.
- Before any new or changed listening port is used, confirm the cloud firewall
  allows the corresponding TCP port.
- Before any new or changed listening port is used, confirm the server firewall
  allows the corresponding TCP port.
- Do not enter real remote creation until the port and firewall status are
  confirmed.

## Local Readiness Checks

Run these checks before asking for a future remote execution stage:

| Check | Expected Result |
| --- | --- |
| Local database backup | Backup completed before risky changes |
| Backup Git safety | Backup files remain outside Git |
| `scripts/local-health-check.sh` | Local health check passes |
| `/api/health` | Backend, PostgreSQL, Redis, and RQ Worker are healthy |
| Redis `temp_credential:*` | Count is `0` |
| Pending/running tasks | Count is `0` |
| Git working tree | Clean before remote execution |
| `main` branch state | Latest expected baseline is available |
| Formal link UI | Still shows `socat` 18443 |
| Fallback link UI | Still shows `gost` 8443 |

If any check fails, remain No-Go and resolve it before requesting remote
execution.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.7.1 because this stage only writes the
readiness checklist.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login to a VPS or transit server.
- Real `socat` or `gost` installation checks.
- Real remote forwarding creation.
- Real remote listening-port checks.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

## Go / No-Go Checklist

### Go Conditions

All of the following must be true before a later real remote execution stage:

- Local database backup is complete.
- Current system health is normal.
- No pending or running tasks exist.
- Target transit server is clear.
- Landing node is clear.
- New listening port is clear.
- New listening port is not `8443`.
- New listening port is not `18443`.
- Cloud security group, cloud firewall, and server firewall allow the planned
  TCP port.
- User explicitly authorizes entering the remote execution stage.
- Workbuddy is available or the user explicitly specifies an approved remote
  execution method.

### No-Go Conditions

Any of the following keeps the flow blocked:

- Local database has not been backed up.
- Port planning is unclear.
- Planned port is `8443` or `18443`.
- Cloud security group, cloud firewall, or server firewall status is not
  confirmed.
- Pending or running tasks exist.
- User has not explicitly authorized remote execution.
- The flow requires `node.share_link` modification without formal approval.
- The flow requires cutover without formal approval.

## Current Link Stable Baseline

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- This stage does not modify `node.share_link`.
- This stage does not add real listening ports.
- This stage does not close, downgrade, or replace `gost` 8443.
- This stage does not let `socat` take over 8443.
- This stage does not overwrite `socat` 18443.
- This stage does not perform cutover.

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

- Stage 3.7.2 can document single-route remote execution approval.
- Stage 3.7.3 can, after explicit authorization, use Workbuddy for remote
  read-only preflight.
- Stage 3.7.4 can, after explicit authorization, create real remote forwarding.
- Candidate link acceptance should be recorded separately after client testing.
- Formal `node.share_link` cutover must enter a separate approval stage.

## Impact Summary

| Item | Result |
| --- | --- |
| Code modified | No |
| Frontend functionality modified | No |
| Backend logic modified | No |
| Scripts added or modified | No |
| Real backup files generated | No |
| Database migration added | No |
| Listening port added | No |
| `node.share_link` read or modified | No |
| SSH or remote command executed | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
