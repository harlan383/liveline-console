# Stage 3.3.22 Worker Token/Register/Heartbeat Foundation

## Current Stage Conclusion

Stage 3.3.22 implements the backend foundation for future lightweight Worker onboarding.

This stage adds local database models, an Alembic migration, and local HTTP APIs for one-time Worker tokens, placeholder setup scripts, Worker registration, Worker heartbeat, and Worker query. It does not implement or install a real Worker binary and does not execute any SSH or remote command.

## Goal

The goal is to prepare the console for a later `curl | bash` Worker onboarding flow while keeping the current production network path untouched.

Allowed in this stage:

- Worker one-time install token.
- Worker register API.
- Worker heartbeat API.
- Worker latest status data structure.
- Worker list/detail query API.
- `landing` and `transit` roles.

Not allowed in this stage:

- Real Worker binary.
- Real Worker installation.
- SSH or remote command execution.
- Node creation.
- Transit route creation.
- Xray modification.
- `socat` / `gost` modification.
- Remote cleanup.
- New listening ports.
- `node.share_link` modification.
- Formal cutover.

## New Models And Tables

### `worker_tokens`

Fields:

| Field | Purpose |
| --- | --- |
| `id` | Token record id |
| `token_hash` | HMAC hash of the one-time token |
| `role` | `landing` or `transit` |
| `status` | `active`, `used`, `expired`, or `revoked` |
| `name` | Optional display name carried into the Worker record |
| `expires_at` | Token expiration time |
| `used_at` | Time of successful registration |
| `created_by` | Admin session account id, when created from the console |
| `server_id` | Optional future binding id; currently nullable |
| `created_at` | Created time |
| `updated_at` | Updated time |

Only `token_hash` is stored. Plaintext tokens are not persisted.

### `workers`

Fields:

| Field | Purpose |
| --- | --- |
| `id` | Worker id |
| `server_id` | Optional future binding id; currently nullable |
| `role` | `landing` or `transit` |
| `name` | Optional display name |
| `public_ip` | Worker-reported public IP |
| `hostname` | Worker-reported hostname |
| `interface_name` | Worker-reported network interface |
| `worker_version` | Worker version |
| `status` | Stored status, with query-time offline calculation |
| `last_heartbeat_at` | Last heartbeat time |
| `registered_at` | Registration time |
| `worker_secret_hash` | HMAC hash of Worker secret |
| `metadata_json` | Latest redacted heartbeat/status payload |
| `created_at` | Created time |
| `updated_at` | Updated time |

First version stores only the latest heartbeat/status data in `workers.metadata_json`. It does not add a `worker_heartbeats` history table.

## New Migration

Migration file:

```text
backend/alembic/versions/0008_worker_foundation.py
```

Revision:

```text
0008_worker_foundation
```

Down revision:

```text
0007_vps_mgmt_fields
```

## New APIs

### `POST /api/worker-tokens`

Creates a one-time Worker install token.

Request:

- `role`: `landing` or `transit`.
- `name`: optional display name.
- `expires_in_minutes`: optional, default `60`.

Response:

- `token_id`
- `role`
- `expires_at`
- `install_command`
- `masked_token`
- `status`

Security behavior:

- Requires admin login.
- Requires CSRF token.
- Stores only `token_hash`.
- Returns the install command only once.
- Does not log or persist plaintext token.

### `GET /worker_setup_script/{token}`

Returns a safe placeholder install script.

The script:

- Prints that it is a bootstrap preview / placeholder.
- Validates `interface_name`.
- Validates expected `role`.
- Does not download a real Worker.
- Does not write systemd units.
- Does not modify remote config.
- Does not add listening ports.
- Does not install Xray, `socat`, or `gost`.
- Does not output the token plaintext.

The real install script remains a future Worker implementation stage.

### `POST /api/workers/register`

Registers a Worker using a one-time token.

Request:

- `token`
- `role`
- `interface_name`
- `hostname`
- `public_ip`, optional
- `worker_version`, optional
- `system_info`, optional

Behavior:

1. Hashes and looks up the token.
2. Verifies token exists.
3. Verifies token is `active`.
4. Verifies token is not expired.
5. Verifies request role matches token role.
6. Creates a Worker record.
7. Generates `worker_secret`.
8. Stores only `worker_secret_hash`.
9. Marks token `used`.
10. Sets `used_at`.
11. Sets Worker `status=online`.
12. Sets `last_heartbeat_at`.

