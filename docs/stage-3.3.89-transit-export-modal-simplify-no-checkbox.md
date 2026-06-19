# Stage 3.3.89 Transit Export Modal Simplify No Checkbox

## Purpose

Stage 3.3.89 simplifies the `临时导出测试配置` modal by removing the transient export checkbox checklist.

This is a frontend-only interaction simplification. It does not change backend APIs, Worker behavior, database schema, production routes, or any network state.

## Observed Issue

After multiple layout hotfixes, public console retesting still showed an awkward checkbox area in the transient export modal:

- the checkbox area could still render incorrectly
- the modal still had unexpected blank space
- the interaction did not match the self-use, simple, low-misoperation product principle

Continuing to patch checkbox layout made the flow more complex than the action required.

## Product Decision

Transient candidate export is a safe, temporary action:

- It does not write the database.
- It does not modify `nodes.share_link`.
- It does not write `transit_routes.share_link`.
- It does not execute cutover.
- It does not create a Worker command.
- It does not execute remote operations.

For a lightweight self-use console, a clear safety notice plus a single generate action is enough. The modal no longer asks the operator to tick multiple confirmations before generating a temporary test configuration.

## Change

The transient export modal now follows a simple flow:

1. Open the modal.
2. Read the route summary.
3. Read the safety notice.
4. Click `生成测试配置`.
5. Review the result in the modal.
6. Copy the candidate link or use the HTTP manual-copy fallback.
7. Close the modal.

The safety notice says:

- only for manual client test import
- no database write
- no `nodes.share_link` mutation
- no cutover
- original direct node remains retained

The frontend still sends the backend-required confirmation fields when calling the transient export API:

- `confirm_transient_export: true`
- `confirm_no_database_write: true`
- `confirm_no_share_link_mutation: true`
- `confirm_no_cutover: true`
- `reason: "client_candidate_test"`

## Unchanged Behavior

The generated result remains transient UI data only:

- candidate name
- server
- port
- protocol summary
- masked link
- copy full candidate link action
- HTTP manual-copy fallback

Complete candidate links must not be written to README, docs, logs, audit text, screenshots, or test fixtures.

The `新增中转链路` modal is not functionally changed in this stage. It remains local-preview-only and still does not create Worker commands or real routes.

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

The transient export modal no longer renders a checkbox checklist. It now presents a concise safety notice and a `生成测试配置` action while preserving the backend confirmation payload and existing manual-copy fallback.
