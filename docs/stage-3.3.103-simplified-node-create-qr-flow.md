# Stage 3.3.103 Simplified Node Create QR Flow

## Stage Goal

Stage 3.3.103 simplifies the direct VLESS Reality node creation experience for daily self-use.

The previous create modal exposed too much Stage 3.3.37 approval text, port review detail, and formal protection checklist. This stage keeps the backend safety boundary intact while making the operator flow shorter:

1. Fill in the node name, landing server, protected port, and Reality SNI / dest.
2. Click create.
3. The frontend creates a readonly landing preflight command and waits for completion.
4. The frontend submits the existing protected landing node create command only after the plan is ready.
5. After successful remote creation and database refresh, the UI offers link copy and QR entry points.

No production node was created during this code stage.

## UI Simplification

The direct node create modal now shows the daily fields first:

- Node name.
- Landing server.
- Current protected TCP port: `27939/TCP`.
- A short explicit confirmation that `27939/TCP` is allowed in the cloud security group, cloud firewall, and server firewall.
- Reality SNI / serverName.
- Reality dest.
- Create and cancel buttons.

Verbose safety notes, firewall reminders, and historical approval details were moved into a default-collapsed section named `高级安全说明`.

This stage does not add dynamic-port creation. The formal create path still uses the current backend protected port capability. Custom-port creation requires a separate dynamic-port create stage.

## Backend Safety Boundary

The backend create path remains protected:

- A successful landing preflight is still required.
- Existing backend validation still gates the selected landing server, Worker, and protected approved port.
- The Worker result must be successful before the backend writes `node.share_link`.
- The backend writes `node.share_link` only after Xray configuration, service startup, and port-listening verification succeed.
- Failure does not write `node.share_link`.

This stage also allows the frontend-supplied node name and Reality SNI / dest to pass through the existing protected create payload. It does not change the success criteria for writing links.

## Link And QR Rules

Complete V2Ray / VLESS links remain sensitive.

- Full links are not written to README, docs, audit text, PR text, frontend console logs, backend logs, or test snapshots.
- The create command result does not display the full link.
- The UI offers copy, QR display, and QR download only after successful creation and list refresh.
- QR codes are generated in the browser from a full link obtained through the existing explicit export flow.
- The QR code is equivalent to the full node link and is shown only after user action.

## Failure Behavior

When creation fails, the modal shows a concise reason and next-step hints:

- Check the cloud security group TCP port.
- Check the cloud firewall TCP port.
- Check the server firewall.
- Change to another port.
- Retry after fixing Worker, Xray, or port conflicts.

Failure state explicitly confirms that `node.share_link` was not written and a full client link was not generated.

## Safety Boundary

Stage 3.3.103 did not perform these actions:

- No real remote creation was executed by Codex.
- No public console deployment was performed.
- No production node was created by Codex.
- No complete node link was generated into logs, docs, README, PR text, or chat.
- No existing deleted resource was modified.
- No old node was restored.
- No cutover occurred.
- No cloud security group, cloud firewall, or server firewall was modified.
- No database record was physically deleted.

## Validation

Required validation:

```text
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
python3 -m unittest discover backend/tests
cd frontend && npm run build
```

The frontend build is required because this stage changes the create modal and node copy / QR entry flow.
