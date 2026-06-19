# Stage 3.3.84 Transit Route Compact Table Polish

## Purpose

Stage 3.3.84 further tightens the `中转链路` page after production UI review. Stage 3.3.83 moved the page away from the original candidate-test block, but the displayed route still occupied more vertical space than the `中转服务器` list. This stage keeps the same behavior and makes the list visually closer to the server table layout.

This is a low-risk frontend-only polish stage. It does not change backend APIs, Worker behavior, database schema, or production state.

## Why

LiveLine Console is a lightweight self-use network build helper. Daily transit route management should show the route list quickly, keep actions on the right side, and avoid large card-style blocks unless the operator explicitly expands a row action.

The compact table reduces page height and keeps the first screen focused on:

- route name
- entry host and port
- landing target host and port
- forwarding method
- route status
- row actions

## Table Columns

The route list now uses compact server-like columns:

| Column | Content |
| --- | --- |
| 名称 | Route name, such as `hk-socat-live-23843`. |
| 入口 | Transit entry host and listen port. |
| 目标 | Landing target host and port. |
| 转发方式 | Forwarding method, currently `socat` for the accepted route. |
| 状态 | Status badge, such as `已启用`. |
| 操作 | `查看摘要`, `临时导出`, and `详情`. |

## Detail Line

Each route keeps one compact detail line below the main row:

`服务：...；SHARE_LINK：未写入；CUTOVER：未切换`

The previous large field block is not used for the default route list. Long service names are truncated with a title tooltip.

## Row Actions

The row actions remain:

- `查看摘要`
- `临时导出`
- `详情`

Summary and transient export results are still rendered only after the operator selects a row action. Full candidate links are not shown in the table. The HTTP manual-copy fallback remains available after a transient export response.

## Add Route Modal

The `新增中转链路` modal remains unchanged in behavior:

- It only generates a local configuration preview.
- It does not call a real create API.
- It does not create a Worker command.
- It does not save a transit route to the database.
- It does not add a listening port.
- It does not modify `nodes.share_link`.
- It does not execute cutover.

## Advanced Section

The `高级调试与审批操作` section remains collapsed by default. It keeps development and troubleshooting controls available without placing them in the daily route-management path.

## Safety Boundary

This stage does not:

- Execute cutover.
- Modify `nodes.share_link`.
- Write `transit_routes.share_link`.
- Read or export complete `nodes.share_link`.
- Generate or record complete node links.
- Create Worker commands.
- Create VPS resources, nodes, or transit routes.
- Add listening ports.
- Restart, stop, or delete `socat`.
- Modify Xray.
- Modify firewalls, cloud firewalls, or cloud security groups.
- Execute SSH or remote commands.
- Add database migrations.
- Deploy the public console.
- Run client tests.
- Modify backend APIs.
- Modify Worker binaries.

## Validation

Required validation for this stage:

- `git diff --check`
- `git diff --cached --check`
- `docker compose exec -T frontend npm run build`
- sensitive information scan

Backend tests and Go builds are not required because this stage does not modify backend or Worker code.

## Result

The transit routes page is now a compact server-like table: one route per main row, a short detail line below it, right-side actions, and local-preview-only add-route behavior preserved. No production state changes are performed.
