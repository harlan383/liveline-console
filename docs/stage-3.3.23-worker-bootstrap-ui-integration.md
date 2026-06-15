# Stage 3.3.23 Worker Bootstrap UI Integration

## Current Stage Conclusion

Stage 3.3.23 integrates the Stage 3.3.22 Worker token API into the local console UI.

This stage changes the default add-server entry for landing servers and transit servers to a `curl | bash` Worker install-command flow. It does not implement a real Worker binary, does not install a real Worker, does not execute SSH or remote commands, and does not change the current production network path.

## Goal

The goal is to let the operator generate a one-time Worker bootstrap command from the UI while keeping the script as the Stage 3.3.22 safe placeholder.

Implemented in this stage:

- Landing server add modal now defaults to Worker install command generation.
- Transit server add modal now defaults to Worker install command generation.
- Landing server tokens use `role=landing`.
- Transit server tokens use `role=transit`.
- The UI calls `POST /api/worker-tokens`.
- The UI displays the returned install command and supports copy.
- The UI displays token status, masked token, and expiration time.
- SSH source code and existing APIs are retained, but the normal add-server UI no longer defaults to SSH forms.

## Landing Server Add Flow

Opening **Add Landing Server** shows:

- Access method: Worker install command.
- Optional server name.
- Expiration time in minutes, default `60`.
- Generate install command button.
- Install command display area.
- Copy command button.
- Token expiration time.
- Current status summary.

The backend-generated command has this shape:

```text
curl -s <console>/worker_setup_script/<one-time-token> | bash -s eth0 landing
```

If the target server network interface is not `eth0`, the operator should adjust it manually, for example `ens3`, `ens5`, or `enp1s0`.

## Transit Server Add Flow

Opening **Add Transit Server** shows the same Worker install-command flow, but uses:

```text
role=transit
```

The command shape is:

```text
curl -s <console>/worker_setup_script/<one-time-token> | bash -s eth0 transit
```

## Current Setup Script Boundary

The current `GET /worker_setup_script/{token}` endpoint returns a safe placeholder script.

The placeholder script:

- Is returned only after the backend endpoint validates token availability.
- Validates role and interface-name input.
- Does not download a real Worker.
- Does not install a real Worker.
- Does not write systemd units.
- Does not modify remote server configuration.
- Does not create nodes.
- Does not create transit routes.
- Does not add listening ports.
- Does not modify `node.share_link`.
- Does not execute formal cutover.

Real Worker installation remains a future approved stage.

## SSH Source Boundary

Existing SSH-related source code and APIs are retained.

This stage does not delete:

- Redis temporary credential logic.
- Existing SSH-related APIs.
- Existing node creation logic.
- Existing transit route logic.

The ordinary add landing/transit server UI no longer defaults to SSH entry forms.

## Modified Files

- `frontend/components/ServerManagementPanel.tsx`
  - Replaces the default add landing server modal with Worker install-command generation.
  - Uses `role=landing`.
  - Keeps SSH recheck and existing node creation flows intact.

- `frontend/components/TransitRoutesPanel.tsx`
  - Replaces the default add transit server modal with Worker install-command generation.
  - Uses `role=transit`.
  - Keeps edit resource and transit route planning flows intact.

- `frontend/lib/api.ts`
  - Adds a typed `createWorkerToken` helper for `POST /api/worker-tokens`.

- `frontend/app/globals.css`
  - Adds styling for Worker command display and metadata.

- `README.md`
  - Adds Stage 3.3.23 status and scope notes.

## Safety Boundary

This stage did not implement a real Worker.

This stage did not install a real Worker.

This stage did not execute SSH or remote commands.

This stage did not create real nodes.

This stage did not create transit routes.

This stage did not add listening ports.

This stage did not modify `node.share_link`.

This stage did not execute formal cutover.

This stage did not delete SSH source code.

This stage did not write plaintext token to README or docs.

This stage did not expose full node links by default.

This stage did not add database migrations.

## Validation Checklist

- `git diff --check`
- `docker compose exec -T frontend npm run build`
- `docker compose up --build -d`
- `http://localhost:3000` HTTP 200
- `/api/health` backend / database / redis / worker all ok
- Redis `temp_credential:*` equals `0`
- pending / running tasks equals `0`
- Sensitive information scan passes

## Stage Result

Stage 3.3.23 completes the UI integration for one-time Worker bootstrap command generation. Real Worker installation and remote execution remain No-Go.
