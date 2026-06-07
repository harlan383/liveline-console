# LiveLine Console

Stage 0 implements only the local project skeleton required by the v2.2
requirements document.

## Stage 0 scope

- Docker Compose project skeleton.
- Empty Next.js frontend with basic layout.
- FastAPI backend with `/api/health`.
- PostgreSQL connection.
- Redis connection.
- RQ Worker startup.
- Admin initialization and HttpOnly Cookie login skeleton.
- Initial Alembic database migration.

Stage 0 does not connect to VPS hosts, does not accept SSH keys, does not run
remote commands, does not install Xray, and does not use 3x-ui.

## Stage 1 scope

Stage 1 adds only the read-empty-VPS flow. SSH credentials are accepted only for
the read task, encrypted into Redis with a TTL, and removed by the Worker after
reading. RQ jobs receive only non-sensitive identifiers: `task_id`, `vps_id`,
and `temp_credential_id`.

The Worker uses paramiko and only runs read-only commands with timeouts. Stage 1
does not add nodes, install Xray, write remote files, edit systemd, change
firewall rules, generate links, generate QR codes, import/take over nodes, or
use 3x-ui.

## Stage 2.1 scope

Stage 2.1 adds only `prepare_node`, an installation pre-check task. It reuses
the Redis temporary credential flow and writes results only to `tasks.result_data`
and `task_logs`. It checks OS, architecture, root user, Xray presence, common
port occupancy, systemd, firewall tool status, and required local tools.

Stage 2.1 still does not install Xray, write VPS files, write Xray config,
create nodes, open ports, modify firewall rules, run `sudo` or `apt`, generate
links, generate QR codes, or use 3x-ui.

## Stage 2.2 scope

Stage 2.2 adds only `install_xray`. It requires the latest successful
`prepare_node` result, reuses Redis temporary SSH credentials, runs the official
XTLS Xray install command, enables and starts `xray.service`, verifies
`command -v xray`, `xray version`, and service status, then writes the result to
`tasks.result_data` and `task_logs`.

Stage 2.2 treats missing `/usr/local/etc/xray/config.json` and inactive
`xray.service` as warnings because business node configuration is created later.

Stage 2.2 does not create VLESS / VMess / Reality nodes, does not write business
node configuration, does not generate links or QR codes, does not write the
`nodes` table, does not modify firewall rules, does not open ports, does not
configure relay, and does not use 3x-ui.

## Stage 2.3 scope

Stage 2.3 adds only `create_direct_node`, which creates one direct VLESS Reality
node on an already installed Xray VPS. It writes
`/usr/local/etc/xray/config.json`, runs `xray run -test`, restarts `xray.service`,
verifies the service and listening port, writes one active `nodes` row, and
returns a `vless://` share link.

Stage 2.3 does not create QR codes, delete nodes, configure relay, modify
firewall rules, open ports, call 3x-ui, or store/return the Reality private key.

Stage 2.3 is frozen after real VPS acceptance. The frozen boundary allows only
one direct VLESS Reality node, `config.json` write, `xray run -test`, Xray
restart, port-listening verification, one `nodes` row, and a `vless://` share
link. It forbids relay, `dokodemo-door`, iptables forwarding, firewall changes,
3x-ui, QR codes, node deletion, multi-node management, traffic statistics, and
subscription links.

## Stage 2.4 scope

Stage 2.4 adds basic node management: node list, node detail, share-link copy,
`refresh_node`, and `restart_xray`. Refresh checks Xray binary/version, config
existence, `xray run -test`, service active state, and port listening state.
Restart runs config test first, restarts `xray.service`, then verifies service
and listening state.

Stage 2.4 does not delete nodes, generate QR codes, configure relay, modify
firewall rules, open ports, call 3x-ui, or store/return the Reality private key.

