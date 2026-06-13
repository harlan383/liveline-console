# Stage 3.7.4 Single Route Readonly Preflight Approval

## Current Stage Conclusion

Stage 3.7.4 creates the approval template for a future real remote read-only
preflight stage. This stage is not an execution stage.

This stage explicitly does not:

- Execute SSH.
- Execute remote commands.
- Create real forwarding.
- Add real listening ports.
- Modify `node.share_link`.
- Perform cutover.
- Trigger backend tasks.
- Require Workbuddy to execute anything.

If a later stage needs real remote read-only preflight, it must obtain explicit
user authorization before Workbuddy or any other remote execution method is
used.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Readonly Preflight Object Fields

The following information must be supplied before a later stage can request real
remote read-only preflight:

| Approval Item | Current Status |
| --- | --- |
| Allow remote read-only preflight | Pending confirmation |
| Allow Workbuddy use | Pending confirmation |
| Target transit server name | Pending confirmation |
| Target transit server IP | Pending confirmation |
| Target landing VPS / node name | Pending confirmation |
| Target landing VPS IP | Pending confirmation |
| Landing target port | Pending confirmation |
| Active node | Pending confirmation |
| New listening port | Pending confirmation |
| Target platform purpose | Pending confirmation |
| Local database backup completed | Pending confirmation |
| Cloud security group confirmed | Pending confirmation |
| Cloud firewall confirmed | Pending confirmation |
| Server firewall confirmed | Pending confirmation |
| Allow remote listening-state read | Not authorized |
| Allow remote process-state read | Not authorized |
| Allow remote systemd-state read | Not authorized |
| Allow transit-to-landing TCP connectivity test | Not authorized |
| Allow real remote forwarding creation | Not authorized |
| Allow `node.share_link` modification | Not authorized |
| Allow cutover | Not authorized |

## Allowed Readonly Preflight Scope For A Future Stage

If a later stage is explicitly authorized, remote preflight may only read state.
It must not modify state. Potential allowed checks include:

- Transit server basic connectivity.
- Whether the planned new listening port is already occupied.
- Whether `18443` is still used by the formal `socat` route.
- Whether `8443` is still used by the `gost` fallback route.
- Current `gost` process or service status.
- Current `socat` process or service status.
- Server firewall status, read-only.
- TCP connectivity from the transit server to the landing VPS target port.
- No complete node-link reads.
- No private-key reads.
- No sensitive configuration reads.
- No remote configuration writes.
- No systemd service creation.
- No remote service start, stop, or restart.
- No firewall modification.
- No `node.share_link` modification.

## Readonly Preflight Prohibitions

The following remain forbidden:

- Creating real forwarding.
- Adding listening ports.
- Stopping `gost` 8443.
- Letting `socat` take over 8443.
- Overwriting `socat` 18443.
- Modifying remote systemd configuration or state.
- Modifying firewall rules.
- Writing remote files.
- Modifying the database.
- Generating real usable node links.
- Modifying `node.share_link`.
- Performing cutover.
- Outputting complete node links.
- Outputting SSH keys, passphrases, tokens, passwords, or real
  `SESSION_SECRET` values.

## Readonly Command Boundary

This stage does not execute any commands. It only records command categories
that a later explicitly authorized stage may request.

Future remote read-only preflight may include command categories such as:

- `ss` or `lsof` for listening-port inspection.
- `ps` for process inspection.
- `systemctl status` for service status inspection.
- `curl`, `nc`, or `timeout` for TCP connectivity checks.
- `iptables` or `ufw` read-only firewall inspection.
- `hostname`, `uname`, or `date` for basic read-only host information.

Before any such command is executed:

- The user must explicitly authorize the execution stage.
- The command list must remain read-only.
- Command output must not contain complete node links or sensitive values.

## Port Safety Boundary

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

## Current Approval Result

The remote read-only preflight approval template is archived, but execution is
not approved.

Current result:

- Remote read-only preflight approval template created.
- Target transit server is not confirmed.
- Target landing node is not confirmed.
- New listening port is not confirmed.
- Cloud security group, cloud firewall, and server firewall confirmations are
  not confirmed.
- Workbuddy execution is not authorized.
- SSH is not allowed.
- Remote commands are not allowed.
- Real forwarding creation is not allowed.
- Adding listening ports is not allowed.
- `node.share_link` modification is not allowed.
- Cutover is not allowed.
- Status: No-Go until the user supplies target information and explicit
  authorization.

## Go / No-Go Checklist

### Go Conditions

All of the following must be true before a later real remote read-only preflight
execution stage:

- User explicitly allows remote read-only preflight.
- User explicitly allows Workbuddy use.
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
- User understands that read-only preflight does not create real forwarding,
  does not modify `node.share_link`, and does not perform cutover.

### No-Go Conditions

Any of the following keeps the flow blocked:

- Whether Workbuddy may be used is unclear.
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
- User has not explicitly authorized read-only preflight.
- The flow requires forwarding creation without creation approval.
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

- Stage 3.7.5 can, after the user supplies target information and explicit
  authorization, use Workbuddy for remote read-only preflight.
- Stage 3.7.6 can record the remote read-only preflight result.
- Stage 3.7.7 can document real remote creation approval.
- Real forwarding creation must be separately approved.
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
