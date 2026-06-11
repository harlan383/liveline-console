# Stage 3.5.3 Local Backup and Restore Implementation

## Current Stage Conclusion

Stage 3.5.3 implements local PostgreSQL backup and restore helper scripts for
the single-user Mac workflow.

This stage does not change business logic, authentication logic, database
schema, `node.share_link`, listening ports, firewall rules, backend tasks, or
the current transit links.

## Project State Checked Before Implementation

The current Docker Compose database service is:

| Item | Value |
| --- | --- |
| PostgreSQL service name | `postgres` |
| Image | `postgres:16-alpine` |
| Default database | `${POSTGRES_DB:-livelines}` |
| Default user | `${POSTGRES_USER:-livelines}` |
| Password source | `POSTGRES_PASSWORD` environment variable |
| Backend database URL source | `DATABASE_URL` environment variable |
| Data volume | `postgres_data` |

The scripts use the existing Docker Compose `postgres` service and read
database name/user from container environment variables. They do not print the
database password.

## Added Scripts

| Script | Purpose |
| --- | --- |
| `scripts/local-db-backup.sh` | Create a local PostgreSQL custom-format backup |
| `scripts/local-db-restore.sh` | Restore a local `.dump`, `.backup`, or `.sql` backup after confirmation |
| `scripts/local-health-check.sh` | Check Docker Compose services and `/api/health` |

All scripts use `set -euo pipefail`.

## Backup Script Usage

Run from the project root:

```bash
scripts/local-db-backup.sh
```

Behavior:

- Checks that Docker is available.
- Checks that the `postgres` service is ready through `pg_isready`.
- Creates `backups/local-db/YYYYMMDD-HHMMSS/`.
- Writes `liveline-db-YYYYMMDD-HHMMSS.dump`.
- Prints the backup path, byte size, and timestamp.
- Does not print database password, `SESSION_SECRET`, SSH Key, token, or
  complete node links.

The backup format is PostgreSQL custom format created with `pg_dump -Fc`.

## Restore Script Usage

Run from the project root with an explicit backup file path:

```bash
scripts/local-db-restore.sh backups/local-db/<timestamp>/liveline-db-<timestamp>.dump
```

Supported file types:

- `.dump`
- `.backup`
- `.sql`

Restore safety behavior:

- Requires a backup file path.
- Verifies the file exists and is non-empty.
- Warns that restore can overwrite current local database state.
- Recommends creating a fresh backup before restore.
- Recommends stopping app services before restore:

  ```bash
  docker compose stop backend worker frontend
  ```

- Requires typing `RESTORE LOCAL DB` before proceeding.
- Does not delete backup files.
- Does not print database password, secrets, tokens, or complete node links.
- After restore, asks the operator to run health checks and manually verify
  records.

## Health Check Script Usage

Run from the project root:

```bash
scripts/local-health-check.sh
```

Behavior:

- Prints `docker compose ps`.
- Calls `http://localhost:8000/api/health`.
- Prints formatted JSON when `jq` is available.
- Prints backend, database, Redis, and worker statuses when `jq` is available.
- Does not trigger backend tasks.
- Does not execute SSH or remote commands.
- Does not modify data.

## Backup Directory and Git Protection

Local backup artifacts should use:

```text
backups/local-db/YYYYMMDD-HHMMSS/
```

`.gitignore` now excludes:

- `backups/`
- `backups/local-db/`
- `liveline-db-*.sql`
- `*.dump`
- `*.backup`

Real backup files must not be committed to Git, pasted into chats, or uploaded
to public storage.

## Restore Acceptance Checklist

After a restore:

1. Start services:

   ```bash
   docker compose up -d
   ```

2. Run:

   ```bash
   scripts/local-health-check.sh
   ```

3. Confirm `/api/health` reports backend, database, redis, and worker healthy.
4. Open `http://localhost:3000`.
5. Log in through the browser.
6. Check VPS records.
7. Check node records.
8. Check transit resources.
9. Check transit routes.
10. Confirm `node.share_link` was not accidentally changed.
11. Confirm `socat` 18443 formal link remains unaffected.
12. Confirm `gost` 8443 fallback link remains unaffected.

## Current Production Link Protection Boundary

| Item | Current state |
| --- | --- |
| Formal link | `socat` 18443 |
| Fallback link | `gost` 8443 |
| `node.share_link` | Already points to `socat` 18443 |
| Stage 3.5.3 `node.share_link` changes | None |
| Stage 3.5.3 new listening ports | None |
| Stage 3.5.3 `socat` 8443 takeover | None |
| Stage 3.5.3 `gost` 8443 shutdown / downgrade / replacement | None |
| Stage 3.5.3 cutover activity | None |

If any future stage adds or changes a listening port, the operator must also
check cloud security group, cloud firewall, and server firewall rules for the
corresponding TCP port.

## Security Boundary

- Do not commit backup files to Git.
- Do not send backup files to Codex, ChatGPT, or public tools.
- Do not upload backup files to public cloud storage.
- Do not write real database passwords into scripts, docs, logs, or Git.
- Do not write real password hashes into scripts, docs, logs, or Git.
- Do not write real `SESSION_SECRET` values into scripts, docs, logs, or Git.
- Do not write SSH Keys or Passphrases into scripts, docs, logs, or Git.
- Do not write tokens into scripts, docs, logs, or Git.
- Do not write complete node links into scripts, docs, logs, or Git.
- Do not read or output complete node links.
- Do not execute SSH or remote commands.
- Do not trigger backend Worker/RQ tasks.
- Do not modify firewall rules.
- Do not perform cutover.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not let `socat` take over 8443.

## Stage 3.5.3 Recorded Impact

| Item | Result |
| --- | --- |
| Modified business code | No |
| Added backup script | Yes |
| Added restore script | Yes |
| Added health check script | Yes |
| Updated `.gitignore` | Yes |
| Generated real backup file | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Local Validation

Validation expected for this stage:

- `bash -n scripts/local-db-backup.sh`
- `bash -n scripts/local-db-restore.sh`
- `bash -n scripts/local-health-check.sh`
- `docker compose ps`
- `curl http://localhost:8000/api/health`
- `git status --short`
- `git diff --check`
- Sensitive information scan

This stage does not require committing a real backup file.

## Implementation Conclusion

Local PostgreSQL backup, restore, and health-check helper scripts are now
available for the local single-user workflow. Backup artifacts are ignored by
Git, restore requires explicit confirmation, and the current production transit
links remain unchanged.
