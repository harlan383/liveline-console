# Codex Rules

This project follows the v2.2 node automation requirements document.

## Stage boundary

- Only develop Stage 0 until the user explicitly approves the next stage.
- Stage 0 covers Docker Compose, empty frontend layout, FastAPI health checks,
  PostgreSQL connectivity, Redis connectivity, RQ Worker startup, admin
  initialization/login skeleton, and the initial Alembic migration.
- Do not implement Stage 1 or later features during Stage 0.

## Hard prohibitions for Stage 0

- Do not connect to any VPS.
- Do not upload, paste, store, or process SSH keys.
- Do not run remote SSH commands.
- Do not write Xray install scripts.
- Do not install 3x-ui.
- Do not call 3x-ui APIs.
- Do not implement VPS reading.
- Do not implement node creation, editing, deletion, or checking.
- Do not generate node links or QR codes.

## Stage 2.1 boundary

- Stage 2.1 may implement only the `prepare_node` installation pre-check task.
- `prepare_node` must not install Xray, modify VPS files, write Xray config,
  create nodes, open ports, modify firewall rules, run `sudo`, or run `apt`.
- `prepare_node` may only execute read-only SSH commands with timeouts.
- `prepare_node` results must be written to `tasks.result_data` and
  `task_logs`; it must not write the `nodes` table.

## Stage 2.2 boundary

- Stage 2.2 may implement only the `install_xray` task.
- `install_xray` may install Xray-core with the official XTLS installation
  script, create/enable/start `xray.service`, and verify `xray version` plus
  service state.
- `install_xray` must require a successful recent `prepare_node` result and
  must reuse encrypted Redis temporary credentials.
- `install_xray` must not create nodes, write business node configuration,
  overwrite existing Xray config, generate links or QR codes, configure relay,
  modify firewall rules, open ports, delete user files, or use 3x-ui.
- `install_xray` results must be written to `tasks.result_data` and
  `task_logs`; it must not write the `nodes` table.

## Stage 2.3 boundary

- Stage 2.3 may implement only one direct VLESS Reality node creation task:
  `create_direct_node`.
- `create_direct_node` may generate Reality keys with `xray x25519`, write
  `/usr/local/etc/xray/config.json`, run `xray run -test`, restart `xray.service`,
  verify the listening port, create one active `nodes` row, and generate a
  `vless://` share link.
- `create_direct_node` must not store or return the Reality private key, print
  full Xray config to logs, create QR codes, delete nodes, configure relay,
  modify firewall rules, open ports, modify `sshd_config`, or use 3x-ui.
- Redis temporary SSH credentials remain required and must be deleted by the
  Worker after reading.
- Stage 2.3 is frozen after real VPS acceptance. Do not modify the
  `create_direct_node` core flow without explicit user approval. The frozen
  flow excludes relay, `dokodemo-door`, iptables forwarding, firewall changes,
  3x-ui, QR codes, node deletion, multi-node management, traffic statistics, and
  subscription links.

## Stage 2.4 boundary

- Stage 2.4 may implement only basic node management: node list, node detail,
  share-link copy, `refresh_node`, and `restart_xray`.
- `refresh_node` may only check Xray binary/version/config test/service status
  and port listening state, then update node status and task results.
- `restart_xray` may run `xray run -test`, restart `xray.service`, verify service
  status and port listening state, then update node status and task results.
- Stage 2.4 must not delete nodes, generate QR codes, configure relay, modify
  firewall rules, open ports, modify `sshd_config`, store Reality privateKey, or
  use 3x-ui.
- Stage 2.4 is frozen after real node-management acceptance. Do not modify the
  node list, node detail, `refresh_node`, or `restart_xray` core flow without
  explicit user approval. The frozen flow excludes new node creation, node
  deletion, node rebuilds, QR codes, IEPL / IPLC relay, `dokodemo-door`,
  iptables forwarding, firewall changes, port opening, 3x-ui, subscription
  links, traffic statistics, automatic speed tests, and `sshd_config` changes.

## Stage 2.5.1 boundary

- Stage 2.5.1 may implement only node soft deletion / disablement through
  `delete_node`.
- `delete_node` may back up `/usr/local/etc/xray/config.json`, stop
  `xray.service`, move the active config to a disabled path, verify service
  inactive state, verify the node port is no longer listening, update
  `nodes.status` to `deleted`, write `nodes.deleted_at`, update
  `vps_servers.status` to `xray_installed_pending_config`, and write task
  results/logs.
