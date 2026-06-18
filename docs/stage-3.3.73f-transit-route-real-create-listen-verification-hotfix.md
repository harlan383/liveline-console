# Stage 3.3.73f Transit Route Real Create Listen Verification Hotfix

## Stage Goal

Stage 3.3.73f fixes the approved Hong Kong `socat` real-create Worker code path
after the first production attempt failed with:

```text
approved TCP port 23843 is not listening after socat start
```

The service had briefly reached the systemd started state, then the Worker
rolled back the LiveLine-managed service. The environment was confirmed clean:
no `23843/TCP` listener, no `transit_routes` row, and no remaining service file.

This stage only changes code, tests, documentation, and the bundled Worker
binary. It does not trigger another real create command.

## Hotfix Changes

- Upgrade the Worker to `0.1.20-stage-3.3.73`.
- Require the same minimum Worker version for `transit_route_create`.
- After `systemctl enable --now liveline-socat-23843.service`, retry service and
  listener verification for several seconds instead of checking only once.
- Record a compact phase list for each listen verification attempt:
  - attempt index
  - `systemctl is-active` result
  - whether `23843/TCP` was detected as listening
- Before rollback on failure, collect compact diagnostics:
  - `systemctl is-active`
  - `systemctl status --no-pager -l`
  - `journalctl -u liveline-socat-23843.service -n 80 --no-pager`
  - `ss -lntp` filtered to `:23843`
  - LiveLine service file summary
- Preserve a structured `real_create` failed result with:
  - `execution_mode=real_create`
  - `real_execution=true`
  - `status=failed`
  - approved route fields
  - service name and path
  - diagnostics
  - listen verification attempts
  - `rollback_attempted=true`
- Fix Worker `/fail` submission so `transit_route_create` failures keep their
  command type even when the failure result is absent or compacted.
- Keep backend normalization from defaulting real execution failures back to
  `dry_run`.

## Approved Route Still Fixed

The hotfix does not widen the route scope. The only approved route remains:

| Field | Value |
| --- | --- |
| transit resource id | `1e222459-9fa2-4c62-800f-a3b35edb7df8` |
| Worker id | `f2e16197-e953-46dd-90af-66f64759a2a9` |
| Worker interface | `eth0` |
| landing node id | `a71472c6-f62c-43b5-a223-9f5f070ae4ef` |
| listen port | `23843/TCP` |
| landing target | `64.90.13.19:27939` |
| forwarding method | `socat` |
| route name | `hk-socat-live-23843` |
| service name | `liveline-socat-23843.service` |
| service path | `/etc/systemd/system/liveline-socat-23843.service` |

## Safety Boundary

Stage 3.3.73f keeps these boundaries:

- no Worker command trigger
- no real transit route creation
- no listener binding by this stage
- no `socat` or `gost` start, stop, restart, or install by Codex
- no firewall, cloud firewall, or cloud security group change
- no Xray modification
- no landing node configuration modification
- no `nodes.share_link` read or modification
- no full client link generation or display
- no cutover

## Validation Checklist

- `git diff --check`
- `git diff --cached --check`
- backend compileall for `backend/app`
- backend compileall for `backend/tests`
- backend unit tests
- `go test ./...`
- `go build ./...`
- Linux amd64 Worker binary rebuilt
- sensitive scan for Worker secrets, tokens, database passwords, SSH private
  keys, complete proxy links, and real `nodes.share_link` values

## Next Stage

The production deployment, Hong Kong Worker upgrade, and any re-attempt of the
approved real create command must happen only in a separately authorized
execution stage.
