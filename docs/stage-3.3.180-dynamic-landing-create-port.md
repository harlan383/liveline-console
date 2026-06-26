# Stage 3.3.180 Dynamic Landing Create Port

## Goal

Stage 3.3.180 generalizes direct Reality node creation so the operator can choose the landing node TCP listen port instead of being locked to `27939/TCP`.

The default remains `27939`, but create requests may use an allowed custom port in the `10000-30000` range.

## Port Rules

- Allowed range: `10000-30000`.
- Default port: `27939`.
- Reserved ports are rejected, including SSH, HTTP/HTTPS, LiveLine service ports, database/cache ports, historical transit ports, and the lower-bound sentinel.
- The same landing VPS cannot create a non-deleted node on a port already used by another non-deleted node.
- The same landing VPS cannot create a node on a port already used as the target port of an active or creating transit route.

## Backend Changes

- `LandingNodePlanRequest.listen_port` and `LandingNodeCreateRequest.approved_port` now share the same dynamic port validation.
- Landing node create commands pass the requested port into `landing_node_create`.
- Successful Worker results are accepted only when the returned `listen_port` matches the command payload.
- New `nodes.xray_port` records use the actual created port.
- `node.share_link` is still written only after Worker success and backend result ingest.

## Worker Changes

- Worker version: `0.1.33-stage-3.3.180-dynamic-landing-create-port`.
- Bundled Linux amd64 binary sha256: `385ffcf6e8da9bc0a5a613286f9831be7165d5c0b1f6d053cc9f64598928d040`.
- `landing_node_create` accepts allowed custom ports and rejects reserved or out-of-range ports.
- The Worker can append a new VLESS Reality inbound to the LiveLine-managed Xray config.
- Existing LiveLine-managed inbounds are preserved.
- Duplicate inbound ports are rejected.
- Invalid existing managed Xray JSON is rejected.
- On failure after appending to an existing config, rollback restores the previous config instead of deleting the whole managed Xray config.

## Frontend Changes

- The direct node create modal exposes an editable listen port input.
- The node name follows the selected port when the default name is still in use.
- The firewall confirmation text references the selected port.
- The create flow still runs preflight, create command, polling, refresh, copy link, QR, and failure handling.

## Safety Boundary

This stage does not:

- Create a real landing node.
- Create a real transit route.
- Restore or add a listener on any production server.
- SSH or run remote commands.
- Modify cloud security groups, cloud firewalls, or server firewalls.
- Cut over traffic.
- Write `transit_routes.share_link`.
- Modify an existing `nodes.share_link`.
- Output full client links in docs, logs, PR text, or chat.

## Validation

Validation is recorded in the PR for this stage:

- `git diff --check`
- `git diff --cached --check`
- `python3 -m compileall backend/app backend/tests`
- Worker Go tests and builds
- Linux amd64 Worker binary version marker check
- Frontend production build
