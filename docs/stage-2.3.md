# Stage 2.3 Notes

Stage 2.3 implements only the `create_direct_node` task.

Implemented:

- `POST /api/nodes/create-direct` creates a direct VLESS Reality node task.
- The VPS must already be in `xray_installed_pending_config` or `xray_installed`.
- The VPS must not already have an active node.
- Redis temporary SSH credentials are encrypted with TTL and deleted by the Worker.
- The Worker writes `/usr/local/etc/xray/config.json`, runs `xray run -test`,
  restarts `xray.service`, verifies service active state and listening port,
  then writes one active `nodes` row.
- The result includes a `vless://` share link for copying.

Remote commands:

- `command -v xray`
- `xray version`
- `systemctl list-unit-files xray.service --no-pager --no-legend`
- `ss -ltnH`
- `xray x25519`
- `xray run -test -config /usr/local/etc/xray/config.json`
- `systemctl restart xray`
- `systemctl is-active xray`
- `ss -ltnH`

Not implemented:

- QR code generation.
- Node deletion or editing.
- Relay configuration.
- Firewall modification or port opening.
- SSH daemon configuration changes.
- 3x-ui installation or API calls.

Security notes:

- SSH Key and Passphrase are never passed in RQ job arguments.
- Reality privateKey is used only to render remote Xray config.
- Reality privateKey is not returned in `result_data`, not saved in the database,
  and not printed to `task_logs`.
- Full `config.json` is not printed to task logs.

## Stage 2.3 Freeze Conclusion

Stage 2.3 is frozen after real VPS acceptance.

Acceptance result:

- `create_direct_node` task completed with `status=success`.
- `/usr/local/etc/xray/config.json` was written successfully.
- `xray run -test -config /usr/local/etc/xray/config.json` passed.
- `systemctl is-active xray` returned `active`.
- `ss -ltnH` confirmed port `443` was listening.
- The `nodes` table contains one new `active` node.
- A `vless://` share link was generated.
- The client verified that the `vless://` link works.
- Redis `temp_credential:*` was cleared after the task.
- Reality privateKey did not enter `result_data`, `task_logs`, or the database.

Final Stage 2.3 boundary:

- Allowed: create one direct VLESS Reality node, write `config.json`, run
  `xray run -test`, restart Xray, verify port listening, write the `nodes` table,
  and generate a `vless://` share link.
- Forbidden: relay, `dokodemo-door`, iptables forwarding, firewall changes,
  3x-ui, QR codes, node deletion, multi-node management, traffic statistics, and
  subscription links.

Compatibility fixes recorded for the frozen Stage 2.3 flow:

- `xray x25519` output parsing is compatible with the Password/PublicKey output
  style observed during acceptance.
- Xray config validation uses `xray run -test`, compatible with Xray 26.3.27.