Stage 2.4 is frozen after real node-management acceptance. The frozen boundary
allows node list, node detail, `vless://` share-link display/copy,
`refresh_node`, `restart_xray`, Xray binary/config/service/listening checks,
`xray run -test`, Xray service restart, `nodes.status` updates, and task
`result_data` / `task_logs`. It forbids new node creation, node deletion, node
rebuilds, QR codes, IEPL / IPLC relay, `dokodemo-door`, iptables forwarding,
firewall changes, port opening, 3x-ui, subscription links, traffic statistics,
automatic speed tests, and `sshd_config` changes.

## Stage 2.5.1 scope

Stage 2.5.1 adds only node soft deletion / disablement through `delete_node`.
It backs up `/usr/local/etc/xray/config.json`, stops `xray.service`, moves the
active config to a disabled path, verifies the service is inactive and the node
port is no longer listening, then marks the node as `deleted` with
`deleted_at`. The historical `nodes` record is retained.

Stage 2.5.1 is frozen after real soft-deletion acceptance. The frozen boundary
allows node soft deletion, config backup, Xray service stop, moving the active
config to a disabled path, inactive/listening verification, `nodes.status`
update to `deleted`, `nodes.deleted_at`, `vps_servers.status` update to
`xray_installed_pending_config`, and task `result_data` / `task_logs`. It
forbids node rebuild, new node creation, new UUID generation, new Reality key
generation, new share-link generation, QR codes, IEPL / IPLC relay,
`dokodemo-door`, iptables forwarding, firewall changes, port opening, 3x-ui,
subscription links, traffic statistics, automatic speed tests, `sshd_config`
changes, and hard deletion of `nodes` records.

## Stage 2.5.2 scope

Stage 2.5.2 adds only a clear "recreate direct node" entry point and safety
protection after soft deletion. It does not add `rebuild_node`; it reuses
`create_direct_node` to create a new active node on the same VPS while keeping
the old deleted node unchanged.

Stage 2.5.2 refuses to overwrite an existing
`/usr/local/etc/xray/config.json`. If the standard config already exists, the
Worker fails before generating a new Reality key, before writing config, before
restarting Xray, and before writing the `nodes` table. Old
`config.json.bak.<timestamp>` and `config.json.disabled.<timestamp>` files are
left untouched.

Stage 2.5.2 does not add APIs, database fields, or Alembic migrations. It does
not restore old links, generate QR codes, configure relay, modify firewall
rules, open ports, call 3x-ui, add subscription links, add traffic statistics,
run speed tests, modify `sshd_config`, or hard-delete node history.

Stage 2.5.2 is frozen after real recreate acceptance. The frozen boundary
allows only reusing `POST /api/nodes/create-direct` and `create_direct_node` to
create a new active direct node after soft deletion, with config overwrite
protection. It keeps old deleted node history and old backup/disabled config
files unchanged, and forbids `rebuild_node`, rebuild APIs, schema changes,
relay, firewall changes, QR codes, 3x-ui, and hard deletion.

## Stage 2.6 scope

Stage 2.6 adds only frontend node export experience improvements. Node details
mask `share_link` by default, allow copying the full `vless://` link, allow
showing or hiding the full link, generate a QR code locally in the browser, and
show short client import hints.

Stage 2.6 does not change backend APIs, add database fields, add Alembic
migrations, connect to VPS hosts, upload SSH keys, trigger remote tasks, modify
Xray config, create/delete/rebuild/refresh nodes, restart Xray, configure relay,
modify firewall rules, open ports, use 3x-ui, add subscription links, add batch
export, add JSON export, add traffic statistics, run speed tests, or modify
`sshd_config`.

## Stage 2.7.1 scope

Stage 2.7.1 adds only Xray backup-file read-only viewing and manual restore
instructions. It creates `list_xray_backups` tasks through
`POST /api/vps/{vps_id}/xray-backups`, scans only `config.json*` file metadata
under `/usr/local/etc/xray/`, shows file name, path, type, size, modified time,
current config existence, Xray service state, and port 443 listening state.

Stage 2.7.1 does not read full config contents, download backup files, upload
backup files, restore config, delete backups, clean backups, modify remote
files, restart/stop/start Xray, create/delete/rebuild/refresh nodes, modify
backend database schema, add Alembic migrations, configure relay, modify
firewall rules, open ports, use 3x-ui, add subscription links, add traffic
statistics, run speed tests, or modify `sshd_config`.

