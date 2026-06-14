# Stage 3.10.2 Local Console Final Acceptance And Long-term Use Guide

## Current Stage Conclusion

Stage 3.10.2 archives the local console final acceptance checklist and
long-term use guide.

Current conclusion: local console final acceptance and long-term use guidance
are documented; remote execution remains No-Go.

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

## Completed Local Console Capabilities

- Transit link stability archive is complete.
- Auth login gate is complete.
- Protected APIs require login.
- Login failure rate limiting is implemented.
- Local database backup and restore scripts exist.
- Local health check script exists.
- Local upgrade and rollback SOP is archived.
- Topology preview safety hints are present.
- Formal route safety guardrails UI is present.
- Task history page is available for local troubleshooting.
- Single-route creation safety gates are present.
- Single-route diagnosis display is polished.
- Local dry-run route planner is present.
- Remote readonly preflight local framework is present.
- Readonly preflight no-op API is present.
- Frontend is integrated with the no-op API.
- Real remote execution remains No-Go.

## Final Local Stability Acceptance Checklist

| Item | Acceptance state |
| --- | --- |
| `git status --short` | Clean before this Stage 3.10.2 documentation edit |
| `docker compose ps` | Expected daily check command |
| `scripts/local-health-check.sh` | Available as the standard local health check |
| `/api/health` backend / database / redis / worker | Expected `ok` in normal local use |
| `http://localhost:3000` | Local console entry point |
| Login page | Expected normal |
| Correct login into system panel | Expected normal; real password only in browser |
| Logout | Expected normal |
| System status page | Expected normal |
| Transit resources page | Expected normal |
| Topology preview page | Expected normal |
| Single route page | Expected normal |
| Task history page | Expected normal |
| Local dry-run planner | Expected normal |
| Readonly preflight no-op API | Expected normal and login protected |
| Redis `temp_credential:*` | Expected `0` before and after local-only work |
| pending / running tasks | Expected `0` before remote execution work |
| Complete node links displayed | No |
| SSH keys / passwords / tokens / `SESSION_SECRET` displayed | No |

After this documentation edit is committed and merged, the worktree should
return to clean.

## Daily Local Use Flow

Use the console only on the local Mac.

1. Enter the project directory.
2. Start or rebuild the local Docker Compose stack.
3. Check container status.
4. Run the local health check.
5. Open `http://localhost:3000`.
6. Log in through the browser.
7. Use the system panel.
8. Review task history when troubleshooting.
9. Review topology preview for local-only route structure.
10. Use the single-route local dry-run planner when planning a future route.
11. Use the readonly preflight no-op API output as planning evidence only.
12. Log out when finished.

Common commands:

```bash
cd "/Users/peng/同步空间/AI项目/直播线路搭建/live-network/LiveLine Console"
docker compose ps
docker compose up -d
docker compose up --build -d
docker compose down
scripts/local-health-check.sh
scripts/local-db-backup.sh
git status --short
git log --oneline --decorate -5
```

Do not put real passwords, complete node links, SSH keys, passphrases, tokens,
or real secrets into terminal commands, docs, logs, screenshots, or Git.

## Before Any Upgrade

Before pulling `main`, merging a PR, rebuilding Docker images, or asking Codex
to make a larger local change:

- Run `scripts/local-db-backup.sh`.
- Confirm the backup file is under the ignored local backups directory and will
  not enter Git.
- Confirm `git status --short` is clean.
- Confirm `/api/health` is healthy.
- Confirm pending / running tasks are `0`.
- Confirm Redis `temp_credential:*` is `0`.
- Confirm `node.share_link` does not need to be modified.
- Confirm the work does not involve remote execution.

## Exception Handling

- If `http://localhost:3000` does not open, first check `docker compose ps`.
- If `/api/health` is unhealthy, inspect backend, database, redis, and worker
  status locally.
- If login fails, do not type the real password into terminal commands.
- If Docker build fails, inspect local changes and logs, but do not copy
  sensitive log content into docs or external tools.
- If data looks abnormal, first back up the current abnormal state, then decide
  whether to restore an older backup.
- If a route looks abnormal, do not immediately modify `node.share_link`.
- If the issue involves remote routes, first decide whether Workbuddy is
  needed; readonly preflight must be separately authorized.

## Current Link Stability Baseline

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.10.2 does not modify `node.share_link`.
- Stage 3.10.2 does not add real listening ports.
- Stage 3.10.2 does not close, stop, downgrade, or replace `gost` 8443.
- Stage 3.10.2 does not let `socat` take over 8443.
- Stage 3.10.2 does not overwrite `socat` 18443.
- Stage 3.10.2 does not perform cutover.

## Future New Route Prerequisites

Before any real new route is created:

- Specify the target transit server.
- Specify the target landing VPS or node.
- Specify the planned new listening port.
- Confirm the new port avoids `8443`, `18443`, `22`, and `20575`.
- Confirm the cloud security group allows the planned TCP port.
- Confirm the cloud firewall allows the planned TCP port.
- Confirm the server firewall allows the planned TCP port.
- Run a local database backup.
- Use the local dry-run planner and reach Ready.
- Use the no-op API and receive `ready=True`.
- Obtain explicit user authorization for Workbuddy readonly preflight.
- Enter a remote readonly preflight execution stage.
- After readonly preflight passes, enter a real forwarding creation approval
  stage.
- Record candidate link acceptance separately.
- Approve any formal `node.share_link` cutover separately.

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.10.2 because this stage only archives local
console acceptance and long-term local use guidance.

The current system already has local planning and the no-op API.

Workbuddy or a separately authorized stage is needed for:

- Real SSH login to a VPS or transit server.
- Real remote readonly preflight.
- Real remote port occupancy checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

## Future Stage Simplification Rules

- Low-risk local feature, UI, no-op API, documentation, and acceptance work may
  be grouped into larger stages.
- Browser acceptance may be included in the same stage completion output.
- Stability archive content may be included at the end of a stage.
- Real remote operations must be split into approval, readonly preflight,
  execution, acceptance, and rollback stages.
- Any new or changed listening port must include a cloud security group, cloud
  firewall, and server firewall reminder.
- Any `node.share_link` modification must be separately approved.
- Any `gost` 8443 or `socat` 18443 change must preserve the fallback boundary.

## Current No-Go Conclusion

- Local console final acceptance and long-term use guidance are archived.
- The user is not ready to create a real new route.
- The project does not enter remote execution.
- SSH is not allowed.
- Remote commands are not allowed.
- Remote server connections are not allowed.
- Real forwarding creation is not allowed.
- New listening ports are not allowed.
- `node.share_link` modification is not allowed.
- Cutover is not allowed.
- Current status remains No-Go until the user later provides a target route,
  target port, firewall confirmations, and explicit authorization.

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
