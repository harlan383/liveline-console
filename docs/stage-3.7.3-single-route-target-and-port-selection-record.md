# Stage 3.7.3 Single Route Target and Port Selection Record

## Current Stage Conclusion

Stage 3.7.3 creates the target and port selection record template for a future
real single-route remote execution stage. This stage is not an execution stage.

This stage explicitly does not:

- Execute SSH.
- Execute remote commands.
- Create real forwarding.
- Add real listening ports.
- Modify `node.share_link`.
- Perform cutover.
- Trigger backend tasks.
- Require Workbuddy.

Important current selection status:

- Whether to create a new route has not been confirmed.
- The target transit server has not been supplied.
- The landing VPS / node has not been supplied.
- The active node has not been supplied.
- The new listening port has not been supplied.
- Cloud security group, cloud firewall, and server firewall confirmations have
  not been supplied.
- Therefore, real remote execution remains No-Go.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Target Selection Fields

The following information must be supplied before a later stage can request real
remote execution:

| Selection Item | Current Status |
| --- | --- |
| Whether to create a new route | Pending confirmation |
| Target transit server name | Pending confirmation |
| Target transit server IP | Pending confirmation |
| Target landing VPS / node name | Pending confirmation |
| Target landing VPS IP | Pending confirmation |
| Landing target port | Pending confirmation |
| Active node | Pending confirmation |
| New listening port | Pending confirmation |
| Target platform purpose | Pending confirmation |
| Expected client usage | Pending confirmation |
| Local database backup completed | Pending confirmation |
| Cloud security group confirmed | Pending confirmation |
| Cloud firewall confirmed | Pending confirmation |
| Server firewall confirmed | Pending confirmation |
| Allow later Workbuddy remote read-only preflight | Pending confirmation |
| Allow later real remote forwarding creation | Not authorized |
| Allow `node.share_link` modification | Not authorized |
| Allow cutover | Not authorized |

## Current Default Selection State

All real target fields remain pending confirmation.

Current result:

- Target and port selection template created.
- Target transit server is not confirmed.
- Target landing node is not confirmed.
- New listening port is not confirmed.
- Cloud security group, cloud firewall, and server firewall confirmations are
  not confirmed.
- Remote execution is not allowed.
- SSH is not allowed.
- Real forwarding creation is not allowed.
- Adding listening ports is not allowed.
- `node.share_link` modification is not allowed.
- Cutover is not allowed.
- Status: No-Go until the user supplies target information and explicit
  authorization.

## Port Selection Rules

Any future new route must satisfy these rules:

- The new listening port must be a valid TCP port in the range `1` to `65535`.
- `8443` is retained for the `gost` fallback route and cannot be used for a new
  `socat` forwarding route.
- `18443` is the current formal `socat` route and cannot be overwritten or
  reused by a new route.
- `22` and other management ports cannot be used for business forwarding.
- `20575` and other system, historical problem, or existing service ports must
  not be reused without separate review.
- The new listening port must not conflict with an existing service port.
- Before any new or changed listening port is used, confirm the cloud security
  group allows the corresponding TCP port.
- Before any new or changed listening port is used, confirm the cloud firewall
  allows the corresponding TCP port.
- Before any new or changed listening port is used, confirm the server firewall
  allows the corresponding TCP port.
- Do not enter real remote creation until port access is confirmed.

## Suggested Port Selection Method

Use this approach when the user later supplies a real target:

- Prefer an unused high TCP port.
- Avoid common management ports, system ports, and current formal or fallback
  ports.
- After a candidate port is selected, perform an approved remote read-only
  preflight to confirm whether it is already listening.
- After a candidate port is selected, confirm the cloud security group, cloud
  firewall, and server firewall rules.
- Enter the next approval stage only after the candidate port and target objects
  are clear.

No real new port is selected in this stage because the user has not supplied a
real target port.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.7.3 because this stage only writes the
target and port selection template.

Workbuddy or a separately authorized remote-execution stage is needed for:

- Real SSH login to a VPS or transit server.
- Real remote port occupancy checks.
- Real `socat` or `gost` installation checks.
- Real remote forwarding creation.
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
- Active node is clear.
- New listening port is clear.
- New listening port is not `8443`.
- New listening port is not `18443`.
- New listening port does not occupy `22`, `20575`, management ports, system
  ports, or existing service ports.
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
- Planned port is `22` or another management port.
- Planned port is `20575` or another existing service port.
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

- The user should later supply the target transit server, landing node, and new
  listening port.
- Confirm that the planned port avoids `8443`, `18443`, `22`, and `20575`.
- Confirm cloud security group, cloud firewall, and server firewall rules before
  remote execution.
- Stage 3.7.4 can document remote read-only preflight approval.
- Stage 3.7.5 can, after explicit authorization, use Workbuddy for remote
  read-only preflight.
- Stage 3.7.6 can, after explicit authorization, create real remote forwarding.
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