## Stage 2.7.2.1 scope

Stage 2.7.2.1 adds only Xray backup cleanup dry-run preview. It creates
`preview_xray_backup_cleanup` tasks through
`POST /api/vps/{vps_id}/xray-backups/cleanup-preview`, reads only
`config.json*` file metadata under `/usr/local/etc/xray/`, and calculates which
`backup`, `disabled`, and `failed` files would be candidates if a future cleanup
stage kept the latest 3 files per type.

Stage 2.7.2.1 is preview-only. It does not delete, move, copy, restore,
download, upload, or read config contents. It does not add database fields or
Alembic migrations, create/delete/rebuild/refresh nodes, restart Xray, modify
Xray config, configure relay, modify firewall rules, open ports, use 3x-ui, add
subscription links, add traffic statistics, run speed tests, or modify
`sshd_config`.

## Stage 2.7.2.2-a scope

Stage 2.7.2.2-a adds only single-file deletion for `failed` dry-run cleanup
candidates. It creates `delete_xray_backup_candidate` tasks through
`POST /api/vps/{vps_id}/xray-backups/delete-candidate`, requires exact filename
confirmation, rescans before deletion, confirms the file is still a candidate,
deletes only `/usr/local/etc/xray/config.json.failed.<timestamp>`, and rescans
after deletion to verify the file is gone.

Stage 2.7.2.2-a does not delete `config.json`, `config.json.bak.*`,
`config.json.disabled.*`, unknown files, retained files, directories, or
multiple files. It does not support batch deletion, automatic cleanup,
wildcards, arbitrary paths, config restore, Xray restart/stop/start, node
changes, relay, firewall changes, port opening, 3x-ui, subscriptions, traffic
statistics, speed tests, `sshd_config` changes, database fields, or Alembic
migrations.

## Stage 3.1 scope

Stage 3.1 adds only transit resource management. It stores future relay resource
metadata in `transit_resources` and provides local database APIs plus a frontend
management panel for list, create, detail, edit, enable, and disable.

Supported resource types are `server`, `iepl`, `iplc`, and `other`. Supported
statuses are `active` and `disabled`. The table includes `deleted_at` for future
soft deletion, but Stage 3.1 does not expose hard deletion.

Stage 3.1 does not connect to Hong Kong servers, IEPL / IPLC lines, or landing
VPS hosts. It does not upload or save SSH keys, passwords, provider backend
accounts, or line secrets. It does not create Worker/RQ tasks, configure relay,
install relay tools, modify Xray config, change firewall rules, open ports,
write iptables, call 3x-ui, affect the current active direct node, generate
relay client links, create topology previews, run connectivity tests, collect
traffic statistics, or run speed tests.

## Stage 3.2 scope

Stage 3.2 adds only frontend local transit topology and configuration preview.
It lets the operator choose an active transit resource and an active node, enter
a planned relay listen port, choose a preview-only forwarding method, and view
the future topology plus a non-executable configuration preview.

Stage 3.2 does not add `transit_routes` or `forwarding_rules`, does not add
database fields, does not add Alembic migrations, does not add backend APIs,
does not create Worker/RQ tasks, does not connect to Hong Kong servers,
IEPL/IPLC lines, or landing VPS hosts, does not upload SSH keys, does not
configure relay, does not modify Xray, firewall, ports, or iptables, does not
call 3x-ui, does not modify `nodes` or `vps_servers`, and does not generate
real usable relay client links.

## Stage 3.3.1 scope

Stage 3.3.1 adds only `read_transit_server`, a read-only check for ordinary
public transit servers. It can read active `server` transit resources with SSH
metadata, accepts SSH credentials only as encrypted Redis temporary credentials,
and passes only `task_id`, `transit_resource_id`, and `temp_credential_id` to
the RQ job.

The Worker may only run read-only SSH commands with timeouts to inspect OS,
architecture, `whoami`, systemd availability, installed tool paths, TCP
listening ports, and firewall status. Results are written to
`tasks.result_data` and `task_logs`.

