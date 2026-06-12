# Stage 3.6.3 Single Route Diagnosis Polish

## Current Stage Conclusion

Stage 3.6.3 improves the local single-route diagnosis display and task-result
readability. The route page now makes it easier to distinguish task status,
listen-port checks, forwarding process checks, systemd status, transit-to-landing
connectivity, failure summaries, next-action hints, and redacted command output.

This stage does not execute SSH, run remote commands, trigger backend tasks,
create real forwarding, add real listening ports, modify `node.share_link`, or
perform cutover.

Current route state remains unchanged:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Modified Files

| File | Change |
| --- | --- |
| `frontend/components/TransitRoutesPanel.tsx` | Polished diagnosis result display, added check labels, failure explanations, next-action hints, task outcome summary, and frontend output redaction |
| `frontend/app/globals.css` | Added layout styles for diagnosis guidance, result grid, check explanations, and redacted output details |
| `README.md` | Added Stage 3.6.3 scope and status |
| `docs/stage-3.6.3-single-route-diagnosis-polish.md` | Records this stage's diagnosis display changes and safety boundaries |

No backend route, schema, database model, Worker, or task execution logic was
changed.

## Diagnosis Display Improvements

The single-route diagnosis result now separates:

- Task status.
- Current step.
- Progress.
- Passed / failed result.
- Error code.
- Error summary.
- Suggested next action.
- `listen_check`: listening-port check.
- `process_check`: gost / socat process check.
- `target_connectivity`: transit-to-landing connectivity check.
- `service_status`: systemd service status check.
- Redacted `raw_output` behind an expandable details section.

For controlled socat restart results, the display also handles:

- `restart_result`.
- `service_status`.
- `listen_check`.
- `target_connectivity`.

The UI reads existing `result_data.checks`, top-level restart result fields,
`hints`, `warnings`, `failures`, task status, and task logs. It does not require
new database fields or migrations.

## Failure Explanation Improvements

The diagnosis view now gives plain-language explanations for common failure
patterns:

| Check | Failure explanation |
| --- | --- |
| Listening port check | `ss` did not find the expected listener; the service may not be running, may have exited, or the port may be occupied |
| Process check | gost / socat process was not found |
| Transit-to-landing connectivity | The transit server may not be able to reach the landing VPS target host and port |
| systemd status | The service may not be active, or the service name / unit file may not match expectations |
| Unknown failure | The UI points the operator to task records and keeps the reason generic |

The UI does not invent a precise cause when backend results do not include one.

## Safety Boundary Shown in UI

The diagnosis area now states:

- Diagnosis display is not formal cutover.
- Diagnosis does not modify `node.share_link`.
- Diagnosis does not close `gost 8443`.
- Diagnosis does not let `socat` take over `8443`.
- New or changed listening ports that fail diagnosis should first be checked
  against cloud security group, cloud firewall, and server firewall rules.
- Real remote diagnosis needs Workbuddy or a separately authorized stage.

## Redaction Strategy

The frontend applies display-layer redaction and truncation for diagnosis output
and logs:

- Complete `vless://`, `vmess://`, `trojan://`, and `ss://` links are replaced
  with redacted protocol labels.
- Private key blocks are replaced with `[redacted private key]`.
- Sensitive-looking text containing password, passphrase, token, cookie, session,
  secret, admin password hash, or SSH key markers is redacted.
- Long command output is truncated.
- Complete `node.share_link` values are not displayed.

This is a UI safety layer. Operators must still avoid copying raw sensitive
logs, complete node links, SSH Keys, passwords, tokens, or secrets into external
tools.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.6.3 because this stage only changes local
display and documentation.

Workbuddy or a separately authorized stage is needed for:

- Real SSH login.
- Real remote diagnosis.
- Real remote listening-port checks.
- Real transit-to-landing connectivity checks.
- Any formal `node.share_link` cutover or rollback.

## Impact Record

| Item | Result |
| --- | --- |
| Modified business logic | No |
| Modified frontend display | Yes |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Read or output complete node link | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Security Boundary

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH Keys.
- Do not write Passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not commit real database backup files.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not trigger backend Worker/RQ tasks.
- Do not modify firewall rules.
- Do not let `socat` take over `8443`.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Stage Conclusion

The single-route diagnosis flow is clearer for local troubleshooting: checks are
grouped by purpose, failed checks explain likely meaning, next actions are
visible, and raw output is redacted and collapsed. The stage remains display-only
and does not change the current production route state.
