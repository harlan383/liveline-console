# Stage 3.5.8 Local Console Stability Archive

## Current Stage Conclusion

Stage 3.5.8 archives the stable baseline for the local single-user console.
This stage is documentation-only. It does not change business logic,
authentication logic, frontend functionality, scripts, `node.share_link`,
listening ports, firewall rules, backend tasks, or the current transit links.

Current route state remains unchanged:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Stage 3.5 Completed Capabilities

| Stage | Capability | Status |
| --- | --- | --- |
| Stage 3.5.1 | Local console daily operations guide | Documented |
| Stage 3.5.2 | Local backup and restore plan | Documented |
| Stage 3.5.3 | Local database backup, restore, and health check scripts | Implemented and documented |
| Stage 3.5.4 | Topology preview usability polish | Implemented and documented |
| Stage 3.5.5 | Route safety guardrails UI | Implemented and documented |
| Stage 3.5.6 | Local task history usability | Implemented and documented |
| Stage 3.5.7 | Local upgrade and rollback SOP | Documented |

Stage 3.5 turns the console into a safer local operations surface: the operator
can start and stop the local system, check health, back up and restore the local
database, understand topology previews, see route safety guardrails, inspect
task history safely, and follow a repeatable local upgrade / rollback process.

## Current Local Stable Baseline

| Item | Stable baseline |
| --- | --- |
| Local console URL | `http://localhost:3000` |
| Local health check URL | `http://localhost:8000/api/health` |
| Core health components | Backend / PostgreSQL / Redis / RQ Worker |
| Login gate | Completed |
| Important API protection | Completed |
| Local task history page | Available for historical task inspection |
| Local backup script | Available |
| Local restore script | Available |
| Local health check script | Available |
| Local upgrade / rollback SOP | Archived |

The console remains a local Mac tool. It is not a public production deployment
and does not require a public domain, HTTPS reverse proxy, multi-user role
model, or enterprise audit console.

## Current Script Inventory

| Script | Purpose | Notes |
| --- | --- | --- |
| `scripts/local-db-backup.sh` | Create a local PostgreSQL backup | Backup files must not be committed to Git |
| `scripts/local-db-restore.sh` | Restore a local PostgreSQL backup after confirmation | Restore requires explicit confirmation |
| `scripts/local-health-check.sh` | Check Docker Compose services and `/api/health` | Does not trigger backend tasks |

Script usage boundary:

- Database backup files must not be committed to Git.
- Database backup files must not be sent to Codex, ChatGPT, public tools, or
  public storage.
- Database restore must use the scripted confirmation flow.
- Before a local upgrade, create a database backup.
- After a local upgrade or restore, run the health check script.

## Current Link Stability Baseline

| Item | Current state |
| --- | --- |
| Formal link | `socat 18443` |
| Fallback link | `gost 8443` |
| `node.share_link` | Already points to `socat 18443` |
| Stage 3.5 `node.share_link` changes | None |
| Stage 3.5 new listening ports | None |
| Stage 3.5 `socat` 8443 takeover | None |
| Stage 3.5 `gost` 8443 shutdown / downgrade / replacement | None |
| Stage 3.5 cutover activity | None |

If any future stage adds or changes a listening port, the operator must check
cloud security group, cloud firewall, and server firewall rules for the
corresponding TCP port.

## Current UI Safety Capabilities

- Topology preview is clearly marked as `PREVIEW ONLY` / `NOT USABLE`.
- Topology preview states that it does not connect to remote hosts.
- Topology preview states that it does not write configuration.
- Topology preview states that it does not generate a real usable transit link.
- Route safety guardrails show `socat 18443` as the formal link.
- Route safety guardrails show `gost 8443` as the fallback link.
- Route safety guardrails warn not to modify `node.share_link`.
- Route safety guardrails warn not to close `gost 8443`.
- Route safety guardrails warn not to let `socat` take over 8443.
- Task history displays task results through a sanitized local view.
- Task history does not show complete node links.
- Task history does not show SSH Keys, passwords, tokens, `SESSION_SECRET`, or
  complete sensitive command output.

## Stable Operations Checklist

For ordinary local use:

1. Start or rebuild with Docker Compose when needed.
2. Check `http://localhost:8000/api/health`.
3. Open `http://localhost:3000`.
4. Log in through the browser.
5. Use the system page for health and task history.
6. Use topology preview only as a local preview.
7. Keep `socat 18443` as the formal link.
8. Keep `gost 8443` as the fallback link.
9. Back up the database before upgrades or risky local changes.
10. Follow the local upgrade / rollback SOP for code changes.

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

## Future Recommendations

- Stage 3.6 may review the single-route forwarding flow again if needed.
- Future real route creation, remote diagnosis, or listening-port changes
  should involve Workbuddy and an explicit stage boundary.
- Future new or changed listening ports must require cloud security group,
  cloud firewall, and server firewall confirmation.
- Future `node.share_link` changes must go through a separate formal cutover
  approval stage.
- Future cleanup of the `gost 8443` fallback link must go through a separate
  approval stage.

## Stage 3.5.8 Recorded Impact

| Item | Result |
| --- | --- |
| Modified code | No |
| Modified frontend functionality | No |
| Modified scripts | No |
| Generated real backup file | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Stability Archive Conclusion

Stage 3.5 is archived as a stable local console operations baseline. The
system has documented daily operations, local backup/restore planning and
scripts, health checks, topology preview safety messaging, route safety
guardrails, task history usability, and local upgrade / rollback SOP.

The current operational baseline remains `socat 18443` as the formal link and
`gost 8443` as the fallback link, with no new cutover or route mutation in this
stage.
