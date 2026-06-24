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

## Stage 3.3.13 UI polish scope

Stage 3.3.13 UI polish upgrades the local console from a development-style
debug panel toward a darker SaaS operations console. It improves AppShell,
navigation, top status messaging, dashboard overview cards, status labels,
server summaries, node status presentation, transit-route route-flow display,
task progress display, and formal/candidate/rollback safety boundaries.

Stage 3.3.13 UI polish is not a formal cutover. It does not modify
`node.share_link`, does not change backend core deployment logic, does not
change existing API compatibility, does not add database migrations, does not
add listening ports, does not trigger Worker/RQ tasks, does not execute SSH or
remote commands, does not stop `gost` 8443, and does not let `socat` take over
8443.

## Stage 3.3.14 UI zh-CN collapsible tips scope

Stage 3.3.14 UI zh-CN collapsible tips localizes the main console UI into
Chinese and turns large route-safety, cutover-risk, task-history, and
diagnostic guardrail blocks into default-collapsed notices. The safety content
is retained and can be expanded with "查看说明", while the main operation panels
stay visible first.

Stage 3.3.14 UI zh-CN collapsible tips is not a formal cutover. It does not
modify `node.share_link`, does not change backend core deployment logic, does
not change existing API compatibility, does not add database migrations, does
not add listening ports, does not trigger Worker/RQ tasks, does not execute SSH
or remote commands, does not stop `gost` 8443, and does not let `socat` take
over 8443.

## Stage 3.3.16 Server management backend foundation scope

Stage 3.3.16 adds the minimum backend foundation needed by the future server
management table. It adds server display metadata and SSH handshake status
fields to `vps_servers`, a focused Alembic migration, `GET /api/vps`,
`POST /api/vps`, `POST /api/vps/{vps_id}/recheck`,
`PATCH /api/vps/{vps_id}`, and `DELETE /api/vps/{vps_id}`. It also adds the
`check_vps_ssh` task type for SSH handshake checks using the existing Redis
temporary credential mechanism.

Stage 3.3.16 does not implement the full server-management table UI; that is
left for a later UI stage. It does not modify `node.share_link`, does not add
listening ports, does not create real nodes, does not create transit routes,
does not change existing node-creation API compatibility, does not execute
formal cutover, and does not automatically clean remote Xray or node
configuration when deleting a server record.

## Stage 3.3.17 Server management UI table scope

Stage 3.3.17 replaces the default Servers page with a local server-management
table backed by the Stage 3.3.16 VPS management APIs. The page lists server
records, SSH status, SSH port, actions, and child node summary rows. It adds
modal flows for adding a server, rechecking SSH, editing server metadata,
deleting system records, and submitting the existing direct-node creation flow
for online servers.

Stage 3.3.17 does not change backend core logic, does not add database
migrations, does not modify `node.share_link`, does not add listening ports by
page load or modal open, does not create transit routes, does not execute
formal cutover, and does not run SSH or remote commands unless the operator
explicitly submits an existing task-backed form such as add server, recheck, or
add node.

## Stage 3.3.18 Node menu consolidation scope

Stage 3.3.18 removes the standalone left-nav Nodes entry and consolidates node
viewing/export actions into the Landing Servers page. The left navigation now
uses the order Dashboard, Transit Servers, Landing Servers, Tasks, Diagnostics,
and Settings. Nodes remain landing-server-owned child records under the
server-management table. The child node row now supports on-demand detail
viewing, full-link copy, and local QR display through the existing
`GET /api/nodes/{node_id}` API.

Stage 3.3.18 keeps the underlying nodes table, node APIs, node creation flow,
and `node.share_link` capability intact. It does not modify backend core logic,
does not add database migrations, does not modify `node.share_link`, does not
add listening ports, does not execute SSH or remote commands, does not create
real nodes by page load or modal open, and does not perform formal cutover.

## Stage 3.3.19 Transit server UI table alignment scope

Stage 3.3.19 aligns the Transit Servers page with the Landing Servers
management-table experience before the first Worker implementation. The page
now defaults to a transit-server table with name, IP address, SSH port, status,
and actions; existing forwarding routes are shown as child rows under their
transit server. Advanced single-route planning, readonly preflight, and legacy
diagnostic tools remain available, but are collapsed behind an advanced-tools
section by default.

Stage 3.3.19 uses existing transit resource and transit route read/write APIs
only for local resource records. Add/edit transit server works through local
resource APIs; remote recheck, remote cleanup, safe route deletion, real Worker
onboarding, and real forwarding creation remain future Worker/API stages. It
does not implement Worker, does not generate Worker tokens, does not execute
SSH or remote commands, does not create real transit routes by default, does
not add HAProxy, does not add database migrations, does not add listening
ports, does not modify `node.share_link`, and does not perform formal cutover.

## Stage 3.3.20 Transit server / route split scope

Stage 3.3.20 splits the previous combined Transit Servers page into two local
frontend responsibilities. The Transit Servers page now manages only transit
VPS resource records, while the new Transit Links page manages forwarding
relationships from a transit server listen port to a landing-server node target
port. The left navigation order is Dashboard, Transit Servers, Landing Servers,
Transit Links, Tasks, Diagnostics, and Settings.

Stage 3.3.20 keeps transit resources, transit route records, `socat`, and
`gost` capabilities intact, but it does not implement Worker, does not generate
Worker tokens, does not execute SSH or remote commands, does not create real
transit routes, does not add HAProxy, does not add database migrations, does
not add listening ports, does not modify `node.share_link`, and does not
perform formal cutover. The Transit Links table uses a dedicated horizontal
scroll area and minimum width so the role and action columns remain readable,
keeps target port and forwarding method in separate aligned columns, and pins
the action column on the right. The route creation dialog remains a local
planning surface only; real remote execution stays in a future Worker/API stage.

## Stage 3.3.21 Lightweight Worker bootstrap design scope

Stage 3.3.21 documents the lightweight Worker bootstrap direction before any
implementation. The intended default onboarding path is a visible
`curl | bash` install command that installs a small systemd-managed
`liveline-worker` binary on landing or transit servers. SSH onboarding source
code remains preserved but hidden from the default frontend path until the
Worker flow is stable.

The first Worker version is designed only for registration, heartbeat, and
basic status reporting. It does not create nodes, create transit routes, delete
nodes, perform remote cleanup, modify Xray, modify `socat` / `gost`, change
`node.share_link`, add listening ports, or perform formal cutover. `socat` and
`gost` remain the current transit methods; HAProxy TCP is deferred to a
separate future stage. The design also records one-time install-token
requirements, future Worker APIs, remote-cleanup rules, and the security
boundary for future implementation.

## Stage 3.3.22 Worker token/register/heartbeat foundation scope

Stage 3.3.22 implements the local backend foundation for lightweight Worker
onboarding. It adds `worker_tokens` and `workers`, an Alembic migration, and
minimal APIs for one-time install token generation, placeholder setup-script
download, Worker registration, Worker heartbeat, and Worker status queries.
Tokens and Worker secrets are stored only as hashes; plaintext values are
returned only once at token creation or registration.

Stage 3.3.22 does not implement a real Worker binary, does not install Worker,
does not execute SSH or remote commands, does not create real nodes, does not
create transit routes, does not modify Xray, does not modify `socat` / `gost`,
does not clean remote services, does not add listening ports, does not modify
`node.share_link`, does not add HAProxy, and does not perform formal cutover.
Worker v1 remains limited to registration, heartbeat, and latest status
reporting; full server binding and task execution stay in later stages.

## Stage 3.3.23 Worker bootstrap UI integration scope

Stage 3.3.23 wires the Worker token foundation into the local console UI. The
default add landing server and add transit server modals now generate one-time
Worker bootstrap commands through `POST /api/worker-tokens`; landing servers
use `role=landing`, and transit servers use `role=transit`.

The displayed command remains a Stage 3.3.22 safe placeholder flow. This stage
does not implement or install a real Worker, does not execute SSH or remote
commands, does not create nodes or transit routes, does not add listening
ports, does not modify `node.share_link`, and does not perform formal cutover.
Existing SSH source paths and APIs remain in the codebase but are no longer the
default add-server UI.

## Stage 3.3.24 Minimal LiveLine Worker binary scope

Stage 3.3.24 implements the first minimal `liveline-worker` binary and upgrades
`GET /worker_setup_script/{token}` from a placeholder to a real install script.
The backend image now packages a locally built Linux amd64 Worker binary and
serves it through `/worker_binary/liveline-worker-linux-amd64`; the install
script downloads it to `/usr/local/bin/liveline-worker`, registers with the
console, writes `/etc/liveline-worker/config.yaml`, and installs
`liveline-worker.service`.

Worker v1 is intentionally limited to registration, heartbeat, and read-only
system status reporting for `landing` and `transit` roles. It does not create
nodes, does not create transit routes, does not modify Xray, does not modify
`socat` / `gost`, does not add listening ports, does not modify
`node.share_link`, does not add HAProxy, and does not perform formal cutover.
This stage does not install the Worker onto any real VPS and does not execute
SSH or remote commands from the console.

## Stage 3.3.25 Worker public install URL fix scope

Stage 3.3.25 fixes Worker bootstrap command generation so commands copied to a
remote VPS no longer use `localhost`. The backend now requires
`PUBLIC_CONSOLE_URL` or `WORKER_PUBLIC_BASE_URL` before generating
`curl -s <public-console-url>/worker_setup_script/<token> | bash -s eth0 ...`.
If the public console URL is missing, local, or invalid, the API refuses to
create an install command instead of falling back to the request host.

The Worker setup script also uses the same public console URL for the Worker
registration endpoint and binary download URL. Landing and transit add-server
modals warn that remote VPS hosts cannot access a localhost script URL and ask
the operator to confirm the VPS can reach the configured console address before
running the command. This stage does not install Worker onto any real VPS, does
not execute SSH or remote commands, does not create nodes or transit routes,
does not add listening ports, does not modify `node.share_link`, and does not
perform formal cutover.

## Stage 3.3.26 Deployment missing credentials fix scope

Stage 3.3.26 restores `backend/app/services/credentials.py` to version control
so public backend deployments can import `app.services.credentials`. The module
provides the Redis temporary credential helpers used by VPS, node, transit
resource, transit route, and worker job flows: `store_temp_credential`,
`pop_temp_credential`, `TempCredentialExpired`, and
`TempCredentialDecryptFailed`.

The fix keeps the existing encrypted Redis temporary credential boundary:
private SSH material is encrypted before being stored under
`temp_credential:<id>`, receives a TTL, and is deleted when the Worker pops it.
It does not store SSH private keys in normal database fields, logs, task
results, README, or docs. This stage does not modify `node.share_link`, does
not add database migrations, does not add listening ports, does not execute SSH
or remote commands, does not create nodes or transit routes, and does not
perform formal cutover.

## Stage 3.3.28 Worker command channel foundation scope

Stage 3.3.28 adds the first local Worker command channel foundation. The
console can enqueue only read-only / no-op Worker commands, Workers can poll
`/api/workers/commands/next`, and Workers can report success or failure through
the command result APIs. The allowed command types are limited to `ping`,
`collect_status`, and `service_status`.

This stage adds the `worker_commands` table for command state, leases, attempts,
sanitized results, and errors. It does not store raw Worker secrets, raw tokens,
SSH keys, full node links, or remote sensitive configuration. The Go
`liveline-worker` now keeps heartbeat behavior and adds a polling loop for the
allowed no-op commands. Landing and transit server pages include a minimal
`Worker 检查` button that creates a `collect_status` command for online Workers
and shows the latest command status.

Stage 3.3.28 does not execute SSH or remote commands, does not create nodes,
does not create transit routes, does not install or upgrade real VPS Workers,
does not modify Xray, socat, or gost, does not add listening ports, does not
modify `node.share_link`, and does not perform formal cutover.

## Stage 3.3.29 Worker command target selection fix scope

Stage 3.3.29 fixes Worker command target selection when multiple Worker
records exist for the same server. Admin command creation no longer blindly
trusts the `worker_id` supplied by the frontend. The backend resolves the best
target Worker by `server_id`, role, online status, command-channel capability,
latest heartbeat, and registration time.

The minimum command-capable Worker version is `0.1.1-stage-3.3.28`. Older
Workers such as `0.1.0-stage-3.3.24` remain registered but do not receive new
commands. If only unsupported online Workers exist, the API returns
`WORKER_COMMAND_UNSUPPORTED` and does not create a pending command. If no online
Worker exists, it returns `WORKER_OFFLINE`; unbound Workers return
`WORKER_NOT_BOUND`.

The UI now sends the server id and role when creating a Worker check command,
then displays the actual `target_worker_id`, target Worker version, status,
result summary, and error message returned by the backend. This stage does not
add a database migration, does not execute SSH or remote commands, does not
create nodes or transit routes, does not add listening ports, does not modify
`node.share_link`, and does not perform formal cutover.

## Stage 3.3.30 Worker landing readonly preflight scope

Stage 3.3.30 adds a landing-server read-only preflight Worker command type:
`landing_preflight`. The command is available only to landing Workers at
version `0.1.2-stage-3.3.30` or newer, so existing older Workers are rejected
with `WORKER_COMMAND_UNSUPPORTED` instead of receiving an unknown command.

The Go Worker performs only fixed local read-only checks: system identity,
network route/IP summary, listening-port summary, Xray/service status,
binary presence, firewall status summaries, and metadata-only Xray file
discovery. The command result is stored in `worker_commands.result_json`; no
database migration is added. The frontend adds a `只读预检` action on online
landing Workers and displays a compact sanitized summary.

Stage 3.3.30 does not read full Xray config, does not return node links, UUIDs,
Reality private keys, Worker tokens, cookies, or session secrets, does not
execute SSH or arbitrary remote commands from Codex, does not create nodes or
transit routes, does not add listening ports, does not modify firewall rules,
does not modify `node.share_link`, and does not perform formal cutover.

## Stage 3.3.32 Landing node create plan scope

Stage 3.3.32 adds a local dry-run landing-node creation plan. The backend exposes
`POST /api/vps/{server_id}/landing-node-plan`, which reads the latest successful
`landing_preflight` result and the currently bound landing Worker record, then
returns a Go / No-Go planning response for a future direct VLESS Reality node.
The endpoint does not enqueue tasks, does not execute Worker commands, and does
not write node, task, or route records.

The plan checks worker availability/version, preflight presence, interface
mismatch, planned port validity, existing listening state, existing Xray config
metadata, cloud security group / cloud firewall / server firewall confirmation,
and whether share-link generation has been explicitly approved for a later
execution stage. The current accepted preflight shows Worker
`53e6535d-7b80-4121-9093-2c55b3f09953` on landing server
`968519b3-9017-4b27-a9a0-d5731033f84f`, with Worker version
`0.1.2-stage-3.3.30`, Debian 12, x86_64, root runtime user, only SSH 22
listening, and no Xray / x-ui / 3x-ui / nginx / caddy / socat / gost installed.
It also records the known interface mismatch: Worker config uses `eth0`, while
the detected default public interface is `ens17`; this remains a blocker before
any formal node creation approval.