Stage 3.3.1 does not install `gost`, `nginx`, `socat`, or Xray
`dokodemo-door`; does not configure relay; does not connect to landing VPS
hosts; does not modify Xray, firewall, ports, or iptables; does not create
`transit_routes` or `forwarding_rules`; does not generate real transit links;
and does not affect the current active direct node.

Stage 3.3.1 is frozen after real Hong Kong transit-server read-only acceptance.
Early records showed `20575` in the listening-port inventory; later
Stage 3.3.3-fix-a validation confirmed the accepted SSH port is `22`. Future
transit forwarding must not reuse historical problem port `20575` as a listen
port without a separate review.

## Stage 3.3.2 scope

Stage 3.3.2 adds only `install_gost`, which installs a fixed gost binary on an
active public transit server and verifies the gost version. SSH credentials are
accepted only as encrypted Redis temporary credentials, and RQ jobs receive only
`task_id`, `transit_resource_id`, and `temp_credential_id`.

Stage 3.3.2 uses go-gost/gost `v3.2.6`, downloads the fixed official
`gost_3.2.6_linux_amd64.tar.gz` release, verifies the fixed sha256, uploads the
binary by SFTP, installs it to `/usr/local/bin/gost`, and runs
`/usr/local/bin/gost -V`.

Stage 3.3.2 does not create relay rules, does not create gost forwarding
systemd services, does not listen on new ports, does not connect to landing VPS
hosts, does not modify Xray, firewall, ports, or iptables, does not create
`transit_routes` or `forwarding_rules`, does not use `latest`, does not use
`curl | bash`, and does not generate relay links.

Stage 3.3.2 is frozen after real Hong Kong transit-server install acceptance.
The frozen boundary permits only fixed-version gost binary installation and
version verification. Real forwarding rule creation must be reviewed and
developed separately in Stage 3.3.3.

## Stage 3.3.3 scope

Stage 3.3.3 adds only one gost TCP transit route. It introduces
`transit_routes`, `POST /api/transit-routes`, optional route list/detail reads,
and `create_transit_route`. SSH credentials are still accepted only through
encrypted Redis temporary credentials, and RQ jobs never carry SSH Key or
Passphrase.

The Worker connects only to the Hong Kong transit server. It verifies
`/usr/local/bin/gost`, rejects listen port `20575`, rejects occupied ports,
writes one `liveline-transit-{route_id}.service`, runs `systemctl daemon-reload`,
`enable`, and `start`, verifies service active and port LISTEN, then stores a
transit `vless://` link in `transit_routes.share_link`.

Stage 3.3.3 does not delete transit routes, create multiple routes, create QR
codes, open firewalls, write iptables, call 3x-ui, install nginx/socat/xray,
configure Xray dokodemo-door, connect to landing VPS hosts, modify landing VPS
Xray, modify the original node, modify `node.share_link`, or modify
`vps_servers`. Cloud security-group port opening remains manual.

## Stage 3.3.3-fix-a scope

Stage 3.3.3-fix-a adds only `install_socat`, an installation/check task for
active public transit servers. It prepares for a later socat transparent TCP
forwarding test but does not create any socat route.

The API is `POST /api/transit-resources/{id}/install-socat`. SSH credentials
are accepted only through encrypted Redis temporary credentials, and the RQ job
receives only `task_id`, `transit_resource_id`, and `temp_credential_id`.

The Worker may check OS, architecture, `whoami`, systemd availability,
`command -v socat`, `command -v apt-get`, and `ss -ltnH`. If socat is missing
on Debian / Ubuntu, the only allowed write operations are `apt-get update` and
`apt-get install -y socat`. It then verifies `command -v socat` and `socat -V`.

Stage 3.3.3-fix-a does not create socat forwarding rules, does not listen on
new ports, does not create socat systemd services, does not modify existing
gost routes, does not generate new transit links, does not connect to landing
VPS hosts, does not modify Xray, firewall, ports, or iptables, and does not add
database fields or Alembic migrations.

