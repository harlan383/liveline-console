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

## Hotfix 8: Worker Auto-submit Trace

Stage 3.3.68-hotfix-8-worker-auto-submit-trace adds Worker-side redacted trace
logs around the automatic result/failure submit path after manual authenticated
submissions and the local payload diagnosis showed that backend routing,
authentication, minimal transit result normalization, and payload size were not
the apparent blockers.

The Worker now logs a single redacted `result` preparation line before calling
the console:

- command id,
- command type,
- endpoint kind,
- sanitized result JSON size,
- submit payload JSON size,
- whether fallback would be triggered,
- result top-level keys,
- checks count,
- largest field path and length,
- content length,
- header key names only,
- console host and path without query strings.

The Worker also logs a redacted `fail` preparation line with command id,
endpoint kind, failure payload size, whether a fallback result is present,
fallback result keys, header key names only, and safe console host/path.

The common JSON submit path now logs before and after each POST:

- endpoint host/path,
- method,
- body size,
- timeout value,
- start timestamp,
- elapsed milliseconds,
- success/failure,
- response status when available,
- error classification when failed.

These traces deliberately omit `X-Worker-Secret` values, Worker setup tokens,
SSH private keys, database passwords, complete result bodies, complete node
links, and `nodes.share_link`. The trace prints header names but never header
values.

The Linux amd64 Worker binary is rebuilt and committed as Worker
`0.1.10-stage-3.3.68` so a later authorized Worker replacement can collect the
new submit trace. This stage does not automatically deploy or restart any
remote Worker.

This hotfix does not change the console `/result` or `/fail` main logic, does
not change `transit_readonly_preflight` collection logic, does not create or
retry readonly preflight commands, does not install, start, stop, or restart
`socat` / `gost`, does not create transit routes, does not add listening ports,
does not modify firewall rules, does not modify Xray, does not read or modify
`nodes.share_link`, and does not perform cutover.

## Hotfix 9: Worker Submit Curl Compatible

Stage 3.3.68-hotfix-9-worker-submit-curl-compatible changes only the Worker
submit transport after decisive diagnostics showed that manual authenticated
curl submission of the same `transit_readonly_preflight` command and token
completed immediately, while the Worker automatic Go `net/http` submission
timed out awaiting response headers.

The Worker HTTP path is made closer to curl:

- `Content-Type: application/json` remains explicit.
- `Content-Length` is set explicitly.
- The Worker no longer forces `Connection: close`.
- The request no longer sets `request.Close=true`.
- The Worker no longer uses a custom `DisableKeepAlives` transport for these
  JSON posts.
- The existing redacted trace continues to log body size, content length,
  endpoint host/path, elapsed time, response status, error classification, and
  whether fallback was triggered.

If Go `net/http` submission fails specifically with `response_headers_timeout`,
the Worker may try a constrained curl fallback. The fallback is intentionally
narrow:

- it is used only by the Worker result/fail submit path,
- it accepts only fixed
  `/api/workers/commands/{command_id}/result` and
  `/api/workers/commands/{command_id}/fail` paths,
- it rejects query strings, fragments, unsupported schemes, and non-result/fail
  paths,
- it uses `exec.CommandContext` without invoking a shell,
- it sends curl options through stdin config so Worker secret values are not
  placed in process arguments,
- it sets a max time and cannot hang indefinitely,
- it does not print Worker secrets, Worker tokens, request bodies, complete
  client links, or `nodes.share_link`.

The Linux amd64 Worker binary is rebuilt and committed as Worker
`0.1.11-stage-3.3.68` so a later authorized Worker replacement can test the
curl-compatible submit path. This stage does not automatically deploy or
restart any remote Worker.

This hotfix does not change the console `/result` or `/fail` main logic, does
not change `transit_readonly_preflight` collection logic, does not create or
retry readonly preflight commands, does not add transit creation capability,
does not install, start, stop, or restart `socat` / `gost`, does not create
transit routes, does not add listening ports, does not modify firewall rules,
does not modify Xray, does not read or modify `nodes.share_link`, and does not
perform cutover.

## Hotfix 10: Worker Result EOF Curl Fallback

