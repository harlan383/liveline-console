# Stage 3.3.37-c Worker Installer ReadWritePaths Precreate Hotfix

## Stage Goal

Stage 3.3.37-c fixes the Worker installer so the hardened systemd unit can start
cleanly when `ReadWritePaths=/opt/liveline-xray /etc/systemd/system /run/systemd`
is present.

This stage is a local code and documentation hotfix only. It does not perform
formal landing node creation.

## Problem

After Stage 3.3.37-b, the Worker unit kept the hardened sandbox:

```text
NoNewPrivileges=true
ProtectSystem=full
ProtectHome=read-only
PrivateTmp=true
ReadWritePaths=/opt/liveline-xray /etc/systemd/system /run/systemd
```

When `/opt/liveline-xray` did not already exist on the server, systemd could
fail namespace setup for `liveline-worker.service` with `status=226/NAMESPACE`.

## Fix

The generated Worker installer now runs the following before writing and
starting `liveline-worker.service`:

```bash
mkdir -p /opt/liveline-xray
chmod 755 /opt/liveline-xray
```

This precreates only the LiveLine-owned writable root required by the Worker
systemd sandbox.

## Explicit Non-Changes

- Does not install Xray.
- Does not create `/opt/liveline-xray/bin/xray`.
- Does not create `/opt/liveline-xray/config/config.json`.
- Does not create `liveline-xray.service`.
- Does not listen on `27939/TCP`.
- Does not trigger `landing_node_create`.
- Does not modify firewall, cloud firewall, or cloud security group rules.
- Does not write `node.share_link`.
- Does not generate a real `vless://` link.
- Does not execute cutover.

## Safety Boundary

This stage did not execute SSH or remote commands, did not connect to the
public console VPS, did not connect to the landing VPS, did not reinstall Worker
on a real VPS, did not install Xray, did not create a node, did not add a
listening port, did not modify firewall or cloud security group state, did not
modify `node.share_link`, did not generate a real node link, and did not perform
cutover.

The previous failed `landing_node_create` record remains historical state. This
stage does not create a new `landing_node_create` record.

## Modified Files

- `backend/app/api/routes/workers.py`
  - Precreates `/opt/liveline-xray` with mode `755` before writing and starting
    `liveline-worker.service`.
- `README.md`
  - Adds the Stage 3.3.37-c scope and stage status.
- `docs/stage-3.3.37-c-worker-installer-readwritepaths-precreate-hotfix.md`
  - Records the issue, fix, validation boundary, and no-execution safety
    constraints.

## Validation Checklist

- `git diff --check`
- `python3 -m compileall backend/app`
- `docker compose exec -T frontend npm run build`
- `docker compose up --build -d`
- `curl -s http://127.0.0.1:8000/api/health`
- `curl -I http://127.0.0.1:3000`
- Redis `temp_credential:*` remains `0`.
- Pending / running tasks remain `0`.
- `landing_node_create` does not get a new record.
- Sensitive scan finds no real token, password, `SESSION_SECRET`, Reality
  privateKey, complete `vless://` node link, or complete Worker token.
