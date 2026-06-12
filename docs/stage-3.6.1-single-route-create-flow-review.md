# Stage 3.6.1 Single Route Create Flow Review

## Current Stage Conclusion

Stage 3.6.1 reviews the current single-route create flow and documents the
standard operator path from local preparation to future formal cutover
approval. This stage is review-only. It does not create a route, execute SSH,
run remote commands, trigger backend tasks, modify `node.share_link`, add
listening ports, or perform cutover.

Current route state remains unchanged:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Code and Page Areas Reviewed

| Area | File / component | Current role |
| --- | --- | --- |
| Single-route UI | `frontend/components/TransitRoutesPanel.tsx` | Selects transit resource, active node, forwarding method, route name, listen port, SSH temporary credentials, create task, diagnose routes, restart socat 18443, copy candidate link |
| Transit resources UI | `frontend/components/TransitResourcesPanel.tsx` | Manages local transit resource records and exposes read/install checks through temporary credentials |
| Topology preview UI | `frontend/components/TransitTopologyPreviewPanel.tsx` | Local preview-only topology draft, no route persistence or remote connection |
| Frontend API types | `frontend/lib/api.ts` | Defines node, transit resource, transit route, task, diagnosis, and restart result types |
| Transit route API | `backend/app/api/routes/transit_routes.py` | Protected route list/detail/create/diagnose/restart endpoints |
| Transit resources API | `backend/app/api/routes/transit_resources.py` | Protected resource metadata and read/install endpoints |
| Nodes API | `backend/app/api/routes/nodes.py` | Protected node list/detail endpoints; list masks full `share_link` |
| Transit route schema | `backend/app/schemas/transit_route.py` | Allows `gost` and `socat`, validates ports and method |
| Transit route model | `backend/app/models/transit_route.py` | Stores route metadata, target, service, status, and optional share link |
| Socat route worker | `backend/app/worker/ssh_socat_route.py` | Creates socat systemd service with checks and rollback |
| Worker jobs | `backend/app/worker/jobs.py` | Loads temporary credentials, updates task state, deletes Redis temp credentials |

## Current Capabilities Already Present

| Capability | Current status |
| --- | --- |
| Transit resource records | Present through local DB and protected UI/API |
| Active node selection | Present in topology preview and single-route UI |
| Topology preview | Present and clearly marked `PREVIEW ONLY` / `NOT USABLE` |
| Single-route page | Present as "创建单条转发" |
| Forwarding methods | `gost` and `socat` supported in create API |
| Socat formal-resource restriction | Present for the accepted Hong Kong transit resource |
| Reserved port protection | `socat` rejects `22`, `8443`, and `20575`; `gost` rejects historical `20575` |
| Duplicate listen-port DB check | Present for same transit resource and creating/active routes |
| Remote port occupancy check | Present in worker through `ss -ltnH` before socat service creation |
| Systemd-managed socat | Present; no bare `nohup` background process |
| Failure rollback | Present for service creation failures and DB save failures |
| Task records | Present through tasks and task logs |
| Task history page | Present and sanitized for local troubleshooting |
| Read-only route diagnosis | Present for active `gost` / `socat` routes with temporary SSH credentials |
| Socat 18443 controlled restart | Present only for `socat` route on port `18443` |
| Candidate link copy | Present for `socat 18443`; derived in frontend from active node link without writing DB |
| Health check | Present through `/api/health` and `scripts/local-health-check.sh` |
| Backup / restore scripts | Present through local PostgreSQL helper scripts |
| Route safety guardrails | Present in local UI |

## Current Missing or Still-Manual Capabilities

| Area | Gap / manual step |
| --- | --- |
| Real route creation approval | A future real create action still requires explicit user confirmation before pressing the create button |
| Workbuddy involvement | Required for any real SSH, remote creation, remote diagnosis, or remote port check |
| Cloud security group check | Displayed as warning, but cloud-side confirmation remains manual |
| Cloud firewall check | Displayed as warning, but provider-side confirmation remains manual |
| Server firewall change | Not automated; future changes must be separately approved |
| Candidate link acceptance record | Must be recorded separately after client testing |
| Formal cutover approval | Must be separate from route creation |
| `node.share_link` modification | Not part of route creation; requires formal cutover approval |
| Full rollback checklist | Must be confirmed before any formal route change or cutover |
| Sensitive raw output review | UI redacts display, but operators must still avoid copying raw sensitive logs externally |

## Standard Single-Route Flow

### A. Preparation Phase

Before creating or changing any route:

1. Back up the local database:

   ```bash
   scripts/local-db-backup.sh
   ```

2. Confirm the current formal link remains healthy:

   - Formal link: `socat 18443`.
   - Fallback link: `gost 8443`.
   - `node.share_link` already points to `socat 18443`.

3. Confirm the stage will not modify `node.share_link`.
4. Confirm the target transit server resource.
5. Confirm the target active landing node.
6. Confirm there are no pending or running tasks.
7. Confirm Redis temporary credentials are clear.

This review stage does not perform those checks against production state. It
only records the required flow.

### B. Port Planning Phase

Before selecting a listening port:

1. Choose a new listening port deliberately.
2. Avoid `8443` because it is retained for the `gost` fallback route.
3. Avoid overwriting `18443` unless a separate formal-change stage explicitly
   approves that action.
