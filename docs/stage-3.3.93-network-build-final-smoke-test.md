# Stage 3.3.93 Network Build Final Smoke Test

## Purpose

Stage 3.3.93 is the final smoke-test stage for the current network-build main flow.

The goal is not to add new features. The goal is to verify that the already completed lightweight self-use flow remains understandable and safe:

- direct Reality node can remain usable
- Hong Kong socat transit route can remain usable
- public console pages show the simplified network-build state clearly
- temporary export remains transient
- complete node links are not written to docs, README, logs, audit records, PRs, or chat
- no cutover occurs

This stage is intentionally verification-only.

## Scope

This stage may record smoke-test checks for:

- GitHub `main` alignment
- public frontend deployment freshness
- overview page visibility
- landing server / direct node page usability
- transit server page visibility
- transit route page usability
- add-transit-route preview modal safety
- transient export modal safety
- database safety checks that do not read full links
- Hong Kong transit read-only checks
- client import / browse smoke test performed by the operator

This stage must not implement new behavior.

## Fixed Safety Boundary

This stage does not:

- execute cutover
- modify `nodes.share_link`
- write `transit_routes.share_link`
- read or export complete `nodes.share_link`
- generate or record complete node links
- create Worker commands
- create VPS records
- create nodes
- create transit routes
- add listening ports
- restart, stop, or delete `socat`
- modify Xray
- modify firewalls, cloud firewalls, or cloud security groups
- execute SSH or remote commands unless the operator separately approves that action
- add database migrations
- deploy the public console unless the operator separately approves that action
- add frontend, backend, Worker, or database features

If any later step creates or changes a listening port, the operator must also check and allow the corresponding TCP port in the cloud security group, cloud firewall, and server firewall.

## Known Accepted Baseline

The following baseline is carried forward from the accepted Stage 3.3 network-build work. This section records known state only; it is not a new full-link export.

### Direct Reality Node

- landing node id: `a71472c6-f62c-43b5-a223-9f5f070ae4ef`
- node name: `liveline-reality-27939`
- landing VPS IP: `64.90.13.19`
- Xray port: `27939`
- `nodes.share_link` exists
- expected `share_link_length`: `250`
- complete `nodes.share_link` must not be queried or written to documentation

### Hong Kong Socat Transit Route

- route id: `d10d3dcc-679f-4f85-ae37-9e5dfa37e6af`
- route name: `hk-socat-live-23843`
- entry: `163.223.216.108:23843`
- target: `64.90.13.19:27939`
- forwarding method: `socat`
- service name: `liveline-socat-23843.service`
- service path: `/etc/systemd/system/liveline-socat-23843.service`
- expected status: `active`
- expected `transit_routes.share_link`: `NULL` / empty
- cutover status: not cut over

### Hong Kong Transit Worker

- worker id: `f2e16197-e953-46dd-90af-66f64759a2a9`
- role: `transit`
- server id: `1e222459-9fa2-4c62-800f-a3b35edb7df8`
- hostname: `WEPC202605221223335`
- interface name: `eth0`
- expected worker version: `0.1.20-stage-3.3.73`
- expected status: `online`

## Smoke Test Checklist

### 1. Repository Alignment

Expected checks:

```bash
git log --oneline -n 5
git status --short
```

Expected result:

- latest `main` contains merge commit `8ab61fdeebabf28a44601463bf0324d825adbd27`
- working tree is clean

Connector-side note for this stage:

- PR #173 is merged.
- PR #173 merge commit is `8ab61fdeebabf28a44601463bf0324d825adbd27`.
- The Stage 3.3.93 branch was created from that merge commit.

### 2. Public Frontend Deployment Freshness

Operator-approved public-console commands, if deployment validation is performed on the public master VPS:

```bash
cd /opt/liveline-console
docker compose build frontend --no-cache
docker compose up -d --force-recreate frontend
curl -I http://127.0.0.1:3200
```

Expected result:

- frontend container is rebuilt and recreated
- `curl -I http://127.0.0.1:3200` returns HTTP 200

Stage note:

- This documentation commit does not deploy or rebuild the public console.
- Deployment must be performed only after operator approval.

### 3. Overview Page

Expected UI result:

- page displays a network-build status summary
- landing server status is visible
- direct node status is visible
- transit Worker status is visible
- transit route status is visible
- safety status is visible
- page shows not-cutover / original direct-node-retained state
- complete node links are not displayed
- old `18443` / `8443` wording does not appear as current-state copy

### 4. Landing Server / Direct Node Page

Expected UI result:

