# Stage 3.3.83 Transit Route Table List Layout

## Purpose

Stage 3.3.83 turns the `中转链路` page into a compact table/list layout similar to the `中转服务器` page. The goal is to keep daily network-building operations simple: view existing routes, open the local-only add-route modal, inspect a route summary, and transiently export a test configuration when needed.

LiveLine Console remains a lightweight self-use network build helper. This stage does not add commercial node-platform behavior, automatic switching, or cutover behavior.

## Layout Changes

The top page area keeps:

- `中转链路` title.
- A concise daily-use description.
- `新增中转链路` button.
- `刷新` button.

The main transit route list now uses table-style rows instead of large route cards. The default columns are:

| Column | Content |
| --- | --- |
| 链路名称 | Route name, such as `hk-socat-live-23843`. |
| 入口 | Transit entry host and listen port. |
| 目标 | Landing target host and port. |
| 转发方式 | Current forwarding method, such as `socat`. |
| 状态 | Status badge plus raw status. |
| 操作 | Row actions, such as summary and transient export. |

Each route row also includes a short detail line:

- service name
- `SHARE_LINK` state
- `CUTOVER` state

The full candidate client link is not displayed in the table.

## Row Actions

Each route row keeps ordinary self-use actions:

- `查看摘要`
- `临时导出测试配置`
- `详情`

`查看摘要` and `临时导出测试配置` expand only the selected route row. They no longer occupy the main page as a large candidate testing block.

Transient export still requires explicit safety confirmations and keeps the HTTP manual-copy fallback. The complete transient candidate link is available only in the export response for manual client import. It is not written to README, docs, audit logs, `nodes.share_link`, or `transit_routes.share_link`.

## Add Route Modal

The `新增中转链路` modal from Stage 3.3.82 remains available.

The modal still only generates a local configuration preview. It does not:

- Call a real create API.
- Create a Worker command.
- Save a transit route to the database.
- Bind or open a port.
- Modify `nodes.share_link`.
- Execute cutover.

Generic multi-route real creation remains intentionally unwired in this stage. If needed later, it should be planned in a separate stage such as `Stage 3.3.84-transit-route-generic-create-plan`.

## Advanced Section

The `高级调试与审批操作` section remains collapsed by default. It continues to contain:

- local planning
- readonly preflight
- Worker allowlist checks
- dry-run create path
- approval and debug controls

These controls are retained for development, approval, and troubleshooting, but they no longer dominate the daily route management page.

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

The transit routes page now behaves like a concise management list: existing routes are visible in compact rows, actions stay on the right side of each row, selected route details expand inline, and the add-route modal remains local-preview-only. No production state changes are performed.
