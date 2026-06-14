# Stage 3.10.3 Local Console V1 Stable Release Tag

## Current Stage Conclusion

Stage 3.10.3 archives the current local console v1 stable baseline and prepares
the future Git tag plan.

Current conclusion: the local console v1 stable baseline is ready to be
documented; the recommended future tag is `local-console-v1-stable`.

This stage is documentation-only. It does not create a Git tag. The tag must be
created manually by the user on `main` after this PR is merged.

This stage does not modify code, frontend behavior, backend logic, scripts,
database schema, `node.share_link`, listening ports, firewall rules, Worker/RQ
tasks, current route state, or current transit links. It does not execute SSH
or remote commands, connect to remote servers, create real forwarding, perform
cutover, let `socat` take over 8443, or stop, downgrade, or replace `gost`
8443.

Current production link state remains unchanged:

- Formal link: `socat` 18443.
- Fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.

## Local Console V1 Stable Scope

The local console v1 stable baseline covers the current long-term local use
version of LiveLine Console.

Included stable capabilities:

- Auth login gate is complete.
- Protected backend APIs require login.
- Login failure rate limiting is complete.
- Local database backup and restore scripts are complete.
- Local health check script is complete.
- Local upgrade and rollback SOP is complete.
- Topology preview safety hints are complete.
- Formal route protection UI is complete.
- Task history page is complete.
- Single-route creation safety gates are complete.
- Single-route diagnosis display polish is complete.
- Local dry-run planner is complete.
- Readonly preflight no-op API is complete.
- Frontend integration with the no-op API is complete.
- Local long-term use guide is complete.

## Current Stable Link Baseline

- Current formal link: `socat` 18443.
- Current fallback link: `gost` 8443.
- `node.share_link` already points to `socat` 18443.
- Stage 3.10.3 does not modify `node.share_link`.
- Stage 3.10.3 does not add real listening ports.
- Stage 3.10.3 does not close, stop, downgrade, or replace `gost` 8443.
- Stage 3.10.3 does not let `socat` take over 8443.
- Stage 3.10.3 does not overwrite `socat` 18443.
- Stage 3.10.3 does not perform cutover.
- Real remote execution remains No-Go.

## Recommended Git Tag

| Item | Value |
| --- | --- |
| Tag name | `local-console-v1-stable` |
| Tag type | Annotated tag |
| Creation time | After this PR is merged into `main` |
| Creation location | Latest stable commit on `main` |
| Purpose | Mark the local console v1 stable baseline for future rollback reference |
| Sensitive content | Must not include real secrets, complete node links, or database backups |

The tag should identify the source-code baseline only. It must not include real
database backup files, real SSH keys, real passwords, complete node links,
tokens, passphrases, or other secrets.

## Future Tag Command Template

Do not execute these commands during Stage 3.10.3. They are only a future
manual template for the user after this PR is merged into `main`.

```bash
cd "/Users/peng/同步空间/AI项目/直播线路搭建/live-network/LiveLine Console"
git checkout main
git pull
git status --short
git tag -a local-console-v1-stable -m "Local console v1 stable baseline"
git push origin local-console-v1-stable
git tag -n
```

Before creating the tag, `git status --short` should be clean and `main` should
contain the merged Stage 3.10.3 documentation.

## Tag Rollback Reference

Future reference commands are documented here as guidance only.

To inspect the stable tag:

```bash
git show local-console-v1-stable
```

To temporarily inspect or test from the stable tag, create a branch from it:

```bash
git checkout -b local-console-v1-stable-restore local-console-v1-stable
```

Do not develop directly on the tag. Tags are immutable references for
identifying a stable baseline.

Database recovery is separate from Git tag rollback. If local database state
must be restored, use the local backup files under `backups/local-db/`. Those
backup files must stay out of Git and must not be sent to Codex, ChatGPT, or
public storage.

## Long-term No-Go Conclusion

- Local console v1 stable baseline is ready for archive.
- The user is not currently preparing to create a real new route.
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

## Workbuddy Boundary

Workbuddy is not needed for Stage 3.10.3 because this stage only archives the
local console v1 stable baseline and prepares a future Git tag plan.

The current system already has local planning and the no-op API.

Workbuddy or a separately authorized stage is needed for:

- Real SSH login to a VPS or transit server.
- Real remote readonly preflight.
- Real remote port occupancy checks.
- Real remote forwarding creation.
- Real remote diagnosis.
- Real `node.share_link` modification or rollback, which must also enter a
  separate formal cutover or rollback approval stage.

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
- Do not create a Git tag in this stage.
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
| Git tag created | No |
| SSH or remote command executed | No |
| Remote server connected | No |
| Backend task triggered | No |
| Real forwarding created | No |
| `socat` 18443 formal link affected | No |
| `gost` 8443 fallback link affected | No |