- `delete_node` must keep the historical `nodes` record and must not hard delete
  it.
- `delete_node` must not rebuild nodes, create nodes, generate new UUIDs,
  generate new Reality keys, generate new share links, generate QR codes,
  configure IEPL / IPLC relay, configure `dokodemo-door`, configure iptables
  forwarding, modify firewall rules, open ports, modify `sshd_config`, create
  subscription links, add traffic statistics, add automatic speed tests, or use
  3x-ui.
- Stage 2.5.1 is frozen after real soft-deletion acceptance. Do not modify the
  `delete_node` core flow without explicit user approval.

## Stage 2.5.2 boundary

- Stage 2.5.2 may implement only a clear "recreate direct node" entry point and
  safety protection after soft deletion.
- Stage 2.5.2 must reuse `POST /api/nodes/create-direct` and the
  `create_direct_node` task type. Do not add `rebuild_node`.
- Stage 2.5.2 creates a new active node record on the same VPS; it must not
  overwrite or modify the old deleted node.
- `create_direct_node` must refuse to overwrite an existing
  `/usr/local/etc/xray/config.json`. If the standard config exists, fail before
  generating a new Reality key, writing config, restarting Xray, or writing the
  `nodes` table.
- Stage 2.5.2 must not add database fields, add Alembic migrations, hard-delete
  historical nodes, delete old `config.json.bak.<timestamp>` or
  `config.json.disabled.<timestamp>` files, restore old links, generate QR
  codes, configure relay, configure `dokodemo-door`, configure iptables
  forwarding, modify firewall rules, open ports, use 3x-ui, create subscription
  links, add traffic statistics, add automatic speed tests, or modify
  `sshd_config`.
- Stage 2.5.2 is frozen after real recreate acceptance. Do not modify the
  recreate entry point, `create_direct_node` config-overwrite protection, or the
  recreate flow without explicit user approval. The frozen flow keeps old
  deleted nodes and old backup/disabled config files unchanged.

## Stage 2.6 boundary

- Stage 2.6 may implement only frontend node export experience improvements:
  masked share-link display, copy full `vless://` link, show/hide full link,
  local browser QR-code generation, and short client import hints.
- Stage 2.6 must not change backend APIs, add database fields, add Alembic
  migrations, connect to VPS hosts, upload SSH keys, or trigger
  `create_direct_node`, `delete_node`, `refresh_node`, or `restart_xray`.
- Stage 2.6 must not modify Xray config, create nodes, delete nodes, rebuild
  nodes, configure relay, configure `dokodemo-door`, configure iptables
  forwarding, modify firewall rules, open ports, use 3x-ui, create subscription
  links, add batch export, add JSON export, add traffic statistics, add
  automatic speed tests, or modify `sshd_config`.
- QR codes are equivalent to full node links. They must be generated only in the
  browser, never uploaded to the backend, never stored in the database, and
  never written to task logs or backend logs.
- Stage 2.6 is frozen after node export experience acceptance. Do not modify
  the node export experience, `share_link` masking strategy, local QR-code
  generation logic, QR security boundary, or short client import hints without
  explicit user approval.

## Stage 2.7.1 boundary

- Stage 2.7.1 may implement only Xray backup-file read-only viewing and manual
  restore instructions.
- Stage 2.7.1 may create only the `list_xray_backups` task through
  `POST /api/vps/{vps_id}/xray-backups`.
- `list_xray_backups` may only scan `/usr/local/etc/xray/` for `config.json*`
  file metadata: file name, path, type, size, and modified time.
- `list_xray_backups` may check only whether the config directory exists,
  whether current `config.json` exists, whether `xray.service` is active, and
  whether port 443 is listening.
- Stage 2.7.1 must continue using Redis temporary encrypted SSH credentials.
  RQ job arguments must not contain SSH Key or Passphrase.
- Stage 2.7.1 must not read full config content, run `cat` / `head` / `tail`
  against config files, return Reality privateKey, print config content to
  task logs, download backups, upload backups, restore config, delete backups,
  clean backups, modify remote files, or restart/stop/start Xray.
