# Stage 3.7.2 Single Route Remote Execution Approval

## Current Stage Conclusion

Stage 3.7.2 creates the approval record and approval template for a future real
single-route remote execution stage. This stage is not an execution stage.

This stage explicitly does not:

- Execute SSH.
- Execute remote commands.
- Create real forwarding.
- Add real listening ports.
- Modify `node.share_link`.
- Perform cutover.
- Trigger backend tasks.
- Require Workbuddy.

Important current approval status:

- The real new route target has not been supplied.
- The target transit server has not been supplied.
- The landing VPS / node has not been supplied.
- The new listening port has not been supplied.
- Cloud security group, cloud firewall, and server firewall confirmations have
  not been supplied.
- Therefore, real remote execution remains No-Go.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Approval Object Fields

The following information must be supplied before a later stage can request real
remote execution:

| Approval Item | Current Status |
| --- | --- |
| Whether to create a new route | Pending confirmation |
| Target transit server | Pending confirmation |
| Target landing VPS / node | Pending confirmation |
| Active node | Pending confirmation |
| New listening port | Pending confirmation |
| Landing target port | Pending confirmation |
| Target platform purpose | Pending confirmation |
| Local database backup completed | Pending confirmation |
| Cloud security group confirmed | Pending confirmation |
| Cloud firewall confirmed | Pending confirmation |
| Server firewall confirmed | Pending confirmation |
| Allow later Workbuddy remote read-only preflight | Pending confirmation |
| Allow later real remote creation stage | Not authorized |
| Allow `node.share_link` modification | Not authorized |
| Allow cutover | Not authorized |

## Current Approval Result

The approval template is archived, but execution is not approved.

Current result:

- Remote execution approval template created.
- Real remote execution is not allowed because target object, port, and firewall
  confirmation information are incomplete.
- SSH is not allowed.
- Route creation is not allowed.
- Adding listening ports is not allowed.
- `node.share_link` modification is not allowed.
- Cutover is not allowed.
- Status: No-Go until the user supplies target information and explicit
  authorization.

## Port Approval Rules

Any future new route must satisfy these rules:

- `8443` is retained for the `gost` fallback route and cannot be used for a new
  `socat` forwarding route.
- `18443` is the current formal `socat` route and cannot be overwritten or
  reused by a new route.
- `22` and other management ports cannot be used for business forwarding.
- `20575` and other system, historical problem, or existing service ports must
  not be reused without separate review.
- The new listening port must be a valid TCP port in the range `1` to `65535`.
- Before any new or changed listening port is used, confirm the cloud security
  group allows the corresponding TCP port.
- Before any new or changed listening port is used, confirm the cloud firewall
  allows the corresponding TCP port.
- Before any new or changed listening port is used, confirm the server firewall
  allows the corresponding TCP port.
- Do not enter real remote creation until port access is confirmed.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.7.2 because this stage only writes the
approval template.

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

All of the following must be true before a later remote read-only preflight or
real creation stage:

- User explicitly says to create a new route.
- Target transit server is clear.
- Target landing VPS / node is clear.
- New listening port is clear.
- New listening port is not `8443`.
- New listening port is not `18443`.
- New listening port does not occupy a management, system, or existing service
  port.
- Cloud security group allows the planned TCP port.
- Cloud firewall allows the planned TCP port.
- Server firewall allows the planned TCP port.
- Local database backup is complete.
- Current system health is normal.
- No pending or running tasks exist.
- User explicitly authorizes the next stage to use Workbuddy for remote
  read-only preflight.

### No-Go Conditions

Any of the following keeps the flow blocked:

- Whether to create a new route is unclear.
- Target transit server is unclear.
- Landing node is unclear.
- New listening port is unclear.
- Planned port is `8443`.
- Planned port is `18443`.
- Cloud security group, cloud firewall, or server firewall status is not
  confirmed.
- Local database has not been backed up.
- Pending or running tasks exist.
- User has not explicitly authorized Workbuddy.
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

- Stage 3.7.3 can document remote read-only preflight approval after the user
  supplies target information.
- Stage 3.7.4 can, after explicit authorization, use Workbuddy for remote
  read-only preflight.
- Stage 3.7.5 can, after explicit authorization, create real remote forwarding.
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
