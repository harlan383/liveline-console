# Stage 3.3.125 - Worker 0.1.24 deploy plan

## 1. Stage goal

Stage 3.3.125 documents the deployment plan, pre-checks, rollback path, and HAProxy readiness checklist for upgrading the transit Worker to:

```text
0.1.24-stage-3.3.122
```

Target scope:

```text
transit Worker
Hong Kong transit VPS Worker
```

This stage is documentation-only. It does not deploy, replace, restart, or remotely execute the Worker.

## 2. Current known state

Known state before the future deployment stage:

```text
Public controller backend/frontend already deployed Stage 3.3.123 code.
UI supports the HAProxy TCP mode option.
Backend supports the socat / haproxy_tcp create-path allowlist.
Backend requires Worker >= 0.1.24-stage-3.3.122 for haproxy_tcp.
Current production socat route remains retained.
This stage does not touch the existing socat route.
```

Current production socat route summary:

```text
route name: hk-socat-live-23843
listen port: 23843
target port: 27939
forwarding_method: socat
service_name: liveline-socat-23843.service
```

No full node link, candidate link, or `nodes.share_link` value is recorded here.

## 3. Deployment pre-check checklist

Before any future Worker upgrade is authorized, verify:

```text
Public controller health returns 200 OK.
PostgreSQL is healthy.
Redis is healthy.
RQ worker is registered.
Transit Worker is currently online.
Transit Worker server_id, role, and interface_name match the expected preflight target.
Existing socat service is still active.
23843 is still LISTEN.
Current client path through the socat route is still usable.
No pending/running/claimed transit_route_create Worker command exists.
No cleanup command is running.
```

If any check fails, do not proceed to Worker replacement.

## 4. Binary build checklist

Before a later deployment stage, build or verify the Linux amd64 Worker binary from:

```text
worker/cmd/liveline-worker
```

Required version string:

```text
0.1.24-stage-3.3.122
```

Recommended local/CI validation before publishing the binary:

```text
go test ./cmd/liveline-worker
go build ./cmd/liveline-worker
```

If using the bundled artifact workflow:

```text
backend/worker-binaries/liveline-worker-linux-amd64
```

then compare:

```text
embedded Worker version string
sha256 checksum
file mode / executable bit
```

The checksum should be recorded in the deployment-stage evidence, not in this plan unless it has been generated from the exact final binary.

## 5. Deployment plan for later stage

The following steps are reserved for a later explicitly authorized stage, for example:

```text
Stage 3.3.126-worker-binary-0.1.24-deploy
```

Planned future sequence:

```text
Upload the new Worker binary to a temporary path on the transit VPS.
Verify sha256 for the uploaded binary.
Stop liveline-worker.
Back up the existing Worker binary.
Replace /usr/local/bin/liveline-worker.
Start liveline-worker.
Confirm systemd active.
Confirm heartbeat recovery.
Confirm Worker version = 0.1.24-stage-3.3.122.
Confirm existing socat service remains active.
Confirm 23843 remains LISTEN.
Confirm the existing socat route remains usable.
```

None of these deployment steps are executed in Stage 3.3.125.

## 6. Rollback plan

Rollback requirements for the future deployment stage:

```text
Keep the old Worker binary backup before replacement.
If the new Worker cannot start, restore the old binary immediately.
Run systemctl restart liveline-worker after restoring the old binary.
Confirm old Worker heartbeat recovery.
Confirm socat 23843 remains active/listening.
Do not delete the socat service.
Do not modify Xray.
Do not modify firewall rules.
Do not modify cloud security group or cloud firewall rules.
Do not cutover.
```

Rollback success criteria:

```text
liveline-worker.service active
Worker heartbeat visible from the controller
existing socat route unchanged
23843 still LISTEN
```

## 7. HAProxy readiness checklist

After the Worker upgrade, and before any real HAProxy TCP route creation, verify:

```text
HAProxy is installed on the transit VPS.
haproxy -v is available.
systemctl is available.
/etc/haproxy or the LiveLine-owned config directory is writable by the approved create path.
Planned listen port is not occupied.
Transit VPS can reach the landing target TCP port.
Cloud security group allows the planned TCP listen port.
Cloud firewall allows the planned TCP listen port.
Server local firewall allows the planned TCP listen port.
```

Stage 3.3.125 does not install HAProxy and does not change firewall rules.

## 8. No-go conditions

Do not proceed to Worker deployment if any of these are true:

```text
Public controller health is not 200.
Database or Redis is unhealthy.
Transit Worker is offline.
Current socat route is unhealthy.
23843 is no longer LISTEN.
A transit_route_create command is pending/running/claimed.
A cleanup command is running.
The old Worker binary cannot be backed up.
The rollback path cannot be confirmed.
The user has not explicitly authorized the deployment stage.
```

## 9. Safety boundary

Stage 3.3.125 safety boundary:

```text
No deployment in this stage.
No Worker replacement in this stage.
No HAProxy route creation in this stage.
No socat restart/stop/delete.
No Xray mutation.
No firewall/security group/cloud firewall mutation.
No cutover.
No full share_link exposure.
No transit_routes.share_link write.
No full VLESS/V2Ray link output.
```

## 10. Next recommended stage

Recommended next stage:

```text
Stage 3.3.126-worker-binary-0.1.24-deploy
```

That stage must require explicit user authorization before any upload, service restart, Worker replacement, remote command, or production validation.
