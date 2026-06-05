# Stage 2.2 Notes

Stage 2.2 implements only the `install_xray` task.

Implemented:

- `POST /api/nodes/install-xray` creates an `install_xray` task for an existing VPS.
- The latest successful `prepare_node` result is required before installation.
- Redis temporary SSH credentials are encrypted with TTL and deleted by the Worker.
- RQ job arguments are limited to `task_id`, `vps_id`, and `temp_credential_id`.
- The Worker installs Xray with the official XTLS install command.
- If Xray is already installed, the Worker skips the install script and verifies
  the existing installation.
- Missing `/usr/local/etc/xray/config.json` and inactive `xray.service` are
  warnings because Stage 2.2 does not create business node configuration.
- Results are saved to `tasks.result_data` and logs are saved to `task_logs`.
- No `nodes` records are created.

Remote commands:

- Preflight checks:
  - `cat /etc/os-release`
  - `whoami`
  - `test -d /run/systemd/system`
  - `command -v xray`
  - `systemctl list-unit-files xray.service --no-pager --no-legend`
  - `test -e /usr/local/etc/xray/config.json`
- Installation:
  - `bash -c "$(curl -L https://github.com/XTLS/Xray-install/raw/main/install-release.sh)" @ install`
  - `systemctl enable xray`
  - `systemctl start xray`
- Verification:
  - `command -v xray`
  - `xray version`
  - `systemctl list-unit-files xray.service --no-pager --no-legend`
  - `systemctl is-enabled xray`
  - `systemctl is-active xray`
  - `systemctl status xray --no-pager`
  - `test -d /usr/local/etc/xray`
  - `test -f /usr/local/etc/xray/config.json`

Not implemented:

- VLESS / VMess / Reality node creation.
- Business node configuration writes.
- Node link or QR code generation.
- `nodes` table writes.
- Relay configuration.
- Firewall modification or port opening.
- SSH daemon configuration changes.
- Existing Xray configuration overwrite.
- 3x-ui installation or API calls.
