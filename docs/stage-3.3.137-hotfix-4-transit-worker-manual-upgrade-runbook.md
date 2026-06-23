# Stage 3.3.137-hotfix-4 Transit Worker Manual Upgrade Runbook

## Goal

Add a safe manual upgrade runbook and acceptance reminder for the `mkiepl广港` transit Worker before re-running the Stage 3.3.137 HAProxy route dry-run.

The remote transit Worker currently needs to move from:

```text
0.1.24-stage-3.3.122
```

to:

```text
0.1.25-stage-3.3.137-hotfix-2
```

The bundled Worker binary checksum for the target version is:

```text
fbc2e240bbb8cd64962e5151752cf410951673efadae704d192ca83f2ab89d2b
```

## UI Change

The transit Worker approval modal now includes a manual upgrade runbook section next to the read-only Worker upgrade acceptance panel.

It shows:

- current Worker version
- target Worker version
- bundled Worker binary checksum
- manual upgrade reminders
- upgrade-after acceptance entry

The page tells the user that this is a preparation and acceptance stage only. The system does not remotely execute the upgrade.

## Manual Upgrade Runbook

The runbook reminds the user to:

1. Confirm the bundled Worker binary on the public controller is the target version and matches the checksum.
2. Manually log in to the transit VPS.
3. Back up the old `liveline-worker` binary.
4. Manually place the target binary at `/usr/local/bin/liveline-worker`.
5. Keep executable permissions.
6. Manually restart `liveline-worker.service`.
7. Wait for heartbeat to return online.
8. Refresh Worker upgrade acceptance in LiveLine Console.
9. Return to Stage 3.3.137 and regenerate HAProxy route dry-run only after the Worker version meets the target.

The UI deliberately does not generate a complete install command or Worker token.

## Safety Boundary

This stage does not:

- SSH or run remote commands
- automatically install Worker
- automatically restart remote Worker
- generate Worker token
- generate complete Worker install command
- create Worker command
- create real execution command
- create HAProxy route
- create TransitRoute active record
- install HAProxy
- bind `23843`
- modify firewall / security group / cloud firewall
- cutover
- read or output full `nodes.share_link`
- write `transit_routes.share_link`
- generate full VLESS / V2Ray client links

The actual Worker upgrade remains a manual user action or a future separately approved execution stage.

## Acceptance

After the user manually upgrades the transit Worker, the existing read-only acceptance endpoint is refreshed:

```text
GET /api/transit-resources/{resource_id}/worker-upgrade-acceptance
```

Acceptance requires:

- Worker role is `transit`
- Worker heartbeat is online
- Worker version is `0.1.25-stage-3.3.137-hotfix-2` or newer according to existing version parsing

When acceptance passes, the page instructs the user to return to Stage 3.3.137 and regenerate the HAProxy route dry-run.

## Validation

Planned validation:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
```

No backend behavior changes are required in this stage.