The landing-server UI replaces the real "add node" action with `创建节点计划`.
The modal only generates the dry-run plan, shows blocked reasons and warnings,
and reminds the operator that future listener ports require cloud security group,
cloud firewall, and server firewall review. Stage 3.3.32 does not install Xray,
does not write Xray config, does not create nodes, does not generate full node
links, does not modify `node.share_link`, does not add listening ports, does not
modify firewall rules, does not execute SSH or remote commands, and does not
perform cutover.

## Stage 3.3.33 Worker preflight interface normalization scope

Stage 3.3.33 normalizes the landing Worker readonly preflight result shape. The
Worker version is `0.1.3-stage-3.3.33`, and `landing_preflight` now reports
`preflight_version=0.2`.

The Worker separates the configured interface from the default public route
interface. It returns `worker_config_interface`, `default_route_interface`,
`default_route_gateway`, `primary_interface`, `primary_interface_ip`, and
`interface_mismatch`, while keeping `system.interface_name` for compatibility.
The backend dry-run plan prefers these new fields and keeps old-field fallbacks.
If the configured Worker interface differs from the default route interface, the
plan remains No-Go with `interface_mismatch`.

Stage 3.3.33 also fixes the `ss -lntup` listener parser so invalid rows no
longer produce `port=0`; only valid TCP `LISTEN` rows are counted. The
linux/amd64 Worker binary is rebuilt with the local Go toolchain.

Stage 3.3.33 does not install Xray, x-ui, 3x-ui, socat, or gost, does not
execute SSH or remote commands, does not connect to real VPS hosts, does not
create nodes or transit routes, does not add listening ports, does not modify
firewall rules, does not modify `node.share_link`, and does not perform cutover.

## Stage 3.3.35 Formal landing node create approval scope

Stage 3.3.35 updates the landing-node dry-run approval plan. The next-stage
prompt now points to `Stage 3.3.35-formal-landing-node-create-approval`, and
the default candidate listen port is no longer `443`. The frontend now randomly
chooses a candidate TCP port in `10000-30000` and avoids common / reserved
ports.

Blocked candidate ports are `22`, `80`, `443`, `8080`, `8443`, `18443`, `3000`,
`3200`, `8000`, `8200`, `5432`, `6379`, `15432`, `16379`, `10000`, and `27017`.
The backend dry-run plan rejects these ports with `unsafe_port`.

The dry-run UI clearly reminds the operator that formal creation requires the
candidate TCP port to be allowed in the cloud security group, cloud firewall,
and server-local firewall before execution. This stage remains plan-only: it
does not install Xray, create nodes, add listening ports, modify firewall rules,
generate real node links, modify `node.share_link`, execute SSH or remote
commands, create tasks, or perform cutover.

## Stage 3.3.36 Formal landing node create execution guard scope

Stage 3.3.36 adds the final execution guard before any formal landing-node
creation. The approved candidate port is fixed to `27939/TCP`, and the operator
has confirmed cloud security group, cloud firewall, and server-local firewall
allowance for that port.

The dry-run plan now points the next stage to
`Stage 3.3.37-formal-landing-node-create-execution`, keeps execution disabled,
and displays a formal execution guard checklist. Before any real execution, the
operator must rerun `landing_preflight` and confirm `27939/TCP` is not
listening, Xray is not installed, and there is no existing Xray config.

`node.share_link` may only be written in a later execution stage after node
creation succeeds, Xray service starts successfully, and `27939/TCP` is
listening. Real node links must not be written to README, stage documents,
terminal logs, task logs, PR descriptions, or chat records. This stage does not
install Xray, create nodes, add listening ports, modify firewall rules or cloud
security groups, generate real node links, modify `node.share_link`, execute SSH
or remote commands, create tasks, or perform cutover.

## Stage 3.3.37 Formal landing node create execution scope

Stage 3.3.37 adds the controlled formal landing-node creation execution path.
The only approved target is landing server
`968519b3-9017-4b27-a9a0-d5731033f84f` at `64.90.13.19`, interface `ens17`,
and listen port `27939/TCP`.

The backend now exposes `POST /api/vps/{server_id}/landing-node-create` with
mandatory second confirmations for firewall allowance, real share-link
generation, post-success `node.share_link` write, no existing Xray, and
rollback scope. The generic Worker command endpoint cannot bypass this
confirmation flow.

The Worker binary now supports `landing_node_create`. It reruns local preflight,
refuses existing Xray / x-ui / 3x-ui or a listening `27939/TCP`, installs only
the controlled Xray-core binary, writes only LiveLine-managed config and
systemd service files, verifies service startup and port listening, then returns
the real link only for backend persistence. Backend removes the complete link
from command history and writes `node.share_link` only after full success.

This stage's local development and PR validation did not execute SSH, remote
commands, public deployment, Xray installation, node creation, new listening
ports, firewall / cloud security group changes, real link generation,
`node.share_link` modification, or cutover.

## Stage 3.3.37-a Formal create Worker targeting hotfix scope

Stage 3.3.37-a fixes the formal landing-node create Worker targeting guard.
The original Stage 3.3.37 implementation locked the create path to one
historical Worker ID. After the Worker was upgraded and re-registered, the
formal create endpoint correctly refused to create a command, but it could not
select the current online Worker.

The hotfix removes the old hard-coded Worker ID and selects the latest eligible
Worker for the approved landing server. A Worker is eligible only when it is
bound to server `968519b3-9017-4b27-a9a0-d5731033f84f`, has role `landing`, has
interface `ens17`, is recorded as `online`, has a fresh heartbeat, and supports
`landing_node_create` with version `0.1.4-stage-3.3.37` or newer. If multiple
Workers match, the backend chooses the one with the newest heartbeat, then
newest registration / creation timestamp.

This hotfix does not lower the formal execution guard. The approved server ID,
approved port `27939/TCP`, required second confirmations, successful preflight,
no-listener check, no-Xray-installed check, and no-existing-Xray-config check
remain required before any command can be created.

This stage's local validation did not trigger `landing_node_create`, execute
SSH or remote commands, deploy the public console, install Xray, create nodes,
add listening ports, modify firewall / cloud security groups, generate real
node links, modify `node.share_link`, or perform cutover.

## Stage 3.3.37-b Xray install path and Worker sandbox hotfix scope

Stage 3.3.37-b fixes the Xray install path and Worker systemd sandbox write
boundary after the first formal create attempt failed safely with
`open /usr/local/bin/xray: read-only file system`. The failure did not leave
`27939/TCP` listening, did not create `liveline-xray.service`, did not leave
LiveLine Xray files, did not create nodes, and did not write `node.share_link`.

The Worker no longer installs Xray to `/usr/local/bin` or writes LiveLine Xray
config under `/usr/local/etc`. It now uses LiveLine-owned paths:
`/opt/liveline-xray/bin/xray`, `/opt/liveline-xray/config/config.json`, and
`/opt/liveline-xray/state`. The generated `liveline-xray.service` runs
`/opt/liveline-xray/bin/xray run -config /opt/liveline-xray/config/config.json`.

The Worker install script keeps `NoNewPrivileges=true`, `ProtectSystem=full`,
`ProtectHome=read-only`, and `PrivateTmp=true`, and adds only the minimal
`ReadWritePaths=/opt/liveline-xray /etc/systemd/system /run/systemd` allowance.
It does not open `/usr`, `/etc`, or `/` broadly.

The formal create preflight now rejects both the new LiveLine-owned paths and
legacy Xray / LiveLine paths if they already exist before the current run.
Rollback removes only files and directories created by the current run.

This stage's local validation did not trigger `landing_node_create`, execute
SSH or remote commands, deploy the public console, connect to the landing VPS,
install Xray, create nodes, add listening ports, modify firewall / cloud
security groups, generate real node links, modify `node.share_link`, or perform
cutover.

## Stage 3.3.37-c Worker installer ReadWritePaths precreate hotfix scope

Stage 3.3.37-c fixes a Worker installer compatibility issue with the hardened
systemd sandbox. The Worker unit uses
`ReadWritePaths=/opt/liveline-xray /etc/systemd/system /run/systemd`; if
`/opt/liveline-xray` does not exist before systemd sets up the namespace,
`liveline-worker.service` can fail with `status=226/NAMESPACE`.

The Worker install script now pre-creates `/opt/liveline-xray` with mode `755`
before writing and starting `liveline-worker.service`. This directory is only
the future LiveLine-owned writable root for Xray execution stages. The installer
does not create `/opt/liveline-xray/bin/xray`, does not create
`/opt/liveline-xray/config/config.json`, and does not create
`liveline-xray.service`.

This stage does not trigger `landing_node_create`, execute SSH or remote
commands, deploy the public console, reinstall Worker on any VPS, install Xray,
create nodes, add listening ports, modify firewall / cloud security groups,
generate real node links, modify `node.share_link`, or perform cutover.

## Stage 3.3.37-d Allow empty LiveLine Xray directory hotfix scope

Stage 3.3.37-d fixes the formal landing-node create Worker preflight after
Stage 3.3.37-c intentionally started pre-creating `/opt/liveline-xray` for the
Worker systemd sandbox. The old guard treated the empty directory as a conflict
and refused execution before any real create command could proceed.

The Worker now allows `/opt/liveline-xray` only when it is a directory and is
empty, or contains only empty known subdirectories such as `bin` and `config`.
It still refuses real Xray artifacts and unknown files, including
`/opt/liveline-xray/bin/xray`, `/opt/liveline-xray/config/config.json`,
`/opt/liveline-xray/state`, `liveline-xray.service`, legacy Xray paths, and
unknown files under `/opt/liveline-xray`.

The Worker version is raised to `0.1.6-stage-3.3.37`, and the backend minimum
version for `landing_node_create` is raised to the same version so older Workers
continue to be rejected for formal creation. This stage does not trigger
`landing_node_create`, deploy the public console, reinstall Worker, install
Xray, create nodes, add listening ports, modify firewall / cloud security
groups, generate real node links, modify `node.share_link`, execute SSH or
remote commands, or perform cutover.

## Stage 3.3.37-e Formal create client acceptance record scope

Stage 3.3.37-e records the successful client acceptance after the formal
landing-node create flow completed outside this documentation-only stage. The
public console was deployed to main commit
`ca10e668b3b089c3e9b2a3707927f0201c7ff0c8`, the landing Worker reported
version `0.1.6-stage-3.3.37`, and the successful `landing_node_create` command
completed at `2026-06-17 01:04:15+00`.

The accepted landing node uses `64.90.13.19:27939/TCP`, with
`liveline-xray.service` active and Xray running from
`/opt/liveline-xray/bin/xray` with config at
`/opt/liveline-xray/config/config.json`. The `nodes` table has an active VLESS
Reality node record for `liveline-reality-27939`; `node.share_link` is written
and present, but the real link is not shown in README or documentation.

Client acceptance confirmed that importing the node into the client allowed
normal internet access. This stage is not a cutover and does not modify any
transit route or fallback route. Next-stage candidates are
`Stage 3.3.38-post-acceptance-security-hardening-or-key-rotation-review` or
`Stage 3.3.38-transit-integration-planning`.

## Stage 3.3.38 Post-acceptance security hardening and key rotation review scope

Stage 3.3.38 records the post-acceptance security review after the formal VLESS
Reality landing node passed client acceptance. It documents sensitive exposure
surfaces, risk levels, whether immediate rotation is required, and the
recommended hardening order.

The review treats any previously pasted complete Worker setup token as
high-risk and recommends confirming invalidation / one-time-use hardening before
future onboarding. It treats copied full `node.share_link` values as a
node-rotation trigger if they were shared externally. UUID, Reality public key,
and shortId are treated as connection material that should not continue to be
shown in logs, PRs, chats, or docs. Runtime summaries such as port, protocol,
service status, and Xray managed paths are lower risk but should not expose full
config content.

This stage does not rotate keys, recreate the node, stop or restart
`liveline-xray`, deploy the public console, connect to any VPS, query the real
database, modify `node.share_link`, generate a real node link, or perform
cutover. Recommended follow-up stages are
`Stage 3.3.39-worker-setup-token-one-time-use-hardening`,
`Stage 3.3.40-share-link-redaction-and-export-confirmation`,
`Stage 3.3.41-node-key-rotation-runbook`,
`Stage 3.3.42-formal-node-rotation-execution-approval`, and
`Stage 3.3.43-transit-integration-planning`.

## Stage 3.3.40 Share-link redaction and export confirmation scope

Stage 3.3.40 hardens node `share_link` handling after formal landing-node
client acceptance. Default node list and detail responses expose only
`has_share_link`, `share_link_length`, and masked link / Reality material
summaries. Full node links are available only through an explicit export API
that requires a confirmation flag and an authenticated CSRF-protected request.

The local UI now keeps full `vless://` links hidden by default. Copy, reveal,
QR-code, and socat-candidate-link flows require a user confirmation warning
that node links are sensitive and must not be pasted into chats, PRs, logs, or
documentation. Task result and task-log API responses also apply recursive
sensitive-field redaction before returning data to the browser.

This stage does not reinstall Worker, install or restart Xray, create / delete /
rotate nodes, add listening ports, modify firewall or cloud security group
rules, modify existing `node.share_link` values, generate new real node links,
connect to any VPS, deploy the public console, or perform cutover. Recommended
follow-up stages remain `Stage 3.3.41-node-key-rotation-runbook` and
`Stage 3.3.43-transit-integration-planning`.

## Stage 3.3.41 Node key rotation runbook scope

Stage 3.3.41 adds the node key rotation / node rebuild / old-link retirement
runbook after formal landing-node acceptance and share-link redaction
hardening. It documents why rotation may be needed, rotation levels, recommended
default strategies, safety pre-checks, future execution-stage splits, rollback
rules, and database / link-handling safety principles.

The runbook keeps the accepted `liveline-reality-27939` node unchanged. It does
not rotate keys, rebuild the node, create or delete nodes, restart or stop
`liveline-xray`, add listening ports, modify firewall or cloud security group
rules, query the real database, modify `node.share_link`, generate real node
links, connect to any VPS, deploy the public console, or perform cutover.

Recommended follow-up stages are
`Stage 3.3.42-formal-node-rotation-execution-approval` or
`Stage 3.3.43-transit-integration-planning`.

## Stage 3.3.50 Transit Worker install command regeneration scope

Stage 3.3.50 adds a recovery path for `pending_worker` transit servers when the
one-time Worker install command was closed before being copied. Eligible transit
server rows can regenerate a new bound role = `transit` Worker install command
while invalidating older active tokens for the same transit server.

The regeneration API is limited to existing `server` transit resources in
`pending_worker` state with no online bound Worker. It reuses the existing
Worker public URL validation and token bootstrap serialization, returns only a
new masked token plus one-time install command in the current response, and
marks older active tokens for the same resource as `revoked`.

This stage does not execute SSH, execute Worker commands, install Worker,
install `socat` / `gost`, create transit routes, add listening ports, change
firewall or cloud security group rules, modify Xray, modify `nodes.share_link`,
export client links, or perform cutover.

## Stage 3.3.63 Transit Worker remote readonly preflight API implementation scope

Stage 3.3.63 adds the first Worker/API execution path for a transit route
readonly preflight. The backend creates a `transit_readonly_preflight` Worker
command only after validating the transit server, online transit Worker, active
landing node, protected ports, and explicit `readonly=true` confirmation.