Stage 3.3.3-fix-a is accepted after real Hong Kong transit-server socat
install/check validation. The accepted resource is
`6d67c275-8ac9-4775-9519-c89b50718157` (`香港中转服务器`) with
`ssh_host=163.223.216.108`, `ssh_port=22`, and `ssh_username=root`. The
successful task is `12ab7383-58c8-4eaa-9f38-68f313d59c59`; it installed
`/usr/bin/socat`, verified `socat -V`, cleared Redis temporary credentials, left
pending/running tasks at 0, and did not create forwarding rules or modify gost
routes, transit routes, nodes, Xray, firewall, or iptables.

Earlier failures were caused by the same resource having `ssh_port=20575`,
which did not return an SSH banner. After correcting the SSH port to `22`, the
install/check task passed. Duplicate Hong Kong transit resource records still
exist and should be reviewed before Stage 3.3.3-fix-b to avoid selecting the
wrong resource; no resource has been deleted.

## Stage 3.3.4-d scope

Stage 3.3.4-d adds the accepted controlled restart path for the socat test
route only. The accepted route is `hk-socat-test-18443`, with route id
`97fe351d-d5e6-4684-a37f-4a00b90b4e1e`, service
`liveline-socat-97fe351dd5e64684a37f4a00b90b4e1e.service`, listen endpoint
`163.223.216.108:18443`, and target `74.211.97.116:443`.

The real restart validation task
`25fcb0c8-2912-4073-bde5-897061672fb6` completed with status `success`,
`restart_result=true`, `service_status=true`, `listen_check=true`, and
`target_connectivity=true`. Redis temporary credentials were cleared, pending
/ running tasks returned to 0, health stayed ok, and the existing gost 8443
route remained active.

Stage 3.3.4-d does not switch traffic from gost to socat. The gost 8443 route
is still retained and must not be replaced by this stage. It also does not
modify `node.share_link`, add or delete routes, change firewall rules, write
iptables / nft rules, or run kill / pkill.

## Stage 3.3.4-e scope

Stage 3.3.4-e accepts the client connectivity validation for the socat 18443
test route. The tested route is `hk-socat-test-18443`, with transit endpoint
`163.223.216.108:18443`, forwarding method `socat`, and target
`74.211.97.116:443`.

The client test copied the existing direct Reality node, changed only the
server to `163.223.216.108` and the port to `18443`, and kept UUID, flow,
Reality, SNI, public key, shortId, fingerprint, spiderX, and other Reality
parameters unchanged. Shadowrocket could use the copied route normally, and
local `nc -vz 163.223.216.108 18443` returned `succeeded`.

Stage 3.3.4-e confirms the socat 18443 route is usable as a test link. It is
not a formal cutover. The gost 8443 route remains retained, `node.share_link`
is unchanged, and any formal switch must be handled in a separate cutover
stage.

## Cutover Plan A scope

Cutover Plan A is accepted as a low-risk frontend display enhancement. It shows
and copies a derived socat 18443 test link from the current direct Reality node
inside the "single route" management view. The derived link changes only the
server to `163.223.216.108` and the port to `18443`; all Reality parameters are
kept unchanged.

The accepted frontend validation confirmed the yellow Cutover status banner,
the `socat 18443` label `测试可用链路 / 待正式 cutover`, the `gost 8443` label
`回退链路 / 保留`, the "socat 测试链接" section, confirmation before copying,
successful copy, Shadowrocket import, and normal connectivity.

Cutover Plan A is not a formal replacement. It does not modify
`node.share_link`, does not modify `transit_routes`, does not trigger tasks,
does not connect to servers, and keeps the two active routes:
`hk-gost-test-8443 / gost / 8443 / active` and
`hk-socat-test-18443 / socat / 18443 / active`.

## Stage 3.3.5 Cutover B review scope

Stage 3.3.5 is a design review for Cutover Plan B. The proposed Plan B keeps
`gost` 8443 unchanged as a fallback route and keeps `socat` 18443 as the
already validated candidate route. It only designs how the frontend may present
and copy a `socat` 18443 candidate formal link derived from the current active
Reality node.

