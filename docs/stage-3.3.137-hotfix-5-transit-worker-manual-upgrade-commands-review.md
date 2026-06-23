# Stage 3.3.137-hotfix-5 Transit Worker Manual Upgrade Commands Review

## Goal

Record a safe manual command review checklist for upgrading the `mkiepl广港` transit Worker before re-running the Stage 3.3.137 HAProxy route dry-run.

Current transit Worker version:

```text
0.1.24-stage-3.3.122
```

Required transit Worker version:

```text
0.1.25-stage-3.3.137-hotfix-2
```

Public controller bundled Worker binary:

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

Expected checksum:

```text
fbc2e240bbb8cd64962e5151752cf410951673efadae704d192ca83f2ab89d2b
```

This stage only documents and displays the command review. It does not perform the upgrade.

## A. Public Controller VPS Checks

These commands are intended for the public controller VPS and only verify the bundled Worker binary exists, has the expected checksum, and reports the target version.

```bash
cd /opt/liveline-console

sha256sum backend/worker-binaries/liveline-worker-linux-amd64

chmod +x backend/worker-binaries/liveline-worker-linux-amd64

./backend/worker-binaries/liveline-worker-linux-amd64 version
```

Expected:

```text
version: 0.1.25-stage-3.3.137-hotfix-2
checksum: fbc2e240bbb8cd64962e5151752cf410951673efadae704d192ca83f2ab89d2b
```

Do not write any real token, private key, complete node link, or share link into this document, PR, logs, notes, or chat.

## B. Transit VPS Manual Template

The following is a user-run template for the transit VPS. LiveLine Console does not generate a real SSH command, upload files, install Worker, or restart the remote service in this stage.

The path `/tmp/liveline-worker-linux-amd64` is only a placeholder for the binary after the user manually transfers it to the transit VPS.

```bash
sudo systemctl stop liveline-worker.service

sudo cp /usr/local/bin/liveline-worker /usr/local/bin/liveline-worker.bak.$(date +%Y%m%d%H%M%S)

sudo install -m 0755 /tmp/liveline-worker-linux-amd64 /usr/local/bin/liveline-worker

/usr/local/bin/liveline-worker version

sudo systemctl start liveline-worker.service

sudo systemctl status liveline-worker.service --no-pager -l
```

Safety notes:

- The user performs these commands manually on the transit VPS.
- The system does not SSH.
- The system does not upload the binary.
- The system does not restart the remote Worker.
- The system does not create Worker command or HAProxy route.

## C. Post-Upgrade Acceptance

Preferred acceptance path:

```text
Stage 3.3.137-hotfix-3：Transit Worker 升级验收
```

Refresh the read-only acceptance panel and verify the Worker version is at least:

```text
0.1.25-stage-3.3.137-hotfix-2
```

Optional read-only database check on the public controller VPS:

```bash
cd /opt/liveline-console

docker compose exec -T postgres psql -U livelines -d livelines -c "
SELECT id, role, status, server_id, hostname, interface_name, worker_version, last_heartbeat_at
FROM workers
WHERE server_id = '80ec346d-3ac1-402e-ab09-33cb404ca81c'
ORDER BY last_heartbeat_at DESC NULLS LAST, created_at DESC
LIMIT 5;
"
```

Do not query or print token, secret, `nodes.share_link`, `transit_routes.share_link`, or complete client links.

Acceptance passes only when:

- `role = transit`
- `status = online` or heartbeat is online
- `worker_version >= 0.1.25-stage-3.3.137-hotfix-2`
- `interface_name = eth0`
- `server_id = 80ec346d-3ac1-402e-ab09-33cb404ca81c`

After acceptance passes, return to Stage 3.3.137 and regenerate the HAProxy route dry-run.

## Safety Boundary

This stage does not:

- SSH or run remote commands
- automatically install Worker
- automatically restart remote Worker
- generate Worker token
- generate complete install command
- create Worker command
- create real execution command
- create HAProxy route
- create TransitRoute active record
- install HAProxy
- bind `23843`
- modify firewall / security group / cloud firewall
- cutover
- read or output full `nodes.share_link`
- write `transit_routes.share_link`
- generate full VLESS / V2Ray client links

## Validation

Planned validation:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
```

Frontend production build is required because this stage adds a UI command review section.
