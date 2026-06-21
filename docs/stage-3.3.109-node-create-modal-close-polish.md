# Stage 3.3.109 Node Create Modal Close Polish

## Stage Goal

Stage 3.3.109 improves the direct Reality node create modal close experience after the simplified create flow succeeds or fails.

After Stage 3.3.108, direct node creation can complete successfully, but the create modal did not provide an obvious close or finish control. This stage makes the modal easier to exit without changing any backend create behavior.

## UI Changes

- Added a visible `×` close button in the create modal header.
- Split the direct node create modal into:
  - fixed header
  - scrollable body
  - fixed footer action area
- Added a success-state action:
  - `完成并关闭`
  - closes the modal and refreshes landing server / node list state
- Added failure-state actions:
  - `关闭`
  - `重新尝试`
- Kept the existing copy V2Ray link, temporary QR code, node summary, and QR download entry points unchanged.

## Behavior

When the create command succeeds and a node summary is available, the modal continues to show:

- node name
- server entry
- protocol summary
- status
- copy V2Ray link action
- temporary QR code action
- node summary action

Clicking `完成并关闭` closes the modal and refreshes the landing server / node list.

When the create flow fails, the modal keeps the redacted error and next-step guidance visible, with `关闭` and `重新尝试` available.

## Security Boundary

This stage only changes frontend modal controls and styling.

It did not:

- execute SSH
- deploy the public console
- create a Worker command
- create a production node
- install Xray
- read full `nodes.share_link`
- write or log a full VLESS / V2Ray link
- modify cloud security groups, cloud firewall, or server firewall
- cut over any route

## Link And QR Boundary

The existing link and QR handling remains unchanged:

- full links are only shown/copied through the existing explicit export path
- QR codes remain a frontend-only temporary display
- full links are not written to docs, README, PR body, logs, or tests

## Validation

Required validation:

```bash
git diff --check
git diff --cached --check
docker compose exec -T frontend npm run build
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
```
