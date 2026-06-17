# Stage 3.3.37-e Formal Create Client Acceptance Record

## Stage Goal

Stage 3.3.37-e records the successful client acceptance result after the formal
landing-node create flow completed.

This stage only updates documentation and README state. It does not execute any
remote operation or change the running environment.

## Execution Boundary

This documentation stage did not:

- execute SSH or remote commands
- connect to the public console VPS
- connect to the landing VPS
- run `docker compose`
- trigger `landing_node_create`
- reinstall Worker
- install Xray
- restart `liveline-xray`
- modify Xray config
- add listening ports
- modify firewall, cloud firewall, or cloud security group rules
- modify the database
- modify `node.share_link`
- generate a real node link
- perform cutover

## Deployment Baseline

The public console had already been deployed to main:

```text
ca10e668b3b089c3e9b2a3707927f0201c7ff0c8
```

## Worker Version Record

The accepted landing Worker was online with:

```text
worker_id = 3d7c1bfa-...-9990
worker_version = 0.1.6-stage-3.3.37
role = landing
interface_name = ens17
status = online
```

The Worker ID is intentionally masked.

## Successful Create Command Record

The latest formal create command succeeded:

```text
command_id = d83828be-...-256a
command_type = landing_node_create
status = succeeded
worker_id = 3d7c1bfa-...-9990
completed_at = 2026-06-17 01:04:15+00
```

Command and Worker IDs are intentionally masked.

## Xray Service State Record

The landing VPS runtime state was recorded as:

```text
landing_ip = 64.90.13.19
node_port = 27939/TCP
27939/TCP = listening
listening_process = xray
liveline-xray.service = active running
xray_path = /opt/liveline-xray/bin/xray
config_path = /opt/liveline-xray/config/config.json
systemd_service = /etc/systemd/system/liveline-xray.service
```

## Node Table Record

The `nodes` table write succeeded:

```text
node_id = a71472c6-...-e4ef
node_name = liveline-reality-27939
protocol = vless
transport = tcp
security = reality
flow = xtls-rprx-vision
xray_port = 27939
service_status = active
status = active
has_share_link = true
share_link_length = 250
connectivity_status = not_checked
```

The node ID is intentionally masked. The real `node.share_link` is recorded only
as present and written. It is not displayed here.

This document does not include the complete `vless://` link, Reality private
key, complete UUID, complete public key, or shortId.

## TCP Reachability Record

TCP reachability was validated:

```text
public_console_vps -> 64.90.13.19:27939 = open
```

## Client Acceptance Record

Client-side acceptance passed:

```text
After importing the node into the client, normal internet access worked.
```

The client import used the real generated node link outside this document. The
link is not written to README, docs, terminal logs, or chat.

## Historical Failure Records

Historical failed records are retained for troubleshooting:

```text
command_id = 2a837896-...-1699
status = failed
error = open /usr/local/bin/xray: read-only file system
hotfix = Stage 3.3.37-b xray install path and worker sandbox hotfix

command_id = 6108ec61-...-afaa
status = failed
error = preflight refused because /opt/liveline-xray already exists
hotfix = Stage 3.3.37-d allow empty liveline xray dir hotfix

command_id = b47c2e04-...-f035
status = failed
error = preflight refused because /opt/liveline-xray already exists
hotfix = Stage 3.3.37-d allow empty liveline xray dir hotfix
```

Historical command IDs are intentionally masked.

## Current Status Conclusion

- Formal landing-node creation completed successfully.
- `liveline-xray.service` is active and running.
- `27939/TCP` is listening.
- The active node record exists in `nodes`.
- `node.share_link` is present and written, but not displayed.
- Client import and normal internet access passed.
- This is not a cutover.
- No transit route or fallback route was changed by this record stage.

## Next Stage Suggestions

Recommended next-stage options:

- `Stage 3.3.38-post-acceptance-security-hardening-or-key-rotation-review`
- `Stage 3.3.38-transit-integration-planning`

Do not execute either next stage from this document.

## Sensitive Information Boundary

This document intentionally does not include:

- complete `vless://` node links
- Reality privateKey
- complete UUID values
- complete public keys
- shortId
- Worker setup tokens
- passwords
- `SESSION_SECRET`
- database passwords
