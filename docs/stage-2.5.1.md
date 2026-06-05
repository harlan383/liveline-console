# Stage 2.5.1 Notes

Stage 2.5.1 implements only node soft deletion / disablement.

Implemented:

- `POST /api/nodes/{node_id}/delete` creates a `delete_node` task.
- The API requires an admin session, CSRF, `multipart/form-data`, a fresh SSH
  Key upload or paste, `confirm=true`, and `confirm_node_name`.
- SSH Key and Passphrase are encrypted into Redis temporary credentials and
  deleted by the Worker after reading.
- RQ job arguments contain only non-sensitive identifiers and confirmation data.
- The Worker backs up `/usr/local/etc/xray/config.json`, stops `xray.service`,
  moves the active config to a disabled path, verifies service inactive state,
  verifies the node port is no longer listening, then soft-deletes the node.
- The database keeps the historical `nodes` record and does not hard delete it.

Remote commands:

- `command -v xray`
- `xray version`
- `test -e /usr/local/etc/xray/config.json`
- `xray run -test -config /usr/local/etc/xray/config.json`
- `systemctl is-active xray`
- `ss -ltnH`
- `cp /usr/local/etc/xray/config.json /usr/local/etc/xray/config.json.bak.<timestamp>`
- `systemctl stop xray`
- `mv /usr/local/etc/xray/config.json /usr/local/etc/xray/config.json.disabled.<timestamp>`
- rollback-only `mv` / `cp` / `systemctl restart xray` when a post-stop failure
  requires restoring the previous service state.

Not implemented:

- Node rebuild.
- New node creation.
- New UUID generation.
- New Reality key generation.
- New share-link generation.
- QR code generation.
- IEPL / IPLC relay.
- `dokodemo-door`.
- iptables forwarding.
- Firewall modification or port opening.
- 3x-ui installation or API calls.
- Subscription links.
- Traffic statistics.
- Automatic speed tests.
- SSH daemon configuration changes.
- Hard deletion of `nodes` records.

Security notes:

- SSH Key and Passphrase are never passed in RQ job arguments.
- Redis temporary credentials are deleted by the Worker after reading.
- Task logs must not print SSH private keys, passphrases, cookies, database
  connection strings, Reality privateKey, or full `config.json`.
- `result_data` does not include Reality privateKey.
- `result_data` does not return the full old share link.
- The database does not add or store any Reality privateKey field.

## Stage 2.5.1 Freeze Conclusion

Stage 2.5.1 is frozen after real node soft-deletion acceptance.

Acceptance basis:

- `delete_node` task completed with `status=success`.
- `classification=delete_node`.
- `deleted=true`.
- `failures=[]`.
- Task logs contain the full expected flow:
  - `queued`
  - `load_credentials`
  - `delete_node`
  - `preflight`
  - `backup_config`
  - `stop_service`
  - `move_config`
  - `verify_stopped`
  - `save_result`
  - `complete`
- `/usr/local/etc/xray/config.json` no longer exists on the VPS.
- A `config.json.bak.<timestamp>` backup exists on the VPS.
- A `config.json.disabled.<timestamp>` disabled config exists on the VPS.
- `systemctl is-active xray` returns inactive.
- `ss -ltnH` no longer shows port `443` listening.
- `command -v xray` and `xray version` still work.
- The original `nodes` record still exists and was not hard deleted.
- `nodes.status=deleted`.
- `nodes.deleted_at` is set.
- `GET /api/nodes` does not show deleted nodes by default.
- `vps_servers.status=xray_installed_pending_config`.
- `vps_servers.xray_config_path=NULL`.
- The old `vless://` link is invalid.
- Redis `temp_credential:*` entries were cleared.
- `npm audit` reported `found 0 vulnerabilities`.
- Task logs do not expose SSH private keys, passphrases, cookies, database
  connection strings, or Reality privateKey.
- `result_data` does not expose Reality privateKey or return the full old share
  link.
- No 3x-ui, relay, `dokodemo-door`, firewall modification, port opening,
  iptables forwarding, QR code generation, new node creation, node rebuild, new
  UUID, new Reality key, new share link, or `sshd_config` modification occurred.

Final allowed scope:

- Soft-delete a node.
- Back up `config.json`.
- Stop `xray.service`.
- Move the active `config.json` to a disabled path.
- Verify `xray.service` is not active.
- Verify the node port is no longer listening.
- Update `nodes.status` to `deleted`.
- Write `nodes.deleted_at`.
- Update `vps_servers.status` to `xray_installed_pending_config`.
- Write task `result_data` and `task_logs`.
- Keep the historical `nodes` record without hard deletion.

Final prohibited scope:

- Do not rebuild nodes.
- Do not create new nodes.
- Do not generate new UUIDs.
- Do not generate new Reality keys.
- Do not generate new share links.
- Do not generate QR codes.
- Do not configure IEPL / IPLC relay.
- Do not configure `dokodemo-door`.
- Do not configure iptables forwarding.
- Do not modify firewall rules.
- Do not open ports.
- Do not call 3x-ui.
- Do not create subscription links.
- Do not add traffic statistics.
- Do not add automatic speed tests.
- Do not modify `sshd_config`.
- Do not hard-delete `nodes` records.
