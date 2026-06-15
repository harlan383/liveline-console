# Stage 3.3.21 Lightweight Worker Bootstrap Design

## Current Stage Conclusion

Stage 3.3.21 is a lightweight Worker bootstrap design stage.

This stage only documents the future Worker onboarding direction. It does not implement a real Worker, does not install a Worker, does not execute SSH or remote commands, does not create nodes, does not create transit routes, does not add listening ports, does not modify `node.share_link`, and does not perform formal cutover.

## Goal

The goal is to design the future LiveLine Console server onboarding model:

1. The console generates a one-time Worker install token.
2. The user copies a `curl | bash` install command to the target VPS.
3. The VPS installs a lightweight `liveline-worker`.
4. The Worker registers with the console.
5. The console shows the server online.
6. The Worker sends periodic heartbeats and status reports.
7. Later stages can gradually add controlled remote tasks.

Worker v1 is intentionally small: registration, heartbeat, and status reporting only.

## Why curl | bash + Lightweight Worker + systemd

The default onboarding path should be easy for single-person local operation:

- `curl | bash` gives the user one copyable command.
- A small binary avoids requiring Docker on every VPS.
- `systemd` gives a familiar service lifecycle for Linux servers.
- Journal logs can be inspected with `journalctl`.
- The console can move away from asking for SSH keys in the browser as the default flow.

The command remains explicit and user-executed. The console does not SSH into servers during this stage.

## Why Docker Is Not The Default Worker Install

Docker is not chosen as the default Worker install path for v1 because:

- Some VPS hosts may not have Docker installed.
- Installing Docker is a larger remote change than installing one small binary.
- Docker networking can complicate host-level port and service checks.
- The current product direction is lightweight local operations, not a production orchestration platform.

Docker can be revisited later if multi-service worker packaging becomes necessary.

## Why cloud-init Is Not The Default

`cloud-init` is not the default because this system needs to onboard existing VPS instances as well as new ones. A copyable install command works for both existing and future servers, while `cloud-init` is mostly useful at instance creation time.

## SSH Mode Hidden But Source Preserved

Existing SSH-based source code should remain in the repository for now, but the default frontend onboarding flow should move toward Worker install commands.

Current design boundary:

- Keep existing SSH APIs and Redis temporary credential mechanism.
- Keep existing node and transit route logic intact.
- Hide SSH onboarding from the default user path when Worker onboarding is introduced.
- Do not delete SSH source code in this stage.
- Revisit SSH source removal only after Worker onboarding is stable and accepted.

## Install Command Format

Landing server command template:

```bash
curl -s https://<console-domain>/worker_setup_script/<one_time_token> | bash -s eth0 landing
```

Transit server command template:

```bash
curl -s https://<console-domain>/worker_setup_script/<one_time_token> | bash -s eth0 transit
```

Parameters:

- `eth0`: target network interface name.
- `landing`: landing server role.
- `transit`: transit server role.

If the server interface is not `eth0`, the user must replace it with the actual interface name, for example `ens3`, `ens5`, or `enp1s0`.

The examples use placeholders only. No real token is written to this document.

## Worker Directory Structure

Suggested binary path:

```text
/usr/local/bin/liveline-worker
```

Suggested config directory:

```text
/etc/liveline-worker/
```

Suggested config file:

```text
/etc/liveline-worker/config.yaml
```

Suggested systemd service:

```text
/etc/systemd/system/liveline-worker.service
```

Suggested log command:

```bash
journalctl -u liveline-worker -f
```

## systemd Service Design

The future service name should be:

```text
liveline-worker.service
```

The service should run the Worker binary as a long-lived process, load configuration from `/etc/liveline-worker/config.yaml`, restart on failure, and report logs to journald.

The service should not receive database passwords, admin credentials, full node links, SSH keys, or application secrets through the unit file.

## Server Role Design

### landing

`landing` represents a landing VPS.

Future responsibilities may include:

- Xray status detection.
- Node port detection.
- Node creation.
- Node deletion.
- Xray config backup and cleanup.

Worker v1 does not execute those tasks. It only registers, heartbeats, and reports status.

### transit

`transit` represents a transit server.

Future responsibilities may include:

- `socat` status detection.
- `gost` status detection.
- Transit listen port detection.
- Transit route creation.
- Transit route deletion.
- Remote cleanup of transit configs.

Worker v1 does not execute those tasks. It only registers, heartbeats, and reports status.

## One-Time Token Design

Future Worker install tokens should satisfy:

- One-time use.
- Expirable.
- Revocable.
- Bound to a server role: `landing` or `transit`.
- Bound to the current console account.
- Invalidated immediately after successful registration.
- Rejected when expired.
- Rejected when already used.
- Not written to README or docs as a real value.
- Not stored or logged in long-lived plaintext.
- Allowed in the install-script URL, but API responses and logs should display only redacted forms.

Suggested future fields:

| Field | Purpose |
| --- | --- |
| `id` | Token record id |
| `token_hash` | Hashed token, never plaintext |
| `role` | `landing` or `transit` |
| `status` | `active`, `used`, `expired`, or `revoked` |
| `expires_at` | Expiration time |
| `used_at` | Registration time |
| `created_by` | Console account id |
| `server_id` | Optional bound server id |
| `created_at` | Created time |
| `updated_at` | Updated time |

This stage does not add the table or migration.