The Worker implementation is allowlist-only: it reports Worker identity,
planned port occupancy, `socat` / `gost` readonly state, transit-to-landing TCP
reachability, and local firewall readonly summary. The frontend adds an
`执行远程只读预检` action and renders command status, checks, and redacted
summary.

This stage does not create transit routes, install or restart `socat` / `gost`,
add listening ports, change firewall or cloud security group rules, modify
Xray, modify `nodes.share_link`, export client links, or perform cutover.

## Stage 3.3.67 Transit readonly preflight simple button scope

Stage 3.3.67 simplifies the Transit Links page readonly preflight experience
into a button-oriented panel. The page now shows a concise plan summary,
required confirmations, a primary `执行远程只读预检` action, and redacted Worker
command results.

The previous advanced readonly preflight panel remains available in a collapsed
legacy section for rollback. This stage is frontend-only: it does not change
backend APIs, create transit routes, execute Worker commands during validation,
add listening ports, modify firewall or cloud security group rules, modify
Xray, modify `nodes.share_link`, export client links, or perform cutover.

## Stage 3.3.68 Transit readonly preflight result polish scope

Stage 3.3.68 improves the Transit Links readonly preflight result display. The
simplified panel now separates overall state, check results, failure summaries,
suggested manual actions, redacted summary, and safety boundary reminders.

Stage 3.3.68-hotfix-preflight-panel-prominent moves the simplified readonly
preflight panel out of the collapsed legacy workbench and places it directly
above the transit route table, after the page note and safety explanation. The
main action is labeled `开始只读预检`, while the page continues to state that
readonly preflight does not create real transit routes.

Stage 3.3.68-hotfix-3-transit-readonly-result-eof hardens Worker command
result ingestion for `transit_readonly_preflight`. The backend now accepts and
normalizes the readonly preflight result shape, truncates and redacts unexpected
or oversized fields, and marks malformed or non-persistable results as failed
instead of leaving commands in `running`.

Stage 3.3.68-hotfix-4-worker-result-submit-eof hardens the Worker-side result
submit path. Worker version `0.1.8-stage-3.3.68` sanitizes and bounds command
results before POST, uses non-reused HTTP connections for command result
submissions, logs HTTP status and response-body summaries on submit failures,
and attempts a minimal `/fail` fallback if a full result submit fails. The
backend minimum version for `transit_readonly_preflight` is raised to
`0.1.8-stage-3.3.68`, so old transit Workers must be upgraded before new remote
readonly preflight commands can be created. This stage does not auto-upgrade
remote Workers or retry real commands.

Stage 3.3.68-hotfix-5-worker-result-endpoint-timeout hardens the console-side
Worker command result endpoints. The `/result` and `/fail` endpoints now log
ingress metadata, read and bound request bodies before parsing, return
idempotent JSON for already finished commands, and mark malformed or
non-normalizable reports as failed instead of leaving commands in `running`.
The `/fail` endpoint accepts the Worker minimal fallback failure report without
requiring a large structured result. This stage does not auto-upgrade remote
Workers or retry production commands.

Stage 3.3.68-hotfix-6-worker-authenticated-result-path adds authenticated-path
instrumentation and fast-failure protection for real Worker result submissions.
Worker authentication, command lookup, request-body read, JSON parse,
normalization, and DB update phases now emit elapsed timings without printing
Worker secrets or payload data. The result endpoints apply a short DB statement
timeout before command result updates, return explicit JSON for locked or
malformed paths, and keep terminal command submissions idempotent. The Worker
source also classifies submit timeouts by phase for future authorized Worker
upgrades; this stage does not auto-upgrade remote Workers or retry production
commands.

Stage 3.3.68-hotfix-7-worker-result-payload-diagnosis adds a local Worker
diagnostic subcommand for transit readonly preflight payloads. The command can
generate the real readonly preflight result on the Worker host, but it does not
submit the result to the console. It prints only a redacted structural summary:
payload sizes, top-level keys, check counts, per-check status and detail
length, largest field path and length, NUL and sensitive-link marker flags, and
whether the sanitized submit payload would exceed the soft limit. The Linux
amd64 Worker binary is rebuilt as Worker `0.1.9-stage-3.3.68` for a later
separately authorized Worker replacement; this stage does not auto-deploy or
retry production commands.

Stage 3.3.68-hotfix-8-worker-auto-submit-trace adds redacted Worker-side trace
logs around automatic result and failure submission. Worker
`0.1.10-stage-3.3.68` logs command id, command type, endpoint kind, payload
sizes, content length, header key names, safe host/path, timeout, timestamp,
elapsed time, HTTP status, and error classification without printing Worker
secrets, tokens, result bodies, or client links. This stage does not change the
console result/fail main logic, readonly collection logic, or real creation
behavior, and it does not auto-deploy the rebuilt Worker binary.

Stage 3.3.68-hotfix-9-worker-submit-curl-compatible makes Worker automatic
result/fail submission more curl-compatible after manual curl submission
succeeded while Go net/http automatic submission timed out awaiting headers.
Worker `0.1.11-stage-3.3.68` keeps the redacted traces, stops forcing
`Connection: close`, uses the default HTTP transport with explicit
`Content-Length`, and adds a constrained curl fallback only for fixed
`/api/workers/commands/{id}/result` and `/fail` paths when Go submission hits a
response-header timeout. The fallback uses a stdin curl config, does not use a
shell, does not print Worker secrets or request bodies, and is not auto-deployed
to remote Workers in this stage.

Stage 3.3.68-hotfix-10-worker-result-eof-curl-fallback extends the same
constrained Worker curl fallback to pre-response EOF class submit failures such
as `request_error: EOF`, `unexpected EOF`, connection reset, broken pipe, and
server closed idle connection. Worker `0.1.12-stage-3.3.68` still allows curl
fallback only for fixed Worker command `/result` and `/fail` paths, rejects
queries and non-command paths, submits the same JSON body without printing
secrets or request bodies, and returns success if the curl fallback succeeds so
the Worker does not immediately downgrade to the minimal failure payload. This
stage does not change backend result/fail main logic, readonly collection
logic, or remote behavior, and it does not auto-deploy the rebuilt Worker
binary.

Stage 3.3.68-hotfix-11-worker-curl-fallback-config-fix fixes the Worker curl
fallback execution path after production logs showed curl fallback was
triggered correctly but failed while reading its `--config` input. Worker
`0.1.13-stage-3.3.68` now writes 0600 temporary body, config, and response
files, invokes curl with a concrete `--config` file path, keeps those files
alive for the curl process lifetime, and removes them after curl exits. The
Worker secret remains outside process arguments and logs, and the fixed-path
result/fail endpoint allowlist, no-query rule, no-shell execution, and
redacted trace boundaries remain unchanged. This stage does not change backend
result/fail main logic, readonly collection logic, or remote behavior, and it
does not auto-deploy the rebuilt Worker binary.

Stage 3.3.68-hotfix-12-worker-curl-fallback-no-config removes curl `--config`
from Worker fallback entirely after production showed both stdin and file-based
curl config modes could fail on the transit Worker host. Worker
`0.1.14-stage-3.3.68` now stores the JSON body and HTTP headers in 0600
temporary files, invokes curl with fixed arguments using `--header @<file>` and
`--data-binary @<file>`, writes the response to a 0600 temporary response file,
and cleans up all temporary files after curl exits. Worker secrets remain in the
header temp file only and never appear in process arguments or logs. The fixed
result/fail endpoint allowlist, no-query rule, no-shell execution, redacted
trace boundaries, and no auto-deploy boundary remain unchanged.

Stage 3.3.68-hotfix-13-worker-curl-fallback-manual-compatible aligns the
Worker curl fallback with the exact manual command shape that succeeded on the
transit Worker host. Worker `0.1.15-stage-3.3.68` now invokes curl with
`-i --max-time ... --request POST --header @<header-file> --data-binary
@<body-file> <fixed-url>`, parses the HTTP status and JSON body from stdout,
and avoids `--output` / `--write-out`. Header and body temp files are synced
and closed before curl starts. Worker secrets remain confined to the temporary
header file and never appear in process arguments or logs. This stage changes
only Worker result/fail fallback transport behavior; it does not change backend
result/fail logic, readonly collection, route creation behavior, or deploy the
rebuilt Worker automatically.

Stage 3.3.68-hotfix-14-worker-compact-result-payload adds compact result
submission for `transit_readonly_preflight` after production isolated the
remaining failure to roughly 2 KB POST bodies on the transit Worker to console
path. Worker `0.1.16-stage-3.3.68` keeps the readonly collection result
unchanged internally, but compacts the `/result` submit payload to preserve only
the essential status, ports, method, Worker metadata, compact check names /
pass flags, short summaries, and a short safety boundary before posting. If the
compact payload is still above the 1200 byte target, check details are removed
and only `checks_count` plus failed check names are retained. The backend
result/fail logic, curl fallback behavior, route creation behavior, and no
auto-deploy boundary remain unchanged.

Stage 3.3.69-transit-readonly-ui-validation-record records production UI
validation after hotfix-14. The public console and Hong Kong transit Worker
were already updated by the operator, Worker `0.1.16-stage-3.3.68` submitted a
compact readonly preflight result successfully, and the real UI-triggered
`transit_readonly_preflight` command completed with `passed` status in one
attempt. This record is documentation only: no Worker command is triggered, no
transit route is created, no listener or firewall is changed, Xray is not
modified, `nodes.share_link` is not read or modified, no real client link is
generated or displayed, and no cutover is performed.

Stage 3.3.70-transit-route-create-approval records the formal approval packet
for a future Hong Kong transit route creation after the successful production
UI readonly preflight. It records the proposed transit resource, landing node,
planned TCP listen port `23843`, forwarding method `socat`, preflight evidence,
and the manual firewall / cloud security group confirmations required before
execution. This stage is documentation only: it does not trigger Worker
commands, create a transit route, bind a listener, modify firewall rules,
modify Xray, read or modify `nodes.share_link`, display a real client link, or
perform cutover. The next possible execution stage is
`Stage 3.3.71-transit-route-create-execution`, and it requires explicit user
authorization before any real action.

Stage 3.3.71-transit-route-worker-create-path adds the controlled Worker create
path needed before any real Hong Kong transit route execution. It introduces
the `transit_route_create` Worker command type, a dedicated backend dry-run
entry point, and a Worker dry-run handler that validates the approved
`23843/TCP` socat route parameters and returns the planned service name,
target, checks, and safety boundary. This stage is still not real execution:
the endpoint requires `dry_run=true`, does not create `transit_routes` records,
does not bind a listener, does not write systemd services, does not install or
start `socat`, does not modify firewall rules, does not read or modify
`nodes.share_link`, and does not perform cutover. Real creation is reserved for
`Stage 3.3.72-transit-route-create-execution` with fresh explicit approval.

Stage 3.3.72a-legacy-ssh-rq-flow-removal removes the old SSH private-key /
Redis temporary credential / RQ job operation surface from active backend and
frontend code. Node direct SSH actions, transit resource SSH read/install
actions, legacy transit route create/diagnose/restart actions, and VPS SSH
backup/check endpoints are removed or downlined. Worker registration,
bootstrap, heartbeat, command polling, readonly preflight, `transit_route_create`
dry-run planning, node redaction/export confirmation, transit resource records,
and transit route read APIs remain. This stage does not add migrations, does not
delete historical database rows, does not deploy the public console, does not
upgrade Worker, does not trigger Worker commands, does not create routes, does
not bind listeners, does not modify firewall/Xray/`nodes.share_link`, and does
not perform cutover.

Stage 3.3.72d-worker-result-large-post-timeout-hotfix compacts
`transit_route_create` Worker dry-run result and fail payloads after production
showed that roughly 2 KB result bodies could hit timeout / EOF on the
Worker-to-console result path. The backend now normalizes compact
`transit_route_create` dry-run results and tests large-body fast rejection before
body read for missing auth / missing commands. This stage does not create a real
transit route, bind `23843/TCP`, start or stop `socat` / `gost`, modify
firewall rules, modify Xray, read or modify `nodes.share_link`, generate client
links, or perform cutover.

The base stage changes frontend result presentation and later hotfixes harden
the readonly preflight result transport. It reuses the existing
`transit_readonly_preflight` Worker command result shape and does not change
real creation behavior, add migrations, execute Worker commands during
validation, create transit routes, add listening ports, modify firewall or
cloud security group rules, modify Xray, modify `nodes.share_link`, export
client links, or perform
cutover.

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

## Stage 3.3.15 C final Go / No-Go approval scope

Stage 3.3.15 records the final C-plan Go / No-Go approval state before any
formal cutover. The current conclusion is No-Go because formal cutover,
`node.share_link` modification, remote commands, `socat` takeover of 8443, and
any stop, downgrade, or replacement of `gost` 8443 are not approved.

Stage 3.3.15 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop, downgrade, or replace `gost` 8443, and does not let `socat` take
over 8443.

## Stage 3.3.16 C No-Go blocker resolution plan scope

Stage 3.3.16 documents the C-plan No-Go blocker resolution plan. It keeps the
current No-Go conclusion and only describes how future stages could resolve the
remaining blockers for formal Go approval, `node.share_link`, remote commands,
8443 takeover, `gost` 8443 fallback, execution windows, owners, runbooks, and
port checks.

Stage 3.3.16 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop, downgrade, or replace `gost` 8443, and does not let `socat` take
over 8443.

## Stage 3.3.17 C execution runbook draft scope

Stage 3.3.17 documents a draft execution-level runbook structure for a future
C-plan cutover. It keeps the current No-Go conclusion and only describes phases,
preconditions, port/firewall checks, placeholder-based cutover flow, validation,
rollback, failure criteria, stop conditions, and acceptance templates.

Stage 3.3.17 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop, downgrade, or replace `gost` 8443, and does not let `socat` take
over 8443.

## Stage 3.3.18 C execution runbook review checklist scope

Stage 3.3.18 documents the review checklist for the Stage 3.3.17 C-plan
execution runbook draft. It checks runbook completeness across preconditions,
port/firewall checks, Phase 0 through Phase 7, validation, rollback, failure
criteria, stop conditions, acceptance templates, and sensitive-information
boundaries.

Stage 3.3.18 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop, downgrade, or replace `gost` 8443, and does not let `socat` take
over 8443.

## Stage 3.3.19 C execution runbook gap fix plan scope

Stage 3.3.19 documents the gap fix plan for the Stage 3.3.18 C-plan execution
runbook review checklist. It turns the remaining gaps into a non-executing plan
covering command whitelist authorization, formal execution window, responsible
roles, `node.share_link` backup confirmation, 8443 security group / firewall
checks, formal Go approval, and execution runbook final approval.

Stage 3.3.19 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop, downgrade, or replace `gost` 8443, and does not let `socat` take
over 8443.

## Stage 3.3.20 C command authorization matrix scope

Stage 3.3.20 documents the command authorization matrix for a future C-plan
cutover. It classifies local read-only commands, remote read-only commands,
remote execution commands, database commands, backend task commands, and
explicitly prohibited commands. It also records approval fields, output
redaction rules, and the principle that commands not listed in a future
whitelist remain forbidden.