- Stage 2.7.1 must not add database fields, add Alembic migrations, create
  nodes, delete nodes, rebuild nodes, refresh node status, modify Xray config,
  configure relay, configure `dokodemo-door`, configure iptables forwarding,
  modify firewall rules, open ports, use 3x-ui, create subscription links, add
  traffic statistics, add automatic speed tests, or modify `sshd_config`.
- Stage 2.7.1 is frozen after real backup-file read-only viewing acceptance. Do
  not modify `list_xray_backups`, backup-file read-only viewing, manual restore
  instructions, metadata-only result shape, or the no-read/no-restore/no-delete
  safety boundary without explicit user approval.

## Stage 2.7.2.1 boundary

- Stage 2.7.2.1 may implement only Xray backup cleanup dry-run preview.
- Stage 2.7.2.1 may create only the `preview_xray_backup_cleanup` task through
  `POST /api/vps/{vps_id}/xray-backups/cleanup-preview`.
- `preview_xray_backup_cleanup` may only read `/usr/local/etc/xray/`
  `config.json*` file metadata and calculate candidate/retained files in memory.
- The dry-run policy must keep the latest 3 files per cleanable type. Current
  `config.json` and unknown file types must never be cleanup candidates.
- The only allowed remote commands are:
  `test -d /usr/local/etc/xray`,
  `find /usr/local/etc/xray -maxdepth 1 -type f -name 'config.json*' -printf ...`,
  `systemctl is-active xray`, and `ss -ltnH`.
- Stage 2.7.2.1 must continue using Redis temporary encrypted SSH credentials.
  RQ job arguments must not contain SSH Key or Passphrase.
- Stage 2.7.2.1 must not read full config content, run `cat` / `head` / `tail`
  against config files, return Reality privateKey, print config content to
  task logs, download backups, upload backups, restore config, delete backups,
  clean backups, modify remote files, or restart/stop/start Xray.
- Stage 2.7.2.1 must not execute `rm`, `mv`, `cp`, `tee`, or `sed`.
- Stage 2.7.2.1 must not add database fields, add Alembic migrations, create
  nodes, delete nodes, rebuild nodes, refresh node status, modify Xray config,
  configure relay, configure `dokodemo-door`, configure iptables forwarding,
  modify firewall rules, open ports, use 3x-ui, create subscription links, add
  traffic statistics, add automatic speed tests, or modify `sshd_config`.
- Stage 2.7.2.1 is frozen after real dry-run preview acceptance. Do not modify
  `preview_xray_backup_cleanup`, the keep-latest-3 dry-run rules,
  `delete_enabled=false`, the no-delete/no-remote-modification safety boundary,
  or the frontend cleanup preview flow without explicit user approval.

## Stage 2.7.2.2-a boundary

- Stage 2.7.2.2-a may implement only real deletion of a single `failed` dry-run
  cleanup candidate file.
- Stage 2.7.2.2-a may create only the `delete_xray_backup_candidate` task
  through `POST /api/vps/{vps_id}/xray-backups/delete-candidate`.
- The only deletable filename pattern is `^config\.json\.failed\.\d{14}$`.
- The Worker must reload Redis temporary SSH credentials, delete those
  credentials after reading, reconnect over SSH, rescan backup metadata,
  recalculate dry-run candidates, and confirm the target is still a `failed`
  candidate before deletion.
- RQ job arguments must not contain SSH Key or Passphrase.
- The delete operation must target only
  `/usr/local/etc/xray/<validated filename>`, preferably through Paramiko SFTP
  `remove()`.
- Stage 2.7.2.2-a must not delete `config.json`, `config.json.bak.*`,
  `config.json.disabled.*`, unknown files, retained files, directories, or more
  than one file.
- Stage 2.7.2.2-a must not add `cleanup_xray_backups`, batch cleanup, automatic
  cleanup, restore tasks, wildcard deletion, arbitrary paths, or path traversal.
- Stage 2.7.2.2-a must not read full config content, return Reality privateKey,
  print config content to task logs, download backups, upload backups, restore
  config, modify Xray config, restart/stop/start Xray, create nodes, delete
  nodes, rebuild nodes, refresh node status, configure relay, configure
  `dokodemo-door`, configure iptables forwarding, modify firewall rules, open
  ports, use 3x-ui, create subscription links, add traffic statistics, add
  automatic speed tests, modify `sshd_config`, add database fields, or add
  Alembic migrations.
