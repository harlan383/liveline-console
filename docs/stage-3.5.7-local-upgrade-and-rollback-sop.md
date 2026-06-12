# Stage 3.5.7 Local Upgrade and Rollback SOP

## Current Stage Conclusion

Stage 3.5.7 documents the local single-user upgrade and rollback SOP. This
stage is documentation-only. It does not change business logic, authentication
logic, `node.share_link`, listening ports, firewall rules, backend tasks, or the
current transit links.

Current route state remains unchanged:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Local Usage Context

LiveLine Console is used only on the operator's own Mac.

- Console URL: `http://localhost:3000`.
- No public production deployment is required.
- No public domain, HTTPS reverse proxy, Nginx, or Caddy is required.
- No multi-user role model is required.
- The priority is safe local upgrades, local backups, clear post-upgrade
  checks, and a workable rollback path.

## Pre-Upgrade Checklist

Run these checks before merging PRs, pulling `main`, rebuilding Docker, or
asking Codex to make changes that may affect local state.

1. Enter the project directory:

   ```bash
   cd <PROJECT_ROOT>
   ```

2. Confirm the current branch and worktree:

   ```bash
   git branch --show-current
   git status --short
   ```

3. Confirm `main` is the expected upgrade target:

   ```bash
   git checkout main
   git pull
   git log --oneline --decorate -5
   ```

4. Create a local database backup:

   ```bash
   scripts/local-db-backup.sh
   ```

5. Confirm the backup artifact is under:

   ```text
   backups/local-db/YYYYMMDD-HHMMSS/
   ```

   The backup file must not appear in `git status --short`.

6. Record the current commit id:

   ```bash
   git rev-parse --short HEAD
   ```

7. Record current health:

   ```bash
   curl http://localhost:8000/api/health
   ```

8. Confirm Redis temporary credentials are clear:

   ```bash
   docker compose exec -T redis redis-cli --scan --pattern 'temp_credential:*'
   ```

   Expected result: no output.

9. Confirm there are no pending or running tasks. If using SQL locally, query
   the `tasks` table for `pending` and `running` statuses. Alternatively, use
   the local task history page after login.

10. Confirm the upgrade stage does not plan to:

    - Modify `node.share_link`.
    - Add a listening port.
    - Trigger remote tasks.
    - Execute SSH or remote commands.
    - Change the formal `socat 18443` link.
    - Change the fallback `gost 8443` link.

## Upgrade Execution SOP

Run the upgrade from the project root.

1. Switch to `main`:

   ```bash
   git checkout main
   ```

2. Pull the latest code:

   ```bash
   git pull
   ```

3. Rebuild and start local services:

   ```bash
   docker compose up --build -d
   ```

4. Check service containers:

   ```bash
   docker compose ps
   ```

5. If needed, inspect recent logs. Do not copy logs containing sensitive values
   into documentation, chat, or Git.

6. Run the local health check:

   ```bash
   scripts/local-health-check.sh
   ```

7. Open the local console:

   ```text
   http://localhost:3000
   ```

8. Confirm the login page appears.

9. Log in through the browser. Real passwords must be typed only into the
   browser login form and must not be written into terminal commands,
   documentation, logs, screenshots, or Git.

10. Enter the system panel and check:

    - System status.
    - Task history page.
    - Topology preview page.
    - Route safety guardrail text.
    - Formal link label: `socat 18443`.
    - Fallback link label: `gost 8443`.

## Post-Upgrade Acceptance Checklist

After the upgrade, confirm:

| Check | Expected result |
| --- | --- |
| `docker compose ps` | Containers are running |
| `/api/health` | backend / database / redis / worker are `ok` |
| `http://localhost:3000` | Page opens |
| Login page | Visible before login |
| Correct login | Enters system panel |
| Logout | Returns to login page |
| Task history page | Opens and shows local task records safely |
| Topology preview page | Opens and remains preview-only |
| Route safety guardrails | Show `socat 18443` and `gost 8443` |
| `node.share_link` | Not modified by the upgrade |
| Listening ports | No new listening port added |
| Redis `temp_credential:*` | No output |
| Pending / running tasks | 0 |

## Rollback Strategy

### Code or Frontend Display Rollback

If the problem is limited to frontend display, layout, local build behavior, or
non-data code changes:

1. Return to the last known stable commit:

   ```bash
   git checkout <STABLE_COMMIT>
   ```

2. Rebuild local services:

   ```bash
   docker compose up --build -d
   ```

3. Run:

   ```bash
   scripts/local-health-check.sh
   ```

4. Recheck `http://localhost:3000`, login, task history, topology preview, and
   route safety guardrails.

### Database Rollback

If local database records are corrupted, missing, or unexpectedly changed:

1. Confirm a restore window.
2. Create a fresh backup of the current abnormal state first:

   ```bash
   scripts/local-db-backup.sh
   ```

3. Restore the pre-upgrade backup:

   ```bash
   scripts/local-db-restore.sh backups/local-db/<timestamp>/<backup-file>
   ```

4. Start services:

   ```bash
   docker compose up -d
   ```

5. Run:

   ```bash
   scripts/local-health-check.sh
   ```

6. Verify:

   - `http://localhost:3000` opens.
   - Login works.
   - Task history page opens.
   - Topology preview page opens.
   - `node.share_link` was not accidentally changed.
   - The `socat 18443` formal link remains unaffected.
   - The `gost 8443` fallback link remains unaffected.

## Current Link Protection Boundary

| Item | Current state |
| --- | --- |
| Formal link | `socat 18443` |
| Fallback link | `gost 8443` |
| `node.share_link` | Already points to `socat 18443` |
| Stage 3.5.7 `node.share_link` changes | None |
| Stage 3.5.7 new listening ports | None |
| Stage 3.5.7 remote commands | None |
| Stage 3.5.7 cutover activity | None |
| Stage 3.5.7 `socat` 8443 takeover | None |
| Stage 3.5.7 `gost` 8443 shutdown / downgrade / replacement | None |

If any future stage adds or changes a listening port, the operator must check
the cloud security group, cloud firewall, and server firewall for the
corresponding TCP port.

## Forbidden Practices

- Do not commit real database backup files to Git.
- Do not send real database backup files to Codex, ChatGPT, or public tools.
- Do not write real passwords into terminal commands.
- Do not write real passwords into documentation.
- Do not write real password hashes into documentation.
- Do not write real `SESSION_SECRET` values into documentation.
- Do not write SSH Keys.
- Do not write Passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not copy complete logs containing sensitive data into documentation or
  chat.
- Do not read or output complete node links.
- Do not execute SSH or remote commands.
- Do not trigger backend Worker/RQ tasks.
- Do not change firewall rules.
- Do not perform cutover.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not let `socat` take over 8443.

## Stage 3.5.7 Recorded Impact

| Item | Result |
| --- | --- |
| Modified code | No |
| Added scripts | No |
| Generated real backup file | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## SOP Conclusion

Local upgrades should follow a fixed pattern: verify the Git state, create a
local database backup, record health, upgrade code, rebuild Docker, validate the
local console, and roll back through either Git or database restore if needed.

This stage documents the process only. It does not perform an upgrade, rollback,
backup, restore, remote operation, or route change.