Stage 3.3.20 is not a formal cutover. It does not modify `node.share_link`,
does not modify `transit_routes`, does not add database migrations, does not add
listening ports, does not trigger Worker/RQ tasks, does not connect to servers,
does not stop, downgrade, or replace `gost` 8443, and does not let `socat` take
over 8443.

## Stage 3.3.21 C read-only preflight command list scope

Stage 3.3.21 documents a future read-only preflight command list derived from
the Stage 3.3.20 command authorization matrix. It separates local repository
checks from future remote read-only preflight categories for service listening,
process, systemd, firewall, connectivity, route state, log viewing, 8443,
`socat` 18443, `gost` 8443, `node.share_link`, and backend task status checks.

Stage 3.3.21 is not a formal cutover and does not authorize remote read-only
commands. It does not modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not connect to servers, does not
stop, downgrade, or replace `gost` 8443, and does not let `socat` take over
8443.

## Stage 3.3.22 C No-Go preflight approval pack scope

Stage 3.3.22 consolidates the remaining “approval-only, no execution” C-plan
preflight items into one No-Go approval pack. It records the current No-Go
status for remote read-only commands, SSH login, systemd operations, firewall
checks, port checks, 8443 checks, `socat` 18443 checks, `gost` 8443 checks,
`node.share_link` read/write, backend task status reads, backend task triggers,
formal cutover, `socat` 8443 takeover, and any `gost` 8443 downgrade or
replacement.

Stage 3.3.22 is not a formal cutover and does not authorize remote read-only
commands. It does not SSH, does not modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not connect to servers, does not
stop, downgrade, or replace `gost` 8443, and does not let `socat` take over
8443.

## Stage 3.3.23 C read-only preflight execution approval scope

Stage 3.3.23 documents the request and approval record for a future real
read-only preflight execution. It allows only the documentation request itself:
SSH login, remote read-only commands, systemd status checks, port-listening
checks, `gost` 8443 checks, `socat` 18443 checks, server firewall checks,
`node.share_link` reads/writes, backend task reads/triggers, and formal cutover
all remain No-Go.

Stage 3.3.23 is not a formal cutover and does not authorize SSH or remote
read-only commands. It does not modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not connect to servers, does not
stop, downgrade, or replace `gost` 8443, and does not let `socat` take over
8443.

## Stage 3.3.24 C read-only preflight execution authorization scope

Stage 3.3.24 records authorization for a future real read-only preflight
execution stage. It allows the next stage to use SSH only for approved
read-only checks, including whitelisted systemd status, port-listening, `gost`
8443, `socat` 18443, and server firewall read-only checks. It still forbids
formal cutover, `node.share_link` reads or writes, backend task triggers,
database migrations, new listening ports, firewall rule changes, systemd write
operations, `socat` 8443 takeover, and any `gost` 8443 stop, downgrade, or
replacement.

Stage 3.3.24 is not a formal cutover and does not execute SSH or remote
commands in this stage. It does not modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not connect to servers in this
stage, does not stop, downgrade, or replace `gost` 8443, and does not let
`socat` take over 8443.

## Stage 3.3.25 C read-only preflight execution scope

Stage 3.3.25 executes the authorized real read-only preflight. SSH is allowed
only for whitelisted read-only checks. The preflight confirms the transit host
is reachable, `gost` 8443 and `socat` 18443 are listening, both related systemd
services are active, server-side firewall state is read only, and transit to the
landing target on port 443 is reachable. The recorded server-side result is
Ready, while the overall C-plan readiness remains Blocked until cloud security
group / cloud firewall manual confirmation and future formal approvals are
completed.

Stage 3.3.25 is not a formal cutover. It does not read or modify
`node.share_link`, does not modify `transit_routes`, does not add database
migrations, does not add listening ports, does not trigger Worker/RQ tasks, does
not modify firewall rules, does not execute systemd start / stop / restart /
disable / enable, does not stop, downgrade, or replace `gost` 8443, and does not
let `socat` take over 8443.

## Stage 3.3.26 C manual read-only preflight evidence record scope

Stage 3.3.26 records desensitized evidence from the user's local manual SSH
read-only preflight. It corrects the prior Workbuddy-environment SSH-key
limitation by documenting that an authorized local key was used outside this
stage's Codex execution to confirm SSH read-only login, `gost` 8443
listening/active, `socat` 18443 listening/active, expected binaries present,
and server-side iptables policies accepting traffic.

The server-side read-only preflight conclusion is Ready. The overall C-plan
readiness remains Blocked until cloud security group / cloud firewall manual
confirmation and future formal approvals are completed. Stage 3.3.26 is not a
formal cutover. It does not read or modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not execute remote write
commands, does not modify firewall rules, does not execute systemd start / stop
/ restart / disable / enable, does not stop, downgrade, or replace `gost` 8443,
and does not let `socat` take over 8443.

## Stage 3.3.27 C cloud security firewall manual confirmation scope

Stage 3.3.27 records the manual confirmation checklist for cloud security
groups, cloud firewall rules, and server-side firewall status before any future
C-plan formal cutover. It carries forward the Stage 3.3.26 server-side Ready
summary and records the human cloud-console confirmation that TCP 8443 and TCP
18443 are allowed by the cloud security group. No separate cloud firewall
feature was found in the current provider console, so the cloud firewall item is
recorded as Not applicable.

Stage 3.3.27 is not a formal cutover. It does not execute SSH or remote
commands, does not read or modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not modify firewall rules, does
not execute systemd start / stop / restart / disable / enable, does not stop,
downgrade, or replace `gost` 8443, and does not let `socat` take over 8443.
The cloud security group / cloud firewall blocker is considered resolved after
the manual cloud-side confirmation. The overall C-plan readiness remains
Blocked until formal cutover, `node.share_link` modification, `socat` 8443
takeover, and `gost` 8443 changes receive separate approval.

## Stage 3.3.28 C final readiness reconciliation scope

Stage 3.3.28 reconciles the final C-plan readiness state after B+ client
acceptance, server-side read-only preflight, and cloud security group / cloud
firewall manual confirmation. The technical preflight side is basically Ready:
client scenarios are recorded as usable, `gost` 8443 and `socat` 18443 remain
listening, related systemd services are active, server-side firewall checks did
not find a local blocker, cloud security group TCP 8443 / 18443 is allowed, and
the standalone cloud firewall item is Not applicable.

Stage 3.3.28 is not a formal cutover. It does not execute SSH or remote
commands, does not read or modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not modify firewall rules, does
not execute systemd start / stop / restart / disable / enable, does not stop,
downgrade, or replace `gost` 8443, and does not let `socat` take over 8443.
The production cutover authorization side remains Blocked until formal cutover,
`node.share_link` modification, `socat` 8443 takeover, `gost` 8443 changes, and
final Go / No-Go are explicitly approved.

## Stage 3.3.29 C final Go decision scope

Stage 3.3.29 records the final C-plan Go decision. The decision is `Go` only
for entering a later formal cutover execution stage under the `C-minimal Go`
scope. It allows a future execution stage to modify `node.share_link` only after
the old value is safely backed up, the new value is confirmed without writing
the full link into documents or logs, client acceptance is performed, and the
old value can be restored immediately on failure.

Stage 3.3.29 is not a formal cutover execution. It does not execute SSH or
remote commands, does not read or modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not modify firewall rules, does
not execute systemd start / stop / restart / disable / enable, does not stop,
downgrade, or replace `gost` 8443, and does not let `socat` take over 8443.
The approved C-minimal boundary keeps `gost` 8443 as the formal / fallback
route, keeps `socat` on 18443 as the accepted candidate route, forbids 8443
takeover, forbids new listening ports, and requires a Stage 3.3.30 final
execution runbook before any real production change.

## Stage 3.3.30 C formal cutover execution runbook final scope

Stage 3.3.30 creates the final C-minimal formal cutover execution runbook. The
runbook defines a future execution flow for switching the formal
`node.share_link` to the already accepted `socat` 18443 candidate link, while
keeping `gost` 8443 as the formal / fallback route. It requires backing up the
old `node.share_link`, confirming the new candidate link without writing the
full link into documents or logs, completing client acceptance, and restoring
the old value immediately if validation fails.

Stage 3.3.30 is not a formal cutover execution. It does not execute SSH or
remote commands, does not read or modify `node.share_link`, does not modify
`transit_routes`, does not add database migrations, does not add listening
ports, does not trigger Worker/RQ tasks, does not modify firewall rules, does
not execute systemd start / stop / restart / disable / enable, does not stop,
downgrade, or replace `gost` 8443, and does not let `socat` take over 8443.
Stage 3.3.31 is the earliest stage that may execute the formal cutover, and it
must follow this runbook without expanding scope to 8443 takeover, new ports,
or `gost` 8443 changes.

## Stage 3.3.31 C formal cutover execution scope

Stage 3.3.31 executes the C-minimal formal cutover. `node.share_link` was found
already pointing to the `socat` 18443 candidate link before this stage executed.
The old link was safely backed up to `.workbuddy/cutover_backup.json` (excluded
from Git). No database write was needed. `gost` 8443 remains the formal/fallback
route. `socat` 18443 is the confirmed formal route.

Stage 3.3.31 did not let `socat` take over 8443, did not stop, downgrade, or
replace `gost` 8443, did not add listening ports, did not add database
migrations, did not modify firewall rules, and did not execute systemd start /
stop / restart / disable / enable.

## Stage 3.3.32 C post-cutover observation scope

Stage 3.3.32 records post-cutover observation for the C-minimal cutover. The
current formal route is `socat` 18443 through `node.share_link`, and `gost`
8443 remains retained as the fallback route. This stage provides the observation
checklist, abnormal-condition criteria, rollback triggers, and observation
result fields.

Stage 3.3.32 is not a new cutover. It does not modify `node.share_link`, does
not add listening ports, does not add database migrations, does not modify
firewall rules, does not execute systemd start / stop / restart / disable /
enable, does not stop, downgrade, or replace `gost` 8443, does not let `socat`
take over 8443, and does not trigger rollback.

## Stage 3.3.33 C post-cutover observation result scope

Stage 3.3.33 records the actual post-cutover observation result. Shadowrocket,
v2rayN, soft-router usage, normal web access, and target platform access are
recorded as normal. Live impact observation reports no obvious impact. The
post-cutover observation conclusion is Healthy and rollback is not required.

Stage 3.3.33 is not a new cutover. It does not modify `node.share_link`, does
not add listening ports, does not add database migrations, does not modify
firewall rules, does not execute systemd start / stop / restart / disable /
enable, does not stop, downgrade, or replace `gost` 8443, does not let `socat`
take over 8443, and does not trigger rollback. `socat` 18443 remains the formal
route and `gost` 8443 remains retained as the fallback route.

## Stage 3.3.34 C stability archive scope

Stage 3.3.34 archives the stable C-minimal cutover state. The C-minimal cutover
is complete, post-cutover observation is Healthy, the formal route is `socat`
18443, the fallback route is `gost` 8443, `node.share_link` points to `socat`
18443, rollback was not triggered, client observation is normal, and live impact
observation reports no obvious impact.

Stage 3.3.34 is not a new cutover. It does not modify `node.share_link`, does
not add listening ports, does not add database migrations, does not modify
firewall rules, does not execute systemd start / stop / restart / disable /
enable, does not stop, downgrade, or replace `gost` 8443, does not let `socat`
take over 8443, and does not trigger rollback. Future cleanup of `gost` 8443 or
any further `node.share_link` change requires a separate approval stage.

## Stage 3.3.35 C maintenance observation plan scope

Stage 3.3.35 records the maintenance observation plan after the C-minimal
cutover reached stable archive state. The current formal route remains `socat`
18443, the fallback route remains `gost` 8443, `node.share_link` points to
`socat` 18443, rollback is not required, and `gost` 8443 should remain retained
for a short-term maintenance observation period.

Stage 3.3.35 is not a new cutover. It does not modify `node.share_link`, does
not add listening ports, does not add database migrations, does not modify
firewall rules, does not execute systemd start / stop / restart / disable /
enable, does not stop, downgrade, or replace `gost` 8443, and does not let
`socat` take over 8443. Future cleanup of `gost` 8443, `socat` 8443 takeover,
port changes, firewall changes, or further `node.share_link` changes require
separate approval.

## Stage 3.4.1 Auth login gate scope

Stage 3.4.1 adds a system login gate. Unauthenticated visitors see only the
LiveLine Console login screen. After successful admin login, the existing
system shell and management panels are rendered. The frontend checks
`GET /api/auth/me` on startup, uses `POST /api/auth/login` for login, and uses
`POST /api/auth/logout` for logout with the existing HttpOnly cookie session and
CSRF flow.

Stage 3.4.1 reuses the existing admin password hash verification and protected
API dependencies. It supports the existing admin-table password hash and an
optional `ADMIN_USERNAME` / `ADMIN_PASSWORD_HASH` configured hash for the
matching active admin user. It does not add database migrations, does not write
real passwords to code or docs, and does not store passwords in the frontend.
This stage is an Auth/UI stage only: it does not read or modify
`node.share_link`, does not add listening ports, does not execute SSH or remote
commands, does not trigger Worker/RQ tasks, does not modify firewall rules,
does not perform a new cutover, does not let `socat` take over 8443, and does
not stop, downgrade, or replace `gost` 8443.

## Stage 3.4.2 Auth login local acceptance record scope

Stage 3.4.2 records the local browser acceptance result for Stage 3.4.1. The
operator confirmed that `http://localhost:3000` shows only the login page before
login, wrong credentials show a failure message, correct credentials enter the
system panel, refresh keeps the session, logout returns to the login page, and
the system panel is hidden after logout.

Stage 3.4.2 is an acceptance-record stage only. It does not modify
authentication logic, does not add database migrations, does not read or modify
`node.share_link`, does not add listening ports, does not execute SSH or remote
commands, does not trigger Worker/RQ tasks, does not modify firewall rules,
does not perform cutover, does not let `socat` take over 8443, and does not
stop, downgrade, or replace `gost` 8443. The formal link remains `socat` 18443
and the fallback link remains `gost` 8443.

## Stage 3.4.3 Auth protected API sweep scope

Stage 3.4.3 reviews backend API route authentication after the login gate. The
sweep confirms that data APIs for VPS records, nodes, tasks, transit resources,
and transit routes use the existing admin session dependency and return `401`
when accessed without login. Public runtime interfaces remain limited to health
and auth endpoints, with `POST /api/admin/init` kept as the one-time
init-token-protected bootstrap exception.

Stage 3.4.3 is an Auth security review stage. No backend route code change was
required because the reviewed data APIs were already protected. This stage does
not add database migrations, does not read or modify `node.share_link`, does
not add listening ports, does not execute SSH or remote commands, does not
trigger Worker/RQ tasks, does not modify firewall rules, does not perform
cutover, does not let `socat` take over 8443, and does not stop, downgrade, or
replace `gost` 8443. The formal link remains `socat` 18443 and the fallback
link remains `gost` 8443.

## Stage 3.4.4 Auth session hardening plan scope