- Stage 2.7.2.2-a is frozen after real failed-candidate deletion acceptance. Do
  not modify `delete_xray_backup_candidate`, the failed-only deletion boundary,
  filename validation rules, Paramiko SFTP fixed-path deletion, single-file
  delete flow, or the no-backup/no-disabled/no-batch/no-wildcard safety
  boundary without explicit user approval.

## Stage 3.1 boundary

- Stage 3.1 may implement only transit resource management.
- Stage 3.1 may add the `transit_resources` model/table, Alembic migration,
  local database APIs, and a frontend management panel.
- Stage 3.1 may support list, create, detail, edit, enable, and disable for
  resource metadata.
- Allowed resource types are `server`, `iepl`, `iplc`, and `other`.
- Allowed statuses are `active` and `disabled`.
- `deleted_at` may exist for future soft deletion, but Stage 3.1 must not add a
  hard-delete flow.
- Stage 3.1 must not connect to Hong Kong servers, IEPL / IPLC lines, or
  landing VPS hosts.
- Stage 3.1 must not upload, save, or process SSH keys, SSH passwords, provider
  backend accounts, provider backend passwords, or line secrets.
- Stage 3.1 must not create Worker jobs, trigger RQ tasks, use Redis temporary
  credentials, configure relay, install `gost` / `nginx` / `socat`, configure
  Xray `dokodemo-door`, modify Xray config, modify firewall rules, open ports,
  write iptables, call 3x-ui, generate relay client links, create topology
  previews, run real connectivity tests, collect traffic statistics, run speed
  tests, or affect the current active direct node.
- Frontend notes and forms must clearly warn users not to enter passwords,
  private keys, backend accounts, or line secrets in notes.
- Stage 3.1 is frozen after real transit-resource management acceptance and the
  `ssh key` notes validation fix. Do not modify the `transit_resources` model,
  APIs, input validation, sensitive-word validation, frontend resource
  management flow, or the no-remote/no-credential/no-relay safety boundary
  without explicit user approval.

## Stage 3.2 boundary

- Stage 3.2 may implement only frontend local transit topology and
  configuration preview.
- Stage 3.2 may reuse only existing read APIs such as
  `GET /api/transit-resources` and `GET /api/nodes`.
- Stage 3.2 may let the operator choose an active transit resource, choose an
  active node, enter a planned relay listen port, choose a preview-only
  forwarding method, and view topology/configuration preview text.
- Stage 3.2 preview text must clearly state `PREVIEW ONLY`, `NOT USABLE`,
  remote hosts were not connected, config was not written, and real transit
  configuration is incomplete.
- Stage 3.2 must not add `transit_routes`, `forwarding_rules`, database fields,
  Alembic migrations, backend APIs, Worker jobs, RQ tasks, task logs, SSH Key
  inputs, execute buttons, test-connection buttons, install buttons, real relay
  links, QR codes, or route persistence.
- Stage 3.2 must not connect to Hong Kong servers, IEPL / IPLC lines, or
  landing VPS hosts.
- Stage 3.2 must not upload or save SSH keys, configure relay, install
  `gost` / `nginx` / `socat`, configure Xray `dokodemo-door`, modify Xray
  config, modify firewall rules, open ports, write iptables, call 3x-ui, modify
  `nodes`, modify `vps_servers`, run real connectivity tests, collect traffic
  statistics, run speed tests, or affect the current active direct node.
- Stage 3.2 must not display full `share_link`, Reality privateKey, SSH Key,
  SSH password, or `notes` content in topology/configuration previews.
- Stage 3.2 is frozen after real topology-preview acceptance. Do not modify the
  transit topology preview flow, `PREVIEW ONLY` / `NOT USABLE` safety markers,
  frontend-only preview boundary, no-route-persistence boundary, or the
  no-remote/no-task/no-real-link safety boundary without explicit user approval.

## Stage 3.3.1 boundary

- Stage 3.3.1 may implement only the `read_transit_server` read-only check for
  ordinary public transit servers.
- Stage 3.3.1 may add only `POST /api/transit-resources/{id}/read-server` and
  the `read_transit_server` task type.
- The API may accept SSH Key / Passphrase only through `multipart/form-data` for
  Redis temporary encrypted credentials.
