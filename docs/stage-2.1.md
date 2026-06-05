# Stage 2.1 Notes

Stage 2.1 implements only the `prepare_node` installation pre-check task.

Implemented:

- `POST /api/nodes/prepare` creates a `prepare_node` task for an existing VPS record.
- The task reuses encrypted Redis temporary credentials with TTL.
- RQ job arguments are limited to `task_id`, `vps_id`, and `temp_credential_id`.
- The Worker uses paramiko and executes only read-only commands with timeout.
- Results are saved to `tasks.result_data` and logs are saved to `task_logs`.
- No `nodes` records are created.
- The frontend shows an install pre-check button after a successful VPS read.
- Common port occupancy is recorded as a warning for Stage 2.2, not as a blocker
  for installing Xray itself.

Read-only SSH commands:

- `cat /etc/os-release`
- `uname -m`
- `whoami`
- `test -d /run/systemd/system`
- `command -v xray`
- `systemctl list-unit-files xray.service --no-pager --no-legend`
- `systemctl is-active xray`
- `ss -ltnH`
- `ufw status`
- `iptables -S`
- `firewall-cmd --state`
- `command -v curl`
- `command -v wget`
- `command -v unzip`
- `command -v tar`

Not implemented:

- Xray installation.
- Xray configuration writes.
- VPS file writes, deletes, or directory creation.
- Port opening or firewall changes.
- `sudo` or `apt`.
- Node creation.
- Node link or QR code generation.
- Node import, edit, or delete.
- 3x-ui installation or API calls.
