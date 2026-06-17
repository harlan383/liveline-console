# Stage 3.3.68 Transit Readonly Preflight Result Polish

## Goal

Stage 3.3.68 improves the Transit Links readonly preflight result display so an
operator can quickly understand whether the preflight has not started, is still
running, passed, failed, or needs manual handling.

This stage is frontend-only result polish. It does not add backend capability
and does not execute remote actions.

## Implemented Scope

- Improved `TransitReadonlyPreflightSimplePanel` result rendering.
- Added an overall result state:
  - not started,
  - running,
  - passed,
  - failed,
  - manual handling required.
- Added a clearer check list with pass / fail state per check.
- Added failure reason summaries derived from the existing redacted Worker
  command result.
- Added suggested manual actions for common failure categories.
- Added a persistent safety boundary block in the result area.
- Kept the old complex readonly preflight panel collapsed and available for
  rollback.

## Result Display Rules

The UI uses the existing `transit_readonly_preflight` Worker command response.
It does not request new backend fields.

The result panel shows:

- Worker command id and status,
- target Worker id and version,
- redacted summary,
- failed check summaries,
- suggested manual actions,
- structured checks with pass / fail labels,
- safety boundary reminders.

## Hotfix: Prominent Panel Placement

Stage 3.3.68-hotfix-preflight-panel-prominent moves the simplified readonly
preflight panel out of the collapsed legacy workbench. It now appears near the
top of the Transit Links page, directly after the page note and collapsible
safety explanation, and before the legacy transit route table.

The hotfix keeps the old transit route table and the old advanced readonly
preflight panel. The old advanced panel remains collapsed for rollback and
comparison, while the simplified panel becomes the visible primary entry point.

The primary button label is now `开始只读预检` to make the action clearer. The
panel still states that readonly preflight only creates or refreshes the
existing safe preflight flow and does not create real transit routes.

## Hotfix 3: Result EOF / Long Running Commands

Stage 3.3.68-hotfix-3-transit-readonly-result-eof hardens the backend Worker
command result ingestion path for `transit_readonly_preflight`.

The issue observed in production was that a transit Worker could run the
readonly checks and then repeatedly fail to post the result with an EOF while
the command stayed in `running`. The backend now handles this class of failure
more defensively:

- The result endpoint parses the Worker payload explicitly.
- `transit_readonly_preflight` results are normalized into the UI contract:
  `passed`, `status`, `summary`, `checks`, `redacted_summary`, and
  `safety_boundary`.
- Oversized strings are truncated and NUL bytes are removed before JSONB
  persistence.
- Sensitive keys and proxy-link values are redacted before persistence and API
  serialization.
- Malformed result payloads are marked as failed with a clear error instead of
  remaining in `running`.
- Result persistence errors are caught, logged without sensitive payload
  content, and converted into a failed Worker command when possible.

This hotfix does not change the Worker allowlist checks and does not add any
real transit creation capability.

## Safety Boundary

This stage does not:

- change backend APIs,
- add database migrations,
- execute SSH,
- execute remote commands,
- trigger a real Worker command during validation,
- create transit routes,
- add listening ports,
- install, start, stop, or restart `socat` / `gost`,
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
- `/api/health` returns backend / database / redis / worker ok
- frontend returns HTTP 200
- Redis `temp_credential:*` count is 0
- pending / running tasks count is 0
- no `transit_readonly_preflight` command is triggered by validation
- sensitive scan finds no real Worker token, install command, SSH key,
  database password, full proxy link, or full `nodes.share_link`