4. Avoid `22` and the historical problem port `20575`.
5. Before adding or changing any listening port, confirm:

   - Cloud security group allows the TCP port.
   - Cloud firewall allows the TCP port, if applicable.
   - Server firewall allows the TCP port.
   - The port is not already listening on the transit server.

### C. Create Phase

Real creation must be deliberate:

1. User confirms route name, transit resource, active node, forwarding method,
   and listen port.
2. User provides SSH Key / Passphrase only through the existing temporary
   credential form.
3. Backend stores SSH credentials only in Redis temporary encrypted credentials.
4. RQ job arguments must not contain SSH Key or Passphrase.
5. Worker reads credentials, deletes them, connects to the transit server, and
   performs whitelisted creation steps.
6. If creation fails, task state must end in `failed` and route state must not
   remain misleadingly active.

Stage 3.6.1 does not execute this phase.

### D. Diagnosis Phase

After a real create stage, diagnosis should check:

1. Listening port state.
2. Forwarding process state.
3. Systemd service state.
4. Transit-to-landing connectivity.
5. Task result and task logs.
6. Local client connectivity command.

Diagnosis output must not include complete node links, SSH Keys, Passphrases,
tokens, passwords, `SESSION_SECRET`, or complete sensitive configs.

### E. Candidate Link Acceptance Phase

After route creation and diagnosis:

1. Derive a candidate client link only from the approved active node link.
2. Change only server and port for the candidate route.
3. Keep Reality parameters unchanged.
4. Import the candidate link manually into the client.
5. Test client connectivity.
6. Record client acceptance without writing the complete link into docs, logs,
   task results, or reports.

### F. Formal Cutover Phase

Route creation is not cutover.

Formal cutover must be a separate stage with:

1. Explicit approval to modify `node.share_link`.
2. Old `node.share_link` backup.
3. New candidate link confirmation.
4. Client acceptance.
5. Rollback plan.
6. `gost 8443` fallback preservation unless separately approved.
7. No implicit `socat` takeover of `8443`.

## Workbuddy Boundary

| Situation | Workbuddy needed? | Reason |
| --- | --- | --- |
| Stage 3.6.1 flow review | No | Documentation-only, no SSH, no remote operation |
| Reading local code and docs | No | Local repository inspection only |
| Real SSH login to transit server | Yes | Remote access and credential handling |
| Real socat install/check | Yes | Remote command execution |
| Real route creation | Yes | Remote systemd service creation and port listening |
| Real remote listening-port check | Yes | Remote command execution |
| Real route diagnosis | Yes | Remote read-only commands through SSH |
| Real `node.share_link` cutover | Separate approval required | Changes formal client-facing state |
| Real rollback | Separate approval required | Restores formal state and may affect clients |

## Current Link Protection Boundary

| Item | Current state |
| --- | --- |
| Formal link | `socat 18443` |
| Fallback link | `gost 8443` |
| `node.share_link` | Already points to `socat 18443` |
| Stage 3.6.1 `node.share_link` changes | None |
| Stage 3.6.1 new listening ports | None |
| Stage 3.6.1 SSH / remote commands | None |
| Stage 3.6.1 backend task triggers | None |
| Stage 3.6.1 cutover activity | None |
| Stage 3.6.1 `socat` 8443 takeover | None |
| Stage 3.6.1 `gost` 8443 shutdown / downgrade / replacement | None |

If any future stage adds or changes a listening port, the operator must check
cloud security group, cloud firewall, and server firewall rules for the
corresponding TCP port.

## Risks to Keep Visible

- Accidentally selecting the wrong transit resource.
- Reusing `8443` and disturbing the `gost` fallback route.
- Reusing `18443` without a formal route-change stage.
- Forgetting cloud security group or cloud firewall checks.
- Treating topology preview as a real usable route.
- Treating candidate link copy as formal cutover.
- Copying complete node links or raw sensitive logs into external tools.
- Triggering a remote task while another route task is pending/running.
- Assuming route creation changes `node.share_link`; it must not.

## Security Boundary

- Do not write real passwords.
- Do not write real password hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH Keys.
- Do not write Passphrases.
- Do not write tokens.
- Do not write complete node links.
- Do not commit real database backup files.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not trigger backend Worker/RQ tasks.
- Do not modify firewall rules.
- Do not let `socat` take over `8443`.
- Do not close, stop, downgrade, or replace `gost` 8443.
- Do not perform cutover.

## Stage 3.6.1 Recorded Impact

| Item | Result |
| --- | --- |
| Modified code | No |
| Added scripts | No |
| Generated real backup file | No |
| Added database migration | No |
| Added listening port | No |
| Modified `node.share_link` | No |
| Executed SSH / remote command | No |
| Triggered backend task | No |
| Affected `socat` 18443 formal link | No |
| Affected `gost` 8443 fallback link | No |

## Review Conclusion

The current system already has the major pieces required for a controlled
single-route workflow: transit resources, active node selection, topology
preview, route creation API/UI, task history, route diagnosis, socat 18443
restart, candidate link copy, health checks, backup/restore scripts, and route
safety guardrails.

The next real route creation or remote diagnosis must be explicitly authorized
in a separate stage and should involve Workbuddy because it would require SSH,
remote commands, or task execution. Formal cutover remains separate from route
creation and must not be implied by candidate link creation or copy.
