# Stage 3.5.1 Local Console Operations Readiness

## Current Stage Conclusion

Stage 3.5.1 documents daily local-console operations for a single-user Mac
workflow.

This stage is documentation-only. It does not change business logic,
authentication logic, database schema, `node.share_link`, listening ports,
firewall rules, backend tasks, or the current transit links.

## Local-Only System Positioning

LiveLine Console is currently operated only on the user's own Mac:

- Access URL: `http://localhost:3000`
- No public production deployment is required.
- No public internet exposure is required.
- No domain name, HTTPS, Nginx, or Caddy setup is required.
- No multi-user roles or enterprise permission model is required.
- No enterprise audit console is required.

The operational focus is local startup reliability, local login usability,
local data safety, and avoiding accidental impact to the current transit links.

## Current Production Link Protection Baseline

| Item | Current state |
| --- | --- |
| Formal link | `socat` 18443 |
| Fallback link | `gost` 8443 |
| `node.share_link` | Already points to `socat` 18443 |
| Stage 3.5.1 `node.share_link` changes | None |
| Stage 3.5.1 new listening ports | None |
| Stage 3.5.1 `socat` 8443 takeover | None |
| Stage 3.5.1 `gost` 8443 shutdown / downgrade / replacement | None |
| Stage 3.5.1 cutover activity | None |

If any future stage adds or changes a listening port, the operator must also
check cloud security group, cloud firewall, and server firewall rules for the
corresponding TCP port.

## Daily Local Operations

### Enter the project directory

```bash
cd "/Users/peng/同步空间/AI项目/直播线路搭建/live-network/LiveLine Console"
```

### Start the system

Use the normal local start command when images are already built:

```bash
docker compose up -d
```

Use the rebuild command after code or dependency changes:

```bash
docker compose up --build -d
```

### Stop the system

```bash
docker compose down
```

Do not use volume deletion commands for normal daily operation.

### Restart the system

```bash
docker compose down
docker compose up -d
```

If local images need to be rebuilt:

```bash
docker compose down
docker compose up --build -d
```

### Check Docker container status

```bash
docker compose ps
```

Expected local services include frontend, backend, PostgreSQL, Redis, and the
RQ Worker.

### Open the local console

Open the browser at:

```text
http://localhost:3000
```

When logged out, only the login page should be visible.

### Check backend health

```bash
curl http://localhost:8000/api/health
```

Expected result: backend, database, redis, and worker are healthy.

### Check Git status

```bash
git status --short
git log --oneline --decorate -5
```

Use these before and after local work to confirm which files changed.

## Local Login Readiness Check

Use the browser for login checks. Do not type the real password into terminal
commands, docs, logs, scripts, or Git.

| Check | Expected result |
| --- | --- |
| Open `http://localhost:3000` while logged out | Login page is shown |
| Enter correct credentials in the browser | System panel opens |
| Refresh after login | Session remains active |
| Click logout | Browser returns to login page |
| Open the page after logout | System panel is not visible |
| Enter wrong credentials | Generic failure or rate-limit message is shown |

## Health Readiness Check

The local health check should confirm:

| Component | Expected result |
| --- | --- |
| Backend | Healthy |
| PostgreSQL | Healthy |
| Redis | Healthy |
| RQ Worker | Healthy |
| Frontend login page | Loads at `http://localhost:3000` |
| Auth gate | Unauthenticated users see only the login page |

## Troubleshooting

### `http://localhost:3000` does not open

1. Check containers:

   ```bash
   docker compose ps
   ```

2. Confirm the frontend container is running.
3. If containers are stale, restart locally:

   ```bash
   docker compose down
   docker compose up -d
   ```

### `/api/health` is not healthy

1. Run:

   ```bash
   curl http://localhost:8000/api/health
   ```

2. Check which component is unhealthy: backend, database, redis, or worker.
3. Check container state with:

   ```bash
   docker compose ps
   ```

### Login page does not load

1. Check the frontend container with `docker compose ps`.
2. Confirm `http://localhost:3000` is the browser target.
3. Confirm backend health if the login page loads but authentication fails.

### Login fails

- Do not type the real password into terminal commands.
- Do not write the real password into docs, logs, shell history, scripts, or
  Git.
- Use the browser login form only.
- Repeated failures may trigger the login rate limit; wait for the lock window
  before trying again.

## Local Usage Boundaries

Stage 3.5.1 records the following local-only boundaries:

- The system is used locally on the user's Mac.
- The console is not exposed to the public internet.
- No public production deployment is performed.
- No domain or HTTPS setup is required for the current local workflow.
- No Nginx or Caddy reverse proxy is required.
- No multi-user role system is added.
- No enterprise audit backend is added.
- No production release flow is introduced.

## Current Prohibited Actions

The following remain prohibited in this stage:

- Do not modify code.
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

## Stage 3.5.1 Recorded Impact

| Item | Result |
| --- | --- |
| Modified code | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Readiness Conclusion

Local console daily operations are documented. The operator can start, stop,
restart, inspect health, open the local console, verify login behavior, and
handle common local failures without changing the current production transit
links.