Stage 3.3.5 does not modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not connect to servers, and does
not perform a formal cutover.

## Stage 3.3.6 Cutover B UI scope

Stage 3.3.6 implements only the Cutover Plan B frontend display enhancement.
It shows `socat` 18443 as a candidate formal link and keeps `gost` 8443 visible
as the current formal / fallback route. The candidate link is derived in the
browser from the current active Reality node by changing only server and port.

Stage 3.3.6 is not a formal cutover. It does not modify `node.share_link`, does
not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
and does not stop or replace `gost` 8443.

## Stage 3.3.7 Cutover decision review scope

Stage 3.3.7 is a cutover decision review. It compares keeping the current
Plan B state, adding a possible Plan B+ acceptance/approval record, and a
higher-risk Plan C formal cutover.

Stage 3.3.7 does not perform a formal cutover. It does not modify
`node.share_link`, does not modify `transit_routes`, does not add database
migrations, does not add listening ports, does not trigger Worker/RQ tasks, does
not connect to servers, does not stop `gost` 8443, and does not let `socat`
take over 8443.

## Stage 3.3.8 Client candidate link acceptance scope

Stage 3.3.8 documents the client-side acceptance flow for the `socat` 18443
candidate formal link. The operator may copy the candidate link from the
frontend and manually import it into a client as a separate test node.

Stage 3.3.8 is not a formal cutover. It does not modify `node.share_link`, does
not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop `gost` 8443, and does not let `socat` take over 8443.

## Stage 3.3.9 Cutover readiness check scope

Stage 3.3.9 documents the readiness checklist and current blockers for any
future formal cutover. It reviews Docker/runtime acceptance, client candidate
link validation, fallback availability, rollback planning, and the unresolved
decision about whether to modify `node.share_link` or let `socat` take over
8443.

Stage 3.3.9 is not a formal cutover. It does not modify `node.share_link`, does
not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop `gost` 8443, and does not let `socat` take over 8443.

## Stage 3.3.10 Client test result record scope

Stage 3.3.10 records real client test results for the `socat` 18443 candidate
formal link. The candidate link should be imported manually as a separate test
node and must not overwrite the current formal node.

Stage 3.3.10 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop `gost` 8443, and does not let `socat` take over 8443.

## Stage 3.3.11 Formal cutover runbook scope

Stage 3.3.11 documents the formal cutover runbook for future execution. It
compares continuing Plan B, a possible B+ readiness-recording path, and a future
Plan C formal switch. It records preconditions, 8443 safety reminders, execution
drafts, rollback guidance, acceptance checks, blockers, and next-stage options.

Stage 3.3.11 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop `gost` 8443, and does not let `socat` take over 8443.

## Stage 3.3.12 Formal cutover approval scope

Stage 3.3.12 documents the formal cutover approval gate. It records the final
Plan B / B+ / C selection approval, execution permission confirmation,
`node.share_link` modification approval, remote-command approval, execution
window, rollback confirmation, Go / No-Go checklist, and current blockers.

Stage 3.3.12 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop `gost` 8443, and does not let `socat` take over 8443.

## Stage 3.3.13 B+ readiness record scope

Stage 3.3.13 records the approved Plan B+ readiness state. It documents the
manual decision that formal cutover is not allowed, `node.share_link` must not
be modified, remote commands are not allowed, `socat` must not take over 8443,
and `gost` 8443 must remain the formal/fallback route. It also records the
2026-06-07 client validation across Shadowrocket, v2rayN, and router scenarios.

Stage 3.3.13 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop `gost` 8443, and does not let `socat` take over 8443.

## Stage 3.3.14 C cutover decision pack scope

Stage 3.3.14 documents the C-plan formal cutover decision pack / pre-review.
It records the manual decision that C must not be formally executed yet,
`node.share_link` must not be modified, remote commands are not allowed,
`socat` must not take over 8443, and `gost` 8443 must remain the current
formal/fallback route.

Stage 3.3.14 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop, downgrade, or replace `gost` 8443, and does not let `socat` take
over 8443.

## Stage Status