Stage 3.4.4 reviews the current auth/session mechanism and records a future
hardening plan. The review covers `POST /api/auth/login`,
`POST /api/auth/logout`, `GET /api/auth/me`, HttpOnly session cookies,
`SESSION_SECRET`, `SESSION_TTL_SECONDS`, `COOKIE_SECURE`, `COOKIE_SAMESITE`,
`ADMIN_USERNAME`, `ADMIN_PASSWORD_HASH`, protected API `401` handling, and
logout cookie clearing.

Stage 3.4.4 is a planning and security-review stage only. It does not implement
login rate limiting, does not force cookie config changes, does not add
database migrations, does not modify authentication code, does not read or
modify `node.share_link`, does not add listening ports, does not execute SSH or
remote commands, does not trigger Worker/RQ tasks, does not modify firewall
rules, does not perform cutover, does not let `socat` take over 8443, and does
not stop, downgrade, or replace `gost` 8443. Future login throttling, forced
secure-cookie startup checks, session rotation, or idle timeout must be handled
in separately approved stages.

## Stage 3.4.5 Auth login rate limit hardening scope

Stage 3.4.5 adds Redis-backed failed-login rate limiting to
`POST /api/auth/login`. The limiter is scoped by client IP plus submitted
username, stores only an HMAC-hashed identifier in Redis keys, and never stores
passwords, password hashes, cookies, session tokens, CSRF tokens, or plaintext
usernames in Redis keys or logs. Defaults are controlled by
`AUTH_LOGIN_MAX_ATTEMPTS`, `AUTH_LOGIN_WINDOW_SECONDS`, and
`AUTH_LOGIN_LOCK_SECONDS`.

Stage 3.4.5 preserves the existing HttpOnly cookie session flow. Failed login
attempts return `401` before the threshold and `429 AUTH_RATE_LIMITED` after
the threshold. A successful login clears the matching failure counter and lock.
This stage does not add database migrations, does not read or modify
`node.share_link`, does not add listening ports, does not execute SSH or remote
commands, does not trigger Worker/RQ tasks, does not modify firewall rules,
does not perform cutover, does not let `socat` take over 8443, and does not
stop, downgrade, or replace `gost` 8443.

## Stage 3.4.6 Auth login rate limit browser acceptance record scope

Stage 3.4.6 records the local browser acceptance result for Stage 3.4.5 login
rate-limit hardening. The browser acceptance passed: opening
`http://localhost:3000` shows the login page, correct credentials enter the
system panel, logout returns to the login page, wrong passwords fail before the
threshold, repeated wrong attempts show a generic rate-limit message, the
rate-limit message does not reveal whether the account exists, and the system
panel is hidden after logout.

Stage 3.4.6 is an acceptance-record stage only. The real password was entered
only in the browser and was not written to documents, terminal commands, logs,
or Git. This stage does not modify authentication logic, does not add database
migrations, does not read or modify `node.share_link`, does not add listening
ports, does not execute SSH or remote commands, does not trigger Worker/RQ
tasks, does not modify firewall rules, does not perform cutover, does not let
`socat` take over 8443, and does not stop, downgrade, or replace `gost` 8443.

## Stage 3.4.7 Auth production environment readiness check scope

Stage 3.4.7 records the production Auth environment readiness check. It reviews
the production requirements for `SESSION_SECRET`, `SESSION_TTL_SECONDS`,
`COOKIE_SECURE`, `COOKIE_SAMESITE`, `ADMIN_USERNAME`,
`ADMIN_PASSWORD_HASH`, `AUTH_LOGIN_MAX_ATTEMPTS`,
`AUTH_LOGIN_WINDOW_SECONDS`, and `AUTH_LOGIN_LOCK_SECONDS`.

The readiness check confirms that `.env.example` contains placeholders and safe
local defaults only, while production must provide strong secrets, a production
password hash, HTTPS with `COOKIE_SECURE=true`, a deliberate SameSite policy, a
finite session TTL, and finite login rate-limit settings. The current config
code requires non-empty `SESSION_SECRET`, validates `COOKIE_SAMESITE`, and
validates login rate-limit values as positive; stricter production startup
guards should be handled in separately approved stages.

Stage 3.4.7 is a documentation and readiness-check stage only. It does not
modify authentication logic, does not add database migrations, does not read or
modify `node.share_link`, does not add listening ports, does not execute SSH or
remote commands, does not trigger Worker/RQ tasks, does not modify firewall
rules, does not perform cutover, does not let `socat` take over 8443, and does
not stop, downgrade, or replace `gost` 8443.

## Stage 3.4.8 Auth production environment guardrails scope

Stage 3.4.8 implements production-only Auth configuration startup guardrails.
The existing `APP_ENV` marker is reused: local development keeps
`APP_ENV=local`, while `APP_ENV=production` enables stricter checks.

In production, the backend now rejects weak or placeholder Auth configuration:
`SESSION_SECRET` must be strong and non-placeholder, `ADMIN_PASSWORD_HASH` must
look like the project secure hash format, `COOKIE_SECURE` must be `true`,
`COOKIE_SAMESITE` must be an explicit allowed value, `SESSION_TTL_SECONDS` must
be positive, and login rate-limit values must remain positive. Startup errors
name the invalid setting but do not print real secret, hash, cookie, session,
token, or node-link values.

Stage 3.4.8 does not add database migrations, does not read or modify
`node.share_link`, does not add listening ports, does not execute SSH or remote
commands, does not trigger Worker/RQ tasks, does not modify firewall rules,
does not perform cutover, does not let `socat` take over 8443, and does not
stop, downgrade, or replace `gost` 8443.

## Stage 3.4.9 Auth production environment guardrails acceptance record scope

Stage 3.4.9 records acceptance after Stage 3.4.8 production Auth guardrails
were merged. Local development still starts with `docker compose up --build -d`;
`/api/health` reports backend/database/redis/worker ok; the frontend opens at
`http://localhost:3000`; protected APIs still return `401` when
unauthenticated; login rate limiting still returns `429 AUTH_RATE_LIMITED` at
the threshold.

Production guardrail simulations used only fake values and placeholders.
`APP_ENV=production` rejects weak `SESSION_SECRET`, `COOKIE_SECURE=false`,
missing `ADMIN_PASSWORD_HASH`, invalid `COOKIE_SAMESITE`, non-positive
`SESSION_TTL_SECONDS`, and non-positive login rate-limit settings. A
valid-shape fake production configuration loads successfully. Error messages
identify configuration names and requirements without printing real secret,
hash, password, cookie, session, token, or full node-link values.

Stage 3.4.9 is an acceptance-record stage only. It does not modify
authentication logic, does not add database migrations, does not read or modify
`node.share_link`, does not add listening ports, does not execute SSH or remote
commands, does not trigger Worker/RQ tasks, does not modify firewall rules,
does not perform cutover, does not let `socat` take over 8443, and does not
stop, downgrade, or replace `gost` 8443.

## Stage 3.4.10 Auth security stability archive scope

Stage 3.4.10 archives the stable baseline for the Stage 3.4 Auth security
module. The archive covers the completed login gate, browser login acceptance,
protected API sweep, Auth/session hardening plan, login failure rate limiting,
rate-limit browser acceptance, production environment readiness check,
production guardrails, and production guardrails acceptance record.

The archived baseline confirms that local development remains usable,
`/api/health` stays public, important APIs return `401` when unauthenticated,
login failures return `401` before the threshold and `429` at the threshold,
and production guardrails reject weak or incomplete Auth configuration. The
real password is entered only in the browser during manual acceptance and is
not written to terminal commands, docs, logs, or Git.

Stage 3.4.10 is documentation-only. It does not modify authentication logic,
does not add database migrations, does not read or modify `node.share_link`,
does not add listening ports, does not execute SSH or remote commands, does
not trigger Worker/RQ tasks, does not modify firewall rules, does not perform
cutover, does not let `socat` take over 8443, and does not stop, downgrade, or
replace `gost` 8443.

## Stage 3.5.1 Local console operations readiness scope

Stage 3.5.1 documents the local single-user console operations workflow. The
system is currently used only on the user's Mac at `http://localhost:3000`; it
does not require public production deployment, a domain, HTTPS, Nginx, Caddy,
multi-user roles, or an enterprise audit backend.

The operations readiness document records daily commands for entering the
project directory, starting, stopping, rebuilding, and restarting Docker
Compose services, checking container status, checking `/api/health`, opening
the local console, verifying the login page, confirming successful login,
confirming logout, and handling common local failures. It also records that
real passwords must be typed only in the browser login form and must not be
written into terminal commands, docs, logs, or Git.

Stage 3.5.1 is documentation-only. It does not modify authentication logic,
does not add database migrations, does not read or modify `node.share_link`,
does not add listening ports, does not execute SSH or remote commands, does
not trigger Worker/RQ tasks, does not modify firewall rules, does not perform
cutover, does not let `socat` take over 8443, and does not stop, downgrade, or
replace `gost` 8443. The current formal link remains `socat` 18443 and the
fallback link remains `gost` 8443.

## Stage 3.5.2 Local backup and restore plan scope

Stage 3.5.2 documents the local single-user database backup and restore plan.
The plan identifies PostgreSQL as the core backup target, records that Docker
Compose local data volumes should be reviewed in a future implementation
stage, and clarifies that README/docs are managed by Git rather than by the
database backup process.

The plan defines a future local backup directory shape under
`backups/local-db/YYYYMMDD-HHMMSS/`, backup timing before upgrades,
migrations, route changes, formal switching, and large deletion operations,
restore safety checks, health checks after restore, and backup artifact safety
rules. Real backup files must not be committed to Git, sent to chat tools, or
uploaded to public storage.

Stage 3.5.2 is planning-only. It does not write backup scripts, does not
generate real backup files, does not modify authentication logic, does not add
database migrations, does not read or modify `node.share_link`, does not add
listening ports, does not execute SSH or remote commands, does not trigger
Worker/RQ tasks, does not modify firewall rules, does not perform cutover,
does not let `socat` take over 8443, and does not stop, downgrade, or replace
`gost` 8443. The current formal link remains `socat` 18443 and the fallback
link remains `gost` 8443.

## Stage 3.5.3 Local backup and restore implementation scope

Stage 3.5.3 implements local helper scripts for the single-user PostgreSQL
backup and restore workflow. The scripts use the existing Docker Compose
`postgres` service, read PostgreSQL database/user values from the container
environment, and do not print database passwords or application secrets.

Added scripts:

- `scripts/local-db-backup.sh` creates a local custom-format PostgreSQL backup
  under `backups/local-db/YYYYMMDD-HHMMSS/`.
- `scripts/local-db-restore.sh` restores an explicit `.dump`, `.backup`, or
  `.sql` file only after an interactive confirmation.
- `scripts/local-health-check.sh` prints `docker compose ps` and checks
  `/api/health`.

Stage 3.5.3 also updates `.gitignore` so local backup artifacts are not
committed. It does not modify business logic or authentication logic, does not
add database migrations, does not read or modify `node.share_link`, does not
add listening ports, does not execute SSH or remote commands, does not trigger
Worker/RQ tasks, does not modify firewall rules, does not perform cutover,
does not let `socat` take over 8443, and does not stop, downgrade, or replace
`gost` 8443. The current formal link remains `socat` 18443 and the fallback
link remains `gost` 8443.

## Stage 3.5.4 Topology preview usability polish scope

Stage 3.5.4 improves the local topology preview page so operators can clearly
see that topology preview is `PREVIEW ONLY` and `NOT USABLE`. The page now
states that preview does not connect to remote hosts, does not write config,
does not save routes, does not create real forwarding, does not generate a
real usable transit link, and does not modify `node.share_link`.

The topology display separates the chain into client, transit resource,
landing VPS / node, and target platform segments. The planned relay listen
port is labeled as a preview port, not an actual listening port. The page also
shows the current link roles: formal link `socat` 18443, fallback link `gost`
8443, and `node.share_link` already pointing to `socat` 18443.

Stage 3.5.4 changes frontend display text and styling only. It does not modify
backend business logic, does not add database migrations, does not read or
modify `node.share_link`, does not add listening ports, does not execute SSH
or remote commands, does not trigger Worker/RQ tasks, does not modify firewall
rules, does not perform cutover, does not let `socat` take over 8443, and does
not stop, downgrade, or replace `gost` 8443.

## Stage 3.5.5 Route safety guardrails UI scope

Stage 3.5.5 adds route safety guardrails to the local UI so the operator can
see the current production route state before working in the console. The UI
now states that the formal link is `socat` 18443, the fallback link is `gost`
8443, and `node.share_link` already points to `socat` 18443.

The guardrails appear in the logged-in shell and in the transit resource,
topology preview, and single-route areas. They remind the operator not to
modify `node.share_link`, not to close `gost` 8443, not to let `socat` take
over 8443, and not to delete or overwrite `socat` 18443. They also remind that
future listening-port additions or changes require checking the cloud security
group, cloud firewall, and server firewall for the corresponding TCP port.

Stage 3.5.5 changes frontend display text and styling only. It does not modify
backend business logic or authentication logic, does not add database
migrations, does not read or modify `node.share_link`, does not add listening
ports, does not execute SSH or remote commands, does not trigger Worker/RQ
tasks, does not modify firewall rules, does not perform cutover, does not let
`socat` take over 8443, and does not stop, downgrade, or replace `gost` 8443.

## Stage 3.5.6 Local task history usability scope

Stage 3.5.6 improves local task history usability. The system page now includes
a protected local task history panel that lists recent tasks, shows status,
current step, progress, timestamps, readable failure summaries, sanitized
`result_data`, and sanitized task logs.

The backend adds only a protected read-only `GET /api/tasks` list endpoint so
the local UI can show existing task history without knowing a task id in
advance. The endpoint does not create, enqueue, update, delete, or retry tasks.
The frontend redacts full node links, private key material, password /
passphrase / token / secret-like fields, long strings, and raw output before
display.

Stage 3.5.6 does not modify route state. It does not add database migrations,
does not read or modify `node.share_link`, does not add listening ports, does
not execute SSH or remote commands, does not trigger Worker/RQ tasks, does not
modify firewall rules, does not perform cutover, does not let `socat` take over
8443, and does not stop, downgrade, or replace `gost` 8443.

## Stage 3.5.7 Local upgrade and rollback SOP scope

Stage 3.5.7 documents the local single-user upgrade and rollback SOP. The SOP
defines how to prepare for local upgrades, back up the PostgreSQL database,
record the current commit and health state, rebuild Docker services, validate
the local console, and roll back through Git or database restore if needed.

The documented flow covers `docker compose` checks, `scripts/local-db-backup.sh`,
`scripts/local-db-restore.sh`, `scripts/local-health-check.sh`,
`http://localhost:3000`, `/api/health`, Redis temporary credential checks,
pending/running task checks, task history review, topology preview review, and
route safety guardrail review.

Stage 3.5.7 is documentation-only. It does not modify code, add scripts, create
real backup files, add database migrations, read or modify `node.share_link`,
add listening ports, execute SSH or remote commands, trigger Worker/RQ tasks,
modify firewall rules, perform cutover, let `socat` take over 8443, or stop,
downgrade, or replace `gost` 8443.

## Stage 3.5.8 Local console stability archive scope