- page loads normally
- direct node entry is clear
- protocol summary is clear
- configuration status is clear
- copy action is visible and understandable
- QR action is visible and understandable
- advanced read/debug operations are collapsed by default
- complete link is not written to permanent docs or logs

### 5. Transit Server Page

Expected UI result:

- Hong Kong transit server record is visible
- Worker online state is visible
- no remote operation is triggered by viewing the page
- no SSH, firewall, socat, or Xray change is performed

### 6. Transit Route Page

Expected UI result:

- compact route table/list loads normally
- `hk-socat-live-23843` is visible
- route status shows `active`
- entry, target, forwarding method, and service name are clear
- `SHARE_LINK` state shows empty / not written
- `CUTOVER` state shows not cut over
- advanced debug operations are collapsed by default

### 7. Add Transit Route Modal

Expected UI result:

- `新增中转链路` opens a modal
- modal only generates local configuration preview
- modal is not wired to generic real creation
- no Worker command is created
- no transit route is created
- no listening port is added
- no socat service is created, restarted, stopped, or deleted

### 8. Transient Export Modal

Expected UI result:

- transient export opens a modal
- old checkbox checklist is not shown
- concise safety notice is shown
- `生成测试配置` creates a transient result only
- copy button remains available
- HTTP manual-copy fallback remains available
- closing the modal leaves the main page clean
- complete candidate link is not written to database, README, docs, logs, audit records, PRs, or chat

### 9. Database Safety Checks

Allowed query shape:

```sql
SELECT
  id,
  name,
  share_link IS NOT NULL AS has_share_link,
  length(share_link) AS share_link_length
FROM nodes
WHERE id = 'a71472c6-f62c-43b5-a223-9f5f070ae4ef';
```

Expected result:

- `has_share_link = true`
- `share_link_length = 250`

Allowed query shape:

```sql
SELECT
  id,
  name,
  share_link IS NULL AS share_link_is_null,
  length(share_link) AS share_link_length
FROM transit_routes
WHERE id = 'd10d3dcc-679f-4f85-ae37-9e5dfa37e6af';
```

Expected result:

- `share_link_is_null = true`
- `share_link_length` is `NULL`

Forbidden database check:

```sql
SELECT share_link FROM nodes;
```

The full node link must not be queried, copied into chat, written into README, written into docs, or stored in a PR body/comment.

### 10. Hong Kong Transit Read-Only Checks

Allowed read-only commands, only if the operator explicitly approves SSH / remote checks:

```bash
systemctl is-active liveline-socat-23843.service
ss -lntp | grep ':23843 '
```

Expected result:

- service is `active`
- `0.0.0.0:23843` is listening

Forbidden actions:

- restarting `liveline-socat-23843.service`
- stopping `liveline-socat-23843.service`
- deleting the service
- changing `ExecStart`
- changing firewall or cloud security-group rules
- changing Xray

### 11. Client Smoke Test

Operator-side client checks:

- manually export the transient transit candidate configuration
- import the candidate configuration into the client
- confirm browsing works
- confirm the exit remains the landing VPS / landing region
- do not paste the complete candidate link into chat, README, docs, logs, or PRs

Known observation to retain:

- after first import, the candidate configuration may have about a one-minute warm-up delay before browsing works
- `socat` journal may show `Broken pipe` or `Connection reset by peer`
- as long as service is active, port is listening, and client browsing works, these remain observation items for later long-duration stability testing

## Execution Record

Repository-side checks completed by connector in this stage:

- confirmed PR #173 is merged
- confirmed PR #173 merge commit is `8ab61fdeebabf28a44601463bf0324d825adbd27`
- created branch `stage-3.3.93-network-build-final-smoke-test` from that merge commit
- added this documentation record only

Checks intentionally not executed by this documentation commit:

- public VPS `docker compose` rebuild / restart
- public console UI walkthrough
- database SQL checks
- Hong Kong SSH read-only checks
- client import / browse test

Reason:

- those actions touch live public infrastructure or require operator-side client operation
- this commit must not perform remote actions without separate operator approval
- this commit must not read or record complete share links

## Result

Stage 3.3.93 records the final smoke-test checklist and repository-side preparation for the existing network-build closure.

No new product capability was added.

No production state was changed.

No complete node link was queried, exported, copied, or recorded.

The remaining live smoke-test items should be executed manually or through a separately approved operator action on the public master VPS, Hong Kong transit VPS, database, and client.

## Follow-Up Reminder

The GitHub repository was temporarily made public to make public VPS clone/deployment easier.

After public deployment, clone, and smoke testing are stable, change the GitHub repository back to private.