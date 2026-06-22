# Stage 3.3.127 - New transit VPS Worker onboarding plan

## 1. Stage goal

Stage 3.3.127 is a documentation-only planning stage. It does not install a Worker, create a transit resource, create a Worker token, connect to any VPS, or perform remote execution.

Goals for later stages:

```text
Add a new transit VPS.
Install the current LiveLine Worker from the public controller.
Confirm the Worker version should be 0.1.24-stage-3.3.122.
Prepare for later HAProxy TCP route creation.
```

## 2. Current accepted state

Accepted context:

```text
The old Hong Kong transit VPS has expired and was removed by the user.
The old MKiepl transit Worker was removed by the user.
The project no longer protects the old hk-socat-live-23843 route.
The current active transit route count may be 0.
Stage 3.3.126-c confirmed the public controller can serve the rebuilt Worker binary.
```

Known Worker binary checksum from Stage 3.3.126-a / 3.3.126-c:

```text
cf7990f3ba0f85348fa714edb69a94d36b8752323fe9c843fa676cf50f38fcce
```

No full node link, candidate link, or `nodes.share_link` value is recorded in this document.

## 3. New transit VPS selection checklist

Recommended selection criteria for a future transit VPS:

```text
Prefer Hong Kong, Singapore, Japan, Taiwan, or another region close to the expected client traffic.
Start with at least 100Mbps bandwidth; use higher bandwidth for multi-stream live workloads.
Prefer Debian 12 or Ubuntu 22.04/24.04.
Root or sudo access must be available for the future Worker install stage.
The VPS must be able to reach the public controller: http://my-con.golirong.xyz:8200.
The VPS must be able to reach the landing VPS target port.
```

Selection should be finalized before any Worker token is generated.

## 4. Firewall and security group checklist

Any future HAProxy TCP route listen port must be opened in all three places:

```text
Cloud server security group allows the chosen TCP port.
Cloud firewall allows the chosen TCP port.
Server local firewall allows the chosen TCP port.
```

Stage 3.3.127 does not modify firewall rules, cloud security groups, or cloud firewalls.

## 5. Worker onboarding plan

Future onboarding plan, reserved for later explicit authorization:

```text
Add a new transit server/resource from the Transit Servers page.
Generate a one-time Worker install command.
Confirm the install command uses the public controller URL, not localhost.
Run the install command on the new transit VPS.
Confirm liveline-worker.service is active.
Confirm Worker heartbeat is online.
Confirm Worker version = 0.1.24-stage-3.3.122.
Confirm role = transit.
Confirm interface_name is correct for the selected VPS network interface.
```

No resource is created and no install command is generated in Stage 3.3.127.

## 6. HAProxy readiness plan

After the future Worker is online, verify HAProxy readiness before creating a HAProxy TCP route:

```text
HAProxy is installed.
haproxy -v is available.
systemctl is available.
The planned listen port is not occupied.
The new transit VPS can reach the landing VPS target TCP port.
Cloud security group allows the planned listen TCP port.
Cloud firewall allows the planned listen TCP port.
Server local firewall allows the planned listen TCP port.
```

If HAProxy is not installed, open a separate future stage for HAProxy installation. Stage 3.3.127 does not install HAProxy.

## 7. Future stage sequence

Recommended future stages:

```text
Stage 3.3.128-new-transit-vps-resource-create-approval
Stage 3.3.129-new-transit-vps-worker-install-approval
Stage 3.3.130-new-transit-vps-worker-install-acceptance
Stage 3.3.131-haproxy-tcp-route-create-preflight
Stage 3.3.132-haproxy-tcp-route-create-approval
Stage 3.3.133-haproxy-tcp-route-create-execution
```

These names are planning suggestions only. They do not authorize automatic execution.

## 8. No-go conditions

Do not proceed to future onboarding or HAProxy route creation if any condition is true:

```text
Public controller health is not 200.
Public Worker binary checksum does not match the expected checksum.
The new transit VPS cannot reach the public controller.
The new transit VPS cannot reach the landing target port.
Root or sudo access cannot be confirmed.
Worker role/interface cannot be confirmed.
The planned listen port has not been opened in all three firewall/security layers.
The user has not explicitly authorized real installation or route creation.
```

## 9. Safety boundary

Stage 3.3.127 safety boundary:

```text
No public controller deployment in this stage.
No new resource creation in this stage.
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

## 10. Next recommended stage

Recommended next stage:

```text
Stage 3.3.128-new-transit-vps-resource-create-approval
```

The next stage should only approve creating a new transit VPS resource record. It should not install the Worker automatically.
