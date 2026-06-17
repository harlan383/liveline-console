# Stage 3.3.67 Transit Readonly Preflight Simple Button

## Goal

Stage 3.3.67 simplifies the Transit Links page remote readonly preflight
experience into a clear button-oriented panel.

This stage is frontend-only. It does not change backend APIs or Worker command
behavior.

## Implemented Scope

- Added `TransitReadonlyPreflightSimplePanel`.
- Made the Transit Links page show the simplified readonly preflight panel as
  the primary UI.
- Kept the previous complex readonly preflight panel in a collapsed legacy
  section for rollback and comparison.
- Kept the existing local planning state, no-op plan check, and Worker command
  creation callbacks.
- Kept result display redacted and structured.

## Simplified Panel Behavior

The new panel focuses the workflow into:

1. Review the selected transit server, landing node, planned listen port, and
   landing target port.
2. Confirm health and safety checkboxes.
3. Click `执行远程只读预检`.
4. Refresh and review Worker command status and redacted checks.

The panel continues to show that readonly preflight:

- only creates a `transit_readonly_preflight` Worker command,
- only runs fixed allowlist readonly checks,
- does not create a real forwarding route,
- does not add listening ports,
- does not modify firewall rules,
- does not modify Xray,
- does not modify `nodes.share_link`,
- does not export full client links,
- does not perform cutover.

## Legacy Panel Retention

The previous advanced readonly preflight UI remains in the page under:

`查看旧版高级只读预检面板`

It is not deleted, so the UI can be compared or rolled back without re-creating
the previous behavior.

## Unchanged Backend Boundary

This stage does not:

- change backend APIs,
- add database migrations,
- change Worker command payloads,
- execute Worker commands during development,
- create transit routes,
- install or restart `socat` / `gost`,
- modify firewall, cloud firewall, or cloud security group rules,
- modify Xray,
- modify `nodes.share_link`,
- generate or display real node links,
- perform cutover.

## Validation Checklist

- `git diff --check`
- `git diff --cached --check`
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app`
- `docker compose exec -T frontend npm run build`
- `docker compose up --build -d`
- `/api/health` returns backend / database / redis / worker ok
- frontend returns HTTP 200
- Redis `temp_credential:*` count is 0
- pending / running tasks count is 0
- no `transit_readonly_preflight` command is triggered by validation
- sensitive scan finds no real Worker token, install command, SSH key,
  database password, full proxy link, or full `nodes.share_link`
