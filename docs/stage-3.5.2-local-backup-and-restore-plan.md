# Stage 3.5.2 Local Backup and Restore Plan

## Current Stage Conclusion

Stage 3.5.2 documents a local database backup and restore plan for the
single-user Mac workflow.

This stage is planning-only. It does not add backup scripts, generate backup
files, change business logic, change authentication logic, modify
`node.share_link`, add listening ports, execute SSH or remote commands, trigger
backend tasks, or change the current transit links.

## Local System Positioning

LiveLine Console is currently operated only on the user's own Mac:

- Access URL: `http://localhost:3000`
- No public production deployment is required.
- No public internet exposure is required.
- No domain name, HTTPS, Nginx, or Caddy setup is required.
- No multi-user role system is required.

The current priority is local data safety, repeatable backup before risky
changes, restore readiness after mistakes, and protection of the current
formal transit link.

## Why Local Backups Are Needed

The local PostgreSQL database may contain important operational state:

| Data category | Why it matters |
| --- | --- |
| VPS records | Preserve known server inventory metadata |
| Node records | Preserve node status and management history |
| Transit resource records | Preserve relay resource metadata |
| Transit route / forwarding records | Preserve current `gost` and `socat` route state |
| Task records | Preserve operation history |
| Task result summaries | Preserve non-sensitive acceptance and diagnostic summaries |
| Stage or acceptance state references | Preserve local workflow context |

Backups are useful before upgrades, migrations, route changes, manual cleanup,
or any operation that could affect the local database.

## Backup Scope

The planned backup scope is:

| Scope item | Backup treatment |
| --- | --- |
| PostgreSQL database | Core backup target |
| Docker Compose local data volumes | Include in future backup review |
| README / docs archive | Managed by Git, not the core database backup object |
| Real SSH private keys | Do not back up through this project plan |
| Real passwords | Do not export or write into backup docs |
| Complete node links | Do not write into docs or reports |
| Secrets and tokens | Do not write into docs or reports |

The database backup may contain sensitive database content. Treat backup files
as private local artifacts, not as source code.

## Planned Backup Directory Layout

Recommended local backup directory shape:

```text
backups/
  local-db/
    YYYYMMDD-HHMMSS/
      database backup artifact
      restore notes
      health-check result summary
```

Boundary for this stage:

- This stage does not create `backups/`.
- This stage does not write real backup files.
- Backup artifacts should not be committed to Git.
- A later stage may verify `.gitignore` coverage for `backups/`.

## Recommended Backup Timing

Create a backup before:

- Important code upgrades.
- Database migrations.
- Adding or modifying route resources.
- Formal cutover or route role changes.
- Large-scale deletion or cleanup.
- Manual operations where a restore point would reduce risk.
- Any moment the operator wants a local checkpoint.

## Restore Plan

The future restore workflow should include these safety checks:

1. Choose a restore window.
2. Stop containers or confirm a safe restore window.
3. Back up the current state before restoring, so a mistaken restore can be
   reversed.
4. Restore the PostgreSQL database from the selected backup artifact.
5. Start Docker Compose.
6. Check `/api/health`.
7. Confirm backend, PostgreSQL, Redis, and RQ Worker are healthy.
8. Log in to `http://localhost:3000`.
9. Check VPS, node, transit resource, and transit route records.
10. Confirm `node.share_link` was not accidentally changed.
11. Confirm the `socat` 18443 formal link remains unaffected.
12. Confirm the `gost` 8443 fallback link remains unaffected.

## Restore Acceptance Checklist

| Check | Expected result |
| --- | --- |
| Docker Compose starts | Services start locally |
| `/api/health` | backend/database/redis/worker are healthy |
| Login page | Opens at `http://localhost:3000` |
| Login | Correct browser-entered credentials open the system panel |
| VPS records | Expected records are present |
| Node records | Expected records are present |
| Transit resources | Expected records are present |
| Transit routes | Expected route records are present |
| `node.share_link` | Not accidentally changed by restore |
| `socat` 18443 formal link | Not affected |
| `gost` 8443 fallback link | Not affected |

## Backup File Safety Boundaries

Backup files may contain sensitive database content. Handle them carefully:

- Do not commit backup files to Git.
- Do not send backup files to Codex, ChatGPT, or public tools.
- Do not upload backup files to public cloud drives.
- Do not include real SSH private keys in project backup artifacts.
- Do not write real passwords into backup docs.
- Do not write real password hashes into backup docs.
- Do not write real `SESSION_SECRET` values into backup docs.
- Do not write tokens into backup docs.
- Do not write complete node links into backup docs.
- Do not paste raw database dumps into issues, pull requests, chats, or docs.

This document records process only. It must not contain real keys, passwords,
tokens, or complete node links.

## Future Implementation Stage

A later Stage 3.5.3 may implement or document exact local commands for:

- PostgreSQL backup.
- PostgreSQL restore.
- Backup file naming.
- `backups/` `.gitignore` verification.
- Health check after backup.
- Health check after restore.
- Sensitive-file-not-in-Git checks.
- Restore acceptance reporting.

Stage 3.5.2 does not implement these commands or scripts.

## Current Production Link Protection Boundary

| Item | Current state |
| --- | --- |
| Formal link | `socat` 18443 |
| Fallback link | `gost` 8443 |
| `node.share_link` | Already points to `socat` 18443 |
| Stage 3.5.2 `node.share_link` changes | None |
| Stage 3.5.2 new listening ports | None |
| Stage 3.5.2 `socat` 8443 takeover | None |
| Stage 3.5.2 `gost` 8443 shutdown / downgrade / replacement | None |
| Stage 3.5.2 cutover activity | None |

If any future stage adds or changes a listening port, the operator must also
check cloud security group, cloud firewall, and server firewall rules for the
corresponding TCP port.

## Current Prohibited Actions

The following remain prohibited in this stage:

- Do not modify code.
- Do not write backup scripts.
- Do not generate real backup files.
- Do not modify `node.share_link`.
- Do not read or output complete node links.
- Do not add listening ports.
- Do not add database migrations.
- Do not execute SSH.
- Do not execute remote commands.
- Do not modify firewall rules.
- Do not trigger backend Worker/RQ tasks.
- Do not perform cutover.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not let `socat` take over 8443.
- Do not write real passwords, real hashes, `SESSION_SECRET` values, SSH Keys,
  Passphrases, tokens, or complete node links.

## Stage 3.5.2 Recorded Impact

| Item | Result |
| --- | --- |
| Modified code | No |
| Wrote backup script | No |
| Generated real backup file | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Backup / Restore Planning Conclusion

The local backup and restore plan is documented. The project now has a clear
planning baseline for what should be backed up, when to back up, how restore
should be checked, how backup artifacts should be protected, and what a future
implementation stage may add.