- RQ job arguments must contain only `task_id`, `transit_resource_id`, and
  `temp_credential_id`; they must never contain SSH Key or Passphrase.
- Worker must delete Redis temporary credentials immediately after reading.
- Stage 3.3.1 may run only read-only SSH commands with timeouts:
  `cat /etc/os-release`, `uname -m`, `whoami`,
  `test -d /run/systemd/system`, `command -v gost`,
  `command -v nginx`, `command -v socat`, `command -v xray`,
  `ss -ltnH`, `ufw status`, `iptables -S`, and
  `firewall-cmd --state`.
- Stage 3.3.1 may write only `tasks.result_data` and `task_logs`; it must not
  modify `transit_resources`, `nodes`, `vps_servers`, Xray config, firewall
  rules, iptables, or remote files.
- Stage 3.3.1 must not add `transit_routes`, `forwarding_rules`, database
  fields, Alembic migrations, install tasks, route creation tasks, real transit
  links, QR codes, or connectivity tests.
- Stage 3.3.1 must not install `gost` / `nginx` / `socat`, configure Xray
  `dokodemo-door`, configure relay, connect to landing VPS hosts, modify Xray,
  modify firewall rules, open ports, write iptables, call 3x-ui, collect traffic
  statistics, run speed tests, or affect the current active direct node.
- Stage 3.3.1 is frozen after real Hong Kong transit-server read-only
  acceptance. Do not modify `read_transit_server`, the read-only command list,
  Redis temporary credential handling, task result/log shape, or the
  no-install/no-relay/no-firewall/no-iptables/no-landing-VPS boundary without
  explicit user approval.
- Earlier Stage 3.3.1/3.3.2 notes recorded `20575` as the Hong Kong transit
  server SSH port. Stage 3.3.3-fix-a later confirmed that was a resource SSH
  port misconfiguration; the accepted SSH port for
  `6d67c275-8ac9-4775-9519-c89b50718157` is `22`.
- Future transit forwarding stages must not reuse the historical problem port
  `20575` as a relay listen port without a separate review and an explicit
  free-port decision.

## Stage 3.3.2 boundary

- Stage 3.3.2 may implement only the `install_gost` task type and
  `POST /api/transit-resources/{id}/install-gost`.
- Stage 3.3.2 may install only a fixed go-gost/gost binary and verify its
  version. It must not create relay rules, forwarding configs, or forwarding
  services.
- The API may accept SSH Key / Passphrase only through `multipart/form-data` for
  Redis temporary encrypted credentials.
- RQ job arguments must contain only `task_id`, `transit_resource_id`, and
  `temp_credential_id`; they must never contain SSH Key or Passphrase.
- Worker must delete Redis temporary credentials immediately after reading.
- The fixed gost version is `v3.2.6`; do not use `latest`.
- The fixed release URL is
  `https://github.com/go-gost/gost/releases/download/v3.2.6/gost_3.2.6_linux_amd64.tar.gz`.
- The fixed sha256 is
  `b39037b0380ea001fb3c0c28441c2e10bfc694f90682739a65b53e55dce5238b`.
- Stage 3.3.2 may install gost only to `/usr/local/bin/gost`.
- Stage 3.3.2 must not overwrite an existing gost binary. If `command -v gost`
  succeeds, read the version and return `already_installed=true`.
- Stage 3.3.2 must not add `transit_routes`, `forwarding_rules`, database
  fields, Alembic migrations, route creation APIs, route creation tasks, real
  transit links, QR codes, connectivity tests, traffic statistics, or speed
  tests.
- Stage 3.3.2 must not create gost forwarding systemd services, execute
  `systemctl start/restart/stop/enable gost-forward`, listen on new ports,
  connect to landing VPS hosts, modify landing VPS hosts, modify Xray config,
  install `nginx` / `socat` / `xray`, configure Xray `dokodemo-door`, modify
  firewall rules, open ports, write iptables, call 3x-ui, or affect the current
  active direct node.
- Stage 3.3.2 must not use `curl | bash`, package managers such as `apt` /
  `yum` / `dnf`, or `latest` release URLs.
- The accepted Hong Kong transit server now uses SSH port `22`. Earlier
  `20575` SSH-port notes were caused by a resource misconfiguration; future
  forwarding stages must not use `20575` as a relay listen port without
  separate review.
