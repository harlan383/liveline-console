# Stage 3.5.6 Local Task History Usability

## Current Stage Conclusion

Stage 3.5.6 improves local task history readability and safety. This stage
adds a protected, read-only task list endpoint and a local frontend task
history panel. It does not create tasks, execute remote commands, modify live
routes, change `node.share_link`, add listening ports, or perform cutover.

Current route state remains unchanged:

- Formal link: `socat 18443`.
- Fallback link: `gost 8443`.
- `node.share_link`: already points to `socat 18443`.

## Updated Frontend Components

- `frontend/components/TaskHistoryPanel.tsx`
  - Adds a local task history panel under the system page.
  - Shows recent task status, short task id, task type, current step, progress,
    timestamps, failure summary, sanitized result data, and sanitized logs.
  - Does not create, restart, diagnose, or mutate any task.
- `frontend/components/AppShell.tsx`
  - Replaces the placeholder system operation area with the local task history
    panel.
- `frontend/app/globals.css`
  - Adds task history list, detail, status label, result summary, and log
    layout styles.
- `frontend/lib/api.ts`
  - Adds the `TaskListResult` frontend type.

## Backend Read-Only Endpoint

- `backend/app/api/routes/tasks.py`
  - Adds `GET /api/tasks`.
  - Returns the most recent existing task records.
  - Uses the existing admin session requirement.
  - Does not create, update, delete, enqueue, or retry tasks.
  - Does not add a database migration.

The endpoint exists because the previous backend only exposed lookup by known
task id. A usable task history page needs a safe read-only list of existing
tasks.

## Task Status Display Improvements

The task history panel shows:

- Short task id.
- Task type.
- Status label.
- Current step.
- Progress.
- Created / updated / started / finished timestamps.
- Error code.
- Failure reason summary when available.
- Sanitized `result_data` summary.
- Sanitized task logs and optional raw output.

If the backend only has a generic error, the frontend shows that generic error
without inventing a more specific cause.

## Failure Summary Rules

The frontend maps existing task fields into readable summaries:

- SSH / banner / authentication text: SSH connection or authentication issue.
- Port / listen text: port listening or occupancy check issue.
- Process / service / systemd text: remote process or service status issue.
- Health text: health check issue.
- Auth / CSRF / login text: authentication or CSRF issue.
- Required / missing / invalid text: parameter issue.
- Otherwise: the sanitized backend error message or unknown error.

These summaries are hints derived from existing task metadata. They do not
replace backend logs or create new facts.

## Sensitive Data Redaction Strategy

The task history panel performs display-layer redaction for:

- Full `vless://`, `vmess://`, `trojan://`, or `ss://` links.
- Private key material.
- Keys containing password, passphrase, secret, token, cookie, session,
  private key, SSH key, or admin password hash.
- Long strings and nested data, which are truncated for local UI safety.

The panel does not print full node links, SSH Keys, Passphrases, tokens,
`SESSION_SECRET`, real passwords, cookies, sessions, or full sensitive command
output.

## Task History Safety Notice

The UI states that task records are for local troubleshooting only. Operators
should not copy raw logs containing sensitive material to external systems and
should not send full node links, SSH Keys, passwords, tokens, or raw secrets to
Codex / ChatGPT.

## Explicit Non-Changes

- `node.share_link` was not read, printed, or modified.
- No full node link was displayed or written to documentation.
- No database migration was added.
- No listening port was added.
- No SSH command was executed.
- No remote command was executed.
- No backend task was triggered.
- No firewall rule was changed.
- No cutover was performed.
- `socat` was not allowed to take over `8443`.
- `gost 8443` was not closed, disabled, downgraded, replaced, or deleted.

## Future Boundary

If a future stage needs to execute real tasks, run remote diagnostics, restart
services, mutate routes, or show raw sensitive task data, it must be reviewed
and approved in a separate stage.

## Acceptance Checklist

- `GET /api/tasks` is protected by the existing admin session check.
- The system page opens the local task history panel.
- Task status, current step, progress, timestamps, and failure summaries are
  easier to scan.
- Empty task state is clear.
- `result_data` and raw output are redacted before display.
- No full node link, SSH Key, password, token, or `SESSION_SECRET` appears in
  the UI or docs.
- No backend task is triggered by opening or refreshing the task history panel.

## Safety Boundary

- Do not write real passwords.
- Do not write real hashes.
- Do not write real `SESSION_SECRET` values.
- Do not write SSH Keys.
- Do not write Passphrases.
- Do not write tokens.
- Do not write full node links.
- Do not read or modify `node.share_link`.
- Do not add database migrations.
- Do not add listening ports.
- Do not execute SSH or remote commands.
- Do not trigger backend tasks.
- Do not modify firewalls.
- Do not let `socat` take over `8443`.
- Do not close `gost 8443`.
- Do not perform cutover.
