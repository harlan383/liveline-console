# Stage 3.3.195 — deleted node share_link scrub

## Goal

Remove persisted client link material from historical deleted node rows while keeping the audit/history rows themselves.

This stage is for cleaning `nodes.share_link` only when the node is already soft-deleted.

## Scope

Allowed:

- Add a backend API endpoint for dry-run and explicit confirmed scrub.
- Match only rows where `nodes.status = 'deleted'` and `nodes.share_link IS NOT NULL`.
- Clear only `nodes.share_link` and update `nodes.updated_at` for matched rows.
- Return only non-sensitive summaries such as node name, port, status, deleted timestamp, and link length.
- Record an audit entry after confirmed scrub.

Not allowed:

- Do not delete node rows.
- Do not modify active nodes.
- Do not modify current active node `香港直连15m` / `28917`.
- Do not modify `vps_servers`.
- Do not modify `transit_resources`.
- Do not modify `transit_routes`.
- Do not modify current active route `mk香港落地15m` / `29833 -> 28917`.
- Do not create Worker commands.
- Do not execute SSH or remote commands.
- Do not restart Xray / HAProxy / socat.
- Do not add or change listening ports.
- Do not perform cutover.
- Do not return full client links in responses.

## API

Endpoint:

```text
POST /api/nodes/deleted-share-links/scrub
```

Dry-run request:

```json
{
  "dry_run": true
}
```

Confirmed scrub request:

```json
{
  "dry_run": false,
  "confirm": "CONFIRM_SCRUB_DELETED_NODE_SHARE_LINKS_ONLY"
}
```

The endpoint requires:

- authenticated admin session;
- CSRF token;
- explicit confirmation text for non-dry-run execution.

## Expected current public VPS target

Before scrub, the public control database showed four deleted node records with `share_link_present = true`:

- `香港落地15m` / `27940` / deleted
- `香港15m中转线路` / `27939` / deleted
- `liveline-reality-27939` / `27939` / deleted
- `liveline-reality-27939` / `27939` / deleted

The current active node must remain untouched:

- `香港直连15m` / `28917` / active / `share_link_present = true`

## Deployment validation checklist

After deploying this stage to the public control VPS:

1. Confirm backend health is OK.
2. Run a SQL pre-check without outputting full links:

```sql
SELECT
  node_name,
  xray_port,
  status,
  share_link IS NOT NULL AS share_link_present,
  deleted_at
FROM nodes
ORDER BY created_at DESC;
```

3. Call the dry-run endpoint and confirm the matched count equals only deleted nodes with a stored link.
4. Call the confirmed scrub endpoint.
5. Re-run the SQL check.
6. Expected result:

```text
active node: share_link_present = true
deleted nodes: share_link_present = false
```

## Safety result

Accepted when the historical deleted node links are scrubbed, the active node link remains present, and no server, Worker, route, port, service, or cutover state changes.