- Stage 3.3.2 is frozen after real Hong Kong transit-server gost install
  acceptance. Do not modify `install_gost`, the fixed gost version, fixed
  official download URL, SHA256 verification, `already_installed=true` behavior,
  or the no-forwarding/no-new-port/no-landing-VPS safety boundary without
  explicit user approval.
- Stage 3.3.2 only installs and verifies the gost binary. Real forwarding rule
  creation must be reviewed and developed separately in Stage 3.3.3.

## Stage 3.3.3 boundary

- Stage 3.3.3 may implement only one gost TCP transit route through
  `transit_routes`, `POST /api/transit-routes`, optional route list/detail read
  APIs, and the `create_transit_route` task type.
- Stage 3.3.3 may connect only to the Hong Kong transit server selected by an
  active `server` transit resource with SSH metadata. It must not connect to
  landing VPS hosts.
- SSH Key / Passphrase may be accepted only through `multipart/form-data` and
  Redis temporary encrypted credentials. RQ job arguments must not contain SSH
  Key or Passphrase.
- Stage 3.3.3 may use only `/usr/local/bin/gost` and `gost`. It must reject
  non-gost forwarding methods.
- Stage 3.3.3 must reject listen port `20575`, because it is a historical
  problem port from earlier transit-resource SSH misconfiguration unless a
  later review explicitly reclassifies it as safe and free.
- Stage 3.3.3 must reject already-listening ports based on `ss -ltnH`.
- Stage 3.3.3 may write only one generated service file under
  `/etc/systemd/system/liveline-transit-{route_id}.service`, then run
  `systemctl daemon-reload`, `systemctl enable`, `systemctl start`,
  `systemctl is-active`, and `ss -ltnH` for verification.
- Stage 3.3.3 must generate the transit `vless://` link by replacing only
  address and port while preserving the original node Reality parameters. It
  must not modify the original node or `node.share_link`.
- Stage 3.3.3 must not delete transit routes, create batch routes, create
  multiple-node transit, create QR codes, open firewalls, write iptables, call
  3x-ui, install `nginx` / `socat` / `xray`, configure Xray `dokodemo-door`,
  modify landing VPS hosts, restart landing Xray, modify `vps_servers`, perform
  IEPL real acceptance, collect traffic statistics, run speed tests, or create
  load balancing.
- If remote service creation succeeds but DB save fails, Stage 3.3.3 must try
  to stop, disable, remove the service file, and daemon-reload. If rollback
  fails, task result data must set `manual_cleanup_required=true`.

## Stage 3.3.3-fix-a boundary

- Stage 3.3.3-fix-a may implement only `install_socat` /
  `POST /api/transit-resources/{id}/install-socat`.
- The task may install or check socat only for `resource_type=server`,
  `status=active`, `has_ssh=true` transit resources with SSH metadata.
- SSH Key / Passphrase may be accepted only through `multipart/form-data` and
  Redis temporary encrypted credentials. RQ job arguments must contain only
  `task_id`, `transit_resource_id`, and `temp_credential_id`.
- Worker must delete Redis temporary credentials immediately after reading.
- Stage 3.3.3-fix-a may run only these preflight/read commands:
  `cat /etc/os-release`, `uname -m`, `whoami`,
  `test -d /run/systemd/system`, `command -v socat`,
  `command -v apt-get`, `ss -ltnH`, and `socat -V`.
- On Debian / Ubuntu only, the only allowed remote write operations are
  `apt-get update` and `apt-get install -y socat`.
- If `command -v socat` succeeds, the task must not reinstall socat and must
  return `already_installed=true` after reading `socat -V`.
- Stage 3.3.3-fix-a must not create socat forwarding rules, create socat
  systemd forwarding services, listen on new ports, modify existing gost
  routes, delete gost routes, modify `transit_routes`, generate new transit
  links, generate QR codes, connect to landing VPS hosts, modify landing VPS
  Xray, rebuild Reality nodes, modify original nodes, modify `node.share_link`,
  modify firewall rules, open ports, write iptables, call 3x-ui, add database
  fields, add Alembic migrations, add `forwarding_rules`, collect traffic
  statistics, run speed tests, or add load balancing.