Response:

- `worker_id`
- `server_id`, currently nullable
- `role`
- `worker_secret`, returned once
- `heartbeat_interval_seconds`
- `server_time`

This stage does not bind Workers to `vps_servers` or `transit_resources`. Binding belongs to a later frontend/Worker integration stage.

### `POST /api/workers/heartbeat`

Receives Worker heartbeat and latest status.

Authentication:

- `X-Worker-Id`
- `X-Worker-Secret`

The backend verifies `worker_secret_hash`.

Request may include:

- `worker_version`
- `interface_name`
- `public_ip`
- `hostname`
- `uptime_seconds`
- `os`
- `kernel`
- `cpu`
- `memory`
- `disk`
- `services.liveline_worker`
- `services.xray`
- `services.socat`
- `services.gost`

Behavior:

- Updates `last_heartbeat_at`.
- Sets `status=online`.
- Updates latest metadata summary.
- Does not execute remote commands.
- Does not create nodes.
- Does not create transit routes.
- Does not modify remote services.

Response:

- `ok`
- `server_time`
- `next_heartbeat_seconds`

### `GET /api/workers`

Returns Worker list.

Returned fields include:

- `id`
- `role`
- `status`
- `public_ip`
- `hostname`
- `interface_name`
- `worker_version`
- `last_heartbeat_at`
- `registered_at`
- `server_id`
- `metadata_summary`

The API does not return `worker_secret`, `worker_secret_hash`, token plaintext, or token hash.

### `GET /api/workers/{id}`

Returns one Worker detail with the same safe fields as the list response.

The API does not return `worker_secret`, `worker_secret_hash`, token plaintext, or token hash.

## Token Mechanism

Worker install tokens are one-time and hash-only at rest.

Token status values:

- `active`
- `used`
- `expired`
- `revoked`

Plaintext token appears only in the creation response as part of `install_command`. Later queries do not return plaintext tokens.

## Worker Secret Mechanism

`worker_secret` is generated during successful registration and returned once.

Stored value:

- `worker_secret_hash`

Returned values never include:

- `worker_secret_hash`
- token hash
- plaintext token after creation

## Status Rules

Heartbeat interval:

```text
60 seconds
```

Offline threshold:

```text
3 * heartbeat_interval_seconds = 180 seconds
```

Query-time status rule:

- `online`: recent heartbeat is within the threshold.
- `offline`: last heartbeat is older than the threshold.
- `unknown`: Worker has never successfully heartbeated.

No scheduled offline updater is implemented in this stage.

## Role Rules

### `landing`

Allowed in v1:

- Register.
- Heartbeat.
- Status report.

Not allowed in v1:

- Node creation.
- Xray modification.
- Node deletion.

### `transit`

Allowed in v1:

- Register.
- Heartbeat.
- Status report.

Not allowed in v1:

- `socat` creation or modification.
- `gost` creation or modification.
- Transit route creation.
- Transit route deletion.

## Safety Boundary

This stage did not implement a real Worker.

This stage did not install a real Worker.

This stage did not execute SSH or remote commands.

This stage did not create real nodes.

This stage did not create transit routes.

This stage did not modify Xray.

This stage did not modify `socat` / `gost`.

This stage did not clean remote Xray / `socat` / `gost`.

This stage did not add listening ports.

This stage did not modify `node.share_link`.

This stage did not execute formal cutover.

This stage did not delete SSH source code.

This stage did not delete existing node creation logic.

This stage did not delete existing transit route logic.

This stage did not add HAProxy.

## Validation Checklist

- `git diff --check`
- `docker compose exec -T backend alembic upgrade head`
- `docker compose exec -T backend alembic current`
- `python3 -m compileall backend/app`
- `docker compose exec -T frontend npm run build`
- `docker compose up --build -d`
- `http://localhost:3000` HTTP 200
- `/api/health` backend / database / redis / worker all ok
- Redis `temp_credential:*` equals `0`
- pending / running tasks equals `0`
- Sensitive information scan passes

## Stage Result

Stage 3.3.22 adds the local Worker token/register/heartbeat foundation. It remains a backend foundation stage only; real Worker installation and remote execution stay No-Go.
