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

## Hotfix 4: Worker Result Submit EOF

Stage 3.3.68-hotfix-4-worker-result-submit-eof hardens the Worker-side
submission path after production showed `transit_readonly_preflight` commands
still stuck in `running` while the transit Worker logged EOF on result POST.

The Worker changes are:

- Worker version is bumped to `0.1.8-stage-3.3.68`.
- `transit_readonly_preflight` result payloads are sanitized and bounded before
  POST.
- NUL bytes are removed and large strings are truncated.
- Result arrays and maps are capped before JSON serialization.
- Sensitive keys and proxy-link values are redacted before submission.
- Result POST requests use `Connection: close` and disable HTTP keepalive reuse
  to avoid stale connection EOF loops.
- HTTP submit failures now include status and response-body summaries when a
  response exists.
- If full result submit fails, the Worker attempts a minimal `/fail` fallback
  result containing command id, command type, redacted error, and the safety
  boundary.

The backend minimum Worker version for `transit_readonly_preflight` is raised
to `0.1.8-stage-3.3.68`. This prevents new remote readonly preflight commands
from being assigned to the older `0.1.7-stage-3.3.63` transit Worker that lacks
the submit fallback. This stage only updates code and the packaged Worker
binary; it does not auto-upgrade any remote Worker or retry any production
command.

## Hotfix 5: Worker Result Endpoint Timeout

Stage 3.3.68-hotfix-5-worker-result-endpoint-timeout hardens the console-side
`/api/workers/commands/{command_id}/result` and
`/api/workers/commands/{command_id}/fail` endpoints after production showed the
upgraded transit Worker timing out while waiting for response headers.

The backend changes are:

- Both endpoints log ingress metadata with command id, command type, Worker id,
  request body size, remote address, begin / end timestamps, elapsed time, and
  outcome.
- Request bodies are read through a bounded fast path before JSON parsing.
- NUL bytes are stripped before JSON parsing, and oversized / invalid / non-
  object reports are converted into a failed Worker command with a clear
  redacted error.
- `transit_readonly_preflight` results continue to be normalized into the safe
  result contract before persistence.
- `/fail` accepts a minimal fallback failure report from the Worker and does
  not require the full result shape.
- Commands that are already `succeeded`, `failed`, `cancelled`, `expired`, or
  `completed` return an idempotent JSON response with `already_completed=true`
  instead of a retry-triggering error.
- Persistence and normalization errors are caught, logged without sensitive
  payload content, and converted into a failed command whenever possible.

This hotfix does not add any real transit creation path, does not retry the
previous production commands, and does not auto-upgrade remote Workers.

## Hotfix 6: Worker Authenticated Result Path

Stage 3.3.68-hotfix-6-worker-authenticated-result-path adds deeper
instrumentation around the authenticated Worker submission path after
unauthenticated `/result` and `/fail` probes returned quickly but real
authenticated transit Worker submissions still timed out while waiting for
response headers.

The backend changes are:

- Worker authentication now logs begin / end metadata for Worker endpoints:
  request path, method, remote address, whether Worker auth headers are
  present, Worker id, elapsed time, and outcome.
- `/result` and `/fail` log an entry record before reading the request body,
  including command id, path, method, content length, remote address, Worker id
  when present, and begin timestamp.
- Authenticated `/result` and `/fail` requests now emit segmented timings:
  `auth_ms`, `statement_timeout_ms`, `command_lookup_ms`, `body_read_ms`,
  `json_parse_ms`, `normalize_ms`, `db_update_ms`, and total elapsed time.
- A short DB statement timeout is applied for command result handling so
  unexpected database waits return explicit JSON instead of hanging until the
  Worker HTTP client times out.
- Body-limit, invalid JSON, missing command, already-completed command, result
  normalization, and DB update failures all return explicit JSON responses.
- Terminal commands remain idempotent with `already_completed=true`.

The Worker source also classifies submit failures such as
`response_headers_timeout`, `tls_handshake_timeout`, `dns_resolution_failed`,
`connect_refused`, `io_timeout`, and generic request timeouts. Updating the
remote Worker still requires a separate user-authorized deployment stage; this
hotfix only changes local source, backend code, and documentation.

This hotfix does not create or retry remote readonly preflight commands and
does not add real transit creation capability.

## Hotfix 7: Worker Result Payload Diagnosis

Stage 3.3.68-hotfix-7-worker-result-payload-diagnosis adds a Worker-side local
diagnostic command for the remaining case where authenticated fake submissions,
already-completed submissions, small `ping` results, and minimal
`transit_readonly_preflight` results all complete quickly, but the Worker
automatically generated real readonly preflight result still times out while
waiting for response headers.

The new command is:

```bash
liveline-worker diagnose-transit-readonly-payload \
  --config /etc/liveline-worker/config.yaml \
  --payload-json '<transit_readonly_preflight payload JSON>'
```

The command reuses the existing `transit_readonly_preflight` readonly collection
path and then stops locally. It does not submit `/result` or `/fail` to the
console. The output is a JSON diagnostic summary only, with these fields:

- raw result JSON size in bytes,
- sanitized result JSON size in bytes,
- submit payload JSON size in bytes,
- top-level result keys,
- check count,
- per-check `id`, `status`, `passed`, and `detail_length`,
- largest string field path and length,
- NUL detection,
- sensitive protocol marker detection for `vless://`, `vmess://`, `ss://`, and
  `trojan://`,
- whether the sanitized submit payload exceeds the Worker soft limit,
- whether fallback submission would be triggered,
- non-JSON-friendly type paths.

The summary deliberately omits the full result body, Worker token, Worker
secret, SSH private keys, database passwords, full client links, and
`nodes.share_link`. It reports lengths and booleans instead of printing full
details.

The Linux amd64 Worker binary is rebuilt and committed as Worker
`0.1.9-stage-3.3.68` so a later authorized Worker replacement can run the
diagnostic command on the transit Worker host. This stage does not
automatically deploy or restart any remote Worker.

This hotfix does not change the console `/result` or `/fail` main logic, does
not create or retry readonly preflight commands, does not install, start, stop,
or restart `socat` / `gost`, does not create transit routes, does not add
listening ports, does not modify firewall rules, does not modify Xray, does not
read or modify `nodes.share_link`, and does not perform cutover.

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