Stage 3.5.8 archives the Stage 3.5 local console stability baseline. The
archive summarizes the local daily operations guide, local backup / restore
plan, local backup / restore / health-check scripts, topology preview safety
polish, route safety guardrails, task history usability, and local upgrade /
rollback SOP.

The archived baseline keeps the local console at `http://localhost:3000`,
keeps `/api/health` as the core backend / database / Redis / worker health
check, keeps `socat` 18443 as the formal link, keeps `gost` 8443 as the
fallback link, and records that `node.share_link` already points to `socat`
18443.

Stage 3.5.8 is documentation-only. It does not modify code, authentication
logic, frontend functionality, scripts, database schema, `node.share_link`,
listening ports, firewall rules, Worker/RQ tasks, or current transit links. It
does not execute SSH or remote commands, perform cutover, let `socat` take over
8443, or stop, downgrade, or replace `gost` 8443.

## Stage 3.6.1 Single route create flow review scope

Stage 3.6.1 reviews the current single-route create flow without executing it.
The review covers transit resource selection, active node selection, topology
preview, listen-port planning, route creation API/UI behavior, read-only
diagnosis, candidate link acceptance, formal cutover approval, Workbuddy
handoff points, and rollback boundaries.

The documented standard flow requires local database backup before risky
changes, avoids `8443` because it is retained for the `gost` fallback route,
avoids overwriting `18443` without a separate formal-change stage, and reminds
that new or changed listening ports require cloud security group, cloud
firewall, and server firewall checks.

Stage 3.6.1 is documentation-only. It does not create real routes, modify code,
add scripts, create real backup files, add database migrations, read or modify
`node.share_link`, add listening ports, execute SSH or remote commands, trigger
Worker/RQ tasks, modify firewall rules, perform cutover, let `socat` take over
8443, or stop, downgrade, or replace `gost` 8443.

## Stage 3.6.2 Single route create safety gates scope

Stage 3.6.2 adds safety gates to the local single-route create flow. The UI now
warns that route creation is not formal cutover, does not modify
`node.share_link`, and requires cloud security group, cloud firewall, and server
firewall checks before any new or changed TCP listening port is used.

The create form rejects invalid ports and protects `8443` and `18443`: `8443`
remains reserved for the `gost` fallback route, while `18443` is the current
formal `socat` route and must not be reused or overwritten by a new route.
Backend route creation validation also rejects protected listen ports before
temporary credentials or Worker/RQ task creation can proceed.

Stage 3.6.2 does not execute SSH or remote commands, create real remote
forwarding, add real listening ports, modify `node.share_link`, trigger backend
tasks, perform cutover, let `socat` take over 8443, or stop, downgrade, or
replace `gost` 8443.

## Stage 3.6.3 Single route diagnosis polish scope

Stage 3.6.3 improves the local single-route diagnosis display. The route page
now separates task status, current step, progress, listen-port checks, forwarding
process checks, systemd status, transit-to-landing connectivity, failure
summaries, next-action hints, and redacted command output.

The polish uses existing diagnosis task result fields such as `checks`,
`hints`, `warnings`, `failures`, task status, and task logs. It does not add
database fields, does not change Worker remote execution behavior, and does not
create new diagnosis capability beyond the already authorized UI controls.

Stage 3.6.3 does not execute SSH or remote commands, trigger backend tasks,
create real forwarding, add listening ports, modify `node.share_link`, perform
cutover, let `socat` take over 8443, or stop, downgrade, or replace `gost`
8443.

## Stage 3.6.4 Single route diagnosis browser acceptance record scope

Stage 3.6.4 records the browser manual acceptance result after Stage 3.6.2
single-route create safety gates and Stage 3.6.3 single-route diagnosis polish
were merged. The acceptance confirms that the local login gate, single-route
page, protected-port warnings, diagnosis result layout, safety reminders, and
logout flow are visible and understandable in the browser.

Stage 3.6.4 is documentation-only. It does not change frontend behavior,
backend logic, database schema, scripts, `node.share_link`, listening ports,
remote services, firewall rules, or route state. It does not execute SSH or
remote commands, trigger backend tasks, perform cutover, let `socat` take over
8443, or stop, downgrade, or replace `gost` 8443.

## Stage 3.6.5 Single route create flow stability archive scope

Stage 3.6.5 archives the stable baseline for the single-route create flow after
the Stage 3.6.1 review, Stage 3.6.2 safety gates, Stage 3.6.3 diagnosis polish,
and Stage 3.6.4 browser acceptance record. The archive records that the local
console now has transit resource records, active node selection, topology
preview, single-route UI/API boundaries, protected-port checks, diagnosis
display polish, redacted task/result display, and browser acceptance coverage.

The archived standard flow keeps `8443` reserved for the `gost` fallback route,
keeps `18443` protected as the current formal `socat` route, states that route
creation is not cutover, and requires cloud security group, cloud firewall, and
server firewall checks before any new or changed TCP listening port is used.
Future real SSH, remote route creation, remote diagnosis, or `node.share_link`
cutover/rollback work must enter a separately authorized stage and involve
Workbuddy where remote execution is required.

Stage 3.6.5 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, perform cutover, let `socat` take
over 8443, or stop, downgrade, or replace `gost` 8443.

## Stage 3.7.1 Single route remote execution readiness scope

Stage 3.7.1 documents the readiness checklist for a future real single-route
remote execution stage. It prepares the operator to confirm the target transit
server, landing node, planned new listen port, local database backup, local
health, empty task queues, port safety, cloud security group, cloud firewall,
server firewall, and Workbuddy handoff boundaries before any remote execution
is requested.

The readiness baseline keeps `8443` reserved for the `gost` fallback route,
keeps `18443` protected as the current formal `socat` route, blocks use of
management or historical problem ports such as `22` and `20575`, and requires
all new or changed TCP listening ports to be confirmed in the cloud security
group, cloud firewall, and server firewall before entering a real creation
stage.

Stage 3.7.1 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, create real forwarding, perform
cutover, let `socat` take over 8443, or stop, downgrade, or replace `gost`
8443. Workbuddy is not required for this readiness document, but will be
required for later real SSH, remote creation, remote listening checks, or
remote diagnosis stages.

## Stage 3.7.2 Single route remote execution approval scope

Stage 3.7.2 documents the approval template for a future real single-route
remote execution stage. The template records the target transit server, landing
node, active node, new listen port, landing target port, platform purpose,
local backup status, cloud security group, cloud firewall, server firewall, and
Workbuddy authorization items that must be filled before any real remote action
can be requested.

Current approval status remains No-Go because the new route target, transit
server, landing VPS / node, listen port, and firewall confirmations have not
been supplied. Stage 3.7.2 does not approve SSH, remote commands, route
creation, new listening ports, `node.share_link` changes, or cutover.

Stage 3.7.2 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, create real forwarding, perform
cutover, let `socat` take over 8443, or stop, downgrade, or replace `gost`
8443. Workbuddy is not required for this approval template, but will be
required for later real SSH, remote creation, remote listening checks, or
remote diagnosis stages.

## Stage 3.7.3 Single route target and port selection record scope

Stage 3.7.3 documents the target and port selection template for a future real
single-route remote execution stage. The template records the future target
transit server, transit IP, landing VPS / node, landing IP, landing port,
active node, planned new listen port, target platform purpose, client usage,
local backup status, cloud security group, cloud firewall, server firewall, and
Workbuddy authorization fields that must be supplied before any real remote
action can be requested.

Current selection status remains No-Go because no real target transit server,
landing VPS / node, active node, listen port, or firewall confirmation has been
supplied. Stage 3.7.3 does not approve SSH, remote commands, route creation,
new listening ports, `node.share_link` changes, or cutover.

Stage 3.7.3 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, create real forwarding, perform
cutover, let `socat` take over 8443, or stop, downgrade, or replace `gost`
8443. Workbuddy is not required for this target-selection template, but will be
required for later real SSH, remote port checks, remote creation, or remote
diagnosis stages.

## Stage 3.7.4 Single route readonly preflight approval scope

Stage 3.7.4 documents the approval template for a future real remote read-only
preflight stage. The template records whether Workbuddy may be used, which
transit server and landing node are being checked, which new listen port is
planned, which read-only checks may be allowed, and which remote checks remain
unauthorized until a later explicit execution stage.

Current approval status remains No-Go because the target transit server,
landing VPS / node, active node, new listen port, cloud security group, cloud
firewall, server firewall, and Workbuddy execution authorization have not been
supplied. Stage 3.7.4 does not approve SSH, remote read-only commands, route
creation, new listening ports, `node.share_link` changes, or cutover.

Stage 3.7.4 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
It does not execute SSH or remote commands, create real forwarding, perform
cutover, let `socat` take over 8443, or stop, downgrade, or replace `gost`
8443. Workbuddy is not required for this approval template, but will be
required for a later explicitly authorized remote read-only preflight execution
stage.

## Stage 3.7.5 Single route local plan builder scope

Stage 3.7.5 adds a frontend-only local dry-run plan builder to the single-route
page. The builder lets the operator select a transit resource, active landing
node, planned listen port, landing target port, target purpose, firewall
confirmation states, and local backup confirmation, then shows a local
Go/No-Go result and a redacted approval summary for a later approval stage.

The builder rejects invalid listen ports and protects `22`, `8443`, `18443`,
and `20575`. A plan can only reach `Ready for readonly preflight approval` when
the port is valid, protected ports are avoided, the purpose is present, cloud
security group / cloud firewall / server firewall confirmations are checked,
and local database backup is confirmed. Ready means only ready for the next
read-only preflight approval stage; it never means remote execution or route
creation is approved.

Stage 3.7.5 does not add a backend dry-run API. It does not modify backend
logic, database schema, Worker/RQ jobs, scripts, `node.share_link`, listening
ports, firewall rules, current route state, or current transit links. It does
not execute SSH or remote commands, create real forwarding, trigger backend
tasks, perform cutover, let `socat` take over 8443, or stop, downgrade, or
replace `gost` 8443. Workbuddy is not required for the local dry-run builder.

## Stage 3.7.6 Single route local plan builder browser acceptance record scope

Stage 3.7.6 records browser manual acceptance for the Stage 3.7.5 local
dry-run plan builder. The user verified locally at `http://localhost:3000` that
the login gate works, the single-route page opens, the local plan builder is
visible, protected ports `8443`, `18443`, `22`, and `20575` stay No-Go, missing
firewall / backup confirmations keep the plan No-Go, and all confirmations can
move the plan only to `Ready for readonly preflight approval`.

The recorded acceptance also confirms that Ready does not authorize real
forwarding creation, SSH, remote commands, new listening ports,
`node.share_link` modification, or cutover. The page does not display complete
node links, SSH keys, passwords, tokens, or `SESSION_SECRET` values. The
current production link state remains unchanged: `socat` 18443 is the formal
link, `gost` 8443 remains the fallback link, and `node.share_link` is not
modified by this stage.

## Stage 3.7.7 Single route local plan builder stability archive scope

Stage 3.7.7 archives the Stage 3.7 stable baseline. Stage 3.7 now includes the
remote-execution readiness checklist, remote-execution approval template,
target / port selection template, remote read-only preflight approval template,
local dry-run plan builder, and browser acceptance record.

The archived baseline states that all remote execution remains No-Go. SSH,
remote commands, Workbuddy execution, real forwarding creation, new listening
ports, `node.share_link` modification, and cutover are not authorized. The
current formal link remains `socat` 18443, the fallback link remains `gost`
8443, and future real route creation requires a separately authorized stage
with target route, target port, firewall confirmations, and explicit user
approval.

## Stage 3.8.1 Single route readonly preflight framework scope

Stage 3.8.1 adds a frontend-only local framework for a future single-route
remote read-only preflight. The framework uses the local dry-run route plan to
show future read-only checks, local Go / No-Go state, and a redacted preflight
approval summary.

The framework lists future checks such as transit-server connectivity, planned
port occupancy, current `socat` 18443 ownership, current `gost` 8443 ownership,
read-only service / process status, transit-to-landing TCP connectivity,
server firewall status, task history / local health, and cloud / firewall
confirmation state. These checks are not executed in Stage 3.8.1.

Stage 3.8.1 does not add a backend validate endpoint. It does not modify
backend logic, database schema, Worker/RQ jobs, scripts, `node.share_link`,
listening ports, firewall rules, current route state, or current transit links.
It does not execute SSH or remote commands, connect to remote servers, create
real forwarding, trigger backend tasks, perform cutover, let `socat` take over
8443, or stop, downgrade, or replace `gost` 8443. Workbuddy is not required
for this local framework.

## Stage 3.8.2 Readonly preflight framework browser acceptance record scope

Stage 3.8.2 records browser manual acceptance for the Stage 3.8.1 readonly
preflight local framework. The accepted browser flow confirms that the login
gate appears, the single-route page opens after login, the readonly preflight
plan area is visible, incomplete or unsafe route inputs show No-Go, and all
local confirmations produce only `Ready for readonly preflight approval`.

The accepted browser flow confirms that `8443`, `18443`, `22`, and `20575`
remain blocked or clearly marked No-Go, that Ready does not mean remote
execution or real forwarding creation, and that the page clearly states it will
not execute SSH, run remote commands, connect to remote servers, create real
forwarding, add real listening ports, modify `node.share_link`, or perform
cutover.

Stage 3.8.2 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
The current formal link remains `socat` 18443, the fallback link remains
`gost` 8443, and Workbuddy is not required for this browser acceptance record.

## Stage 3.8.3 Readonly preflight framework stability archive scope

Stage 3.8.3 archives the Stage 3.8 readonly preflight framework stable
baseline. Stage 3.8 now includes the local readonly preflight framework, future
read-only check item list, local Go / No-Go judgment, redacted approval
summary, and browser acceptance record.

The archived baseline states that all remote execution remains No-Go. SSH,
remote commands, remote server connections, Workbuddy execution, real
forwarding creation, new listening ports, `node.share_link` modification, and
cutover are not authorized. The current formal link remains `socat` 18443, the
fallback link remains `gost` 8443, and future real read-only preflight or route
creation requires a separately authorized stage with target route, target port,
firewall confirmations, and explicit user approval.

## Stage 3.9.1 Readonly preflight execution contract scope

Stage 3.9.1 documents the future execution contract for a single-route remote
read-only preflight. It defines the proposed request fields, response fields,
task result shape, check item structure, status model, safety boundaries,
redaction rules, frontend display expectations, and Workbuddy authorization
boundary for a later stage.

Stage 3.9.1 is documentation-only. It does not add a backend endpoint, enqueue
tasks, add schemas, modify frontend behavior, execute SSH, run remote commands,
connect to remote servers, create real forwarding, add real listening ports,
modify `node.share_link`, or perform cutover. The current formal link remains
`socat` 18443, the fallback link remains `gost` 8443, and remote execution
remains No-Go until a separately authorized stage.

## Stage 3.9.2 Readonly preflight no-op API scaffold scope

Stage 3.9.2 adds `POST /api/transit-routes/readonly-preflight-plan`, a
login-protected no-op backend API scaffold for the future single-route readonly
preflight flow. The endpoint validates local input and returns a redacted
readonly preflight plan with Go / No-Go state, check items, safety boundaries,
and next-action text.

