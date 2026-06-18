# Stage 3.3.72a Legacy SSH/RQ Flow Removal

## Goal

Stage 3.3.72a removes the old legacy flows that accepted SSH credentials and
queued RQ jobs for node, transit server, and transit route operations. The
active remote-control model is now the authenticated `liveline-worker` command
channel.

This stage is a code cleanup and safety boundary stage. It does not deploy the
public console, upgrade any Worker, create a transit route, bind a listener,
install or start `socat` / `gost`, modify firewall rules, modify Xray, read or
modify `nodes.share_link`, export full client links, or perform cutover.

## Removed Active Legacy Paths

Backend active routes removed:

- Node SSH/RQ actions: `read`, `prepare`, `install-xray`, `create-direct`,
  `refresh`, `restart`, and `delete`.
- Transit resource SSH/RQ actions: `read-server`, `install-gost`, and
  `install-socat`.
- Transit route SSH/RQ actions: legacy route create, route diagnose, and
  `restart-socat`.
- VPS SSH/RQ actions: SSH create/recheck, host-key confirm, and Xray backup
  SSH task endpoints.

Backend implementation removed:

- Redis temporary SSH credential service used only by the legacy SSH/RQ flow.
- Old `backend/app/worker/ssh_*.py` modules.
- Old RQ job implementations for SSH-based node, backup, transit resource, and
  transit route operations.

Frontend legacy components removed:

- Old node panel with direct SSH node actions.
- Old read VPS panel.
- Old standalone transit resource SSH install/read panel.

## Preserved Worker Model

The following Worker-oriented capabilities remain active:

- Worker registration, heartbeat, command polling, result reporting, and fail
  reporting.
- Worker token/bootstrap APIs.
- `POST /api/transit-resources/worker-bootstrap`.
- `POST /api/transit-resources/{resource_id}/worker-bootstrap/regenerate`.
- `transit_readonly_preflight` Worker command.
- `transit_route_create` Worker dry-run command path.
- `POST /api/transit-routes/readonly-preflight-plan`.
- `POST /api/transit-routes/readonly-preflight-command`.
- `POST /api/transit-routes/worker-create-plan`.
- Node list/detail APIs with default redaction.
- Explicit node share-link export with confirmation.
- Transit resource list/detail/edit and transit route list/detail.
- Existing Linux amd64 Worker binary packaging.

## Data Boundary

This stage does not drop tables, delete records, add migrations, or hard-delete
historical data. Existing historical `tasks`, `task_logs`, `transit_routes`,
`transit_resources`, `vps_servers`, and `nodes` records remain in place.

`nodes.share_link` is not read or modified by this stage. Full client links are
not generated, displayed, logged, or written to documentation.

## Safety Boundary

- No SSH or remote command execution.
- No public console deployment.
- No Worker upgrade or remote Worker restart.
- No Worker command is triggered by this cleanup.
- No transit route is created.
- No listener is bound.
- No `socat` / `gost` install, start, stop, or restart.
- No firewall, cloud security group, or cloud firewall change.
- No Xray modification.
- No `nodes.share_link` read or write.
- No full client link export.
- No cutover.

## Validation Checklist

- `git diff --check`
- `git diff --cached --check`
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app`
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/tests`
- Go tests/build from the `worker/` module.
- Frontend production build.
- Grep checks confirm active code no longer contains old SSH credential fields,
  temporary credential helpers, legacy RQ job names, or old SSH/RQ endpoint
  strings.

## Conclusion

Stage 3.3.72a completes the active-code removal of the legacy SSH/RQ operation
surface. Future remote work must use Worker bootstrap, Worker command polling,
structured Worker results, and explicit approval stages.
