# Stage 2.4 Notes

Stage 2.4 implements only basic node management.

Implemented:

- `GET /api/nodes` returns the node list.
- `GET /api/nodes/{node_id}` returns node details with VPS information and
  `share_link`.
- `POST /api/nodes/{node_id}/refresh` creates a `refresh_node` task.
- `POST /api/nodes/{node_id}/restart` creates a `restart_xray` task.
- The frontend shows node list, node details, share-link copy, refresh status,
  restart Xray, task progress, and task logs.

Refresh checks:

- `command -v xray`
- `xray version`
- `test -e /usr/local/etc/xray/config.json`
- `xray run -test -config /usr/local/etc/xray/config.json`
- `systemctl is-active xray`
- `ss -ltnH`

Restart steps:

- `xray run -test -config /usr/local/etc/xray/config.json`
- `systemctl restart xray`
- `systemctl is-active xray`
- `ss -ltnH`

Not implemented:

- QR code generation.
- Node deletion.
- Relay configuration.
- Firewall modification or port opening.
- iptables forwarding.
- SSH daemon configuration changes.
- 3x-ui installation or API calls.

Security notes:

- SSH Key and Passphrase are never passed in RQ job arguments.
- Redis temporary credentials are deleted by the Worker after reading.
- Task logs must not print full `config.json`.
- `result_data` does not include Reality privateKey.
- The database does not add any privateKey field.

## Stage 2.4 Freeze Conclusion

Stage 2.4 is frozen after real node-management acceptance.

Acceptance basis:

- `GET /api/nodes` returns the existing active node.
- `GET /api/nodes/{node_id}` returns node details including node name,
  `protocol=vless`, port `443`, `status=active`, share link, VPS information,
  Reality public key, short ID, server name, and flow.
- The frontend displays node list, node details, and the share-link copy area.
- `refresh_node` completed successfully with `config_exists=true`,
  `config_test_passed=true`, `service_active=true`, `listening=true`,
  `node.status=active`, and no failures.
- `restart_xray` completed successfully with `restarted=true`,
  `config_test_passed=true`, `service_active=true`, `listening=true`,
  `node.status=active`, and no failures.
- Direct VPS verification passed for:
  - `xray run -test -config /usr/local/etc/xray/config.json`
  - `systemctl is-active xray`
  - `ss -ltnH | grep ':443'`
- Redis `temp_credential:*` entries were cleared.
- `npm audit` reported `found 0 vulnerabilities`.
- Task logs do not expose SSH private keys, passphrases, cookies, or database
  connection strings.
- Task logs, `result_data`, and database records do not expose the Reality
  private key.
- No 3x-ui, relay, firewall modification, port opening, iptables forwarding, QR
  code generation, node deletion, new node creation, or `sshd_config`
  modification occurred.

Final allowed scope:

- View node list.
- View node details.
- Display and copy `vless://` share links.
- Refresh node status.
- Check Xray binary.
- Check whether `config.json` exists.
- Run `xray run -test`.
- Check whether `xray.service` is active.
- Check whether the node port is listening.
- Restart `xray.service`.
- Update `nodes.status`.
- Write task `result_data` and `task_logs`.

Final prohibited scope:

- Do not create new nodes.
- Do not delete nodes.
- Do not rebuild nodes.
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