The endpoint is intentionally side-effect free. It does not create database
records, create tasks, write Redis temporary credentials, execute SSH, run
remote commands, connect to remote servers, create real forwarding, add real
listening ports, modify `node.share_link`, or perform cutover. The current
formal link remains `socat` 18443, the fallback link remains `gost` 8443, and
remote execution remains No-Go.

## Stage 3.9.3 Readonly preflight no-op API acceptance record scope

Stage 3.9.3 records local acceptance for the Stage 3.9.2 readonly preflight
no-op API scaffold. The record confirms that local services start, health is
ok, the frontend responds with HTTP 200, unauthenticated access to the no-op
API returns `401`, protected ports return blocked / No-Go, missing local
confirmations return No-Go, and a safe high port with all local confirmations
returns `ready=true` only for a future readonly preflight approval / execution
stage.

Stage 3.9.3 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
The current formal link remains `socat` 18443, the fallback link remains
`gost` 8443, and remote execution remains No-Go.

## Stage 3.9.4 Readonly preflight UI API integration scope

Stage 3.9.4 connects the frontend readonly preflight planning area to the
Stage 3.9.2 local no-op API:
`POST /api/transit-routes/readonly-preflight-plan`. The UI can request the
backend no-op plan and display `ready`, `blocked`, `status`, `summary`,
`next_action`, `checks`, `safety_boundary`, and `redacted_summary`.

The integration remains side-effect free. It does not execute SSH, run remote
commands, connect to remote servers, create real forwarding, add real listening
ports, modify `node.share_link`, trigger backend tasks, or perform cutover.
The current formal link remains `socat` 18443, the fallback link remains
`gost` 8443, and remote execution remains No-Go.

## Stage 3.9.5 Readonly preflight UI API browser acceptance record scope

Stage 3.9.5 records browser manual acceptance for the Stage 3.9.4 readonly
preflight UI API integration. The record confirms that the login gate works,
the single-route page opens, the readonly preflight area calls the no-op API,
protected ports show blocked / No-Go, missing confirmations show `no_go`, and
all local confirmations can show `ready=True` only for a future readonly
preflight approval stage.

Stage 3.9.5 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
The current formal link remains `socat` 18443, the fallback link remains
`gost` 8443, and remote execution remains No-Go.

## Stage 3.10.1 Readonly preflight local package stability and next-step plan scope

Stage 3.10.1 archives the Stage 3.9 readonly preflight local package and
records the next-step plan. The archive covers the execution contract, no-op
API scaffold, no-op API acceptance record, frontend UI integration, and browser
acceptance record.

Stage 3.10.1 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
The current formal link remains `socat` 18443, the fallback link remains
`gost` 8443, and remote execution remains No-Go until the user later provides a
target route, target port, firewall confirmations, and explicit authorization.

## Stage 3.10.2 Local console final acceptance and long-term use guide scope

Stage 3.10.2 archives the final local console acceptance checklist and
long-term use guide. It covers daily local operation, health checks, backup
before upgrades, exception handling, current route safety boundaries, future
new-route prerequisites, Workbuddy boundaries, and the simplified future stage
planning rules for low-risk local work.

Stage 3.10.2 is documentation-only. It does not modify code, frontend behavior,
backend logic, scripts, database schema, `node.share_link`, listening ports,
firewall rules, Worker/RQ tasks, current route state, or current transit links.
The current formal link remains `socat` 18443, the fallback link remains
`gost` 8443, and remote execution remains No-Go until the user later provides a
target route, target port, firewall confirmations, and explicit authorization.

## Stage 3.10.3 Local console v1 stable release tag scope

Stage 3.10.3 archives the current local console v1 stable baseline and prepares
the future `local-console-v1-stable` Git tag plan. The recommended tag is an
annotated tag to be created manually on `main` after this PR is merged.

