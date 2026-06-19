# Stage 3.3.88 Transit Add-Route Modal Confirmation Layout Fix

## Purpose

Stage 3.3.88 fixes the `新增中转链路` modal confirmation checklist layout. This is a frontend-only JSX and CSS hotfix.

The goal is to keep both transit route modals readable and bounded:

- `新增中转链路`
- `临时导出测试配置`

This stage does not change backend APIs, Worker behavior, database schema, production routes, or any network state.

## Observed Issue

After Stage 3.3.87, the transient export modal confirmation checklist was rewritten, but public console retesting showed the same layout problem in the add-route preview modal:

- Checkbox inputs and confirmation text were far apart.
- Confirmation text was pushed to the right side.
- Text could wrap one character per line.
- The modal could show horizontal overflow and a horizontal scrollbar.

## Root Cause Judgment

The transient export modal had been fixed, but the add-route preview modal still used the older confirmation checklist structure and shared legacy styles.

That left the add-route modal vulnerable to the same layout pattern:

- confirmation wrapper not dedicated to modal checklist rows
- checkbox and text not guarded by a single controlled layout component
- modal children able to keep a minimum width and stretch the modal

## Fix

This stage introduces a single local safety confirmation row structure for transit route modals:

- `SafetyConfirmRow` renders one `label`.
- The checkbox and text live in the same row.
- The row uses `flex-start`, not `space-between`.
- Text has `min-width: 0` and wraps normally.
- The safety confirmation list is one column.

Both modals now use the same confirmation structure:

- transient export confirmations
- add-route preview confirmations

The modal CSS also now:

- hides horizontal overflow at the modal-card level
- keeps modal children within the modal width
- constrains the add-route modal and export modal
- keeps textarea and result panels from stretching the modal

## Unchanged Behavior

The `新增中转链路` modal remains local-preview-only:

- no real create API
- no Worker command
- no listening port
- no database write
- no cutover

The transient export modal remains temporary and test-only. Complete candidate links remain transient UI data only and must not be written to README, docs, logs, audit text, screenshots, or test fixtures.

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

The add-route preview modal and transient export modal now share the same explicit safety confirmation rows. Checkbox inputs stay next to their text, confirmation text wraps normally, and modal content is constrained to avoid horizontal overflow.
