# Stage 3.3.111 Simplified Transit Route Create QR Flow

## Stage Goal

Stage 3.3.111 makes the transit route creation experience mirror the simplified direct node creation flow.

The operator flow is now:

1. Fill in the route name, transit server, landing node, transit listen port, and forwarding method.
2. Confirm the transit listen TCP port is already allowed in the cloud security group, cloud firewall, and server firewall.
3. Click `创建中转链路`.
4. The UI runs the protected sequence: readonly preflight, protected `transit_route_create` Worker command, route refresh, and transient client-link export.
5. After success, the modal offers copy, temporary QR display, QR download, and `完成并关闭`.

This PR does not execute the flow in production.

## Transit Link Generation

Transit client links are derived from the landing direct node's existing `nodes.share_link`.

The generation rule is intentionally narrow:

- Preserve the landing node UUID and Reality query parameters.
- Preserve flow, security, public key, shortId, SNI / serverName, fingerprint, transport type, and related parameters.
- Replace only the client-facing address with the transit entry host.
- Replace only the client-facing port with the transit listen port.
- Replace the fragment / display name with the transit route name.

The complete generated link is returned only by the explicit transient export API after a successful active transit route exists. It is not stored in `transit_routes.share_link`.

## Backend Safety Boundary

The real create endpoint remains the existing protected Worker path.

- The UI creates a `transit_readonly_preflight` command first and waits for success.
- The UI then calls the protected `worker-create-execute` endpoint.
- The backend still validates the protected route parameters, Worker role, Worker identity, interface, route name, listen port, landing target, and previous preflight result.
- The Worker command result must succeed before a `transit_routes` record is created.
- The route record keeps `share_link = NULL`.
- If the route is not active, has no landing `nodes.share_link`, or is already cut over, transient export is refused.

This stage does not add arbitrary shell, arbitrary systemd unit content, generic remote execution, firewall mutation, or cutover.

## Frontend UX

The `新增中转链路` modal is now a create flow:

- Fixed header with a visible close button.
- Scrollable body for the form, progress, errors, and success result.
- Fixed footer with create / cancel, retry / close, or finish controls.
- A concise confirmation replaces the previous preview-only checklist.
- Advanced safety notes are default-collapsed.
- Success state displays the transit entry, landing target, protocol summary, copy action, QR action, and download action.
- Failure state does not show a full link or QR code.

## Link And QR Rules

Complete V2Ray / VLESS links and QR codes are sensitive.

- Full links are not written to README, docs, audit text, PR text, backend logs, frontend console logs, or test snapshots.
- QR codes are generated only in the browser from the transient export response.
- QR codes are shown only after user action.
- Failure does not return or display a complete client link.

## Safety Boundary

Stage 3.3.111 did not perform these actions:

- No SSH was executed.
- No public console deployment was performed.
- No real transit route was created by Codex.
- No Worker command was created by Codex.
- No socat, gost, or Xray service was installed, restarted, stopped, or deleted by Codex.
- No full `nodes.share_link` value was printed into docs, README, PR text, tests, or chat.
- No `nodes.share_link` was modified.
- No `transit_routes.share_link` was written.
- No firewall, cloud security group, or cloud firewall was modified.
- No cutover occurred.
- No database record was physically deleted.

## Validation

Required validation:

```text
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
docker compose build backend frontend
docker compose run --rm backend python -m unittest discover tests
docker compose exec -T frontend npm run build
```

Worker build and tests are not required unless Worker code changes.
