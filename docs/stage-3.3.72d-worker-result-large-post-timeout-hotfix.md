# Stage 3.3.72d Worker Result Large POST Timeout Hotfix

## Stage Goal

Stage 3.3.72d fixes the Worker result/fail transport problem observed after the
controlled `transit_route_create` dry-run path was introduced. The Hong Kong
transit Worker could generate a dry-run result, but posting a result body around
2 KB to `/api/workers/commands/{id}/result` or `/fail` could hit timeout / EOF
on the path to the public console.

This stage is a transport and safety hotfix only. It does not create a real
transit route.

## Production Symptom

- `transit_route_create` dry-run generated a result locally on the Worker.
- `/result` submission failed with `request_error: EOF`.
- curl fallback also failed for the larger result body.
- `/fail` fallback was also larger than the stable small-body range and could
  hit `response_headers_timeout`.
- Small `/result` probes returned quickly, while a roughly 2 KB body could time
  out before reaching normal result handling.

## Root-Cause Hypothesis

The backend result/fail path already handles authenticated small payloads and
terminal command idempotency. The failure appears related to larger POST body
delivery on the Worker-to-console network path. The safest immediate fix is to
keep Worker result/fail bodies small for `transit_route_create` dry-run reports.

## Implementation

- Worker version is raised to `0.1.18-stage-3.3.72`.
- `transit_route_create` result submissions are compacted before POST.
- Compact dry-run results retain only the required execution summary fields:
  - `execution_mode`
  - `real_execution`
  - `status`
  - `summary`
  - `planned_listen_port`
  - `landing_target_port`
  - `forwarding_method`
  - `route_name`
  - `worker_version`
  - `hostname`
  - `role`
  - `interface_name`
- Long `checks`, `planned_actions`, `planned_service`, and `safety_boundary`
  fields are summarized or removed from the submit payload.
- Failure payloads are also compacted so `/fail` is smaller than the result it
  is trying to replace.
- Backend result normalization now accepts compact `transit_route_create`
  result shapes.
- Backend route tests cover large-body fast rejection before body read for
  missing auth / missing commands and compact dry-run result ingestion.

## Safety Boundary

This stage does not:

- Create a real transit route.
- Bind `23843/TCP`.
- Start, stop, restart, or install `socat` / `gost`.
- Modify Xray.
- Modify firewall, cloud firewall, or cloud security group rules.
- Read, output, or modify `nodes.share_link`.
- Generate or display a full client link.
- Perform cutover.
- Mark a failed command as succeeded by hand.

## Sensitive Information Policy

This stage does not write Worker secrets, tokens, database passwords, SSH keys,
full proxy links, or `nodes.share_link` values to docs, README, tests, logs, or
PR text.

## Validation Checklist

- `git diff --check`
- `git diff --cached --check`
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/app`
- `python3 -X pycache_prefix=/private/tmp/liveline-pycache -m compileall backend/tests`
- Backend unit tests for Worker result route and normalization.
- `GOCACHE=/private/tmp/liveline-go-cache go test ./...`
- `GOCACHE=/private/tmp/liveline-go-cache go build ./...`
- Linux amd64 Worker binary rebuild.
- Sensitive information scan.

## Next Stage

After this hotfix is deployed and the Hong Kong Worker is explicitly upgraded by
the operator, a new dry-run validation can be attempted. Real transit route
creation remains blocked until a later explicit execution approval.