## Worker Registration Flow

Future registration flow:

1. User clicks add landing server or add transit server.
2. Console generates a one-time token.
3. Frontend shows the install command.
4. User copies the command to the VPS and executes it.
5. Install script downloads `liveline-worker`.
6. Install script writes the Worker config file.
7. Install script creates the systemd service.
8. Worker starts.
9. Worker calls the console registration API.
10. Console validates the token.
11. Console creates or binds a server record.
12. Worker receives `worker_id`, `server_id`, and heartbeat settings.
13. Token is marked `used`.
14. Server status becomes online after heartbeat.

## Worker Heartbeat Flow

Worker v1 heartbeat should report:

- Worker id.
- Server id.
- Worker version.
- Role.
- Network interface name.
- Public IP or console-observed IP.
- Timestamp.
- Basic health state.

Heartbeat does not execute high-risk tasks.

## Status Reporting Content

Worker v1 may report read-only status data:

- OS.
- Kernel.
- CPU summary.
- Memory summary.
- Disk summary.
- Uptime.
- `liveline-worker` active state.
- Optional landing-only Xray status.
- Optional transit-only `socat` / `gost` status.

Suggested server states:

- `online`: recent heartbeat received.
- `offline`: heartbeat timeout exceeded.
- `unknown`: never successfully reported.

## Transit Forwarding Methods

Current transit methods remain:

- `socat`: temporary testing and simple forwarding.
- `gost`: compatibility and fallback forwarding.

HAProxy TCP is not added in this stage. If needed, it should be evaluated in a later dedicated stage, for example:

```text
Stage 3.3.x-haproxy-transit-engine
```

## Future Remote Cleanup Rules

### Landing Server Deletion

Future rule:

- Remote Xray cleanup must succeed before system records can be deleted.
- If remote cleanup fails, system record deletion must be blocked and the failure reason shown.

Required future capabilities:

- Worker task execution.
- Xray config backup.
- Precise Xray cleanup.
- Cleanup dry-run.
- Cleanup verification.
- Failure-safe blocking of system-record deletion.

### Transit Server Deletion

Future rule:

- Remote `socat` / `gost` cleanup must succeed before system records can be deleted.
- If remote cleanup fails, system record deletion must be blocked and the failure reason shown.

Required future capabilities:

- Worker task execution.
- Precise `socat` / `gost` systemd unit cleanup.
- Cleanup dry-run.
- Cleanup verification.
- Failure-safe blocking of system-record deletion.

Worker v1 does not perform any cleanup.

## Worker v1 Scope

Worker v1 may include:

- Registration.
- Heartbeat.
- Basic server status reporting.
- Worker version reporting.
- Role reporting.
- Network interface reporting.

Worker v1 must not include:

- Node creation.
- Transit route creation.
- Node deletion.
- Server remote cleanup.
- Xray modification.
- `socat` / `gost` modification.
- Firewall modification.
- Port opening.
- `node.share_link` modification.
- cutover.

## Future API Design

Future API candidates:

| API | Purpose |
| --- | --- |
| `POST /api/worker-tokens` | Generate one-time Worker install token |
| `GET /worker_setup_script/{token}` | Return install script |
| `POST /api/workers/register` | Register Worker |
| `POST /api/workers/heartbeat` | Receive Worker heartbeat |
| `GET /api/workers/{id}` | View Worker state |
| `POST /api/workers/{id}/tasks` | Future task dispatch; not Worker v1 |
| `GET /api/workers/{id}/tasks` | Future Worker task polling; not Worker v1 |
| `POST /api/workers/{id}/task-results` | Future task result reporting; not Worker v1 |

This stage does not implement these APIs.

## Security Design

Required security principles:

- Do not save plaintext SSH private keys.
- Worker tokens are one-time use.
- Worker tokens expire.
- Worker tokens can be revoked.
- Registered Workers should use a separate Worker secret or HMAC-style mechanism for follow-up auth; exact implementation belongs to a future stage.
- Install scripts must be readable and auditable.
- Install scripts must not contain real database passwords.
- Install scripts must not contain console admin tokens.
- Worker accepts only console-authorized tasks.
- Worker v1 does not execute high-risk tasks.
- Do not default-display full `node.share_link`.
- Do not modify `node.share_link`.
- Do not perform cutover.
- New or changed listen ports must still require cloud security group / cloud firewall / server firewall checks.

## Prohibited In This Stage

- No formal cutover.
- No `node.share_link` modification.
- No new listening ports.
- No real node creation.
- No transit route creation.
- No SSH or remote command execution.
- No database migration.
- No real Worker installation.
- No SSH source deletion.
- No existing node creation flow changes.
- No existing transit route creation flow changes.
- No remote cleanup implementation.
- No Docker default onboarding.
- No HAProxy addition.
- No remote Xray / `socat` / `gost` cleanup.
- No server or node record deletion.

## Verification Checklist

- README records Stage 3.3.21.
- This design document exists.
- No backend core logic changed.
- No frontend runtime behavior changed.
- No Worker implemented.
- No Worker installed.
- No database migration added.
- No listening port added.
- No `node.share_link` read or write performed.
- No SSH or remote command executed.
- No formal cutover executed.

## Stage Result

Stage 3.3.21 documents the future lightweight Worker bootstrap design. The current implementation remains unchanged, and remote execution remains No-Go.
