# Stage 2.5.2 Notes

Stage 2.5.2 implements only a clear entry point and safety protection for
recreating a direct node after soft deletion.

Stage 2.5.2 is "recreate a new direct node", not rebuilding or overwriting an
old node. It reuses the frozen `create_direct_node` flow from Stage 2.3 and
creates a new active `nodes` record on the same VPS.

Implemented:

- Reuse `POST /api/nodes/create-direct`.
- Reuse the `create_direct_node` task type.
- Reuse Redis temporary SSH credentials.
- Reuse Reality key generation, config writing, `xray run -test`,
  `xray.service` restart, port-listening verification, `nodes` insert, and
  `vless://` share-link generation.
- Add frontend wording and flow for "重新创建直连节点" after a successful
  Stage 2.5.1 soft deletion.
- Add a remote pre-write guard: if `/usr/local/etc/xray/config.json` already
  exists, the Worker refuses to continue and does not overwrite it.

Remote safety checks before writing config:

- `command -v xray`
- `xray version`
- `systemctl list-unit-files xray.service --no-pager --no-legend`
- `test -e /usr/local/etc/xray/config.json`
- `ss -ltnH`

If the standard config already exists, the task fails with
`XRAY_CONFIG_ALREADY_EXISTS`, does not generate a new Reality key, does not write
config, does not restart Xray, and does not write a new `nodes` row.

Not implemented:

- No `rebuild_node` task.
- No `rebuild_node` API.
- No database field additions.
- No Alembic migration.
- No changes to old deleted nodes.
- No hard deletion of historical nodes.
- No deletion of old `config.json.bak.<timestamp>` or
  `config.json.disabled.<timestamp>` files.
- No old-link restoration.
- No QR code generation.
- No IEPL / IPLC relay.
- No `dokodemo-door`.
- No iptables forwarding.
- No firewall modification or port opening.
- No 3x-ui installation or API calls.
- No subscription links.
- No traffic statistics.
- No automatic speed tests.
- No SSH daemon configuration changes.

Expected state transition:

- Before: old node `status=deleted`, VPS `status=xray_installed_pending_config`,
  `xray_config_path=NULL`, no active node.
- Success: new node `status=active`, VPS `status=configured`,
  `xray_config_path=/usr/local/etc/xray/config.json`.
- Failure: no new active node is created; old deleted node remains unchanged.

Security notes:

- SSH Key and Passphrase are never passed in RQ job arguments.
- Redis temporary credentials are deleted by the Worker after reading.
- Reality privateKey is not returned in `result_data`, not written to
  `task_logs`, and not saved in the database.
- Full `config.json` is not printed to task logs.
- A new share link may be returned for the new node.
- The old deleted node share link is not returned by the recreate flow.

## Stage 2.5.2 Freeze Conclusion

Stage 2.5.2 is frozen after real recreate acceptance. The stage successfully
recreated a new direct VLESS Reality node on the same VPS after Stage 2.5.1 soft
deletion, without adding `rebuild_node`, a rebuild API, database fields, or an
Alembic migration.

Acceptance basis:

- Pre-checks passed: Docker Compose services were healthy, `/api/health` was
  all ok, Redis `temp_credential:*` count was 0, the old node was `deleted`,
  `vps_servers.status` was `xray_installed_pending_config`, `xray.service` was
  inactive, port 443 was not listening, standard `config.json` was absent, old
  backup/disabled config files were retained, and `npm audit` reported 0
  vulnerabilities.
- Recreate task `9f72a857-5069-4416-bb32-f142e2523989` finished with
  `status=success`, `classification=create_direct_node`, `created=true`, and
  `failures=[]`.
- New node `c4c00cfd-569d-4081-abf7-bb6cc8106fcd` was created as
  `direct-reality-recreated`, `protocol=vless`, `port=443`,
  `flow=xtls-rprx-vision`, `reality_server_name=www.microsoft.com`,
  `reality_dest=www.microsoft.com:443`, and a new `vless://` share link was
  generated.
- Old and new nodes are isolated: the old `direct-reality-test` node remains
  `deleted`, the new node is `active`, and the new UUID, Reality public key, and
  shortId differ from the old values.
- VPS validation passed: `command -v xray`, `xray version`,
  `/usr/local/etc/xray/config.json`, `xray run -test`, `systemctl is-active
  xray`, and port 443 listening were all verified. Old `.bak` and `.disabled`
  files remained in place.
- Database validation passed: the old node was not hard-deleted, the new node is
  the only active node returned by `GET /api/nodes`, and `vps_servers.status`
  is `configured`.
- Overwrite protection passed: `create_direct_node` checks
  `/usr/local/etc/xray/config.json` before writing and raises
  `XRAY_CONFIG_ALREADY_EXISTS` if it already exists, without silently
  overwriting remote config.
- Safety checks passed: Redis temporary credentials were cleared, logs and
  results did not expose SSH private keys, Passphrase, Cookie, database
  connection strings, Reality privateKey, full `config.json`, or the old share
  link.

Final allowed boundary:

- Reuse `POST /api/nodes/create-direct`.
- Reuse the `create_direct_node` task type.
- Recreate a direct node only when the VPS is installed and pending config with
  no active node.
- Generate a new UUID, Reality key, shortId, and `vless://` share link.
- Write a new `/usr/local/etc/xray/config.json`.
- Run `xray run -test`, restart `xray.service`, and verify port 443 listening.
- Insert a new active `nodes` record.
- Keep old deleted node history and old backup/disabled config files.
- Refuse to overwrite if standard `config.json` already exists.

Final prohibited boundary:

- No `rebuild_node` task or rebuild API.
- No database field additions or Alembic migration.
- No overwrite of old deleted nodes.
- No hard deletion of node history.
- No deletion of old `.bak` or `.disabled` config files.
- No old-link restoration.
- No QR codes.
- No IEPL / IPLC relay.
- No `dokodemo-door`.
- No iptables forwarding.
- No firewall modification or port opening.
- No 3x-ui.
- No subscription links.
- No traffic statistics.
- No automatic speed tests.
- No `sshd_config` changes.
