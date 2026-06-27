# Stage 3.3.194 — stale worker record UI folding

## Goal

Fold old transit Worker records in the UI so the current usable Worker is easier to identify.

This stage is a frontend display-only change. It does not delete any database rows and does not change worker targeting, transit route creation, HAProxy, ports, or client links.

## Scope

Allowed:

- Keep the current transit server management panel behavior.
- Add a small client-side wrapper around the transit server panel.
- Detect stale / offline / deleted Worker rows from the rendered transit server table.
- Hide those rows by default in the browser.
- Render a collapsible history section showing a read-only summary of hidden rows.
- Provide a temporary reveal button so the original historical rows can still be shown during manual inspection.

Not allowed:

- Delete transit resource rows.
- Delete Worker rows.
- Change worker targeting.
- Change `/api/transit-resources` semantics.
- Change `/api/transit-routes` semantics.
- Create Worker commands.
- Execute SSH or remote commands.
- Create, delete, restart, or rebuild HAProxy / socat / Xray services.
- Add or change listening ports.
- Modify `nodes.share_link` or `transit_routes.share_link`.
- Perform cutover.

## Implementation

Files:

- `frontend/components/TransitServersPanelWithWorkerFolding.tsx`
- `frontend/components/AppShell.tsx`

Implementation summary:

1. The original `TransitServersPanel` remains unchanged.
2. `TransitServersPanelWithWorkerFolding` renders the original panel and uses a browser-side `MutationObserver` to watch the rendered transit server table.
3. Rows whose displayed Worker status indicates stale / offline / deleted are hidden from the primary list.
4. Hidden rows are summarized under a collapsed `历史 Worker 记录` section.
5. The reveal button restores the original rows temporarily for manual inspection.

## Safety notes

This approach is intentionally frontend-only for Stage 3.3.194. It avoids changing backend filtering because backend resource lists may be used by route creation, approval, and worker targeting flows.

The folding is presentation-only:

- no database writes;
- no API writes;
- no Worker command creation;
- no remote execution;
- no HAProxy operation;
- no port change;
- no cutover;
- no share-link mutation.

## Manual validation checklist

After deployment:

1. Open `http://my-con.golirong.xyz:3200`.
2. Go to `中转服务器`.
3. Confirm the current online Worker / current transit server remains visible in the primary list.
4. Confirm stale / offline / deleted Worker records are folded under `历史 Worker 记录`.
5. Expand the history section and confirm the hidden rows are visible as read-only summaries.
6. Click `临时显示原始历史行` and confirm original rows can be shown for inspection.
7. Go to `中转链路` and confirm current active route `mk香港落地15m` is still visible and unchanged.
8. Do not create a new route, do not delete resources, do not restart services, and do not export full client links during this validation unless separately needed.

## Expected result

`Stage 3.3.194` is accepted when the UI clearly highlights the current online Worker and folds stale Worker records into a history area without changing any backend data or network behavior.
