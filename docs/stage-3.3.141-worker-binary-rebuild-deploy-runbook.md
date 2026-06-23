# Stage 3.3.141 Worker Binary Rebuild / Deploy Runbook

## Stage Goal

Stage 3.3.141 prepares the rebuild and deployment runbook for the transit Worker binary that includes the Stage 3.3.139 HAProxy real-create Worker source and the Stage 3.3.140 backend fixed-parameter gate.

This stage is a documentation and operator-safety stage only. It does not rebuild or deploy the Worker binary by itself.

## Current Baseline

Required merged code before this runbook:

- Stage 3.3.139: HAProxy real-execution code path merged.
- Stage 3.3.140: backend fixed approved-parameter gate merged.

Current approved HAProxy real-create route remains:

```text
listen: 23843
target: 64.90.13.19:27939
route_name: haproxy-tcp-23843
service_name: liveline-haproxy-23843.service
forwarding_method: haproxy_tcp
```

## Safety Boundary

This runbook does not authorize any automatic remote execution.

This stage does not:

- Build a Worker binary in CI or this PR.
- Update `backend/worker-binaries/liveline-worker-linux-amd64`.
- Deploy the public controller.
- Restart backend, frontend, Redis, or Postgres.
- Deploy, restart, or replace any remote Worker.
- Install, start, stop, reload, or configure HAProxy.
- Bind port `23843` or any other listener.
- Modify cloud security group, cloud firewall, or server firewall.
- SSH into any VPS.
- Create a Worker command.
- Create a HAProxy route.
- Create a `TransitRoute` active record.
- Read, print, log, or write full `nodes.share_link`.
- Write `transit_routes.share_link`.
- Generate a full client link.
- Cut over traffic.

## Operator Roles and Execution Locations

### Local computer

Use the local development checkout for building and committing the Worker binary.

Expected path from prior stages:

```bash
cd "/Users/peng/同步空间/AI项目/直播线路搭建/live-network/LiveLine Console"
```

### Public controller VPS

Use only for pulling merged code and restarting controller services after the Worker binary update is merged.

Expected path:

```bash
cd /opt/liveline-console
```

### Transit VPS

Use only for manually replacing and restarting the transit Worker after the public controller has the updated bundled Worker binary.

Do not run public-controller commands on the transit VPS.
Do not run transit Worker replacement commands on the public controller VPS.

## Local Rebuild Plan

From the local development checkout:

```bash
cd "/Users/peng/同步空间/AI项目/直播线路搭建/live-network/LiveLine Console"
git checkout main
git pull --ff-only origin main
git checkout -b stage-3.3.141-worker-binary-rebuild-deploy
```

Build the Linux AMD64 Worker binary:

```bash
cd worker
GOCACHE=/private/tmp/liveline-go-cache GOOS=linux GOARCH=amd64 go test ./...
GOCACHE=/private/tmp/liveline-go-cache GOOS=linux GOARCH=amd64 go build -o ../backend/worker-binaries/liveline-worker-linux-amd64 ./cmd/liveline-worker
cd ..
```

Confirm the binary exists and record its checksum:

```bash
ls -lh backend/worker-binaries/liveline-worker-linux-amd64
shasum -a 256 backend/worker-binaries/liveline-worker-linux-amd64
```

Expected source-level Worker version currently remains:

```text
0.1.25-stage-3.3.137-hotfix-2
```

If the stage intentionally changes `workerVersion`, document that change and ensure backend version gates match it.

## Local Validation

Run these from the local checkout:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./... && GOCACHE=/private/tmp/liveline-go-cache go build ./... && cd ..
```

Frontend build is optional for binary-only update, but should be run if frontend files change.

Sensitive scan must confirm no secrets or full client links are committed:

```bash
git diff --cached -- . ':!backend/worker-binaries/liveline-worker-linux-amd64' | grep -Ei 'BEGIN .*PRIVATE KEY|worker_secret|install_token|vless://|vmess://|trojan://' || true
```

Binary files are not text-scanned with grep.

## Commit / PR Plan

Expected changed file for binary-only rebuild:

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

Optional documentation update:

```text
README.md
docs/stage-3.3.141-worker-binary-rebuild-deploy-runbook.md
```

Commit example:

```bash
git status
git add backend/worker-binaries/liveline-worker-linux-amd64 README.md docs/stage-3.3.141-worker-binary-rebuild-deploy-runbook.md
git commit -m "Stage 3.3.141 rebuild transit Worker binary for HAProxy real create"
git push -u origin stage-3.3.141-worker-binary-rebuild-deploy
```

Open PR against `main` and include:

- Binary checksum.
- `go test ./...` result.
- `go build ./...` result.
- Backend compile result.
- Sensitive scan result.
- Explicit statement that no deploy or remote execution occurred in the PR.

## Public Controller Deployment After Merge

Only after the binary rebuild PR is merged:

```bash
cd /opt/liveline-console
git pull --ff-only origin main
docker compose ps
```

If the controller containers need restart to serve the updated bundled binary:

```bash
docker compose up -d --build backend frontend
curl -sS http://127.0.0.1:8200/health
curl -I http://127.0.0.1:3200
```

Preserve current public port mapping:

```text
frontend 3200 -> 3000
backend 8200 -> 8000
postgres 15432 -> 5432
redis 16379 -> 6379
```

## Transit Worker Replacement Acceptance

Before replacing the transit Worker, confirm:

- Correct transit resource selected.
- Current transit Worker is online or replacement window is accepted.
- New binary checksum matches the PR checksum.
- No HAProxy route creation is triggered by replacing the Worker binary.
- No WorkerCommand is created during replacement.
- No firewall or cloud security group changes are made during replacement.

After replacement, verify heartbeat in LiveLine Console:

```sql
SELECT id, role, status, server_id, hostname, interface_name, worker_version, last_heartbeat_at
FROM workers
WHERE role = 'transit'
ORDER BY last_heartbeat_at DESC NULLS LAST;
```

Acceptance requires:

- Transit Worker status is `online`.
- Worker role is `transit`.
- `interface_name` is present.
- `worker_version` matches the rebuilt binary source version.
- `last_heartbeat_at` is fresh.

## Port and Firewall Reminder

Before any future real HAProxy route create on `23843/TCP`, manually confirm all three layers:

- Cloud security group allows `23843/TCP`.
- Cloud firewall allows `23843/TCP`.
- Transit VPS server firewall allows `23843/TCP`.

This runbook itself does not open or verify firewall rules.

## Final Go / No-Go for Real HAProxy Route Create

Even after Worker binary rebuild and deploy, real HAProxy route creation remains blocked unless all are true:

- Stage 3.3.137 HAProxy dry-run command succeeded.
- Stage 3.3.138 final approval is ready.
- Stage 3.3.139 real-execution typed confirmation is entered.
- Stage 3.3.140 backend fixed-parameter gate passes.
- Transit Worker is online and supports HAProxy TCP.
- HAProxy is installed on the transit VPS, or a separate approved install stage has completed.
- Cloud security group, cloud firewall, and server firewall are manually confirmed.
- User explicitly approves real creation.

No cutover or share-link mutation is authorized by this runbook.
