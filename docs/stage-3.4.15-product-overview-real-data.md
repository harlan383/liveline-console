# Stage 3.4.15 Product Overview Real Data

## Scope

Stage 3.4.15 adds a read-only product overview aggregation API and updates the product dashboard to use it as the primary data source.

This stage keeps the product UI safe:

- No real create flow is connected.
- No Worker command is created.
- No remote execution is performed.
- No database migration is added.
- No share link is read, written, or returned.

## New Read-Only API

New endpoint:

```text
GET /api/product/overview
```

Implemented in:

- `backend/app/api/routes/product_overview.py`
- `backend/app/services/product_overview.py`
- `backend/app/main.py`

Authentication:

- Requires an admin session via `require_admin_session`.
- GET-only and read-only.
- Does not require CSRF because it does not mutate state.

Response groups:

- `generated_at`
- `health`
- `stats`
- `attention_items`
- `recent_created`
- `tips`
- `safety_boundary`

## Frontend Dashboard Changes

Updated:

- `frontend/lib/api.ts`
- `frontend/components/AppShell.tsx`

The dashboard now:

- Calls `GET /api/product/overview`.
- Uses `overview.stats` for the four summary cards.
- Uses `overview.attention_items` for "今日需要关注".
- Uses `overview.recent_created` for "最近创建".
- Uses `overview.tips` for "使用提示".
- Updates the sidebar health card from `overview.health`.
- Shows "总览数据暂时无法读取" when the overview API fails instead of falling back to fake customer alerts.

## Removed Hardcoded Overview Items

The frontend dashboard no longer hardcodes:

- `客户A`
- `客户B`
- `Facebook越南主线`
- `TikTok新加坡线`
- Fixed `09:42`
- Fixed `10:15`

Attention items are generated only from real aggregate data or generic system guidance such as no landing server, no active node, or no transit server.

## Data Sources

The backend overview service reads only local control-plane data:

- `VpsServer`
- `Node`
- `TransitResource`
- `TransitRoute`
- `Task`
- latest landing/transit `Worker` heartbeat summaries
- database/Redis/RQ health checks

It does not read or return complete client links, Worker install commands, tokens, private keys, passwords, or raw task result payloads.

## Safety Boundary

This stage does not:

- Create Worker commands.
- Execute SSH or remote commands.
- Create nodes.
- Create transit routes.
- Delete or mutate nodes, routes, resources, tasks, or workers.
- Read, write, or return full `nodes.share_link`.
- Read, write, or return full `transit_routes.share_link`.
- Perform cutover.
- Add ports.
- Modify firewall, cloud firewall, or cloud security groups.
- Add database migrations.
- Modify Worker binaries.
- Modify Docker Compose.

The response includes a `safety_boundary` array to make the read-only boundary explicit.

## Validation

Required validation:

```bash
git diff --check
git diff --cached --check
PYTHONPYCACHEPREFIX=/tmp/liveline-pycache python3 -m compileall backend/app backend/tests
cd frontend
node node_modules/next/dist/bin/next build
```