Stage 3.3.68-hotfix-10-worker-result-eof-curl-fallback keeps the hotfix-9
curl-compatible submit path and extends its trigger conditions. The decisive
production diagnosis showed that Worker `0.1.11-stage-3.3.68` still received a
Go `net/http` pre-response `request_error: EOF` while submitting the full
`transit_readonly_preflight` `/result` payload. The Worker then successfully
submitted the smaller `/fail` payload, so commands no longer remained
indefinitely running, but the complete readonly preflight result was still not
stored.

Worker `0.1.12-stage-3.3.68` therefore attempts the same constrained curl
fallback for these pre-response submit failures:

- `response_headers_timeout`,
- `request_error: EOF`,
- `unexpected EOF`,
- connection reset by peer,
- broken pipe,
- server closed idle connection,
- closed network connection.

The fallback remains tightly scoped:

- it is still used only by Worker command result/fail submission,
- it accepts only fixed
  `/api/workers/commands/{command_id}/result` and
  `/api/workers/commands/{command_id}/fail` paths,
- it rejects query strings, fragments, unsupported schemes, and non-result/fail
  paths,
- it submits the same JSON body that Go `net/http` attempted to submit,
- it uses `exec.CommandContext` without invoking a shell,
- it keeps Worker secret values out of process arguments,
- it does not print Worker secrets, Worker tokens, request bodies, complete
  client links, or `nodes.share_link`,
- if curl fallback succeeds, the Worker treats the result submission as
  successful instead of immediately downgrading to the minimal `/fail` payload.

This hotfix does not change the console `/result` or `/fail` main logic, does
not change `transit_readonly_preflight` collection logic, does not add transit
creation capability, does not install, start, stop, or restart `socat` /
`gost`, does not create transit routes, does not add listening ports, does not
modify firewall rules, does not modify Xray, does not read or modify
`nodes.share_link`, and does not perform cutover. The rebuilt Linux amd64
Worker binary is committed for a later separately authorized Worker
replacement; this stage does not automatically deploy it.

## Hotfix 11: Worker Curl Fallback Config Fix

Stage 3.3.68-hotfix-11-worker-curl-fallback-config-fix keeps the hotfix-10 EOF
fallback trigger behavior and fixes the curl fallback execution path. Production
logs showed that Worker `0.1.12-stage-3.3.68` correctly entered curl fallback
for a full `/result` submit after Go `net/http` returned `request_error: EOF`,
but curl itself failed with an error while reading its `--config` input.

Worker `0.1.13-stage-3.3.68` now uses concrete 0600 temporary files for the
fallback:

- a JSON body file used by `data-binary`,
- a curl config file passed as `curl --config <config-path>`,
- a response file used by curl `output`.

Those files are created before curl starts, stay present for the full curl
process lifetime, and are removed after curl exits. The JSON body is still not
placed in command arguments. Worker secret values remain in the temporary curl
config file only, with 0600 permissions, and are not printed to logs or placed
in process arguments.

The fallback safety boundary remains unchanged:

- fixed result/fail endpoint allowlist only,
- no query strings or fragments,
- no arbitrary shell,
- no arbitrary URL,
- no Worker token or secret logging,
- no complete result body logging,
- no client link or `nodes.share_link` output.

This hotfix does not change the console `/result` or `/fail` main logic, does
not change `transit_readonly_preflight` collection logic, does not add transit
creation capability, does not install, start, stop, or restart `socat` /
`gost`, does not create transit routes, does not add listening ports, does not
modify firewall rules, does not modify Xray, does not read or modify
`nodes.share_link`, and does not perform cutover. The rebuilt Linux amd64
Worker binary is committed for a later separately authorized Worker
replacement; this stage does not automatically deploy it.

## Hotfix 12: Worker Curl Fallback Without Config

Stage 3.3.68-hotfix-12-worker-curl-fallback-no-config removes curl `--config`
from the Worker fallback path. Production logs showed Worker
`0.1.13-stage-3.3.68` still reached curl fallback correctly, but both `/result`
and `/fail` fallback failed while curl attempted to read the config file. The
problem was therefore isolated to the curl config mechanism rather than the
backend, database, Worker token, command row, payload size, or fallback trigger
conditions.

