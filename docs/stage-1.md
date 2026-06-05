# Stage 1 Notes

Stage 1 implements only the read-empty-VPS flow.

Implemented:

- `POST /api/nodes/read` creates a `read_node` task.
- `GET /api/tasks/{id}` and `GET /api/tasks/{id}/logs` expose task state and logs.
- `POST /api/vps/{id}/confirm-host-key` updates a confirmed SSH Host Key fingerprint only.
- SSH Key and Passphrase are encrypted into Redis with TTL and deleted by the Worker after reading.
- RQ job arguments are limited to `task_id`, `vps_id`, and `temp_credential_id`.
- Worker uses paramiko and executes only read-only commands with timeout.
- Worker records system version, root status, Xray binary presence, standard config path presence, and Xray service state.
- Blank VPS or missing Xray returns `未发现节点，可以新建`.
- `tasks.result_data` stores the sanitized read result.
- Frontend shows the read form, task status, logs, error code, and result.

Read-only SSH commands:

- `cat /etc/os-release`
- `whoami`
- `command -v xray`
- `test -f /usr/local/etc/xray/config.json`
- `systemctl is-active xray`

Not implemented:

- Node creation, editing, deletion, or checking.
- Xray installation.
- Xray config writes.
- VPS file writes, deletes, directory creation, systemd changes, firewall changes, `sudo`, or `apt`.
- Node link or QR code generation.
- Node import/takeover.
- 3x-ui installation or API calls.
