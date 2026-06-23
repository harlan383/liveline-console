# Stage 3.3.137-hotfix-2 HAProxy Dry-Run Worker Validation

## Goal

Fix the Worker-side `transit_route_create` dry-run validation so the approved Stage 3.3.137 HAProxy TCP dry-run payload is accepted without weakening the existing socat dry-run path.

Production dry-run evidence showed the Worker still validated every `transit_route_create` dry-run as the older Stage 3.3.71 socat create path, causing the HAProxy dry-run command to fail with an approval stage mismatch.

## Fix

- Upgraded `liveline-worker` source version to `0.1.25-stage-3.3.137-hotfix-2`.
- Added explicit HAProxy dry-run constants for:
  - `Stage 3.3.137-new-transit-haproxy-route-create-dry-run`
  - `forwarding_method=haproxy_tcp`
  - listen port `23843`
  - landing target `64.90.13.19:27939`
- Added a HAProxy-specific dry-run validation branch.
- Kept the old Stage 3.3.71 socat dry-run validation path unchanged.
- Added a HAProxy dry-run result path that returns only approval/dry-run metadata.
- Rebuilt `backend/worker-binaries/liveline-worker-linux-amd64`.
- Raised the backend HAProxy TCP minimum Worker version to `0.1.25-stage-3.3.137-hotfix-2` so older Workers are not treated as supporting the fixed dry-run path.

## Dry-Run Result Boundary

The HAProxy dry-run result reports:

- `status=approval_required`
- `execution_mode=dry_run`
- `real_execution=false`
- `route_created=false`
- `haproxy_installed=false`
- `listener_bound=false`
- `firewall_modified=false`
- `share_link_mutated=false`
- `cutover=false`
- `next_stage=Stage 3.3.138-new-transit-haproxy-route-create-final-approval`

No system command is executed by this dry-run path.

## Safety Boundary

This hotfix does not:

- SSH to any server.
- Deploy or upgrade any remote Worker.
- Generate a real Worker install command.
- Create a Worker command.
- Create a real execution command.
- Create a HAProxy route.
- Create a `TransitRoute` active record.
- Install HAProxy.
- Bind a listener.
- Modify firewall, cloud security group, or cloud firewall rules.
- Read, print, or mutate `nodes.share_link`.
- Write `transit_routes.share_link`.
- Generate a complete VLESS/V2Ray client link.
- Perform cutover.

## Validation

Planned validation:

- `git diff --check`
- `git diff --cached --check`
- `PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests`
- `cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./...`
- Worker Linux amd64 binary rebuild and embedded version string check.
- Sensitive diff scan for tokens, private keys, full node links, and full share-link values.
