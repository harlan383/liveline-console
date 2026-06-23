# Stage 3.3.137-hotfix-3 Transit Worker Upgrade Approval

## Goal

Add a read-only acceptance stage for the transit Worker upgrade required before re-running the Stage 3.3.137 HAProxy TCP route dry-run.

The current remote transit Worker can be older than the HAProxy dry-run validation support introduced by Stage 3.3.137-hotfix-2. This stage makes that blocker explicit in the UI and API.

## Required Version

- Required Worker version: `0.1.25-stage-3.3.137-hotfix-2`
- Bundled Linux amd64 Worker checksum: `fbc2e240bbb8cd64962e5151752cf410951673efadae704d192ca83f2ab89d2b`
- Required role: `transit`

Version acceptance uses the existing Worker version parsing and HAProxy TCP minimum-version helper. It does not rely on raw string comparison.

## API

Added read-only endpoint:

```text
GET /api/transit-resources/{resource_id}/worker-upgrade-acceptance
```

The response reports:

- transit resource id/name
- bound Worker id/status/hostname/interface
- current Worker version
- required Worker version
- required bundled binary checksum
- whether an upgrade is required
- whether acceptance passed
- blocked reason and next action
- read-only safety checks

If the Worker version is older than `0.1.25-stage-3.3.137-hotfix-2`, the response blocks HAProxy TCP dry-run and instructs the user to manually upgrade the transit Worker before refreshing acceptance.

If the Worker is online with a supported version, the response instructs the user to return to Stage 3.3.137 and regenerate the HAProxy route dry-run.

## UI

The transit Worker approval modal now includes:

- resource name
- current Worker status/version
- required Worker version
- bundled binary checksum
- upgrade required / not required
- acceptance passed / blocked
- next action
- read-only safety checklist
- refresh button

The panel warns that Stage 3.3.137 dry-run should not be retried until the Worker upgrade acceptance passes.

## Safety Boundary

This stage does not:

- generate Worker token
- generate Worker install command
- SSH or run remote commands
- install or restart Worker
- create Worker command
- create real execution command
- create HAProxy route
- create TransitRoute active record
- install HAProxy
- bind listener port
- modify firewall / security group / cloud firewall
- cutover
- read or output full `nodes.share_link`
- write `transit_routes.share_link`
- generate full VLESS / V2Ray client links

Any actual Worker upgrade remains a manual action or a future separately approved stage.

## Validation

Planned validation:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/private/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
```

Relevant unit tests cover:

- Worker version `0.1.24-stage-3.3.122` blocks acceptance
- Worker version `0.1.25-stage-3.3.137-hotfix-2` passes acceptance
- offline Worker blocks acceptance
- non-transit role blocks acceptance
- missing Worker version blocks acceptance
- no WorkerCommand is created
- no TransitRoute is created
- no share link is read or written