Stage 3.10.3 is documentation-only. It does not create a Git tag, modify code,
frontend behavior, backend logic, scripts, database schema, `node.share_link`,
listening ports, firewall rules, Worker/RQ tasks, current route state, or
current transit links. The current formal link remains `socat` 18443, the
fallback link remains `gost` 8443, and remote execution remains No-Go.

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
| Stage 3.3.13 UI polish | Dark SaaS operations-console UI polished; no cutover / no `node.share_link` change |
| Stage 3.3.14 UI zh-CN collapsible tips | Console UI localized to Chinese; large safety tips collapsed by default |
| Stage 3.3.17 Server management UI table | Servers page changed to server-management table backed by VPS APIs |
| Stage 3.3.18 Node menu consolidation | Nodes left-nav entry removed; nav renamed to Transit Servers / Landing Servers; node actions consolidated under landing-server child rows |
| Stage 3.3.19 Transit server UI table alignment | Transit Servers page aligned to management-table UI; Worker/remote execution remains future-stage |
| Stage 3.3.20 Transit server / route split | Transit Servers and Transit Links separated; remote execution remains No-Go |
| Stage 3.3.21 Lightweight Worker bootstrap design | Lightweight Worker bootstrap design documented; implementation remains No-Go |
| Stage 3.3.22 Worker token/register/heartbeat foundation | Worker token, register, heartbeat, and query APIs added; no real Worker execution |
| Stage 3.3.23 Worker bootstrap UI integration | Landing/transit add-server UI now generates one-time Worker bootstrap commands |
| Stage 3.3.24 Minimal LiveLine Worker binary | Minimal Go Worker binary and real install script implemented; no real VPS install |
| Stage 3.3.25 Worker public install URL fix | Worker install commands require a configured public console URL; localhost fallback removed |
| Stage 3.3.26 Deployment missing credentials fix | Redis temporary credential service restored to version control for deployment imports |
| Stage 3.3.27 Worker server binding UI | Add-server flow creates landing/transit records before bound Worker install commands |
| Stage 3.3.28 Worker command channel foundation | Read-only Worker command queue, polling, result reporting, and UI check entry added |
| Stage 3.3.29 Worker command target selection fix | Worker checks now target the latest online command-capable Worker |
| Stage 3.3.30 Worker landing readonly preflight | Landing Worker read-only preflight command added; no remote SSH or cutover |
| Stage 3.3.32 Landing node create plan | Dry-run landing node creation plan added; no node creation, no SSH, no cutover |
| Stage 3.3.33 Worker preflight interface normalization | Landing preflight interface fields normalized and listener parsing fixed; no remote execution |
| Stage 3.3.35 Formal landing node create approval | Landing-node dry-run uses random high candidate ports and blocks common ports; no real execution |
| Stage 3.3.36 Formal landing node create execution guard | Fixed 27939/TCP execution guard documented; real execution remains disabled |
| Stage 3.3.37 Formal landing node create execution | Controlled landing-node create command path added; local validation did not execute real creation |
| Stage 3.3.37-a Formal create Worker targeting hotfix | Formal create now targets the latest eligible online ens17 landing Worker; no real execution |
| Stage 3.3.37-b Xray install path and Worker sandbox hotfix | Xray path moved to /opt/liveline-xray and Worker sandbox write paths narrowed |
| Stage 3.3.37-c Worker installer ReadWritePaths precreate hotfix | Worker installer precreates /opt/liveline-xray before starting the sandboxed service |
| Stage 3.3.37-d Allow empty LiveLine Xray directory hotfix | Worker formal-create guard allows an empty precreated /opt/liveline-xray while still rejecting real artifacts |
| Stage 3.3.37-e Formal create client acceptance record | Formal landing node create completed client acceptance; this record stage is not cutover |
| Stage 3.3.38 Post-acceptance security hardening and key rotation review | Formal node post-acceptance security review recorded; no rotation or environment change |
| Stage 3.3.40 Share-link redaction and export confirmation | Node share links are default-redacted and require confirmed export; no node or environment change |
| Stage 3.3.41 Node key rotation runbook | Node key rotation / rebuild / old-link retirement runbook documented; no real rotation or node change |
| Stage 3.3.50 Transit Worker install command regeneration | pending_worker transit servers can regenerate a bound Worker install command; real installation remains manual |
| Stage 3.3.63 Transit Worker remote readonly preflight API implementation | Worker/API readonly preflight command implemented; real transit creation remains No-Go |
| Stage 3.3.67 Transit readonly preflight simple button | Transit Links readonly preflight UI simplified into a button panel; backend and real creation remain unchanged |
| Stage 3.3.68 Transit readonly preflight result polish | Transit readonly preflight results now show clearer state, failure summaries, manual actions, and safety boundaries |
| Stage 3.3.68 hotfix preflight panel prominent | Simplified readonly preflight panel moved above the transit route table so the action and result area are visible near the top |
| Stage 3.3.68 hotfix transit readonly result EOF | Transit readonly preflight result ingestion now normalizes returned results and fails malformed payloads instead of leaving commands running |
| Stage 3.3.68 hotfix Worker result submit EOF | Worker result submit now sanitizes payloads, reports HTTP diagnostics, uses fallback failure submit, and requires Worker 0.1.8 for transit readonly preflight |
| Stage 3.3.68 hotfix Worker result endpoint timeout | Worker result/fail endpoints now use bounded fast-path ingestion, ingress logs, fallback failure handling, and idempotent already-completed responses |
| Stage 3.3.68 hotfix Worker authenticated result path | Worker-authenticated result/fail paths now log phase timings, apply short DB statement timeout, and classify Worker submit timeout phases |
| Stage 3.3.68 hotfix Worker result payload diagnosis | Worker can locally generate transit readonly preflight results and print redacted payload diagnostics without submitting to the console |
| Stage 3.3.68 hotfix Worker auto-submit trace | Worker automatic result/fail submission now emits redacted size, endpoint, timing, status, and error-classification traces |
| Stage 3.3.68 hotfix Worker submit curl compatible | Worker result/fail submit uses curl-compatible HTTP behavior plus constrained curl fallback for response-header timeouts |
| Stage 3.3.68 hotfix Worker result EOF curl fallback | Worker result/fail submit now also uses the constrained curl fallback for pre-response EOF/reset/broken-pipe submit failures |
| Stage 3.3.68 hotfix Worker curl fallback config fix | Worker curl fallback now uses readable 0600 temp config/body files and keeps secrets out of process args and logs |
| Stage 3.3.68 hotfix Worker curl fallback no config | Worker curl fallback no longer uses curl --config; it uses 0600 header/body/response temp files with fixed curl args |
| Stage 3.3.68 hotfix Worker curl fallback manual compatible | Worker curl fallback now matches the manually successful curl -i header/body-file command shape |
| Stage 3.3.68 hotfix Worker compact result payload | Transit readonly preflight Worker result payload is compacted below the small-body target before submission |
| Stage 3.3.69 Transit readonly UI validation record | Production UI readonly preflight validation passed with Worker 0.1.16 compact result submission; no real route creation or cutover |
| Stage 3.3.70 Transit route create approval | Formal pre-execution approval packet recorded for the planned Hong Kong socat transit route; no real creation, listener, firewall change, or cutover |
| Stage 3.3.71 Transit route Worker create path | Controlled Worker dry-run create path added for the approved Hong Kong socat route; real route creation remains deferred |
| Stage 3.3.72a Legacy SSH/RQ flow removal | Old SSH private-key / Redis temp credential / RQ operation paths removed from active code; Worker command model remains the supported remote path |
| Stage 3.3.72d Worker result large POST timeout hotfix | `transit_route_create` Worker dry-run result/fail payloads are compacted to avoid large POST timeout/EOF; no real route creation or cutover |
| Stage 3.3.73d Transit route real create code path | Controlled Worker/API real-create path added for the approved Hong Kong socat 23843 route; no command triggered, no route created, no cutover |
| Stage 3.3.73f Transit route real create listen verification hotfix | Worker real-create verification now retries service/listener checks and reports compact diagnostics before rollback; no command triggered, no route created, no cutover |
| Stage 3.3.73h Production success record | Approved Hong Kong socat 23843 transit route created successfully; service active, route active, share_link remains NULL, no cutover |
| Stage 3.3.74c Client candidate success record | Hong Kong socat 23843 candidate validated by client import; browsing works, exit remains landing region, no cutover |
| Stage 3.3.75 Formal route promotion approval | Formal approval pack for promoting hk-socat-live-23843 as client candidate; no cutover, no share_link mutation |
| Stage 3.3.75b Route promotion implementation plan | Plan candidate promotion approaches without cutover or share_link mutation |
| Stage 3.3.76 Longer stability observation | Observation plan for hk-socat-live-23843 before any promotion; no cutover or share_link mutation |
| Stage 3.3.77 Transit candidate UI and transient export | Add safe candidate route display and transient client export without cutover or share_link mutation |
| Stage 3.3.77c Candidate export copy fallback hotfix | Add HTTP-safe manual copy fallback for transient candidate export; no cutover or share_link mutation |
| Stage 3.3.77e System test result record | Record successful candidate UI/export system test with HTTP manual-copy fallback; no cutover or share_link mutation |
| Stage 3.3.77f System test final record and next decision pack | Record successful candidate UI/export retest, HTTP manual-copy fallback, database non-mutation, and next-stage backlog; no cutover or share_link mutation |
| Stage 3.3.78 Transit feature complete record | Record lightweight self-use product principle and current network-building feature completion; troubleshooting remains a later separate stage |
| Stage 3.3.79 Multi-resource capability check | Audit support boundaries for multiple transit resources, landing VPS, nodes, and transit routes; no production action |
| Stage 3.3.80 Network build usability polish plan | Plan simple UI and flow improvements for self-use network setup; no production action |
| Stage 3.3.81 Transit page advanced sections collapse | Default-collapse advanced transit debug and approval sections to reduce misoperation risk; no backend or production action |
| Stage 3.3.82 Transit route list layout and create modal | Refactor transit routes page into list layout with add-route preview modal; no Worker command or production action |
| Stage 3.3.83 Transit route table list layout | Convert transit route cards into server-like table list layout while keeping add-route preview modal local-only; no backend or production action |
| Stage 3.3.84 Transit route compact table polish | Convert transit route card list into compact server-like table rows; no backend or production action |
| Stage 3.3.85 Transit export modal polish | Move transient candidate export confirmations and result into a modal with close action; no backend or production action |
| Stage 3.3.86 Transit export modal layout hotfix | Fix transient export modal overflow and checkbox alignment; no backend or production action |
| Stage 3.3.87 Transit export modal confirmation layout fix | Fix modal confirmation checklist alignment and remove horizontal overflow; no backend or production action |
| Stage 3.3.88 Transit add-route modal confirmation layout fix | Fix add-route preview modal confirmation checklist alignment and remove horizontal overflow; no backend or production action |
| Stage 3.3.89 Transit export modal simplify no checkbox | Replace transient export checkbox checklist with simple safety notice and generate action; no backend or production action |
| Stage 3.3.90 Landing server node usability polish | Simplify landing VPS and direct node display/copy flow; no backend or production action |
| Stage 3.3.91 Overview network status summary polish | Simplify overview page into network-build status summary and navigation; no backend or production action |
| Stage 3.3.92 Network build UI polish complete record | Record completion of simplified network-build workflow and UI polish; no code or production action |
| Stage 3.3.93 Network build final smoke test | Final smoke-test record for the simplified self-use network-build flow; no feature or production change |
| Stage 3.3.94 Landing summary strip remove | Hide redundant landing-server top summary strip; UI-only cleanup, no backend or production action |
| Stage 3.3.95 Resource list safe delete | Add safe delete buttons for transit servers, landing servers, nodes, and transit routes; soft-delete system records only, no remote cleanup |
| Stage 3.3.96 Resource safe delete public smoke record | Record public-console smoke test for Stage 3.3.95 safe-delete buttons and confirmation dialogs; no delete executed |
| Stage 3.3.97 Protected remote cleanup delete flow | Upgrade delete buttons to protected remote cleanup flows for nodes, servers, transit routes, and transit resources; cleanup succeeds before soft-delete |
| Stage 3.3.99 Remote Worker upgrade to 0.1.21 | Upgrade landing/transit Workers to support protected cleanup commands; no cleanup or production delete executed |
| Stage 3.3.100 Protected cleanup final approval | Final approval checklist and readonly preflight before any protected remote cleanup execution; no cleanup command created |
| Stage 3.3.101 Worker self-cleanup residual fix | Prevent deleted/cleanup-expected Workers from being revived by heartbeat and record residual Worker cleanup follow-up; no remote command executed |
| Stage 3.3.102 Residual Worker final cleanup | Mark residual Workers cleanup-expected, verify post-cleanup heartbeat guard, then manually stop/disable stale remote Worker services |
| Stage 3.3.103 Simplified node create QR flow | Simplify direct Reality node creation UX and show V2Ray link/QR only after successful protected remote creation |
| Stage 3.3.105 Generalize protected landing create server approval | Replace fixed historical landing-server guard with protected active-server approval while keeping fixed port and preflight safeguards |
| Stage 3.3.107 Landing create Xray listen diagnostics | Add retrying Xray listen checks and safe failure diagnostics for landing_node_create without changing share-link success gates |
| Stage 3.3.107-b Rebuild Worker binary artifact | Rebuild bundled Linux amd64 Worker binary for 0.1.22-stage-3.3.107 diagnostics before remote Worker upgrade |
| Stage 3.3.109 Node create modal close polish | Add visible close / finish controls to the direct node create modal after success or failure |
| Stage 3.3.109-b Node create modal TS narrowing fix | Remove stale nodePlan render branch after dedicated modal path to restore frontend production build |
| Stage 3.3.111 Simplified transit route create QR flow | Make transit route creation mirror direct node creation with protected remote create, generated V2Ray link, and QR after successful listen/connectivity checks |
| Stage 3.3.113 Generalize protected transit route create approval | Replace fixed historical transit route approval with protected active-resource approval while keeping socat, preflight, and no-cutover safeguards |
| Stage 3.3.115 Worker command read endpoint and transit poll fix | Add admin WorkerCommand status read endpoint and make transit create polling tolerate short command visibility delays without undefined errors |
| Stage 3.3.117 Generalize worker-side transit route create approval | Replace historical Worker id approval in transit_route_create with dynamic payload/current-worker approval while keeping socat and no-cutover safeguards |
| Stage 3.3.119 Unified delete offline local remove | Upgrade existing delete buttons to support offline local soft-removal for expired transit servers, landing servers, direct nodes, and transit routes without remote cleanup |
| Stage 3.3.125 Worker 0.1.24 deploy plan | Documents the Worker 0.1.24 deployment plan and rollback checklist for HAProxy TCP readiness; no deployment, Worker replacement, HAProxy route creation, socat mutation, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.126-a Worker 0.1.24 build artifact | Rebuild bundled Linux amd64 Worker binary for HAProxy TCP readiness; no deploy, remote Worker replacement, HAProxy route creation, socat mutation, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.127 New transit VPS Worker onboarding plan | Documents the new transit VPS onboarding path after old transit resources were removed; plans Worker 0.1.24 installation and HAProxy TCP readiness without creating resources, generating tokens, installing Worker, creating routes, mutating firewall, or cutover |
| Stage 3.3.128 New transit VPS resource create approval | Documents approval requirements and field mapping for creating a new transit VPS resource record; no resource creation, Worker token generation, Worker installation, SSH/remote command, HAProxy route creation, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.129 New transit resource draft and demo flow | Adds/records the no-real-VPS draft flow for new transit resources with pending_worker guidance and HAProxy readiness reminders; no Worker token generation, Worker install, SSH/remote command, Worker command, HAProxy route, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.130 New transit Worker install approval preview | Adds/records the no-real-VPS Worker install approval preview for pending_worker transit resources with placeholder command safety and Go/No-Go checks; no Worker token generation, real install command generation, Worker install, SSH/remote command, Worker command, HAProxy route, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.131 New transit Worker install command generation approval | Adds/records the no-real-VPS approval gate for future Worker install command generation with typed confirmation and placeholder token safety; no Worker token generation, real install command generation, Worker install, SSH/remote command, Worker command, HAProxy route, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.132 New transit Worker install command generation dry-run | Adds/records a no-real-VPS dry-run result view for future Worker install command generation with placeholder token safety; no Worker token generation, real install command generation, Worker install, SSH/remote command, Worker command, HAProxy route, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.133 New transit Worker install command real approval | Adds/records the final approval gate for future real one-time Worker token and install command generation with real VPS readiness checks; no Worker token generation, real install command generation, Worker install, SSH/remote command, Worker command, HAProxy route, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.134 New transit Worker install command generation execution | Adds/records the approved generation path for one-time Worker token and install command for pending_worker transit resources; no Worker installation, SSH/remote command, Worker command, HAProxy route, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.135 New transit Worker manual install and heartbeat acceptance | Adds/records read-only acceptance checks for a manually installed transit Worker after user-executed install command; no install command exposure, Worker token exposure, SSH/remote execution, Worker command, HAProxy route, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.136 New transit HAProxy readiness and route create approval | Adds/records read-only HAProxy TCP route creation approval after transit Worker heartbeat acceptance; no Worker command, HAProxy route, HAProxy install, firewall/security group/cloud firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.137 New transit HAProxy route create dry-run | Adds/records HAProxy TCP route creation dry-run after readiness approval; dry-run Worker command only, no real HAProxy route, HAProxy install, listener binding, firewall/security group/cloud firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.138 New transit HAProxy route create final approval | Adds/records final approval checks after HAProxy route dry-run; no Worker command, real HAProxy route, TransitRoute active record, HAProxy install, listener binding, firewall/security group/cloud firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.137 hotfix 2 HAProxy dry-run Worker validation | Upgrade Worker dry-run validation to accept the approved Stage 3.3.137 HAProxy TCP dry-run payload and rebuild Worker 0.1.25 artifact; no remote deployment, Worker command, HAProxy route, listener binding, firewall mutation, cutover, or share-link mutation occurred |
| Stage 3.3.137 hotfix 3 Transit Worker upgrade approval | Add read-only transit Worker upgrade acceptance before re-running HAProxy TCP dry-run; no token/install command generation, remote execution, Worker command, route creation, listener binding, firewall mutation, cutover, or share-link mutation |
| Stage 3.3.137 hotfix 4 Transit Worker manual upgrade runbook | Add manual transit Worker upgrade runbook and acceptance reminder for mkiepl Guang-Hong before re-running HAProxy TCP dry-run; no token/install command generation, remote execution, Worker command, route creation, listener binding, firewall mutation, cutover, or share-link mutation |
| Stage 3.3.137 hotfix 5 Transit Worker manual upgrade commands review | Add manual command review checklist separating public controller checks, transit VPS manual steps, and post-upgrade acceptance; no SSH, token/install command generation, Worker command, HAProxy route, listener binding, firewall mutation, cutover, or share-link mutation |
| Stage 3.3.139 New transit HAProxy route create real execution | Add protected real-execution Worker command entry after succeeded HAProxy dry-run and final approval; no deployment, direct route creation, listener binding, firewall mutation, cutover, or share-link mutation |
| Stage 3.3.152 HAProxy parity cleanup and Worker install | Support HAProxy TCP route cleanup, mixed socat/HAProxy transit-resource cleanup, Worker install HAProxy write paths, and active-route UI parity; no real delete, route creation, firewall mutation, cutover, or share-link mutation |
| Stage 3.3.153 HAProxy create result persist parity | Persist successful HAProxy TCP real-create results as active transit routes while preserving socat behavior; no real create, delete, Worker command, cutover, firewall mutation, or share-link mutation |
| Stage 3.3.14 C cutover decision pack | C-plan pre-review documented, No-Go for formal cutover |
| Stage 3.3.15 C final Go / No-Go approval | Final No-Go documented, no formal cutover |
| Stage 3.3.16 C No-Go blocker resolution plan | Blocker resolution plan documented, still No-Go |
| Stage 3.3.17 C execution runbook draft | Execution runbook draft documented, still No-Go |
| Stage 3.3.18 C execution runbook review checklist | Runbook review checklist documented, still No-Go |
| Stage 3.3.19 C execution runbook gap fix plan | Gap fix plan documented, still No-Go |
| Stage 3.3.20 C command authorization matrix | Command authorization matrix documented, still No-Go |
| Stage 3.3.21 C read-only preflight command list | Read-only preflight command list documented, still No-Go |
| Stage 3.3.22 C No-Go preflight approval pack | No-Go preflight approval pack documented, still No-Go |
| Stage 3.3.23 C read-only preflight execution approval | Execution approval request documented, still No-Go |
| Stage 3.3.24 C read-only preflight execution authorization | Read-only preflight execution authorized for next stage, no cutover |
| Stage 3.3.25 C read-only preflight execution | Server-side preflight Ready; overall C-plan readiness Blocked |
| Stage 3.3.26 C manual read-only preflight evidence record | Manual server-side evidence recorded Ready; overall C-plan readiness Blocked |
| Stage 3.3.27 C cloud security firewall manual confirmation | Cloud security group / firewall confirmation completed; overall C-plan readiness still Blocked |
| Stage 3.3.28 C final readiness reconciliation | Technical preflight basically Ready; production cutover authorization still Blocked |
| Stage 3.3.29 C final Go decision | C-minimal Go recorded for next execution stage; no cutover executed |
| Stage 3.3.30 C formal cutover execution runbook final | Final execution runbook documented; no cutover executed |
| Stage 3.3.31 C formal cutover execution | Cutover already in effect (`node.share_link` = socat 18443); gost 8443 retained as fallback |
| Stage 3.3.32 C post-cutover observation | Observation template documented; no new cutover executed |
| Stage 3.3.33 C post-cutover observation result | Observation Healthy; socat 18443 formal route retained; gost 8443 fallback retained |
| Stage 3.3.34 C stability archive | C-minimal cutover stable archive documented; maintenance observation recommended |
| Stage 3.3.35 C maintenance observation plan | Maintenance observation plan documented; gost 8443 fallback retained |
| Stage 3.4.1 Auth login gate | Development complete |
| Stage 3.4.2 Auth login local acceptance record | Local browser acceptance passed |
| Stage 3.4.3 Auth protected API sweep | Protected API sweep passed |
| Stage 3.4.4 Auth session hardening plan | Hardening plan documented; no auth logic change |
| Stage 3.4.5 Auth login rate limit hardening | Redis-backed login failure rate limiting implemented |
| Stage 3.4.6 Auth login rate limit browser acceptance record | Browser acceptance passed |
| Stage 3.4.7 Auth production environment readiness check | Production Auth env readiness documented |
| Stage 3.4.8 Auth production environment guardrails | Production-only Auth startup guardrails implemented |
| Stage 3.4.9 Auth production environment guardrails acceptance record | Guardrails acceptance recorded |
| Stage 3.4.10 Auth security stability archive | Auth security baseline archived |
| Stage 3.5.1 Local console operations readiness | Local console daily operations documented |
| Stage 3.5.2 Local backup and restore plan | Local backup and restore plan documented |
| Stage 3.5.3 Local backup and restore implementation | Local backup and restore scripts documented / implemented |
| Stage 3.5.4 Topology preview usability polish | Topology preview clarified as preview-only |
| Stage 3.5.5 Route safety guardrails UI | Route safety guardrails added to local UI |
| Stage 3.5.6 Local task history usability | Local task history usability improved |
| Stage 3.5.7 Local upgrade and rollback SOP | Local upgrade and rollback SOP documented |
| Stage 3.5.8 Local console stability archive | Local console stability baseline archived |
| Stage 3.6.1 Single route create flow review | Single route create flow reviewed |
| Stage 3.6.2 Single route create safety gates | Single route create safety gates added |
| Stage 3.6.3 Single route diagnosis polish | Single route diagnosis display polished |
| Stage 3.6.4 Single route diagnosis browser acceptance record | Single route diagnosis browser acceptance recorded |
| Stage 3.6.5 Single route create flow stability archive | Single route create flow baseline archived |
| Stage 3.7.1 Single route remote execution readiness | Single route remote execution readiness documented |
| Stage 3.7.2 Single route remote execution approval | Remote execution approval template documented; execution remains No-Go |
| Stage 3.7.3 Single route target and port selection record | Target and port selection template documented; execution remains No-Go |
| Stage 3.7.4 Single route readonly preflight approval | Readonly preflight approval template documented; execution remains No-Go |
| Stage 3.7.5 Single route local plan builder | Single route local dry-run plan builder added; remote execution remains No-Go |
| Stage 3.7.6 Single route local plan builder browser acceptance record | Single route local plan builder browser acceptance recorded |
| Stage 3.7.7 Single route local plan builder stability archive | Single route local planning baseline archived; remote execution remains No-Go |
| Stage 3.8.1 Single route readonly preflight framework | Single route readonly preflight framework added; remote execution remains No-Go |
| Stage 3.8.2 Readonly preflight framework browser acceptance record | Readonly preflight framework browser acceptance recorded |
| Stage 3.8.3 Readonly preflight framework stability archive | Readonly preflight framework baseline archived; remote execution remains No-Go |
| Stage 3.9.1 Readonly preflight execution contract | Readonly preflight execution contract documented; remote execution remains No-Go |
| Stage 3.9.2 Readonly preflight no-op API scaffold | Readonly preflight no-op API scaffold added; remote execution remains No-Go |
| Stage 3.9.3 Readonly preflight no-op API acceptance record | Readonly preflight no-op API acceptance recorded; remote execution remains No-Go |
| Stage 3.9.4 Readonly preflight UI API integration | Readonly preflight UI integrated with no-op API; remote execution remains No-Go |
| Stage 3.9.5 Readonly preflight UI API browser acceptance record | Readonly preflight UI API browser acceptance recorded |
| Stage 3.10.1 Readonly preflight local package stability and next-step plan | Readonly preflight local package archived; remote execution remains No-Go |
| Stage 3.10.2 Local console final acceptance and long-term use guide | Local console final acceptance and long-term use guide documented; remote execution remains No-Go |
| Stage 3.10.3 Local console v1 stable release tag | Local console v1 stable tag prepared; remote execution remains No-Go |

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
- `ADMIN_USERNAME`
- `ADMIN_PASSWORD_HASH`
- `AUTH_LOGIN_MAX_ATTEMPTS`
- `AUTH_LOGIN_WINDOW_SECONDS`
- `AUTH_LOGIN_LOCK_SECONDS`
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

Check current admin session:

```bash
curl -b /tmp/livelines-cookies.txt http://localhost:8000/api/auth/me
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
