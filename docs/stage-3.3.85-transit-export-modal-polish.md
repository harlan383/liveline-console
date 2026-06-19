# Stage 3.3.85 Transit Export Modal Polish

## Purpose

Stage 3.3.85 moves the `中转链路` page transient candidate export flow into a modal. The goal is to keep the compact route table clean while still allowing the operator to explicitly confirm safety boundaries, generate a temporary test configuration, copy it, or use the HTTP manual-copy fallback.

This is a low-risk frontend-only interaction polish stage. It does not change backend APIs, Worker behavior, database schema, or production state.

## Why

Stage 3.3.84 made the transit route list compact, but transient export confirmations and results could still expand as a large inline block under the table. That made the route management page feel less like the `中转服务器` and `落地服务器` management pages.

Moving export into a modal keeps the default page focused on:

- route list
- route status
- row actions
- local-only add-route preview modal
- collapsed advanced debug section

## Modal Flow

The `临时导出` row action now opens a modal:

1. Open `临时导出测试配置`.
2. Review the selected route context.
3. Confirm all safety items:
   - temporary export only
   - no database write
   - no `nodes.share_link` mutation
   - no cutover
   - original direct node retained
4. Click `生成测试配置`.
5. Review the compact result in the modal:
   - candidate name
   - server
   - port
   - protocol summary
   - masked link
6. Copy the complete candidate link from the modal response only.
7. If Clipboard API is unavailable in HTTP, use the modal's manual-copy textarea.
8. Close the modal to return to the clean route table.

Closing the modal clears the transient export result and confirmation state. The route table does not keep a large export block after close.

## Database and Cutover Boundary

Transient export remains a test-only operator action:

- It does not write `transit_routes.share_link`.
- It does not modify `nodes.share_link`.
- It does not replace the original direct node.
- It does not execute cutover.
- It does not create a Worker command.
- It does not create or modify transit routes.

Complete candidate links must not be written to README, docs, console logs, audit text, screenshots, or test fixtures.

## Other Page Areas

The `查看摘要` action remains inline for now. This stage focuses only on the transient export flow.

The `新增中转链路` modal remains local-preview-only:

- no real create API
- no Worker command
- no listening port
- no database write
- no cutover

The `高级调试与审批操作` section remains collapsed by default.

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

The transient export flow is now modal-based: confirmations, generation, copy, manual-copy fallback, and close all happen inside the modal. The main transit route page remains a compact table after export.
