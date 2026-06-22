# Stage 3.3.128 - New transit VPS resource create approval

## 1. Stage goal

Stage 3.3.128 is a documentation-only approval stage. It does not create a transit resource, write the database, generate a Worker token, install a Worker, connect to any VPS, or create a HAProxy route.

The goal is to prepare approval requirements for creating a future new transit VPS resource record:

```text
Confirm the new transit VPS baseline information.
Confirm the public controller is available.
Confirm the Worker 0.1.24 binary can be downloaded.
Confirm resource field mapping rules.
Confirm future Worker install and HAProxy route creation require separate stages.
```

## 2. Accepted current state

Accepted context:

```text
The old Hong Kong transit VPS was removed by the user.
The old MKiepl transit Worker was removed by the user.
The project no longer protects the old hk-socat-live-23843 route.
The current active transit route count may be 0.
The public controller can serve the rebuilt Worker binary.
Future new transit VPS should install Worker 0.1.24-stage-3.3.122.
```

Known Worker binary checksum:

```text
cf7990f3ba0f85348fa714edb69a94d36b8752323fe9c843fa676cf50f38fcce
```

No full node link, candidate link, SSH credential, Worker token, or `nodes.share_link` value is recorded in this document.

## 3. Required new transit VPS information

Before creating a future resource record, the user must provide or confirm:

```text
Resource name, for example hk-transit-01 or sg-transit-01.
Cloud vendor or provider.
Transit VPS public IP or domain.
SSH port.
SSH username.
Whether root or sudo is available.
Operating system version, for example Debian 12, Ubuntu 22.04, or Ubuntu 24.04.
Ingress region.
Egress region.
Bandwidth Mbps.
Traffic limit.
Whether the VPS can access the public controller at http://my-con.golirong.xyz:8200.
Whether the VPS can access the landing VPS target port.
Planned network interface name, for example eth0 or ens3.
```

Do not record these sensitive values in docs, PRs, logs, or chat:

```text
SSH private key.
SSH password.
One-time Worker token.
Full node link.
Full share_link.
```

## 4. Resource creation field mapping

Future resource creation should map user-approved values into the existing `transit_resources` schema. Final field values must be checked against the current frontend and API schema immediately before execution.

Mapping direction:

```text
name: resource name.
resource_type: existing system-allowed transit VPS/server type.
provider: cloud vendor or provider.
entry_host: transit VPS public IP or domain.
entry_port: future transit entry port; may be empty or system default during resource creation.
entry_region: transit VPS region.
exit_region: future target egress region.
bandwidth_mbps: bandwidth.
traffic_limit_gb: traffic limit.
protocol_hint: haproxy_tcp / socat / unknown, using only system-allowed values.
has_ssh: whether SSH management is available.
ssh_host: SSH host.
ssh_port: SSH port.
ssh_username: SSH username.
status: initial state should be pending_worker or the current system-approved waiting-for-Worker state.
notes: safe notes only; no keys, passwords, Worker tokens, or full client links.
```

If current code or schema uses different enum names, the true execution stage must follow the code/schema rather than this planning text.

## 5. Public controller readiness checklist

Before creating a new transit VPS resource record, confirm:

```text
Public controller frontend is reachable.
Public controller backend health returns 200 OK.
PostgreSQL is healthy.
Redis is healthy.
Console worker is registered.
Local download checksum for /worker_binary/liveline-worker-linux-amd64 is correct.
Public download checksum for /worker_binary/liveline-worker-linux-amd64 is correct.
```

## 6. Network reachability checklist

Before onboarding a new transit VPS, confirm:

```text
The new transit VPS can access http://my-con.golirong.xyz:8200.
The public controller is resolvable and the Worker binary can be downloaded from the new VPS.
The new transit VPS can access the landing VPS target port.
DNS resolution works.
System time is correct.
systemd is available.
curl is available.
```

## 7. Firewall and security group reminder

Stage 3.3.128 does not open or modify any port.

Before a future HAProxy TCP route is created, any new listen port must be allowed in all three layers:

```text
Cloud server security group allows the TCP port.
Cloud firewall allows the TCP port.
Server local firewall allows the TCP port.
```

## 8. Approval packet template

Template for a future user approval message before creating a new transit VPS resource record:

```text
Resource name:
Cloud vendor:
Public IP / domain:
SSH port:
SSH username:
Operating system version:
Root/sudo permission:
Ingress region:
Egress region:
Bandwidth:
Traffic limit:
Planned interface:
Can access public controller:
Can access landing target port:
Confirm this stage creates only the resource record and does not install Worker:
Confirm no Worker token is generated:
Confirm no HAProxy route is created:
```

Do not paste SSH private keys, SSH passwords, one-time Worker tokens, full client links, or full share links into the approval packet.

## 9. No-go conditions

Do not proceed to real resource creation if any condition is true:

```text
Public controller health is not 200.
Worker binary checksum does not match.
New transit VPS information is incomplete.
SSH user or port cannot be confirmed.
Root or sudo permission cannot be confirmed.
The new transit VPS cannot access the public controller.
The future Worker install command cannot be confirmed to use the public URL.
The user has not explicitly approved creating the resource record.
The user asks to install Worker or create a route in the same stage without entering the matching approval stage.
```

## 10. Safety boundary

Stage 3.3.128 safety boundary:

```text
No public controller deployment in this stage.
No database write in this stage.
No new transit resource creation in this stage.
No Worker token generation in this stage.
No Worker installation in this stage.
No SSH or remote command in this stage.
No Worker command creation in this stage.
No HAProxy route creation in this stage.
No HAProxy installation in this stage.
No socat mutation in this stage.
No Xray mutation in this stage.
No firewall/security group/cloud firewall mutation in this stage.
No cutover in this stage.
No full share_link exposure.
No transit_routes.share_link write.
```

## 11. Next recommended stage

Recommended next stage:

```text
Stage 3.3.129-new-transit-vps-resource-create-execution
```

The next stage should only create the new transit VPS resource record after explicit approval. Worker installation should remain in a later separate stage.
