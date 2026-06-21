# Stage 3.3.107 Landing Create Xray Listen Diagnostics

## Stage Goal

Stage 3.3.107 improves diagnostics for the protected `landing_node_create` Worker path when Xray starts but the approved TCP port is not confirmed as listening.

The observed failure class is:

```text
approved TCP port 27939 is not listening after Xray start
```

This stage only changes local code, tests, and documentation. It does not execute a real landing node create command.

## What Changed

- Worker version advances to `0.1.22-stage-3.3.107`.
- After starting the managed Xray service, the Worker now retries listener verification for a short bounded window instead of checking only once.
- Each listen-check attempt records a compact phase summary:
  - attempt index
  - Xray service active state
  - whether the approved port is detected as listening
  - matching `ss` listen lines when present
- If listener verification still fails, the Worker gathers redacted diagnostics before rollback:
  - `systemctl is-active` summary
  - `systemctl is-enabled` summary
  - Xray config file existence
  - managed Xray binary existence
  - Xray config-test result
  - inbound summary containing only tag, listen address, port, and protocol
  - compact listen socket summary
  - compact `systemctl status` summary
  - compact `journalctl` tail summary
  - rollback summary for current-run artifacts only
- Backend Worker result normalization now preserves the safe landing-create diagnostic fields for failed commands.
- Failed `landing_node_create` results explicitly drop full client links and sensitive Reality fields.

## Safety Gates Kept

This stage does not loosen the protected create flow:

- The approved formal port remains `27939/TCP`.
- No dynamic port support is introduced.
- The Worker still requires Xray config test success.
- The Worker still requires the managed Xray service to be active.
- The Worker still requires the approved port to be listening before success.
- The backend must write `nodes.share_link` only after a successful Worker result.
- Failed commands must not write `nodes.share_link`.
- Failed commands must not return or store a full client link.

## Redaction Rules

Failure diagnostics are intentionally compact and redacted:

- No full proxy link is returned in failed command results.
- No Reality private key is returned.
- No full Xray config is returned.
- No Worker secret or token is returned.
- No SSH private key is returned.
- No database password is returned.
- No `nodes.share_link` value is read or written.

The Xray inbound summary keeps only safe structural fields:

```text
tag / listen / port / protocol
```

It does not preserve clients, UUIDs, private keys, short IDs, or settings.

## Rollback Boundary

On failure, rollback remains scoped to artifacts created by the current Worker run:

- managed Xray service
- managed Xray config
- managed Xray binary/state paths created by this run

This stage does not add broad server cleanup behavior.

## Not Executed

This stage did not:

- execute SSH
- deploy the public console
- create a Worker command
- create a production node
- install or restart Xray in production
- modify cloud security groups, cloud firewall, or server firewall
- generate or record a full client link
- read or modify `nodes.share_link`
- cut over any route

## Validation

Required validation for this stage:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
python3 -m unittest discover backend/tests
cd worker && GOCACHE=/private/tmp/liveline-go-cache go test ./...
cd worker && GOCACHE=/private/tmp/liveline-go-cache go build ./...
```

Frontend build is not required unless frontend files change.