- Stage 3.3.3-fix-a is accepted after real `install_socat` validation on
  resource `6d67c275-8ac9-4775-9519-c89b50718157` with SSH
  `163.223.216.108:22` as `root`. The accepted task is
  `12ab7383-58c8-4eaa-9f38-68f313d59c59`, with socat installed at
  `/usr/bin/socat`.
- After Stage 3.3.3-fix-a, automatic socat forwarding rule creation remains
  forbidden. Stage 3.3.3-fix-b must be separately reviewed before creating any
  socat service, listening port, forwarding rule, or transit link.
- SSH Key / Passphrase must continue to travel only through Redis temporary
  encrypted credentials. They must never be stored in the database, written to
  `task_logs`, backend logs, worker logs, or RQ job arguments.
- Duplicate Hong Kong transit resource records currently exist. Do not delete
  or merge them without explicit user approval; future stages should review
  cleanup/disable/merge options to avoid selecting the wrong resource.
- Stage 3.3.3-fix-b must be separately reviewed before creating a socat 2083
  transparent TCP forwarding test.

## Stage 3.3.4-d boundary

- Stage 3.3.4-d is accepted after real controlled restart validation for the
  socat test route `hk-socat-test-18443`.
- The accepted route id is `97fe351d-d5e6-4684-a37f-4a00b90b4e1e`.
- The accepted service is
  `liveline-socat-97fe351dd5e64684a37f4a00b90b4e1e.service`.
- `restart-socat` may only operate on the socat test route with
  `forwarding_method=socat` and `listen_port=18443`.
- `restart-socat` must not operate on the gost 8443 route. The gost route
  `hk-gost-test-8443` is retained and must not be replaced or modified by
  Stage 3.3.4-d.
- The only allowed restart-stage remote operations are the backend-generated
  whitelist commands for restarting the accepted socat service and then reading
  service status, listen state, and target connectivity.
- Do not accept arbitrary shell commands from the frontend.
- Do not execute `kill`, `pkill`, `iptables`, `nft`, firewall modification
  commands, route deletion commands, route creation commands, or gost service
  modification commands in Stage 3.3.4-d.
- Stage 3.3.4-d must not modify `node.share_link`, create or delete routes,
  modify database schema, modify firewall rules, open ports, or call 3x-ui.
- SSH Key / Passphrase must continue to travel only through Redis temporary
  encrypted credentials. They must never be stored in the database, written to
  `task_logs`, backend logs, worker logs, result data, or RQ job arguments.

## Stage 3.3.4-e boundary

- Stage 3.3.4-e is accepted after client connectivity validation for
  `hk-socat-test-18443`.
- The accepted test path is client to `163.223.216.108:18443`, through socat,
  to `74.211.97.116:443`.
- The accepted client procedure copied the existing direct Reality node and
  changed only server and port. UUID, flow, Reality parameters, SNI, public key,
  shortId, fingerprint, spiderX, and related Reality parameters stayed
  unchanged.
- `socat` 18443 is verified usable, but it remains a test route.
- Stage 3.3.4-e is not a formal cutover.
- The gost 8443 route must remain retained until a separate cutover stage is
  explicitly planned and approved.
- Before cutover, do not modify gost 8443, do not modify
  `transit_routes.active`, do not modify `node.share_link`, do not delete the
  gost route, and do not make socat 18443 the formal route implicitly.

## Cutover Plan A boundary

- Cutover Plan A is accepted as a frontend-only low-risk display enhancement.
- Plan A may only derive and copy a `socat` 18443 test link in the frontend.
- The derived link may change only server to `163.223.216.108` and port to
  `18443`; existing Reality parameters must remain unchanged.
- Plan A must not write `node.share_link`.
- Plan A must not modify `transit_routes` or `transit_routes.active`.
- Plan A must not delete the gost route.
- Plan A must not directly make `socat` 18443 the formal route.
- Plan A must not trigger Worker/RQ tasks, connect to servers, execute remote
  commands, or require SSH Key / Passphrase.
- Plan B and Plan C require separate design review and explicit user approval
  before any code, database, route, or remote changes.

## Fixed technology stack

- Frontend: Next.js + React + TypeScript.
- Backend: FastAPI + Python.
- Database: PostgreSQL.
- Queue: Redis + RQ.
- SSH library for later stages: paramiko.
- Deployment: Docker Compose.

Do not replace the fixed stack without explicit user approval and a document
update.
