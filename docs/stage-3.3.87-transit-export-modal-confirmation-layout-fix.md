# Stage 3.3.87 Transit Export Modal Confirmation Layout Fix

## Purpose

Stage 3.3.87 fixes the remaining `临时导出测试配置` modal confirmation checklist layout issue after Stage 3.3.86.

This is a frontend-only JSX and CSS hotfix. It does not change backend APIs, Worker behavior, database schema, production routes, or any network state.

## Observed Issue

Public console retesting still showed an unusable confirmation area:

- The modal could still show a horizontal scrollbar.
- Checkbox inputs and confirmation text were not aligned.
- Confirmation text was pushed to the right side of the modal.
- Text could wrap one character per line.
- The content area could be horizontally stretched.

## Root Cause Judgment

The confirmation checklist was still sharing generic confirmation classes with older candidate-export styles. That left room for legacy selectors and wrapper behavior to keep influencing the modal.

The fix therefore avoids another CSS-only override and gives the transient export modal its own explicit structure:

- a dedicated modal class
- a dedicated route context class
- a dedicated confirmation list class
- one `label` per confirmation item
- checkbox and text inside the same controlled row

## Fix

The modal confirmation checklist now uses a single-column structure:

1. Each confirmation item is one `label` row.
2. The checkbox is the first item in the row.
3. The confirmation text is the second item in the row.
4. The row uses `flex-start`, not `space-between`.
5. The text has `min-width: 0`, normal wrapping, and safe overflow handling.

The modal itself now:

- uses a bounded responsive width
- hides horizontal overflow
- allows vertical scrolling only
- applies border-box sizing to modal children
- constrains route context, result text, and manual-copy textarea width

## Unchanged Behavior

The transient export behavior remains unchanged:

- The operator must confirm all safety items.
- The export remains temporary and test-only.
- Clipboard API copy is attempted only after generation.
- HTTP manual-copy fallback remains available.
- Closing the modal clears the transient result and confirmation state.

The complete candidate link remains transient UI data only and must not be written to README, docs, logs, audit text, screenshots, or test fixtures.

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

The transient export confirmation checklist is now rendered as explicit label rows. Checkbox inputs stay next to their text, confirmation text wraps normally, and the modal is constrained to avoid horizontal overflow.