Worker `0.1.14-stage-3.3.68` keeps the existing EOF and response-header-timeout
trigger conditions, but invokes curl with fixed arguments instead of `--config`:

- headers are written to a 0600 temporary header file,
- the JSON body is written to a 0600 temporary body file,
- the response is written to a 0600 temporary response file,
- curl uses `--header @<header-file>` and `--data-binary @<body-file>`,
- the Worker secret stays in the temporary header file and never appears in
  process arguments,
- all fallback temporary files are removed after curl exits.

The fallback remains tightly scoped:

- fixed result/fail endpoint allowlist only,
- no query strings or fragments,
- no arbitrary shell,
- no arbitrary URL,
- no Worker token or secret logging,
- no complete result body logging,
- no client link or `nodes.share_link` output.

## Hotfix 13: Worker Curl Fallback Manual-Compatible Mode

Stage 3.3.68-hotfix-13-worker-curl-fallback-manual-compatible responds to the
next production diagnosis: Worker `0.1.14-stage-3.3.68` correctly triggered
curl fallback and no longer failed on `--config`, but its automatic fallback
still timed out while a manually run command using `curl -i --max-time ...
--request POST --header @<header-file> --data-binary @<body-file>
<fixed-url>` succeeded immediately for the same command, headers, body, token,
and endpoint.

Worker `0.1.15-stage-3.3.68` therefore aligns the fallback with the manual
command form:

- curl is invoked with `-i`, `--max-time`, `--request POST`,
  `--header @<header-file>`, and `--data-binary @<body-file>`,
- `--output` and `--write-out` are no longer used,
- the HTTP status and JSON body are parsed from stdout,
- header and body temporary files are synced and closed before curl starts,
- the fixed result/fail endpoint allowlist and no-query rule remain enforced,
- Worker secrets stay in the 0600 temporary header file and are not printed in
  process arguments, logs, README, docs, or PR output.

This hotfix does not change backend result/fail main logic, does not change
`transit_readonly_preflight` collection logic, and does not add any real
transit creation capability. The rebuilt Worker binary is committed for a
later separately authorized Worker replacement; this stage does not deploy or
restart the remote Worker.

## Hotfix 14: Worker Compact Result Payload

Stage 3.3.68-hotfix-14-worker-compact-result-payload follows the next
production finding: manual small-body curl result submission succeeds, while
manual and automatic result submissions around two kilobytes can time out on
the transit Worker to console network path. That points to a payload-size /
MTU / fragmentation class of problem rather than a backend route, token,
database row, curl argument, or command-row issue.

Worker `0.1.16-stage-3.3.68` therefore compacts only the
`transit_readonly_preflight` `/result` submission payload. The readonly
collection result remains unchanged inside the Worker, but the posted result is
reduced before serialization:

- `passed`, `status`, short `summary`, Worker metadata, planned listener port,
  landing target port, forwarding method, and `checks_count` are retained,
- each check keeps only a compact `name`, `passed`, and short detail when the
  payload stays within the target,
- if the compact body remains above the 1200 byte target, details are removed
  and the payload keeps only `checks_count` plus failed check names,
- the safety boundary is reduced to a short no-write / no-cutover list,
- compact trace logs include original size, compact size, check count, maximum
  detail length, and endpoint path, but never include Worker secrets or the
  full body.

This hotfix does not change backend result/fail main logic, does not change the
readonly collection checks, and does not add route creation, listener binding,
firewall mutation, Xray mutation, `nodes.share_link` access, client link export,
or cutover behavior. The rebuilt Worker binary is committed for a later
separately authorized Worker replacement; this stage does not deploy or restart
the remote Worker.

This hotfix does not change the console `/result` or `/fail` main logic, does
not change `transit_readonly_preflight` collection logic, does not add transit
creation capability, does not install, start, stop, or restart `socat` /
`gost`, does not create transit routes, does not add listening ports, does not
modify firewall rules, does not modify Xray, does not read or modify
`nodes.share_link`, and does not perform cutover. The rebuilt Linux amd64
Worker binary is committed for a later separately authorized Worker
replacement; this stage does not automatically deploy it.

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