| Stage | Status |
| --- | --- |
| Stage 1 | Frozen |
| Stage 2.1 | Frozen |
| Stage 2.2 | Frozen |
| Stage 2.3 | Frozen |
| Stage 2.4 | Frozen |
| Stage 2.5.1 | Frozen |
| Stage 2.5.2 | Frozen |
| Stage 2.6 | Frozen |
| Stage 2.7.1 | Frozen |
| Stage 2.7.2.1 | Frozen |
| Stage 2.7.2.2-a | Frozen |
| Stage 3.1 | Frozen |
| Stage 3.2 | Frozen |
| Stage 3.3.1 | Frozen |
| Stage 3.3.2 | Frozen |
| Stage 3.3.3 | Development complete, pending real route acceptance |
| Stage 3.3.3-fix-a | Accepted: socat install/check passed |
| Stage 3.3.4-d | Accepted: socat 18443 controlled restart passed |
| Stage 3.3.4-e | Accepted: socat 18443 client connectivity passed |
| Cutover Plan A | Accepted: frontend derived socat test link passed |
| Stage 3.3.5 Cutover B review | Design review documented, no formal cutover |
| Stage 3.3.6 Cutover B UI | Frontend runtime acceptance passed; Docker compose acceptance blocked by local Buildx permission limit |
| Stage 3.3.7 Cutover decision review | Decision review documented, no formal cutover |
| Stage 3.3.8 Client candidate link acceptance | Acceptance flow documented, no formal cutover |
| Stage 3.3.9 Cutover readiness check | Readiness blockers documented, no formal cutover |
| Stage 3.3.10 Client test result record | Client result template documented, no formal cutover |
| Stage 3.3.11 Formal cutover runbook | Runbook documented, no formal cutover |
| Stage 3.3.12 Formal cutover approval | Approval gate documented, no formal cutover |
| Stage 3.3.13 B+ readiness record | Plan B+ readiness recorded, no formal cutover |
| Stage 3.3.14 C cutover decision pack | C-plan pre-review documented, No-Go for formal cutover |

## Environment

Create a local `.env` from the example before starting:

```bash
cp .env.example .env
```

At minimum, keep these variables configured:

- `DATABASE_URL`
- `REDIS_URL`
- `POSTGRES_PASSWORD`
- `ENCRYPTION_KEY`
- `SESSION_SECRET`
- `INIT_TOKEN`
- `COOKIE_SECURE`
- `COOKIE_SAMESITE`
- `APP_ENV`

If `ENCRYPTION_KEY` or `SESSION_SECRET` is missing, the backend and worker will
refuse to start with `ENV_REQUIRED_MISSING`.

Default local ports:

- Frontend: `3000`
- Backend: `8000`
- PostgreSQL: `5432`
- Redis: `6379`

If a local port is already in use, change the host-side port in
`docker-compose.yml` and update the relevant environment variable in `.env`.

## Start

```bash
docker compose up --build
```

## Verify

Backend health:

```bash
curl http://localhost:8000/api/health
```

PostgreSQL tables:

```bash
docker compose exec postgres psql -U livelines -d livelines -c "\\dt"
```

Redis:

```bash
docker compose exec redis redis-cli ping
```

Worker:

```bash
docker compose logs worker
```

Frontend:

```text
http://localhost:3000
```

Admin initialization:

```bash
curl -X POST http://localhost:8000/api/admin/init \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"change-this-strong-password","init_token":"change-me-before-use"}'
```

Admin login with HttpOnly Cookie Session:

```bash
curl -i -c /tmp/livelines-cookies.txt \
  -X POST http://localhost:8000/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"change-this-strong-password"}'
```

Fetch CSRF token:

```bash
curl -b /tmp/livelines-cookies.txt http://localhost:8000/api/auth/csrf
```

Logout requires `X-CSRF-Token` from the previous response:

```bash
curl -b /tmp/livelines-cookies.txt \
  -X POST http://localhost:8000/api/auth/logout \
  -H "Content-Type: application/json" \
  -H "X-CSRF-Token: <csrf_token>" \
  -d '{}'
```
